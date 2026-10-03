"""Portable, bounded neighborhood processing for global Presence controls.

Purpose: adjust medium-scale texture, broader local contrast and optical veil.
Inputs: an owned linear ProPhoto-D65 FP32 strip, validated recipe and output/source
pixel scale. Outputs: linear RGB plus a finite support radius for renderer halos.
No I/O, catalog mutation, inferred scene airlight, local masks or Adobe equations.
Dehaze uses normalized neutral white as airlight and a bounded dark-channel model.
Texture/Clarity share log luminance and preserve channel ratios; zero is an exact
bypass. Radii follow source pixels, including half-size RAW and fitted previews.
All operators run on CPU before the shared CPU/Metal grading/output adapter.
"""
import math

import numpy as np
from scipy.ndimage import gaussian_filter, minimum_filter

from .imaging import LUMA


def _sigma(radius, scale):
    return max(.4, radius * scale)


def support(recipe, pixel_scale):
    """Conservative summed support of sequential operators, in output pixels."""
    radius = 0
    if recipe.dehaze > 0:
        radius += max(1, math.ceil(8 * pixel_scale))
        radius += math.ceil(4 * _sigma(2, pixel_scale))
    contrast_radius = 0
    if recipe.texture:
        contrast_radius = math.ceil(4 * _sigma(4, pixel_scale))
    if recipe.clarity:
        contrast_radius = max(contrast_radius, math.ceil(4 * _sigma(12, pixel_scale)))
    return radius + contrast_radius


def apply(pixels, recipe, pixel_scale=1):
    if not (recipe.texture or recipe.clarity or recipe.dehaze):
        return pixels
    if recipe.dehaze > 0:
        dark = np.clip(pixels.min(axis=2), 0, 1)
        radius = max(1, math.ceil(8 * pixel_scale))
        dark = minimum_filter(dark, size=2 * radius + 1, mode='nearest')
        dark = gaussian_filter(dark, _sigma(2, pixel_scale), mode='nearest', truncate=4)
        transmission = np.maximum(.25, 1 - (.9 * recipe.dehaze / 100) * dark)
        pixels = np.maximum(0, (pixels - 1) / transmission[:, :, None] + 1)
    elif recipe.dehaze < 0:
        transmission = 1 + .55 * recipe.dehaze / 100
        pixels = pixels * transmission + (1 - transmission)
    if recipe.texture or recipe.clarity:
        luminance = np.maximum(pixels @ LUMA, 1e-8)
        log_luminance = np.log2(luminance)
        gain = np.zeros_like(luminance)
        if recipe.texture:
            band = gaussian_filter(log_luminance, _sigma(.8, pixel_scale), mode='nearest', truncate=4)
            band -= gaussian_filter(log_luminance, _sigma(4, pixel_scale), mode='nearest', truncate=4)
            gain += (.8 * recipe.texture / 100) * band
        if recipe.clarity:
            band = gaussian_filter(log_luminance, _sigma(1.5, pixel_scale), mode='nearest', truncate=4)
            band -= gaussian_filter(log_luminance, _sigma(12, pixel_scale), mode='nearest', truncate=4)
            weight = 4 * luminance * .18 / (luminance + .18) ** 2
            gain += (recipe.clarity / 100) * band * weight
        pixels *= np.exp2(np.clip(gain, -1.5, 1.5))[:, :, None]
    return pixels
