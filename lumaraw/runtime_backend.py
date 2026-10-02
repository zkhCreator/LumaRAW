"""Installed RAW implementation identity without importing pixel libraries.

Inputs: the active rawpy distribution's version and actual wrapper/native bytes.
Outputs: a path-free descriptor and SHA-256, memoized for the process lifetime.
The broker hashes this bounded package at startup; ordinary cache lookup reuses
the result. RECORD enumerates files but its declared hashes are never trusted.
No rawpy/NumPy import, image decode, catalog access, environment override or
capability inference from package version. Frozen engines use their build manifest.
"""
from functools import lru_cache
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re


def _native(name):
    return name.endswith(('.so', '.dylib', '.dll', '.pyd')) or '.so.' in name


def _artifact_name(name):
    path = PurePosixPath(name)
    if ('\\' in name or name != path.as_posix() or path.is_absolute() or
            '..' in path.parts or not path.parts or
            path.parts[0] not in ('rawpy', 'rawpy.libs')):
        return False
    return _native(path.name) or path.parts[0] == 'rawpy' and path.suffix == '.py'


def _extension(name):
    path = PurePosixPath(name)
    return path.parent == PurePosixPath('rawpy') and path.name.startswith('_rawpy.') and _native(name)


def _hash(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def describe(distribution, package_root):
    """Hash one selected distribution; reject mismatched or escaped packages."""
    root = Path(distribution.locate_file('')).resolve(strict=True)
    package_root = Path(package_root).resolve(strict=True)
    expected = Path(distribution.locate_file('rawpy/__init__.py')).resolve(strict=True)
    if expected.parent != package_root or not package_root.is_relative_to(root):
        raise ValueError('The active rawpy package does not match its installed distribution')
    paths = {}
    for member in distribution.files or ():
        name = str(member).replace('\\', '/')
        if _artifact_name(name):
            paths[name] = Path(distribution.locate_file(member))
    # Include current package code even if an installer omitted or added a file
    # after RECORD creation. Symlinks may resolve only inside this distribution.
    for folder in (package_root, root / 'rawpy.libs'):
        if not folder.exists():
            continue
        for path in folder.rglob('*'):
            name = folder.name + '/' + path.relative_to(folder).as_posix()
            if _artifact_name(name):
                paths[name] = path
    artifacts = []
    for name, path in sorted(paths.items()):
        resolved = path.resolve(strict=True)
        allowed_root = package_root if name.startswith('rawpy/') else root / 'rawpy.libs'
        if not resolved.is_relative_to(allowed_root) or not resolved.is_file():
            raise ValueError('A rawpy artifact is outside its installed package')
        artifacts.append({'path': name, 'sha256': _hash(resolved)})
    if not any(_extension(row['path']) for row in artifacts):
        raise ValueError('The installed rawpy native extension is missing')
    version = str(distribution.version)
    if not re.fullmatch(r'[0-9][A-Za-z0-9.+_-]{0,63}', version):
        raise ValueError('The installed rawpy version is invalid')
    return {'format': 1, 'distribution': 'rawpy', 'version': version, 'artifacts': artifacts}


def descriptor_digest(value):
    """Validate a build descriptor before using it as a pixel-cache namespace."""
    if (not isinstance(value, dict) or
            set(value) != {'format', 'distribution', 'version', 'artifacts'} or
            type(value['format']) is not int or value['format'] != 1 or
            value['distribution'] != 'rawpy' or not isinstance(value['version'], str) or
            not re.fullmatch(r'[0-9][A-Za-z0-9.+_-]{0,63}', value['version']) or
            not isinstance(value['artifacts'], list) or not value['artifacts']):
        raise ValueError('Invalid RAW backend build descriptor')
    names = []
    for row in value['artifacts']:
        if (not isinstance(row, dict) or set(row) != {'path', 'sha256'} or
                not isinstance(row['path'], str) or not _artifact_name(row['path']) or
                not isinstance(row['sha256'], str) or
                not re.fullmatch(r'[0-9a-f]{64}', row['sha256'])):
            raise ValueError('Invalid RAW backend artifact descriptor')
        names.append(row['path'])
    if names != sorted(set(names)) or not any(_extension(name) for name in names):
        raise ValueError('Invalid RAW backend artifact inventory')
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@lru_cache(maxsize=1)
def installed_descriptor():
    distribution = importlib.metadata.distribution('rawpy')
    spec = importlib.util.find_spec('rawpy')
    if spec is None or not spec.origin:
        raise ValueError('The active rawpy package cannot be identified')
    return describe(distribution, Path(spec.origin).parent)
