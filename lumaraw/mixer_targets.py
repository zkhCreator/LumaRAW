"""Sparse, exact float32 band weights for photo-targeted HSL and B&W controls.

Inputs: linear pixels immediately before HSL or monochrome mixing, source identity
and viewport geometry. Outputs: immutable file-backed weights, no recipe writes.
The eight existing 50-degree supports overlap at most three ways. Each 16-byte
pixel stores a little-endian uint32 (three byte-sized band IDs, then count) and
three float32 weights. The strongest band moves by the requested control delta;
neighbors move proportionally, with the existing neutral protection retained.
No Adobe parameter equivalence, sample quantization or native pixel computation.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile

import numpy as np

from .color import oklab, mixer_weight, mixer_neutral_weight, MIXER_CENTERS
from .model import Recipe, MIXER_FIELDS, BW_FIELDS, MIXER_BANDS
from .source_identity import fingerprint

MAGIC = b'LRMIX1\0\0'
STAGE = 'mixer-target-v1'
MAX_PIXELS = 2048 * 1536


def packed_weights(pixels):
    lab = oklab(np.asarray(pixels, np.float32))
    hue = np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360
    neutral = mixer_neutral_weight(lab)
    strongest = np.zeros_like(hue)
    for center in MIXER_CENTERS:
        strongest = np.maximum(strongest, mixer_weight(hue, center))
    result = np.zeros((*hue.shape, 4), np.uint32)
    count = np.zeros(hue.shape, np.uint32)
    for index, center in enumerate(MIXER_CENTERS):
        weight = np.divide(mixer_weight(hue, center), strongest,
                           out=np.zeros_like(neutral), where=strongest > 0) * neutral
        rows, columns = np.nonzero(weight > 0)
        slot = count[rows, columns]
        if np.any(slot >= 3):
            raise ValueError('Mixer supports exceed the sparse map contract')
        result[rows, columns, 0] |= np.uint32(index) << (slot * 8)
        result[rows, columns, slot + 1] = weight[rows, columns].view(np.uint32)
        count[rows, columns] += 1
    result[..., 0] |= count << 24
    return result


def target_path(path, recipe, cache, geometry, mode):
    if mode not in ('hsl', 'bw'):
        raise ValueError('Unknown mixer target stage')
    upstream = recipe.dict()
    defaults = Recipe().dict()
    downstream = (*BW_FIELDS, 'monochrome', 'masks', 'lut', 'lut_amount')
    if mode == 'hsl':
        downstream += MIXER_FIELDS
    for key in downstream:
        upstream[key] = defaults[key]
    identity = [STAGE, mode, fingerprint(path), upstream, geometry]
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return Path(cache) / (key + '.mixer')


def header(width, height):
    if not (0 < width <= 2048 and 0 < height <= 2048 and width * height <= MAX_PIXELS):
        raise ValueError('Mixer target map exceeds preview bounds')
    return MAGIC + struct.pack('<II', width, height)


def cached(target, width, height):
    expected = header(width, height)
    try:
        if target.is_symlink() or target.stat().st_size != 16 + width * height * 16:
            return False
        with target.open('rb') as stream:
            if stream.read(16) != expected:
                return False
        os.utime(target, None)
        return True
    except OSError:
        return False


def write(target, values):
    height, width, channels = values.shape
    if values.dtype != np.uint32 or channels != 4:
        raise ValueError('Invalid mixer target buffer')
    prefix = header(width, height)
    fd, name = tempfile.mkstemp(prefix='.mixer-target-', suffix='.part', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(prefix)
            # Direct buffer write avoids another full preview-sized byte copy.
            stream.write(np.ascontiguousarray(values, dtype='<u4'))
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def receipt(target, width, height, hit, mode):
    return {'path': str(target), 'width': width, 'height': height,
            'stage': STAGE, 'mode': mode, 'bands': list(MIXER_BANDS), 'cache_hit': hit}
