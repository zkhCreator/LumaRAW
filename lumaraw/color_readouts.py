"""Bounded SDR Develop RGB and CIELAB D50 readout maps, before display proofing.

Inputs: final graded linear ProPhoto D65 tiles and immutable preview geometry.
Outputs: six little-endian float32 values per displayed pixel, RGB percent using
ProPhoto D50 primaries/sRGB transfer followed by CIELAB D50. Clip to the SDR
ProPhoto cube before either conversion; no display-profile or gamut-overlay
colors are sampled. Maps are disposable, bounded and atomically published.
No catalog mutations, original writes or Adobe processing equivalence claim.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile

import numpy as np

from .color import encode, output_matrix, PROPHOTO_XYZ
from .source_identity import fingerprint

MAGIC = b'LRCOL1\0\0'
STAGE = 'develop-sdr-d50-v1'
MAX_PIXELS = 2048 * 1536


def values(work):
    wide = np.clip(work @ output_matrix('prophoto').T, 0, 1)
    rgb = encode(wide) * 100
    ratio = (wide @ PROPHOTO_XYZ.T) / np.array([.96422, 1, .82521])
    f = np.where(ratio > (6/29)**3, np.cbrt(ratio), ratio/(3*(6/29)**2)+4/29)
    lab = np.stack([116*f[..., 1]-16, 500*(f[..., 0]-f[..., 1]),
                    200*(f[..., 1]-f[..., 2])], axis=-1)
    return np.concatenate([rgb, lab], axis=-1).astype(np.float32)


def target_path(path, recipe, cache, geometry):
    # Include external LUT bytes through the ordinary recipe cache identity.
    from .source_identity import cache_key
    key = hashlib.sha256(json.dumps([STAGE, fingerprint(path),
        cache_key(path, recipe, STAGE), geometry], sort_keys=True).encode()).hexdigest()
    return Path(cache)/(key+'.readouts')


def header(width, height):
    if not (0 < width <= 2048 and 0 < height <= 2048 and width*height <= MAX_PIXELS):
        raise ValueError('Color readout map exceeds the preview bounds')
    return MAGIC + struct.pack('<II', width, height)


def cached(target, width, height):
    expected = header(width, height)
    try:
        if target.is_symlink() or target.stat().st_size != 16+width*height*24:
            return False
        with target.open('rb') as stream:
            if stream.read(16) != expected:
                return False
        os.utime(target, None)
        return True
    except OSError:
        return False


def write(target, data):
    height, width, channels = data.shape
    prefix = header(width, height)
    if channels != 6 or not np.isfinite(data).all():
        raise ValueError('Invalid color readout values')
    fd, name = tempfile.mkstemp(prefix='.color-readouts-', suffix='.part', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(prefix)
            stream.write(np.ascontiguousarray(data, dtype='<f4'))
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def receipt(target, width, height, hit):
    return {'path': str(target), 'width': width, 'height': height, 'stage': STAGE,
            'channels': ['R', 'G', 'B', 'L', 'a', 'b'], 'cache_hit': hit,
            'rgb_space': 'ProPhoto-D50-sRGB-transfer', 'lab_white': 'D50',
            'proofed': False, 'sdr_clipped': True}


def image_dimensions(meta, recipe, orientation):
    """Cropped full-resolution dimensions, independent of fitted proxy rounding."""
    width, height = meta['decoded_width'], meta['decoded_height']
    if recipe.rotation//90 % 2:
        width, height = height, width
    x0, y0, x1, y1 = recipe.crop_box
    width *= x1-x0
    height *= y1-y0
    if recipe.crop != 'original':
        n, d = map(int, recipe.crop.split(':'))
        if width/height > n/d:
            width = height*n/d
        else:
            height = width*d/n
    width, height = max(1, round(width)), max(1, round(height))
    return (height, width) if orientation % 2 else (width, height)
