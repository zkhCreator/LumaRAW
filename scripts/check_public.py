"""Check a source snapshot before publication, without printing matched values.

Input: a source directory. Output: relative paths/categories and a nonzero exit on
findings. Credential-looking entries are rejected before reading. Git history,
ignored environments and external files are never scanned. This is a conservative
pattern gate, not proof of absence of unknown secrets or a license audit.
"""
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import zlib

ROOT_FILES = {'.gitignore', 'LICENSE', 'README.md', 'ARCHITECTURE.md', 'METAL.md',
              'AGENTS.md', 'DEVELOPMENT.md', 'PARITY.md',
              'TESTING.md', 'VERIFICATION.md', 'THIRD_PARTY_NOTICES.md',
              'PUBLIC_RELEASE.md', 'Package.swift', 'launch.py', 'pyproject.toml', 'uv.lock'}
ROOT_DIRS = {'.github', 'assets', 'licenses', 'lumaraw', 'metal', 'native', 'scripts', 'skills', 'tests', 'examples'}
RAW_BUILD_INPUTS = {'scripts/rawpy-wheel/requirements.in',
                    'scripts/rawpy-wheel/requirements.lock',
                    'scripts/rawpy-wheel/toolchain.cmake',
                    'scripts/rawpy-wheel/patches/rawpy-greybox.patch',
                    'scripts/rawpy-wheel/patches/rawpy-cmake-toolchain.patch',
                    'scripts/rawpy-wheel/patches/libraw-greybox-validity.patch'}
RUNTIME = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache', '.build', 'build', 'dist',
           'work', 'outputs', 'cache', 'catalog', 'exports', 'fixtures', 'evidence', '.swiftpm'}
GENERATED = {'.pyc', '.pyo', '.dylib', '.so', '.dll', '.exe', '.zip', '.dmg', '.log',
             '.sqlite', '.db', '.npy', '.nef', '.nrw', '.dng', '.arw', '.cr2', '.cr3',
             '.raf', '.orf', '.rw2', '.tif', '.tiff', '.jpg', '.jpeg', '.lumarecipe', '.cube'}
PATTERNS = {
    'machine-home-path': re.compile(rb'(?:/(?:Users|home)/[A-Za-z0-9_.-]+|[A-Za-z]:\\(?:Users|Documents and Settings)\\[^\\\s]+)'),
    'local-task-link': re.compile(rb'(?:thread|codex|plugin)://'),
    'private-key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----'),
    'known-token': re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-(?:proj-)?[A-Za-z0-9_-]{30,}|AKIA[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]{20,})'),
    'credential-url': re.compile(rb'https?://[^/\s:@]+:[^/\s@]+@'),
}


def credential_name(path):
    """Use names only; never inspect contents of a suspected credential file."""
    return any(p.lower().startswith(('.env', 'credentials', 'secrets')) or
               p.lower() in {'.ssh', '.aws', '.azure', '.gnupg', 'auth.json', 'tokens.json', 'id_rsa', 'id_ed25519'} or
               Path(p).suffix.lower() in {'.pem', '.key', '.p12', '.pfx', '.jks', '.keystore'} or
               '.keychain' in p.lower() for p in path.parts)


def excluded(path):
    return any(p in RUNTIME or p.startswith('evidence-') or p.endswith(('.app', '.egg-info')) for p in path.parts) or path.suffix.lower() in GENERATED or path.name.startswith('verification') and path.suffix == '.json' or path.name in {'.DS_Store', '._metadata'}


def allowed(path):
    if len(path.parts) == 1:
        return path.name in ROOT_FILES
    if path.parts[0] not in ROOT_DIRS:
        return False
    if path.as_posix() in RAW_BUILD_INPUTS:
        return True
    if path.parts[0] == '.github':
        return path.as_posix() == '.github/workflows/release.yml' or (
            path.parent.as_posix() == '.github/release-notes' and
            re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+\.md', path.name) is not None)
    if path.parts[0] == 'licenses':
        return True  # Upstream attribution texts retain original names and emails.
    return path.suffix.lower() in {'.py', '.swift', '.mm', '.h', '.metal', '.md', '.json', '.svg', '.png', '.icns', '.icc'}


def png_findings(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        return ['invalid-png']
    result = []; offset = 8; ended = False
    while offset + 12 <= len(data):
        size = int.from_bytes(data[offset:offset+4], 'big'); kind = data[offset+4:offset+8]
        end = offset + 12 + size
        if end > len(data):
            return result + ['invalid-png']
        if zlib.crc32(data[offset+4:end-4]) != int.from_bytes(data[end-4:end], 'big'):
            result.append('invalid-png-crc')
        if kind in {b'tEXt', b'zTXt', b'iTXt', b'eXIf'}:
            result.append('image-private-metadata')
        offset = end
        if kind == b'IEND':
            ended = True; break
    if not ended or offset != len(data):
        result.append('invalid-png')
    return result


def content_findings(path, data):
    findings = [name for name, pattern in PATTERNS.items() if pattern.search(data)]
    if path.suffix == '.png':
        findings += png_findings(data)
    if path.suffix == '.icns':
        offset = 8
        if data[:4] != b'icns' or int.from_bytes(data[4:8], 'big') != len(data):
            findings.append('invalid-icns')
        while offset + 8 <= len(data):
            size = int.from_bytes(data[offset+4:offset+8], 'big')
            if size < 8 or offset + size > len(data):
                findings.append('invalid-icns'); break
            chunk = data[offset+8:offset+size]
            if chunk.startswith(b'\x89PNG'):
                findings += png_findings(chunk)
            offset += size
        if offset != len(data):
            findings.append('invalid-icns')
    if path.suffix == '.icc' and (len(data) < 128 or data[36:40] != b'acsp'):
        findings.append('invalid-icc')
    # Non-asset files must be text: do not disguise compiled or opaque data as source.
    if path.suffix not in {'.png', '.icns', '.icc'}:
        try:
            data.decode('utf-8')
            if b'\x00' in data: findings.append('unexpected-binary')
        except UnicodeDecodeError:
            findings.append('unexpected-binary')
    return sorted(set(findings))


def audit(root, strict=False):
    root = Path(root).absolute(); findings = []; selected = []
    def add(path, category):
        # Filenames may themselves be private; redact credential names entirely.
        findings.append({'path': '[credential entry]' if credential_name(path) else path.as_posix(), 'category': category})
    if (root / '.git').exists():
        result = subprocess.run(['git', '-C', str(root), 'ls-files', '--stage', '-z'], capture_output=True)
        if result.returncode:
            add(Path('.git'), 'git-index-unreadable')
        else:
            for row in result.stdout.split(b'\0'):
                if not row: continue
                meta, name = row.split(b'\t', 1); path = Path(os.fsdecode(name))
                if credential_name(path) or excluded(path) or not allowed(path) or meta.startswith(b'120000') or meta.startswith(b'160000'):
                    add(path, 'forbidden-tracked-entry')
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in list(dirs):
            path = Path(folder, name); rel = path.relative_to(root)
            if name == '.git' and len(rel.parts) == 1:
                dirs.remove(name); continue
            category = ('credential-entry' if credential_name(rel) else 'symlink' if path.is_symlink() else
                        'excluded-artifact' if excluded(rel) else 'unknown-directory' if rel.parts[0] not in ROOT_DIRS else None)
            if category:
                dirs.remove(name)
                if strict or category != 'excluded-artifact': add(rel, category)
        for name in sorted(files):
            path = Path(folder, name); rel = path.relative_to(root)
            category = ('credential-entry' if credential_name(rel) else 'symlink' if path.is_symlink() else
                        'excluded-artifact' if excluded(rel) else 'unknown-file' if not allowed(rel) else None)
            if category:
                if strict or category != 'excluded-artifact': add(rel, category)
                continue
            if path.stat().st_size > 8 * 1024 * 1024:
                add(rel, 'oversize-file'); continue
            issues = content_findings(rel, path.read_bytes())
            for issue in issues: add(rel, issue)
            selected.append(rel)
    return sorted(selected), findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--strict', action='store_true', help='Also reject untracked generated artifacts.')
    args = parser.parse_args(); files, findings = audit(args.root, args.strict)
    print(json.dumps({'checked_files': len(files), 'findings': findings, 'scope': 'current source and index; no Git history'}, indent=2))
    return bool(findings)

if __name__ == '__main__':
    raise SystemExit(main())
