"""Bounded source-linear raster white-balance sampling and relative solving.

Purpose: sample one bounded source-linear raster patch at a displayed Develop point
and solve the existing relative Temperature/Tint recipe axes. Inputs: a full-
resolution RenderPlan/OrientedPlan, full decoded source dimensions and normalized
full-output UV. Outputs: a candidate plus compact sample diagnostics. No RAW matrix
guess, catalog write, filesystem access, full-image map, hover work or UI behavior.
Geometry is delegated to RenderPlan.sample and orientation.inverse_rect. A cloned
plan disables only vignette so lens shading cannot masquerade as source clipping.
"""
from dataclasses import replace
import math

import numpy as np

from lumaraw.color import SRGB_XYZ
from lumaraw.imaging import SRGB_TO_PROPHOTO
from lumaraw.orientation import inverse_rect
from lumaraw.render import OrientedPlan, RenderPlan


SAMPLE_EDGE = 5
DARK_LINEAR_LUMA = 0.005
CLIP_LINEAR = 0.99
CLIP_FRACTION = 0.5
MIN_USABLE_FRACTION = 0.5
WB_MIN = -100.0
WB_MAX = 100.0
PROPHOTO_TO_SRGB = np.linalg.inv(SRGB_TO_PROPHOTO).astype(np.float64)
SRGB_LUMA = SRGB_XYZ[1].astype(np.float64)


class WhiteBalanceSampleError(ValueError):
    """The selected point cannot produce a safe candidate in this recipe model."""


def _full_plan(plan, decoded_size):
    oriented = plan if isinstance(plan, OrientedPlan) else None
    base = oriented.base if oriented is not None else plan
    if not isinstance(base, RenderPlan):
        raise WhiteBalanceSampleError('White balance sampling requires a Develop render plan')
    if (not isinstance(decoded_size, (tuple, list)) or len(decoded_size) != 2 or
            any(type(value) is not int or value <= 0 for value in decoded_size)):
        raise WhiteBalanceSampleError('Decoded source dimensions are invalid')

    width, height = decoded_size
    rotation = base.recipe.rotation
    expected_shape = (height, width) if rotation % 180 == 0 else (width, height)
    if base.source.shape[:2] != expected_shape:
        raise WhiteBalanceSampleError('White balance sampling requires a full-resolution source')
    if base.width != max(1, round(base.crop_w)) or base.height != max(1, round(base.crop_h)):
        raise WhiteBalanceSampleError('White balance sampling requires full-resolution output geometry')
    return base, oriented


def _point_uv(point):
    try:
        x, y = point['x'], point['y']
    except (TypeError, KeyError, IndexError):
        try:
            x, y = point
        except (TypeError, ValueError):
            raise WhiteBalanceSampleError('Choose a point inside the photograph') from None
    if (isinstance(x, bool) or isinstance(y, bool) or
            not isinstance(x, (int, float)) or not isinstance(y, (int, float))):
        raise WhiteBalanceSampleError('Choose a point inside the photograph')
    x, y = float(x), float(y)
    if not math.isfinite(x) or not math.isfinite(y) or not 0 <= x <= 1 or not 0 <= y <= 1:
        raise WhiteBalanceSampleError('Choose a point inside the photograph')
    return x, y


def _window(center, length):
    count = min(SAMPLE_EDGE, length)
    start = min(max(0, center - count // 2), length - count)
    return start, count


def source_patch(plan, point, decoded_size):
    """Return at most 5×5 source-linear pixels for normalized full-output UV.

    The command caller must build the source with ``base_image(..., full=True)``
    and a RenderPlan with ``max_edge=0``. Point coordinates are post-recipe-
    geometry, post-catalog-orientation, and pre-detail-ROI normalized coordinates.
    """
    base, oriented = _full_plan(plan, decoded_size)
    full_width = oriented.width if oriented is not None else base.width
    full_height = oriented.height if oriented is not None else base.height
    u, v = _point_uv(point)
    px = min(full_width - 1, int(math.floor(u * full_width)))
    py = min(full_height - 1, int(math.floor(v * full_height)))
    x, width = _window(px, full_width)
    y, height = _window(py, full_height)

    orientation = oriented.orientation if oriented is not None else 0
    source_rect = inverse_rect(x, y, width, height, base.width, base.height, orientation)
    sx, sy, sw, sh = source_rect

    # RenderPlan.source is already recipe-rotated. Keep all sampling transforms,
    # crop and aspect ratio; remove only vignette to avoid false clipping signals.
    sample_recipe = replace(base.recipe, rotation=0, vignette=0)
    sample_plan = RenderPlan(base.source, sample_recipe, max_edge=0)
    if (sample_plan.width, sample_plan.height) != (base.width, base.height):
        raise WhiteBalanceSampleError('White balance source geometry changed')
    patch = sample_plan.sample(sx, sy, sw, sh)
    if patch.shape != (sh, sw, 3) or not np.isfinite(patch).all():
        raise WhiteBalanceSampleError('The selected image sample is invalid')
    return patch


def solve_raster(source_patch, current_temperature, current_tint):
    """Solve relative WB from a linear-ProPhoto raster patch after current WB.

    The caller supplies source-stage pixels from ``RenderPlan.sample`` with
    vignette disabled. No grading, camera profile, LUT, soft proof, SDR clipping,
    or display pixels participate in the solve.
    """
    pixels = np.asarray(source_patch, dtype=np.float64)
    if (pixels.ndim != 3 or pixels.shape[2] != 3 or
            not 1 <= pixels.shape[0] <= SAMPLE_EDGE or
            not 1 <= pixels.shape[1] <= SAMPLE_EDGE or
            not np.isfinite(pixels).all()):
        raise WhiteBalanceSampleError('The selected image sample is invalid')
    for value in (current_temperature, current_tint):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise WhiteBalanceSampleError('Current white balance values are invalid')
        if not WB_MIN <= float(value) <= WB_MAX:
            raise WhiteBalanceSampleError('Current white balance values are outside the supported range')

    # Reverse only the two existing source gains. The source remains pre-tone and
    # pre-profile, so its sRGB reconstruction is also the clipping/darkness test.
    current_gain = np.array([
        2 ** (float(current_temperature) / 120),
        2 ** (-float(current_tint) / 180),
        2 ** (-float(current_temperature) / 120),
    ], dtype=np.float64)
    unbalanced = pixels / current_gain
    if not np.isfinite(unbalanced).all():
        raise WhiteBalanceSampleError('The selected point is too dark or cannot be solved')

    # Geometry can place a few black border pixels or interpolation artifacts in
    # the footprint. Ignore those isolated samples, but fail closed when fewer
    # than half of the bounded window has a solvable positive RGB triplet.
    usable = np.all(unbalanced > 0, axis=2)
    usable_count = int(np.count_nonzero(usable))
    minimum_usable = math.ceil(unbalanced.shape[0] * unbalanced.shape[1] * MIN_USABLE_FRACTION)
    if usable_count < minimum_usable:
        raise WhiteBalanceSampleError('The selected point is too dark or cannot be solved')
    usable_unbalanced = unbalanced[usable]

    source_srgb = usable_unbalanced @ PROPHOTO_TO_SRGB.T
    if not np.isfinite(source_srgb).all():
        raise WhiteBalanceSampleError('The selected image sample is invalid')
    clipped = np.mean(np.any(source_srgb >= CLIP_LINEAR, axis=1))
    if clipped >= CLIP_FRACTION:
        raise WhiteBalanceSampleError('Choose a point without clipped highlights')
    luminance = source_srgb @ SRGB_LUMA
    if not np.isfinite(luminance).all() or float(np.median(luminance)) <= DARK_LINEAR_LUMA:
        raise WhiteBalanceSampleError('Choose a brighter point')

    # Median each channel over the bounded footprint. Do not reject on chroma:
    # the user, rather than pixel color classification, asserts the point is neutral.
    sample = np.median(usable_unbalanced, axis=0)
    if not np.isfinite(sample).all() or np.any(sample <= 0):
        raise WhiteBalanceSampleError('The selected point is too dark or cannot be solved')
    a = math.log2(sample[0] / sample[1])
    b = math.log2(sample[2] / sample[1])
    temperature = 60 * (b - a)
    tint = -90 * (a + b)
    if not math.isfinite(temperature) or not math.isfinite(tint):
        raise WhiteBalanceSampleError('The selected point cannot be solved')
    if not WB_MIN <= temperature <= WB_MAX or not WB_MIN <= tint <= WB_MAX:
        raise WhiteBalanceSampleError('The selected point needs a value outside the supported WB range')
    return {
        'temperature': temperature,
        'tint': tint,
        'sampled_pixels': int(pixels.shape[0] * pixels.shape[1]),
        'solver': 'raster_linear',
    }


def sample_raster(plan, point, decoded_size):
    """Sample and solve a raster using the current plan's captured WB values."""
    base, _ = _full_plan(plan, decoded_size)
    patch = source_patch(plan, point, decoded_size)
    return solve_raster(patch, base.recipe.temperature, base.recipe.tint)
