"""Cheap read-only source identity and thumbnail cache lookup for broker/worker.

Inputs: source stat information, a recipe and a catalog cache directory. Outputs:
stable keys or an existing thumbnail path. No NumPy, image decoding, SQL or UI.
Stat identity invalidates on path/size/mtime changes; it is not a content hash.
Only the image worker creates pixels; the broker can reuse completed JPEG files.
"""
import hashlib
import json
import os
from pathlib import Path

PIPELINE_VERSION = 'libraw-prophoto-d65-v3'


def fingerprint(path):
    source = Path(path).resolve(strict=True)
    stat = source.stat()
    return hashlib.sha256(
        f'{source}|{stat.st_size}|{stat.st_mtime_ns}|{PIPELINE_VERSION}'.encode()
    ).hexdigest()[:24]


def cache_key(path, recipe, kind):
    return hashlib.sha256((fingerprint(path) + kind +
                           json.dumps(recipe.dict(), sort_keys=True)).encode()).hexdigest()


def thumbnail_path(path, cache):
    return Path(cache) / (fingerprint(path) + '-thumb.jpg')


def cached_thumbnail(path, cache):
    """Do not return partial legacy writes or follow a cache-entry symlink."""
    try:
        target = thumbnail_path(path, cache)
        if target.is_symlink() or not target.is_file() or not 4 <= target.stat().st_size <= 2*1024**2:
            return None
        with target.open('rb') as stream:
            if stream.read(2) != b'\xff\xd8':
                return None
            stream.seek(-2, os.SEEK_END)
            if stream.read(2) != b'\xff\xd9':
                return None
        os.utime(target, None)
        return str(target)
    except OSError:
        return None
