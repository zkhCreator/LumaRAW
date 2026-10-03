"""RAW selector admission, allocation, source binding and real service evidence.

Inputs: synthetic decoder handles and an explicit read-only NEF fixture in an
API 2 environment. Outputs: pre-unpack budget/capability guards, bounded geometry,
read-only sampling, one paired catalog edit and undo assertions. No desktop input,
camera calibration or Lightroom pixel-equivalence claim.
"""
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import rawpy

from lumaraw import white_balance_worker as worker
from lumaraw.service import Service, ConflictError
from lumaraw.source_identity import fingerprint


class FakeRaw:
    def __init__(self, calls, width=256, height=192):
        self.calls = calls
        self.sizes = SimpleNamespace(raw_width=width, raw_height=height, width=width,
            height=height, iwidth=width, iheight=height, flip=0, pixel_aspect=1.0)
        self.num_colors = 3
        self.raw_pattern = np.array([[0,1],[3,2]])
        self.color_desc = b'RGBG'
        self.camera_make = 'Nikon'
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.calls.append('close')
    def open_file(self, path):
        self.calls.append('open')
    def unpack(self):
        self.calls.append('unpack')


@pytest.mark.parametrize('capability', [None, 1, 3])
def test_unverified_decoder_fails_before_any_source_decode(tmp_path, monkeypatch, capability):
    path = tmp_path / 'original.NEF'
    path.write_bytes(b'fixture')
    monkeypatch.setattr(rawpy, 'GREYBOX_WB_API_VERSION', capability, raising=False)
    monkeypatch.setattr(rawpy, 'RawPy', lambda: pytest.fail('Unverified decoder opened RAW'))
    with pytest.raises(ValueError, match='not supported for this RAW'):
        worker.sample(path, {}, 0, {'x':.5,'y':.5}, tmp_path, 4096, fingerprint(path))


def test_raw_memory_preflight_precedes_unpack(tmp_path, monkeypatch):
    path = tmp_path / 'original.NEF'
    path.write_bytes(b'fixture')
    calls = []
    monkeypatch.setattr(rawpy, 'GREYBOX_WB_API_VERSION', 2, raising=False)
    monkeypatch.setattr(rawpy, 'RawPy', lambda: FakeRaw(calls, 12000, 8000))
    with pytest.raises(MemoryError, match='worker budget'):
        worker.sample(path, {}, 0, {'x':.5,'y':.5}, tmp_path, 512, fingerprint(path))
    assert calls == ['open', 'close']


def test_point_geometry_uses_constant_storage_and_no_linear_cache(tmp_path, monkeypatch):
    path = tmp_path / 'original.NEF'
    path.write_bytes(b'fixture')
    calls = []
    monkeypatch.setattr(rawpy, 'GREYBOX_WB_API_VERSION', 2, raising=False)
    monkeypatch.setattr(rawpy, 'RawPy', lambda: FakeRaw(calls))
    monkeypatch.setattr(worker, 'base_image', lambda *a, **k: pytest.fail('RAW created a linear cache'))
    def sample(raw, plan, point, **kwargs):
        source = plan.base.source
        assert source.shape == (192,256,3) and source.strides == (0,0,4)
        assert not source.flags.writeable
        assert kwargs['camera_make'] == 'Nikon'
        return {'temperature':12., 'tint':-7., 'solver':'libraw_greybox', 'greybox':[96,64,64,64]}
    monkeypatch.setattr(worker, 'sample_raw_white_balance', sample)
    result = worker.sample(path, {}, 0, {'x':.5,'y':.5}, tmp_path, 4096, fingerprint(path))
    assert result['cache_keep'] == [] and calls == ['open','unpack','close']
    assert set(tmp_path.iterdir()) == {path}


@pytest.fixture
def raw_library(tmp_path):
    path_text = os.environ.get('LUMARAW_TEST_NEF')
    capable = getattr(rawpy, 'GREYBOX_WB_API_VERSION', None) == 2
    if not path_text or not capable:
        if os.environ.get('LUMARAW_REQUIRE_RAW_WB') == '1':
            pytest.fail('RAW WB acceptance requires API 2 and LUMARAW_TEST_NEF')
        pytest.skip('Set LUMARAW_TEST_NEF and install verified greybox API 2')
    path = Path(path_text).resolve(strict=True)
    service = Service(tmp_path / 'catalog', presets_root=tmp_path / 'presets')
    service.dispatch('queue_control', {'action':'pause'})
    service.dispatch('settings', {'compute_backend':'cpu'})
    service.dispatch('import_photos', {'paths':[str(path)]})
    yield service, path
    service.close()


def params(path, revision=0, generation=1):
    return {'photo_id':1, 'expected_revision':revision,
        'expected_source_fingerprint':fingerprint(path), 'client_id':'raw-wb-test',
        'generation':generation, 'point':{'x':.5,'y':.5}}


def test_real_raw_sample_is_read_only_absolute_to_as_shot_and_one_edit_undo(raw_library):
    service, path = raw_library
    original_hash = hashlib.sha256(path.read_bytes()).digest()
    preview = service.dispatch('preview_photo', {'photo_id':1,'expected_revision':0,'include_before':False})
    before = service.dispatch('get_photo', {'photo_id':1})
    history = service.dispatch('list_history', {'photo_id':1,'expected_revision':0})
    cache_before = set(service.cache.iterdir())
    candidate = service.dispatch('sample_white_balance', params(path))
    assert candidate['solver'] == 'libraw_greybox'
    assert candidate['greybox'][2:] == [64,64]
    assert candidate['source_fingerprint'] == preview['source_fingerprint']
    assert candidate['cache_keep'] == [] and 'sampled_pixels' not in candidate
    assert set(service.cache.iterdir()) == cache_before
    assert service.dispatch('get_photo', {'photo_id':1}) == before
    assert service.dispatch('list_history', {'photo_id':1,'expected_revision':0}) == history
    patch = {key:candidate[key] for key in ('temperature','tint')}
    saved = service.dispatch('edit_photo', {'photo_id':1,'expected_revision':0,
        'expected_source_fingerprint':candidate['source_fingerprint'], 'patch':patch})
    assert saved['revision'] == 1
    after_history = service.dispatch('list_history', {'photo_id':1,'expected_revision':1})
    assert len(after_history['steps']) == len(history['steps']) + 1
    repeated = service.dispatch('sample_white_balance', params(path, revision=1, generation=2))
    assert {key:repeated[key] for key in patch} == patch
    undone = service.dispatch('undo_photo', {'photo_id':1,'expected_revision':1})
    assert undone['recipe'] == before['recipe']
    assert hashlib.sha256(path.read_bytes()).digest() == original_hash


def test_real_raw_completed_sample_rejects_a_newer_recipe(raw_library, monkeypatch):
    service, path = raw_library
    original_hash = hashlib.sha256(path.read_bytes()).digest()
    run = service.run_worker
    def race(request):
        reply = run(request)
        service.dispatch('edit_photo', {'photo_id':1,'expected_revision':0,'patch':{'temperature':25,'tint':-14}})
        return reply
    monkeypatch.setattr(service, 'run_worker', race)
    with pytest.raises(ConflictError):
        service.dispatch('sample_white_balance', params(path))
    photo = service.dispatch('get_photo', {'photo_id':1})
    assert photo['recipe']['temperature'] == 25 and photo['recipe']['tint'] == -14
    assert hashlib.sha256(path.read_bytes()).digest() == original_hash
