"""Portable pointwise four-wheel Color Grading, shared with the Metal adapter.

Inputs: owned linear ProPhoto-D65 FP32 tiles and a validated recipe. Outputs:
toned RGB, immutable bounded wheel coefficients and matching GPU parameters.
Shadows/midtones/highlights overlap in encoded, white-normalized working luminance. Balance
shifts tone classification; Blending widens overlap. Global remains independent.
Luminance moves encoded tone before tinting; tint strength vanishes at black/white.
Hue follows an HSV display wheel mapped to an Oklab chroma direction. These bounded
LumaRAW equations are not Adobe equations or old Split Toning/preset compatibility.
No I/O, SQL, masks, spatial filters, scene inference or output-profile conversion.
Neutral grading bypasses exactly, including hue-only changes at zero saturation.
"""
import colorsys
from functools import lru_cache

import numpy as np

from .color import decode, encode, from_oklab, oklab, WORK_FROM_SRGB
from .imaging import LUMA
from .model import GRADING_FIELDS, GRADING_RANGES


@lru_cache(maxsize=128)
def _coefficients(values):
    result = np.zeros(14, np.float32)
    for index in range(4):
        hue, saturation, luminance = values[index*3:index*3+3]
        if saturation:
            rgb = np.array(colorsys.hsv_to_rgb((hue % 360)/360, 1, 1), np.float32)
            work = decode(rgb) @ WORK_FROM_SRGB.T
            direction = oklab(work.reshape(1, 1, 3))[0, 0, 1:]
            direction /= np.linalg.norm(direction)
            result[index*3:index*3+2] = direction * (.24 * saturation/100)
        result[index*3+2] = .25 * luminance/100
    result[12] = .12 + .38 * values[12]/100
    result[13] = .35 * values[13]/100
    result.setflags(write=False)
    return result


def coefficients(recipe):
    """Four (chroma-a, chroma-b, tone-shift) rows, sigma and balance offset."""
    return _coefficients(tuple(getattr(recipe, key) for key in GRADING_FIELDS))


def flags(recipe):
    """Bit 0 enables grading; bit 1 enables the Oklab tint stage."""
    tint = any(getattr(recipe, f'grading_{region}_saturation') for region in GRADING_RANGES)
    light = any(getattr(recipe, f'grading_{region}_luminance') for region in GRADING_RANGES)
    return (1 if tint or light else 0) | (2 if tint else 0)


def weights(tone, sigma, balance):
    shifted = np.clip(tone + balance, 0, 1)
    distances = (shifted[..., None] - np.array([0, .5, 1], np.float32)) / sigma
    weights = np.exp(-.5 * distances * distances)
    return weights / weights.sum(axis=-1, keepdims=True)


def apply(pixels, recipe):
    enabled = flags(recipe)
    if not enabled:
        return pixels
    packed = coefficients(recipe)
    wheel = packed[:12].reshape(4, 3)
    # Normalize this stage's inherited, rounded matrix weights at neutral white.
    # Other processing stages retain their established luminance coefficients.
    luminance = (pixels @ LUMA) / LUMA.sum()
    tone = np.clip(encode(np.maximum(luminance, 0)), 0, 1)
    # Working dot products/encoding can round a white endpoint down one FP32 ULP.
    # Snap only that endpoint before applying black/white tint protection.
    tone = np.where(luminance >= 1-1e-7, np.float32(1), tone)
    tonal_weights = weights(tone, packed[12], packed[13])
    shifts = (tonal_weights * wheel[:3, 2]).sum(axis=-1) + wheel[3, 2]
    target_tone = np.clip(tone + shifts, 0, 1)
    if np.any(wheel[:, 2]):
        target = decode(target_tone)
        gain = target / np.maximum(luminance, 1e-7)
        adjusted = pixels * gain[..., None]
        adjusted = np.where((luminance <= 1e-7)[..., None], target[..., None], adjusted)
        pixels = np.where((shifts != 0)[..., None], adjusted, pixels)
    if enabled & 2:
        strength = 4 * target_tone * (1 - target_tone)
        chroma = tonal_weights @ wheel[:3, :2] + wheel[3, :2]
        lab = oklab(pixels)
        lab[..., 1:] += strength[..., None] * chroma
        tinted = from_oklab(lab)
        pixels = np.where((strength > 0)[..., None], tinted, pixels)
    return pixels.astype(np.float32, copy=False)
