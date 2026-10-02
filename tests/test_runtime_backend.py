"""RAW build-input identity, frozen manifests and pixel-cache isolation.

Synthetic installed packages prove byte-based identity independent of RECORD,
local paths and version labels. Generated photographs exercise actual disposable
pixel artifacts across namespace switches. Fresh processes verify that broker
identity startup imports no pixel libraries; no camera or desktop claim is made.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from lumaraw import runtime, runtime_backend, source_identity


class Distribution:
    version = '0.27.1'

    def __init__(self, root):
        self.root = root
        self.files = ['rawpy/__init__.py', 'rawpy/_rawpy.cpython-312.so']

    def locate_file(self, name):
        return self.root / name


def installed(root):
    package = root / 'rawpy'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('VERSION="0.27.1"\n')
    (package / '_rawpy.cpython-312.so').write_bytes(b'compiled implementation')
    (package / 'codecs').mkdir()
    (package / 'codecs' / 'libraw.dylib').write_bytes(b'codec implementation')
    (root / 'rawpy.libs').mkdir()
    (root / 'rawpy.libs' / 'libjpeg.so.1').write_bytes(b'jpeg implementation')
    return Distribution(root), package


def descriptor(root):
    return runtime_backend.describe(*installed(root))


def test_actual_bytes_and_unlisted_codecs_change_identity_without_version_or_path(tmp_path):
    one = descriptor(tmp_path / 'one')
    dist, package = installed(tmp_path / 'two')
    assert runtime_backend.describe(dist, package) == one
    assert len(one['artifacts']) == 4
    # RECORD remains unchanged while the installed binary changes.
    (package / '_rawpy.cpython-312.so').write_bytes(b'patched implementation')
    two = runtime_backend.describe(dist, package)
    assert two['version'] == one['version']
    assert runtime_backend.descriptor_digest(one) != runtime_backend.descriptor_digest(two)
    (dist.root / 'rawpy.libs' / 'libjpeg.so.1').write_bytes(b'patched codec')
    assert runtime_backend.describe(dist, package) != two
    assert str(tmp_path) not in json.dumps(two)
    assert runtime.source_digest(tmp_path, backend=one) != runtime.source_digest(tmp_path, backend=two)


def test_distribution_mismatch_missing_extension_and_escaped_artifacts_fail(tmp_path):
    dist, package = installed(tmp_path / 'one')
    _, other = installed(tmp_path / 'two')
    with pytest.raises(ValueError, match='does not match'):
        runtime_backend.describe(dist, other)
    binary = package / '_rawpy.cpython-312.so'
    binary.unlink()
    with pytest.raises(FileNotFoundError):
        runtime_backend.describe(dist, package)
    dist.files = ['rawpy/__init__.py']
    with pytest.raises(ValueError, match='extension is missing'):
        runtime_backend.describe(dist, package)
    binary.symlink_to(other / '_rawpy.cpython-312.so')
    with pytest.raises(ValueError, match='outside'):
        runtime_backend.describe(dist, package)


@pytest.mark.parametrize('name', [
    '/rawpy/_rawpy.so', 'rawpy/../_rawpy.so', 'rawpy//_rawpy.so',
    'rawpy/./_rawpy.so', 'rawpy\\_rawpy.so', 'elsewhere/_rawpy.so'])
def test_manifest_rejects_noncanonical_artifact_paths(tmp_path, name):
    value = descriptor(tmp_path)
    value['artifacts'][0]['path'] = name
    with pytest.raises(ValueError, match='descriptor'):
        runtime_backend.descriptor_digest(value)


@pytest.mark.parametrize('fault', ['duplicate', 'unordered', 'hash', 'format', 'extension', 'version'])
def test_manifest_rejects_invalid_inventory(tmp_path, fault):
    value = descriptor(tmp_path)
    if fault == 'duplicate': value['artifacts'].append(deepcopy(value['artifacts'][-1]))
    elif fault == 'unordered': value['artifacts'].reverse()
    elif fault == 'hash': value['artifacts'][0]['sha256'] = 'Z' * 64
    elif fault == 'format': value['format'] = True
    elif fault == 'extension': value['artifacts'] = [row for row in value['artifacts'] if '_rawpy.' not in row['path']]
    elif fault == 'version': value['version'] = '../0.27.1'
    with pytest.raises(ValueError):
        runtime_backend.descriptor_digest(value)


@pytest.fixture
def fresh_runtime():
    functions = (runtime.raw_backend, runtime.pixel_cache_namespace, runtime.engine_identity)
    for function in functions: function.cache_clear()
    yield
    for function in functions: function.cache_clear()


def test_frozen_startup_validates_descriptor_without_installed_discovery(tmp_path, monkeypatch, fresh_runtime):
    value = descriptor(tmp_path / 'installed')
    manifest = tmp_path / 'engine_build.json'
    manifest.write_text(json.dumps({'digest': 'a' * 64, 'raw_backend': value}))
    monkeypatch.setattr(runtime, '__file__', str(tmp_path / 'runtime.py'))
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(runtime_backend, 'installed_descriptor', lambda: pytest.fail('Frozen backend rediscovery'))
    identity = runtime.engine_identity()
    assert runtime.valid_identity(identity) and identity['digest'] == 'a' * 64
    assert runtime.pixel_cache_namespace() == runtime_backend.descriptor_digest(value)
    value['artifacts'][0]['sha256'] = 'invalid'
    manifest.write_text(json.dumps({'digest': 'a' * 64, 'raw_backend': value}))
    for function in (runtime.raw_backend, runtime.pixel_cache_namespace, runtime.engine_identity): function.cache_clear()
    with pytest.raises(ValueError): runtime.engine_identity()


def test_identity_initialization_keeps_broker_pixel_free_and_hashes_only_once():
    code = '''import sys
from lumaraw import runtime, runtime_backend
identity = runtime.engine_identity()
assert runtime.valid_identity(identity)
assert not any(name in sys.modules for name in ("rawpy", "numpy", "PIL", "scipy"))
runtime_backend.describe = lambda *args: (_ for _ in ()).throw(AssertionError("rehash"))
assert runtime.engine_identity() == identity
assert len(runtime.pixel_cache_namespace()) == 64
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_backend_probe_does_not_open_catalog(tmp_path):
    catalog = tmp_path / 'unused-catalog'
    result = subprocess.run([sys.executable, '-m', 'lumaraw.bridge', '--catalog', str(catalog),
                             '--backend-info'], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value['engine'] == runtime.engine_identity()
    assert value['pixel_cache_namespace'] == runtime.pixel_cache_namespace()
    assert value['rawpy_version'] == runtime.raw_backend()['version']
    assert not catalog.exists() and str(tmp_path) not in result.stdout


def test_pixel_artifacts_miss_after_backend_change_and_reuse_after_restoration(tmp_path, monkeypatch):
    from PIL import Image
    from lumaraw import render
    from lumaraw.imaging import make_thumbnail
    from lumaraw.model import Recipe

    path = tmp_path / 'photo.png'
    Image.new('RGB', (64, 48), (70, 90, 110)).save(path)
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    cache = tmp_path / 'cache'
    backend = ['a' * 64]
    monkeypatch.setattr(source_identity, 'pixel_cache_namespace', lambda: backend[0])
    recipe = Recipe()

    def pixels():
        source = make_thumbnail(path, cache, 512)
        developed = render.make_thumbnail(path, recipe, cache, 512)
        preview = render.make_preview(path, recipe, cache, 512, include_before=True,
            include_curve_tones=True, mixer_target='hsl', include_color_readouts=True)
        paths = {source['thumbnail'], developed['thumbnail'], preview['preview'], preview['before'],
                 preview['curve_tones']['path'], preview['mixer_target']['path'],
                 preview['color_readouts']['path']}
        # Both full/proxy linear identities must move with the backend too.
        paths.update(source_identity.cache_key(path, recipe, kind)
                     for kind in ('full-linear-v4', 'proxy-linear-v4'))
        return paths, preview

    physical = source_identity.fingerprint(path)
    first, cold = pixels()
    assert not cold['curve_tones']['cache_hit']
    backend[0] = 'b' * 64
    second, changed = pixels()
    assert first.isdisjoint(second)
    assert not changed['curve_tones']['cache_hit'] and not changed['mixer_target']['cache_hit']
    assert not changed['color_readouts']['cache_hit']
    assert source_identity.fingerprint(path) == physical
    backend[0] = 'a' * 64
    restored, warm = pixels()
    assert restored == first and warm['before_cache_hit']
    assert all(warm[field]['cache_hit'] for field in ('curve_tones', 'mixer_target', 'color_readouts'))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original
