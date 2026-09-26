"""Publication gate regressions using synthetic data and disposable repositories.
Tests never read real credentials, publish, or change an existing Git repository.
"""
import importlib.util
from pathlib import Path
import subprocess
import sys
import zipfile
import zlib
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from check_public import audit, png_findings
from package_public import package


def test_clean_source(tmp_path):
    (tmp_path / 'README.md').write_text('Public source\n')
    assert audit(tmp_path, strict=True)[1] == []


def test_credentials_not_opened(tmp_path, monkeypatch):
    target = tmp_path / '.env'
    target.write_text('synthetic fixture')
    original = Path.read_bytes
    def guarded(path):
        assert path != target, 'credential-looking file was opened'
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', guarded)
    files, findings = audit(tmp_path)
    assert files == []
    assert findings == [{'path': '[credential entry]', 'category': 'credential-entry'}]


@pytest.mark.parametrize('sample,category', [
    ('/' + 'Users' + '/private-user/photos', 'machine-home-path'),
    ('ghp_' + 'a' * 36, 'known-token'),
    ('https:' + '//person:password@example.invalid', 'credential-url'),
])
def test_redacted_matches(tmp_path, sample, category):
    (tmp_path / 'README.md').write_text(sample)
    findings = audit(tmp_path)[1]
    assert category in [f['category'] for f in findings]
    assert sample not in str(findings)


def test_symlink_never_followed(tmp_path):
    (tmp_path / 'README.md').symlink_to(tmp_path / 'missing')
    assert audit(tmp_path)[1][0]['category'] == 'symlink'


def test_generated_and_unknown_files(tmp_path):
    (tmp_path / '.venv').mkdir()
    (tmp_path / '.venv' / 'opaque').write_bytes(b'private environment')
    assert audit(tmp_path)[1] == []
    assert audit(tmp_path, strict=True)[1][0]['category'] == 'excluded-artifact'
    (tmp_path / 'unexpected.txt').write_text('data')
    assert audit(tmp_path)[1][0]['category'] == 'unknown-file'


def test_force_tracked_exclusion(tmp_path):
    subprocess.run(['git', 'init', '-q', '-b', 'public-scan-test', str(tmp_path)], check=True)
    (tmp_path / '.gitignore').write_text('*.log\n')
    (tmp_path / 'private.log').write_text('synthetic')
    subprocess.run(['git', '-C', str(tmp_path), 'add', '-f', 'private.log'], check=True)
    assert any(f['category'] == 'forbidden-tracked-entry' for f in audit(tmp_path)[1])


def test_image_metadata():
    def chunk(tag, data):
        return len(data).to_bytes(4, 'big') + tag + data + zlib.crc32(tag + data).to_bytes(4, 'big')
    header = b'\x89PNG\r\n\x1a\n'
    end = chunk(b'IEND', b'')
    assert png_findings(header + chunk(b'eXIf', b'synthetic') + end) == ['image-private-metadata']
    assert png_findings(header + end) == []
    assert 'invalid-png' in png_findings(header + end + b'trailing')


def test_package_is_checked_and_reproducible(tmp_path):
    root = tmp_path / 'source'; root.mkdir()
    (root / 'README.md').write_text('public')
    (root / 'ignored.log').write_text('local')
    first = tmp_path / 'first.zip'; second = tmp_path / 'second.zip'
    assert package(root, first) == 1
    package(root, second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ['LumaRAW-public/README.md']
    with pytest.raises(FileExistsError): package(root, first)
    (root / 'private.txt').write_text('unknown')
    with pytest.raises(ValueError): package(root, tmp_path / 'rejected.zip')
    assert not (tmp_path / 'rejected.zip').exists()


def test_release_version_and_archive_manifest(tmp_path):
    from prepare_release import prepare
    import hashlib
    import json
    root = tmp_path / 'source'; root.mkdir()
    (root / 'README.md').write_text('Public source')
    (root / 'pyproject.toml').write_text('[project]\nversion="1.2.3"\n')
    notes = root / '.github' / 'release-notes'; notes.mkdir(parents=True)
    (notes / 'v1.2.3.md').write_text('English release notes')
    with pytest.raises(ValueError, match='does not match'):
        prepare(root, tmp_path / 'bad-version', 'v1.2.4')
    assert not (tmp_path / 'bad-version').exists()
    with pytest.raises(ValueError, match='stable'):
        prepare(root, tmp_path / 'bad-tag', '../private')
    output = tmp_path / 'release'
    assert prepare(root, output, 'v1.2.3') == 3
    manifest = json.loads((output / 'source-manifest.json').read_text())
    with zipfile.ZipFile(output / 'LumaRAW-1.2.3-source.zip') as archive:
        for name, digest in manifest.items():
            assert hashlib.sha256(archive.read('LumaRAW-public/' + name)).hexdigest() == digest
    for line in (output / 'SHA256SUMS.txt').read_text().splitlines():
        digest, name = line.split('  ')
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError): prepare(root, output, 'v1.2.3')


def test_unapproved_github_file_blocks_release(tmp_path):
    root = tmp_path / 'source'; (root / '.github').mkdir(parents=True)
    (root / '.github' / 'local.json').write_text('unreviewed')
    assert any(f['category'] == 'unknown-file' for f in audit(root)[1])
