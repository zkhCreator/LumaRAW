"""Bounded, disposable input-tone maps for photograph-targeted curve controls.

Inputs: source/backend identity, upstream recipe and rendered viewport geometry.
Outputs: atomically written little-endian float32 maps plus a versioned receipt.
Values are encoded working luminance before parametric/RGB curves, clipped to
the curve's SDR input domain. Display proofing never changes them. Downstream
edits reuse maps; source/basic/geometry/detail edits invalidate them. No catalog
mutations, source writes or photo sampling on the native UI thread.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile

import numpy as np

from .model import Recipe, PARAMETRIC_FIELDS, POINT_CURVE_FIELDS, MIXER_FIELDS, BW_FIELDS, GRADING_FIELDS
from .source_identity import pixel_fingerprint

MAGIC = b'LRTONE1\0'
STAGE = 'pre-parametric-v1'
MAX_PIXELS = 2048 * 1536
DOWNSTREAM = (*PARAMETRIC_FIELDS, 'parametric_splits', *POINT_CURVE_FIELDS,
              *MIXER_FIELDS, *BW_FIELDS, *GRADING_FIELDS, 'monochrome', 'masks', 'lut', 'lut_amount')


def target_path(path, recipe, cache, geometry):
    upstream = recipe.dict()
    defaults = Recipe().dict()
    for key in DOWNSTREAM:
        upstream[key] = defaults[key]
    identity = [STAGE, pixel_fingerprint(path), upstream, geometry]
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return Path(cache) / (key + '.tones')


def header(width, height):
    if not (0 < width <= 2048 and 0 < height <= 2048 and width * height <= MAX_PIXELS):
        raise ValueError('Curve input map exceeds the preview bounds')
    return MAGIC + struct.pack('<II', width, height)


def cached(target, width, height):
    expected = header(width, height)
    try:
        if target.is_symlink() or target.stat().st_size != 16 + width * height * 4:
            return False
        with target.open('rb') as stream:
            if stream.read(16) != expected:
                return False
        os.utime(target, None)
        return True
    except OSError:
        return False


def write(target, values):
    height, width = values.shape
    prefix = header(width, height)
    if not np.isfinite(values).all() or np.any((values < 0) | (values > 1)):
        raise ValueError('Invalid curve input tones')
    fd, name = tempfile.mkstemp(prefix='.curve-tones-', suffix='.part', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(prefix)
            stream.write(values.astype('<f4', copy=False).tobytes())
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def receipt(target, width, height, hit):
    return {'path': str(target), 'width': width, 'height': height, 'stage': STAGE, 'cache_hit': hit}
