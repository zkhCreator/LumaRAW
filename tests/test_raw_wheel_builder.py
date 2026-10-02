"""Isolated RAW build-workflow boundary checks.

Inputs: synthetic caches, wheel archives and disposable work paths. Outputs:
assertions that existing outputs, bad hashes, unsafe paths and failed tools are
rejected. No downloads, compiler execution or application-environment changes.
"""
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import zipfile

import pytest

spec = importlib.util.spec_from_file_location('raw_wheel_builder', Path(__file__).resolve().parents[1] / 'scripts/rawpy-wheel/build_rawpy_wheel.py')
builder = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = builder
spec.loader.exec_module(builder)


def test_work_refuses_existing_outputs_and_dangling_links(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    project.mkdir()
    monkeypatch.setattr(builder, 'PROJECT_ROOT', project)
    existing = tmp_path / 'existing'
    existing.mkdir()
    marker = existing / 'keep'
    marker.write_text('retained')
    link = tmp_path / 'link'
    link.symlink_to(tmp_path / 'absent', target_is_directory=True)
    for path in (existing, link, project / 'new', Path('/')):
        with pytest.raises(builder.BuildFailure):
            builder.require_fresh_work_path(str(path))
    assert marker.read_text() == 'retained' and link.is_symlink()
    assert builder.require_fresh_work_path(str(tmp_path / 'fresh')) == tmp_path / 'fresh'


def test_cached_source_rejects_tampering_before_extracting(tmp_path):
    cache = tmp_path / 'cache'
    cache.mkdir()
    output = tmp_path / 'output'
    output.mkdir()
    source = builder.SourceArchive('source.tar.gz', 'https://example.invalid/source.tar.gz',
                                  hashlib.sha256(b'expected').hexdigest(), 'source')
    (cache / source.filename).write_bytes(b'tampered')
    with pytest.raises(builder.BuildFailure, match='SHA-256 mismatch'):
        builder.materialize_source(source, output, source_cache=cache, offline=True)
    assert list(output.iterdir()) == []
    (cache / source.filename).write_bytes(b'expected')
    result = builder.materialize_source(source, output, source_cache=cache, offline=True)
    assert result.read_bytes() == b'expected'
    with pytest.raises(builder.BuildFailure):
        builder.materialize_source(source, output, source_cache=cache, offline=True)
    assert result.read_bytes() == b'expected'


@pytest.mark.parametrize('name', ['../outside', '/outside'])
def test_wheel_extraction_preflights_all_members(tmp_path, name):
    wheel = tmp_path / 'bad.whl'
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('rawpy/allowed.py', 'allowed')
        archive.writestr(name, 'forbidden')
    destination = tmp_path / 'unpacked'
    destination.mkdir()
    with pytest.raises(builder.BuildFailure, match='unsafe'):
        builder.extract_wheel_safely(wheel, destination)
    assert list(destination.iterdir()) == []


def test_failed_subprocess_retains_redacted_log_and_stops(tmp_path):
    log = builder.BuildLog(tmp_path / 'build.log', {str(tmp_path): '$WORK'})
    with pytest.raises(builder.BuildFailure, match='failed'):
        log.command('Synthetic failure', [sys.executable, '-c',
                    'import sys; print(sys.argv[1]); sys.exit(3)', str(tmp_path)],
                    cwd=tmp_path, env=dict(os.environ))
    text = log.path.read_text()
    assert '$WORK' in text and str(tmp_path) not in text and 'exit status: 3' in text


def test_patch_hashes_and_dependency_inputs_are_synchronized():
    builder.check_dependency_lock_inputs()
    assert all(builder.sha256_file(builder.SCRIPT_DIR / 'patches' / name) == expected
               for name, expected in builder.PATCH_SHA256.items())
