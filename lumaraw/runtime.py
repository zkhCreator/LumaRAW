"""Portable engine identity and catalog compatibility boundaries.

Inputs: shipped build manifest or current source and installed RAW backend bytes.
Outputs: stable engine and pixel-cache identities, cached for the process lifetime.
No catalog writes or process control.
Generation orders releases; the digest distinguishes edits/builds within one
generation. Same-generation switches need an explicit connection activation.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys

ENGINE_GENERATION = 62
CATALOG_VERSION = 37
BROKER_PROTOCOL = 1


class EngineChangedError(RuntimeError):
    can_activate = True


@lru_cache(maxsize=1)
def raw_backend():
    from .runtime_backend import descriptor_digest, installed_descriptor
    if getattr(sys, 'frozen', False):
        value = json.loads(Path(__file__).with_name('engine_build.json').read_text())['raw_backend']
    else:
        value = installed_descriptor()
    descriptor_digest(value)
    return value


@lru_cache(maxsize=1)
def pixel_cache_namespace():
    from .runtime_backend import descriptor_digest
    return descriptor_digest(raw_backend())


def source_digest(root, *, backend=None):
    root = Path(root)
    digest = hashlib.sha256()
    for name in ('pyproject.toml', 'uv.lock'):
        if (root/name).is_file():
            digest.update(name.encode()+b'\0'+hashlib.sha256((root/name).read_bytes()).digest())
    for folder in ('lumaraw', 'metal'):
        for path in sorted((root/folder).rglob('*')):
            if path.is_file() and path.suffix in ('.py', '.json', '.icc', '.metal', '.mm', '.h'):
                if path.name == 'engine_build.json':
                    continue
                digest.update(path.relative_to(root).as_posix().encode()+b'\0')
                digest.update(hashlib.sha256(path.read_bytes()).digest())
    from .runtime_backend import descriptor_digest
    namespace = descriptor_digest(raw_backend() if backend is None else backend)
    digest.update(b'raw-backend-v1\0' + bytes.fromhex(namespace))
    return digest.hexdigest()


@lru_cache(maxsize=1)
def engine_identity():
    # Validate/warm the namespace before commands reach cache lookups. Frozen
    # manifests describe build inputs; packaging may rewrite signed Mach-O bytes.
    pixel_cache_namespace()
    if getattr(sys, 'frozen', False):
        manifest = json.loads(Path(__file__).with_name('engine_build.json').read_text())
        digest = manifest['digest']
    else:
        digest = source_digest(Path(__file__).resolve().parents[1])
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Invalid engine build identity')
    return {'protocol':BROKER_PROTOCOL, 'generation':ENGINE_GENERATION,
            'digest':digest, 'catalog_version':CATALOG_VERSION}


def valid_identity(value):
    return (isinstance(value, dict) and set(value) == {'protocol','generation','digest','catalog_version'}
            and type(value['protocol']) is int and value['protocol'] == BROKER_PROTOCOL
            and type(value['generation']) is int and 1 <= value['generation'] <= 2**31-1
            and type(value['catalog_version']) is int and 1 <= value['catalog_version'] <= 2**31-1
            and isinstance(value['digest'], str) and len(value['digest']) == 64
            and all(c in '0123456789abcdef' for c in value['digest']))
