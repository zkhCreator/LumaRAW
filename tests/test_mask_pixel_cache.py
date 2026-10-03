"""Mask-label cache reuse with real workers, catalog history and stale guards.

Generated read-only rasters exercise Fit/detail, Before/readouts/target maps and
developed thumbnails. Names stay in stored and frozen recipes; only pixel keys
omit them. Worker bypass is measured by admission assertions, not desktop latency.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

from PIL import Image
import pytest

from lumaraw import preview_cache
from lumaraw.model import Recipe
from lumaraw.service import ConflictError, Service
from lumaraw.source_identity import cache_key, pixel_recipe_key_data


@pytest.fixture
def library(tmp_path):
    path = tmp_path / 'photo.png'
    Image.new('RGB', (480, 320), (35, 70, 145)).save(path)
    service = Service(tmp_path / 'catalog', presets_root=tmp_path / 'presets')
    service.dispatch('queue_control', {'action': 'pause'})
    service.dispatch('settings', {'compute_backend': 'cpu'})
    service.dispatch('import_photos', {'paths': [str(path)]})
    service.dispatch('edit_photo', {'photo_id': 1, 'expected_revision': 0, 'patch': {
        'masks': [{'kind': 'radial', 'name': 'Skin 肤色', 'exposure': .6, 'radius': .3}]}})
    yield service, path
    service.close()


@pytest.mark.parametrize('extra', [{}, {'detail': {'width': 180, 'height': 120, 'cx': .6, 'cy': .4}}])
def test_rename_reuses_all_completed_pixels_with_new_revision(library, monkeypatch, extra):
    service, path = library
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    service.dispatch('before_after', {'photo_id': 1, 'expected_revision': 1, 'action': 'after_to_before'})
    old = service.dispatch('get_photo', {'photo_id': 1})
    job = service.dispatch('enqueue_exports', {'photo_ids': [1], 'destination': str(service.root / 'exports'),
        'format': 'tiff16', 'request_key': 'mask-cache-frozen'})
    options = {'photo_id': 1, 'include_color_readouts': True, 'include_curve_tones': True,
               'mixer_target': 'hsl', **extra}
    first = service.dispatch('preview_photo', {**options, 'expected_revision': old['revision']})
    thumbnail = service.dispatch('thumbnail', {'photo_id': 1, 'kind': 'developed'})
    fields = ('preview', 'before', 'color_readouts', 'before_color_readouts', 'curve_tones', 'mixer_target')
    paths = {field: first[field]['path'] if isinstance(first[field], dict) else first[field] for field in fields}
    pixels = {field: hashlib.sha256(Path(target).read_bytes()).hexdigest() for field, target in paths.items()}
    renamed = service.dispatch('mask_action', {'photo_id': 1, 'expected_revision': old['revision'],
        'mask_index': 0, 'action': 'rename', 'name': 'Portrait 🐈'})
    assert renamed['revision'] == old['revision'] + 1
    assert renamed['recipe']['masks'][0]['name'] == 'Portrait 🐈'

    def forbidden(_):
        pytest.fail('A label-only change admitted an image worker')
    monkeypatch.setattr(service, 'run_worker', forbidden)
    hit = service.dispatch('preview_photo', {**options, 'expected_revision': renamed['revision']})
    assert hit['preview_cache_hit'] and not hit['worker_spawned'] and hit['revision'] == renamed['revision']
    assert hit['processing']['backend'] == 'cache' and hit['processing']['worker_seconds'] == 0
    assert hit['processing']['presence_metal_gaussian_passes'] == 0
    for field, target in paths.items():
        assert (hit[field]['path'] if isinstance(hit[field], dict) else hit[field]) == target
        assert hashlib.sha256(Path(target).read_bytes()).hexdigest() == pixels[field]
    assert hit['histogram'] == first['histogram'] and hit['source_fingerprint'] == first['source_fingerprint']
    warm = service.dispatch('thumbnail', {'photo_id': 1, 'kind': 'developed'})
    assert warm['cache_hit'] and not warm['worker_spawned'] and warm['revision'] == renamed['revision']
    assert warm['thumbnail'] == thumbnail['thumbnail']
    with pytest.raises(ConflictError):
        service.dispatch('preview_photo', {**options, 'expected_revision': old['revision']})
    frozen = service.dispatch('get_job', {'job_id': job['job_ids'][0]})
    assert frozen['recipe']['masks'][0]['name'] == 'Skin 肤色'

    # Copying the renamed After into Before changes catalog state and its label,
    # while both sides still have exactly the previously cached pixels.
    captured = service.dispatch('before_after', {'photo_id': 1,
        'expected_revision': renamed['revision'], 'action': 'after_to_before'})
    current = service.dispatch('get_photo', {'photo_id': 1})
    before_hit = service.dispatch('preview_photo', {**options, 'expected_revision': current['revision']})
    assert captured and before_hit['preview_cache_hit'] and before_hit['before'] == first['before']
    assert original == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('action,patch', [
    ('invert', None), ('duplicate', None), ('delete', None),
    (None, {'exposure': 1}), (None, {'enabled': False}),
    (None, {'x': .2}), (None, {'saturation': 30})])
def test_pixel_changes_cannot_reuse_label_only_identity(library, action, patch):
    service, _ = library
    first = service.dispatch('preview_photo', {'photo_id': 1, 'expected_revision': 1})
    if action:
        changed = service.dispatch('mask_action', {'photo_id': 1, 'expected_revision': 1,
            'mask_index': 0, 'action': action})
    else:
        masks = service.dispatch('get_photo', {'photo_id': 1})['recipe']['masks']
        masks[0].update(patch)
        changed = service.dispatch('edit_photo', {'photo_id': 1, 'expected_revision': 1, 'patch': {'masks': masks}})
    result = service.dispatch('preview_photo', {'photo_id': 1, 'expected_revision': changed['revision']})
    assert result['worker_spawned'] and not result['preview_cache_hit']
    assert result['preview'] != first['preview']


def test_name_history_undo_redo_keeps_distinct_names_and_shared_pixels(library, monkeypatch):
    service, _ = library
    first = service.dispatch('preview_photo', {'photo_id': 1, 'expected_revision': 1})
    renamed = service.dispatch('mask_action', {'photo_id': 1, 'expected_revision': 1,
        'mask_index': 0, 'action': 'rename', 'name': ''})
    monkeypatch.setattr(service, 'run_worker', lambda _: pytest.fail('History name change decoded pixels'))
    undo = service.dispatch('undo_photo', {'photo_id': 1, 'expected_revision': renamed['revision']})
    assert undo['recipe']['masks'][0]['name'] == 'Skin 肤色'
    redo = service.dispatch('redo_photo', {'photo_id': 1, 'expected_revision': undo['revision']})
    assert redo['recipe']['masks'][0]['name'] == ''
    hit = service.dispatch('preview_photo', {'photo_id': 1, 'expected_revision': redo['revision']})
    assert hit['preview_cache_hit'] and hit['preview'] == first['preview']


def test_rename_during_cache_validation_rejects_old_revision(library, monkeypatch):
    service, _ = library
    options = {'photo_id': 1, 'expected_revision': 1, 'include_color_readouts': True}
    service.dispatch('preview_photo', options)
    load = preview_cache.load
    def racing(*args, **kwargs):
        result = load(*args, **kwargs)
        assert result is not None
        service.dispatch('mask_action', {'photo_id': 1, 'expected_revision': 1,
            'mask_index': 0, 'action': 'rename', 'name': 'Concurrent label'})
        return result
    monkeypatch.setattr(preview_cache, 'load', racing)
    with pytest.raises(ConflictError):
        service.dispatch('preview_photo', options)
    assert service.dispatch('get_photo', {'photo_id': 1})['recipe']['masks'][0]['name'] == 'Concurrent label'


def test_pixel_key_omits_only_mask_name_and_preserves_captured_input(tmp_path):
    path = tmp_path / 'source.png'; Image.new('RGB', (40, 30)).save(path)
    recipe = Recipe(masks=[{'kind': 'radial', 'name': 'One'}, {'kind': 'linear', 'name': 'Two'}])
    raw = recipe.dict(); raw['future_pixel_field'] = {'name': 'Must stay'}
    captured = deepcopy(raw)
    keyed = pixel_recipe_key_data(raw)
    assert raw == captured and keyed['future_pixel_field'] == raw['future_pixel_field']
    assert all('name' not in mask for mask in keyed['masks'])
    renamed = Recipe(masks=[{'kind': 'radial', 'name': '🐈'}, {'kind': 'linear'}])
    assert cache_key(path, recipe, 'test') == cache_key(path, renamed, 'test')
    reversed_masks = Recipe(masks=list(reversed(renamed.masks)))
    assert cache_key(path, recipe, 'test') != cache_key(path, reversed_masks, 'test')
    changed = {**raw, 'future_pixel_field': {'name': 'Changed'}}
    assert pixel_recipe_key_data(changed) != keyed
