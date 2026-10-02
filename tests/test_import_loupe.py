"""Full-resolution loupe previews for staged Add/Copy import reviews.

Inputs: a scanned source, captured import settings and a bounded viewport. Outputs:
read-only preview pixels that match the shared render pipeline and are rejected
when their source, plan or client generation becomes stale. Synthetic PNGs verify
viewport contracts, not RAW decoding or Lightroom pixel equivalence.
"""
from pathlib import Path
import threading

import numpy as np
from PIL import Image
import pytest
from jsonschema import ValidationError

from lumaraw import preview_cache
from lumaraw.service import Service
from test_import_processing import choice as preset_choice, develop as create_develop
from test_import_review import prepare, scan


@pytest.fixture
def library(tmp_path):
    service = Service(tmp_path / 'catalog', presets_root=tmp_path / 'presets')
    service.dispatch('queue_control', {'action': 'pause'})
    service.dispatch('settings', {'compute_backend': 'cpu'})
    yield service, tmp_path
    service.close()


def pattern(path, width=2400, height=1800):
    """Write a coordinate-coded RGB image whose pixels expose ROI alignment."""
    x = np.arange(width, dtype=np.uint32)[None, :]
    y = np.arange(height, dtype=np.uint32)[:, None]
    pixels = np.empty((height, width, 3), dtype=np.uint8)
    pixels[:, :, 0] = (x * 37 + y * 17) % 256
    pixels[:, :, 1] = (x // 7 + y * 29) % 256
    pixels[:, :, 2] = (x * 5 ^ y * 11) % 256
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(pixels, 'RGB').save(path)
    return path


def reviewed(service, source, *, mode='add', destination=None):
    options = {'mode': mode}
    if destination is not None:
        options['destination'] = str(destination)
    plan = scan(service, prepare(service, [source], **options))
    item = service.dispatch('get_import', {'plan_id': plan['id']})['items'][0]
    return plan, item


def preview(service, plan, item, *, generation=1, detail=True, viewport=None):
    request = {
        'plan_id': plan['id'],
        'item_id': item['id'],
        'expected_revision': plan['revision'],
        'client_id': 'import-loupe-test',
        'generation': generation,
        'detail': detail,
    }
    if viewport is not None:
        request['viewport'] = viewport
    return service.dispatch('preview_import_item', request)


def view(cx=0.5, cy=0.5, width=640, height=480):
    return {'cx': cx, 'cy': cy, 'width': width, 'height': height}


def pixels(path):
    with Image.open(path) as image:
        return np.asarray(image.convert('RGB')).copy()


@pytest.mark.parametrize('missing', ['cx', 'cy', 'width', 'height'])
def test_viewport_schema_requires_all_four_fields(library, missing):
    service, _ = library
    viewport = view()
    del viewport[missing]
    with pytest.raises(ValidationError):
        service.dispatch('preview_import_item', {
            'plan_id': 1, 'item_id': 1, 'expected_revision': 0,
            'client_id': 'schema-test', 'generation': 1,
            'detail': True, 'viewport': viewport,
        })


@pytest.mark.parametrize('viewport', [
    {'cx': -0.01, 'cy': 0.5, 'width': 20, 'height': 20},
    {'cx': 0.5, 'cy': 1.01, 'width': 20, 'height': 20},
    {'cx': 0.5, 'cy': 0.5, 'width': 0, 'height': 20},
    {'cx': 0.5, 'cy': 0.5, 'width': 20, 'height': 1537},
])
def test_viewport_schema_rejects_out_of_bounds_values(library, viewport):
    service, _ = library
    with pytest.raises(ValidationError):
        service.dispatch('preview_import_item', {
            'plan_id': 1, 'item_id': 1, 'expected_revision': 0,
            'client_id': 'schema-test', 'generation': 1,
            'detail': True, 'viewport': viewport,
        })


def test_viewport_requires_explicit_detail_mode(library, monkeypatch):
    service, root = library
    source = pattern(root / 'source.png', 96, 64)
    plan, item = reviewed(service, source)
    monkeypatch.setattr(service, 'run_worker', lambda _: pytest.fail('Invalid viewport started image work'))
    with pytest.raises(ValidationError):
        preview(service, plan, item, detail=False, viewport=view(width=32, height=24))
    request = {
        'plan_id': plan['id'], 'item_id': item['id'], 'expected_revision': plan['revision'],
        'client_id': 'import-loupe-test', 'generation': 2,
        'viewport': view(width=32, height=24),
    }
    with pytest.raises(ValidationError):
        service.dispatch('preview_import_item', request)


def test_high_resolution_roi_pixels_match_a_reusable_render_reference(library, monkeypatch):
    service, root = library
    source = pattern(root / 'pattern.png')
    original = source.read_bytes()
    plan, item = reviewed(service, source)
    worker_requests = []
    run_worker = service.run_worker

    def capture(request):
        worker_requests.append(request)
        return run_worker(request)

    monkeypatch.setattr(service, 'run_worker', capture)
    reference = preview(service, plan, item, viewport=view(0.4, 0.4, 2048, 1536))
    roi = preview(service, plan, item, generation=2, viewport=view(0.5, 0.5, 640, 480))

    assert reference['full_width'] == 2400 and reference['full_height'] == 1800
    assert reference['roi'] == [0, 0, 2048, 1536]
    assert reference['geometry']['orientation'] == 0
    assert roi['full_width'] == 2400 and roi['full_height'] == 1800
    assert roi['width'] == 640 and roi['height'] == 480
    assert roi['roi'] == [880, 660, 640, 480]
    assert np.array_equal(pixels(roi['preview']), pixels(reference['preview'])[660:1140, 880:1520])
    assert source.read_bytes() == original
    assert len(worker_requests) == 2
    assert worker_requests[0]['detail'] == view(0.4, 0.4, 2048, 1536)
    assert worker_requests[1]['detail'] == view(0.5, 0.5, 640, 480)
    for request in worker_requests:
        assert 'max_edge' not in request
        assert request['include_before'] is False


def test_roi_clamps_to_bottom_right_and_to_small_image_bounds(library):
    service, root = library
    source = pattern(root / 'small.png', 128, 96)
    plan, item = reviewed(service, source)

    bottom_right = preview(service, plan, item, viewport=view(1.0, 1.0, 50, 40))
    assert bottom_right['full_width'] == 128 and bottom_right['full_height'] == 96
    assert bottom_right['roi'] == [78, 56, 50, 40]

    larger_than_source = preview(service, plan, item, generation=2,
                                 viewport=view(0.2, 0.8, 200, 120))
    assert larger_than_source['roi'] == [0, 0, 128, 96]
    assert larger_than_source['width'] == 128 and larger_than_source['height'] == 96


def test_detail_without_viewport_keeps_1600_fit_and_thumbnail_default(library, monkeypatch):
    service, root = library
    source = pattern(root / 'fit.png')
    plan, item = reviewed(service, source)
    worker_requests = []
    run_worker = service.run_worker

    def capture(request):
        worker_requests.append(request)
        return run_worker(request)

    monkeypatch.setattr(service, 'run_worker', capture)
    fit = preview(service, plan, item, detail=True)
    assert max(fit['width'], fit['height']) == 1600
    assert fit['roi'] is None
    assert worker_requests[0]['max_edge'] == 1600

    thumbnail = preview(service, plan, item, generation=2, detail=False)
    assert 'thumbnail' in thumbnail


def test_cached_thumbnail_hit_rechecks_generation_before_return(library, monkeypatch):
    from lumaraw import source_identity

    service, root = library
    source = pattern(root / 'cached-thumbnail.png', 128, 96)
    plan, item = reviewed(service, source)
    first = preview(service, plan, item, detail=False)
    assert first['thumbnail']
    cached_thumbnail = source_identity.cached_thumbnail
    observed_hit = False

    def hit_then_cancel(*args, **kwargs):
        nonlocal observed_hit
        path = cached_thumbnail(*args, **kwargs)
        assert path is not None
        observed_hit = True
        service.dispatch('cancel_preview', {
            'client_id': 'import-loupe-test', 'generation': 3,
        })
        return path

    monkeypatch.setattr(source_identity, 'cached_thumbnail', hit_then_cancel)
    monkeypatch.setattr(service, 'run_worker', lambda _: pytest.fail('Cached thumbnail started an image worker'))
    with pytest.raises(InterruptedError, match='superseded'):
        preview(service, plan, item, generation=2, detail=False)
    assert observed_hit


@pytest.mark.parametrize('mode', ['add', 'copy'])
def test_add_and_copy_previews_never_write_original_or_copy_destination(library, mode):
    service, root = library
    source = pattern(root / 'original.png', 64, 48)
    destination = root / 'copy-destination'
    destination.mkdir()
    original = source.read_bytes()
    destination_before = sorted(path.name for path in destination.iterdir())
    plan, item = reviewed(service, source, mode=mode,
                          destination=destination if mode == 'copy' else None)

    result = preview(service, plan, item, viewport=view(width=32, height=24))
    thumbnail = preview(service, plan, item, generation=2, detail=False)

    assert result['width'] == 32 and result['height'] == 24
    assert 'thumbnail' in thumbnail
    assert source.read_bytes() == original
    assert sorted(path.name for path in destination.iterdir()) == destination_before


def test_import_develop_crop_defines_the_full_resolution_viewport(library):
    service, root = library
    seed = pattern(root / 'preset-seed.png', 32, 24)
    service.dispatch('import_photos', {'paths': [str(seed)]})
    preset_id = create_develop(service, {'crop_box': [0.25, 0.25, 0.75, 0.75]})
    source = pattern(root / 'cropped-source.png', 240, 180)
    plan, item = reviewed(service, source)
    service.dispatch('set_import_processing', {
        'plan_id': plan['id'], 'expected_revision': plan['revision'],
        'develop_preset': preset_choice(service, 'develop', preset_id),
    })
    plan = service.dispatch('get_import', {'plan_id': plan['id']})['plan']

    result = preview(service, plan, item, viewport=view(width=40, height=30))
    assert result['full_width'] == 120 and result['full_height'] == 90
    assert result['roi'] == [40, 30, 40, 30]
    assert result['geometry']['crop_box'] == [0.25, 0.25, 0.75, 0.75]


@pytest.mark.parametrize('mutation', ['source', 'plan', 'generation'])
def test_worker_result_is_rejected_after_source_plan_or_generation_changes(library, monkeypatch, mutation):
    service, root = library
    source = pattern(root / 'mutable.png', 96, 64)
    plan, item = reviewed(service, source)
    original_worker = service.run_worker

    def finish_then_mutate(request):
        result = original_worker(request)
        if mutation == 'source':
            source.write_bytes(source.read_bytes() + b'changed')
        elif mutation == 'plan':
            service.dispatch('select_import_items', {
                'plan_id': plan['id'], 'expected_revision': plan['revision'],
                'item_ids': [item['id']], 'selected': False,
            })
        else:
            service.dispatch('cancel_preview', {
                'client_id': request['client_id'], 'generation': request['generation'] + 1,
            })
        return result

    monkeypatch.setattr(service, 'run_worker', finish_then_mutate)
    error = InterruptedError if mutation == 'generation' else ValueError
    with pytest.raises(error):
        preview(service, plan, item, viewport=view(width=32, height=24))


def test_cached_roi_hit_skips_worker_even_while_image_lock_is_held(library, monkeypatch):
    service, root = library
    source = pattern(root / 'cached.png', 128, 96)
    plan, item = reviewed(service, source)
    first = preview(service, plan, item, viewport=view(width=50, height=40))
    assert first['preview']
    assert first['preview_cache_hit'] is False and first['worker_spawned'] is True

    monkeypatch.setattr(service, 'run_worker', lambda _: pytest.fail('Cached ROI started an image worker'))
    finished = threading.Event()
    outcome = {}

    def call_from_thread():
        try:
            outcome['result'] = preview(service, plan, item, viewport=view(width=50, height=40))
        except BaseException as error:
            outcome['error'] = error
        finally:
            finished.set()

    with service.image_lock:
        thread = threading.Thread(target=call_from_thread)
        thread.start()
        completed_while_locked = finished.wait(timeout=3)
    thread.join(timeout=3)
    assert not thread.is_alive(), 'Preview did not leave its worker thread after releasing image_lock'
    assert completed_while_locked, 'A completed cache hit waited for image_lock'
    if 'error' in outcome:
        raise outcome['error']
    hit = outcome['result']
    assert hit['preview'] == first['preview']
    assert hit['roi'] == first['roi']
    assert hit['preview_cache_hit'] is True and hit['worker_spawned'] is False


@pytest.mark.parametrize('mutation', ['plan', 'source', 'generation'])
def test_cached_result_rechecks_plan_source_and_generation_after_receipt_load(library, monkeypatch, mutation):
    service, root = library
    source = pattern(root / 'cached-stale.png', 128, 96)
    plan, item = reviewed(service, source)
    first = preview(service, plan, item, viewport=view(width=50, height=40))
    assert first['preview']
    load = preview_cache.load
    changed = False

    def load_then_change(*args, **kwargs):
        nonlocal changed
        result = load(*args, **kwargs)
        if result is not None and not changed:
            changed = True
            if mutation == 'plan':
                service.dispatch('select_import_items', {
                    'plan_id': plan['id'], 'expected_revision': plan['revision'],
                    'item_ids': [item['id']], 'selected': False,
                })
            elif mutation == 'source':
                source.write_bytes(source.read_bytes() + b'changed')
            else:
                service.dispatch('cancel_preview', {
                    'client_id': 'import-loupe-test', 'generation': 2,
                })
        return result

    monkeypatch.setattr(preview_cache, 'load', load_then_change)
    monkeypatch.setattr(service, 'run_worker', lambda _: pytest.fail('Stale cache result started an image worker'))
    error = InterruptedError if mutation == 'generation' else ValueError
    with pytest.raises(error):
        preview(service, plan, item, viewport=view(width=50, height=40))
    assert changed


def test_cached_result_rechecks_backend_after_receipt_load(library, monkeypatch):
    service, root = library
    source = pattern(root / 'cached-backend.png', 128, 96)
    plan, item = reviewed(service, source)
    first = preview(service, plan, item, viewport=view(width=50, height=40))
    assert first['preview']
    load = preview_cache.load
    original_backend = service.compute_backend

    def load_then_change_backend(*args, **kwargs):
        result = load(*args, **kwargs)
        if result is not None:
            service.compute_backend = 'auto'
        return result

    monkeypatch.setattr(preview_cache, 'load', load_then_change_backend)
    try:
        with pytest.raises(ValueError, match='changed'):
            preview(service, plan, item, viewport=view(width=50, height=40))
    finally:
        service.compute_backend = original_backend
