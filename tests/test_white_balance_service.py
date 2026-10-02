"""WB frame/source binding, read-only sampling and cancellation through services.

Generated raster originals and real disposable workers exercise the shared API.
Gated replies expose revision/source/generation races; a disposable sleeping child
checks active-process cancellation without depending on decoding speed. No desktop
input, camera-color equivalence or RAW sampling support is implied.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import sys
import threading
import time

import jsonschema
import numpy as np
from PIL import Image
import pytest

from lumaraw.api import TOOLS
from lumaraw.imaging import SRGB_TO_PROPHOTO, srgb_decode
from lumaraw.service import ConflictError, Service
from lumaraw.source_identity import fingerprint


@pytest.fixture
def library(tmp_path):
    path = tmp_path / 'neutral-candidate.png'
    Image.new('RGB', (180, 120), (150, 125, 110)).save(path)
    service = Service(tmp_path / 'catalog', presets_root=tmp_path / 'presets')
    service.dispatch('queue_control', {'action': 'pause'})
    service.dispatch('settings', {'compute_backend': 'cpu'})
    service.dispatch('import_photos', {'paths': [str(path)]})
    yield service, path
    service.close()


def sample_params(path, **changes):
    return {'photo_id': 1, 'expected_revision': 0,
            'expected_source_fingerprint': fingerprint(path),
            'client_id': 'wb-test', 'generation': 1,
            'point': {'x': .5, 'y': .5}, **changes}


def touch_source(path):
    state = path.stat()
    os.utime(path, ns=(state.st_atime_ns, state.st_mtime_ns + 1_000_000))


def test_real_preview_sample_single_edit_and_undo_preserve_original(library):
    service, path = library
    original_hash = hashlib.sha256(path.read_bytes()).digest()
    preview = service.dispatch('preview_photo', {
        'photo_id': 1, 'expected_revision': 0, 'include_before': False,
    })
    assert preview['source_fingerprint'] == fingerprint(path)
    before = service.dispatch('get_photo', {'photo_id': 1})
    history = service.dispatch('list_history', {'photo_id': 1, 'expected_revision': 0})
    receipts = set(service.cache.glob('*.preview.json'))

    sample = service.dispatch('sample_white_balance', sample_params(path))
    assert sample['source_fingerprint'] == preview['source_fingerprint']
    assert sample['photo_id'] == 1 and sample['revision'] == 0
    assert sample['solver'] == 'raster_linear' and sample['sampled_pixels'] == 25
    assert set(service.cache.glob('*.preview.json')) == receipts
    assert 'preview' not in sample
    assert service.dispatch('get_photo', {'photo_id': 1}) == before
    assert service.dispatch('list_history', {'photo_id': 1, 'expected_revision': 0}) == history

    # Independent neutral check against the actual source color and recipe axes.
    source = srgb_decode(np.array([150, 125, 110], np.float32) / 255) @ SRGB_TO_PROPHOTO.T
    gains = np.array([2**(sample['temperature']/120), 2**(-sample['tint']/180),
                      2**(-sample['temperature']/120)])
    neutral = source * gains
    np.testing.assert_allclose(neutral / neutral[1], np.ones(3), atol=2e-6)
    updated = service.dispatch('edit_photo', {
        'photo_id': 1, 'expected_revision': 0,
        'expected_source_fingerprint': preview['source_fingerprint'],
        'patch': {key: sample[key] for key in ('temperature', 'tint')},
    })
    assert updated['revision'] == 1
    after_history = service.dispatch('list_history', {'photo_id': 1, 'expected_revision': 1})
    assert len(after_history['steps']) == len(history['steps']) + 1
    undone = service.dispatch('undo_photo', {'photo_id': 1, 'expected_revision': 1})
    assert undone['recipe'] == before['recipe']
    assert hashlib.sha256(path.read_bytes()).digest() == original_hash


def test_preview_without_revision_and_cache_hit_return_bound_token(library):
    service, path = library
    first = service.dispatch('preview_photo', {'photo_id': 1, 'include_before': False})
    second = service.dispatch('preview_photo', {'photo_id': 1, 'include_before': False})
    assert second['preview_cache_hit'] and not second['worker_spawned']
    assert first['source_fingerprint'] == second['source_fingerprint'] == fingerprint(path)


@pytest.mark.parametrize('with_revision', [False, True])
def test_preview_rejects_source_change_after_worker_without_unbound_token(library, monkeypatch, with_revision):
    service, path = library
    real_worker = service.run_worker

    def changed(request):
        result = real_worker(request)
        touch_source(path)
        return result

    monkeypatch.setattr(service, 'run_worker', changed)
    params = {'photo_id': 1, 'include_before': False}
    if with_revision:
        params['expected_revision'] = 0
    with pytest.raises(ValueError, match='Source changed during preview'):
        service.dispatch('preview_photo', params)


def test_stale_source_rejected_before_worker_and_before_edit(library, monkeypatch):
    service, path = library
    params = sample_params(path)
    touch_source(path)
    monkeypatch.setattr(service, 'run_worker', lambda _: pytest.fail('Stale source started decoding'))
    with pytest.raises(ValueError, match='Source changed before white balance'):
        service.dispatch('sample_white_balance', params)
    with pytest.raises(ValueError, match='Source changed before saving'):
        service.dispatch('edit_photo', {
            'photo_id': 1, 'expected_revision': 0,
            'expected_source_fingerprint': params['expected_source_fingerprint'],
            'patch': {'temperature': 12, 'tint': 9},
        })
    assert service.dispatch('get_photo', {'photo_id': 1})['revision'] == 0


@pytest.mark.parametrize('race', ['source', 'revision', 'cancel'])
def test_completed_sample_rechecks_source_revision_and_generation(library, monkeypatch, race):
    service, path = library
    real_worker = service.run_worker

    def completed(request):
        result = real_worker(request)
        if race == 'source':
            touch_source(path)
        elif race == 'revision':
            service.dispatch('edit_photo', {'photo_id': 1, 'expected_revision': 0,
                                             'patch': {'exposure': 1}})
        else:
            service.dispatch('cancel_preview', {'client_id': 'wb-test', 'generation': 2})
        return result

    monkeypatch.setattr(service, 'run_worker', completed)
    expected = {'source': ValueError, 'revision': ConflictError, 'cancel': InterruptedError}[race]
    with pytest.raises(expected):
        service.dispatch('sample_white_balance', sample_params(path))
    row = service.dispatch('get_photo', {'photo_id': 1})
    assert row['recipe']['temperature'] == row['recipe']['tint'] == 0
    assert row['revision'] == (1 if race == 'revision' else 0)


def test_waiting_sample_does_not_hold_catalog_lock(library, monkeypatch):
    service, path = library
    entered, release = threading.Event(), threading.Event()

    def gated(request):
        entered.set()
        assert release.wait(10)
        return {'temperature': 0, 'tint': 0}

    monkeypatch.setattr(service, 'run_worker', gated)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(service.dispatch, 'sample_white_balance', sample_params(path))
        try:
            assert entered.wait(5)
            edit = pool.submit(service.dispatch, 'edit_photo', {
                'photo_id': 1, 'expected_revision': 0, 'patch': {'exposure': 1},
            })
            assert edit.result(timeout=5)['revision'] == 1
        finally:
            release.set()
        with pytest.raises(ConflictError):
            pending.result(timeout=5)


def test_cancel_during_final_revision_read_discards_candidate(library, monkeypatch):
    service, path = library
    real_check = service.check_revision
    calls = 0

    def cancelling_check(*args):
        nonlocal calls
        row = real_check(*args)
        calls += 1
        if calls == 2:
            service.dispatch('cancel_preview', {'client_id': 'wb-test', 'generation': 2})
        return row

    monkeypatch.setattr(service, 'check_revision', cancelling_check)
    with pytest.raises(InterruptedError, match='superseded'):
        service.dispatch('sample_white_balance', sample_params(path))
    assert calls == 2


def test_cancel_stops_actual_sample_child_but_other_client_cannot(library, monkeypatch):
    service, path = library
    # A real child remains alive deterministically; this isolates supervision
    # from machine-dependent raster decoding speed and never modifies a source.
    monkeypatch.setattr('lumaraw.service.executable_args', lambda: [
        sys.executable, '-c', 'import time; time.sleep(30)',
    ])
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(service.dispatch, 'sample_white_balance', sample_params(path))
        until = time.monotonic() + 5
        while service.active is None and time.monotonic() < until:
            time.sleep(.01)
        assert service.active and service.active['operation'] == 'white_balance_sample'
        process = service.process
        try:
            other = service.dispatch('cancel_preview', {'client_id': 'other-client', 'generation': 2})
            assert not other['cancelled'] and process.poll() is None
            result = service.dispatch('cancel_preview', {'client_id': 'wb-test', 'generation': 2})
            assert result['cancelled']
            with pytest.raises(InterruptedError):
                pending.result(timeout=5)
            assert process.poll() is not None
        finally:
            if process.poll() is None:
                process.kill()
    assert service.dispatch('get_photo', {'photo_id': 1})['revision'] == 0


def test_raw_fails_explicitly_before_raster_decode(tmp_path, monkeypatch):
    from lumaraw import white_balance_worker
    raw = tmp_path / 'source.NEF'
    raw.write_bytes(b'RAW decoder must not be called by the raster adapter')
    monkeypatch.setattr(white_balance_worker, 'base_image', lambda *a, **k: pytest.fail('RAW entered raster solve'))
    with pytest.raises(ValueError, match='not supported for this RAW'):
        white_balance_worker.sample(raw, {}, 0, {'x': .5, 'y': .5}, tmp_path / 'cache',
                                    512, fingerprint(raw))


def test_cached_proxy_cannot_masquerade_as_full_resolution(library, monkeypatch):
    from lumaraw import white_balance_worker
    service, path = library
    monkeypatch.setattr(white_balance_worker, 'base_image', lambda *a, **k: (
        np.full((12,18,3), .3, np.float32),
        {'decoded_width':180,'decoded_height':120}, str(service.cache/'wrong.npy'),
    ))
    with pytest.raises(ValueError, match='full-resolution photograph'):
        white_balance_worker.sample(path, {}, 0, {'x':.5,'y':.5}, service.cache, 512, fingerprint(path))


def test_nonfinite_point_cannot_supersede_an_existing_generation(library):
    service, path = library
    service.preview_versions['wb-test'] = 1
    with pytest.raises(ValueError, match='finite point'):
        service.dispatch('sample_white_balance', sample_params(path, generation=20,
                         point={'x':float('nan'),'y':.5}))
    assert service.preview_versions['wb-test'] == 1


@pytest.mark.parametrize('change', [
    {'point': {'x': True, 'y': .5}}, {'point': {'x': -.1, 'y': .5}},
    {'point': {'x': .5, 'y': 1.1}}, {'expected_source_fingerprint': 'a'*64},
    {'expected_source_fingerprint': 'A'*24}, {'generation': -1},
])
def test_sample_contract_rejects_invalid_input(library, change):
    service, path = library
    with pytest.raises(jsonschema.ValidationError):
        service.dispatch('sample_white_balance', sample_params(path, **change))
    assert TOOLS['sample_white_balance']['annotations']['readOnlyHint']
