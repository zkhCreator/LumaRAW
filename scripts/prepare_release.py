"""Prepare a verified source release from a clean snapshot and matching version tag.

Inputs: project source, a stable vMAJOR.MINOR.PATCH tag, and a new output directory.
Outputs: deterministic source ZIP, SHA-256 manifest/checksums, and release notes.
No credentials, network, app binaries, Git mutation, or publication occurs here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tomllib
import zipfile
sys.dont_write_bytecode = True
from check_public import audit
from package_public import package


def prepare(root, destination, tag):
    root = Path(root).resolve(); destination = Path(destination).resolve()
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag):
        raise ValueError('Expected a stable vMAJOR.MINOR.PATCH tag.')
    if destination == root or root in destination.parents:
        raise ValueError('Release output must be outside the source directory.')
    files, findings = audit(root, strict=True)
    if findings:
        raise ValueError('Public source check failed; run check_public.py --strict.')
    version = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
    if tag != 'v' + version:
        raise ValueError('Tag does not match the project version.')
    notes_path = root / '.github' / 'release-notes' / (tag + '.md')
    notes = notes_path.read_text()
    if not notes.strip():
        raise ValueError('Release notes must not be empty.')
    destination.mkdir(parents=True, exist_ok=False)
    archive = destination / f'LumaRAW-{version}-source.zip'
    package(root, archive)
    manifest = {}
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip() is not None:
            raise ValueError('Archive integrity check failed.')
        expected = {'LumaRAW-public/' + path.as_posix() for path in files}
        if set(zipped.namelist()) != expected:
            raise ValueError('Archive inventory differs from the checked source.')
        for path in files:
            data = zipped.read('LumaRAW-public/' + path.as_posix())
            if data != (root / path).read_bytes():
                raise ValueError('Source changed during packaging.')
            manifest[path.as_posix()] = hashlib.sha256(data).hexdigest()
    manifest_path = destination / 'source-manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    (destination / 'SHA256SUMS.txt').write_text(''.join(
        hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n'
        for path in (archive, manifest_path)))
    (destination / 'release-notes.md').write_text(notes)
    return len(manifest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print('Verified source release files:', prepare(Path(__file__).resolve().parents[1], args.output, args.tag))
