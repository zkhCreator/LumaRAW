"""Synthetic regressions for source-linear raster WB sampling and solving.

Purpose: exercise the determinable source-linear raster solve and geometry reuse
independently of UI, worker contracts and catalogs.
Inputs: synthetic linear sRGB/ProPhoto arrays and production RenderPlan helpers.
Outputs: numeric solver and bounded-patch assertions. RAW is intentionally absent
until its matrix and black-level path are resolved. No camera accuracy or Lightroom pixel equivalence is claimed.
"""
from dataclasses import replace

import numpy as np
import pytest

from lumaraw.imaging import SRGB_TO_PROPHOTO
from lumaraw.model import Recipe
from lumaraw.orientation import apply_array
from lumaraw.render import OrientedPlan, RenderPlan
from lumaraw.white_balance import (
    WhiteBalanceSampleError,
    sample_raster,
    solve_raster,
    source_patch,
)


def _gain(temperature, tint):
    return np.array([
        2 ** (temperature / 120),
        2 ** (-tint / 180),
        2 ** (-temperature / 120),
    ], dtype=np.float64)


def _source_for_candidate(prophoto_neutral, wanted, current):
    # Build directly in the working space so the expected relative solve is
    # exact; the production sRGB matrix rows are close to, but not exactly, 1.
    unbalanced = np.asarray(prophoto_neutral, np.float64) / _gain(*wanted)
    displayed = unbalanced * _gain(*current)
    return np.broadcast_to(displayed, (21, 31, 3)).copy()


def _plan(source, temperature=0, tint=0, vignette=0, rotation=0, orientation=0):
    recipe = Recipe(temperature=temperature, tint=tint, vignette=vignette, rotation=rotation)
    base = RenderPlan(source, recipe, max_edge=0)
    return OrientedPlan(base, orientation), recipe


def test_known_relative_candidate_uses_current_values_without_kelvin_conversion():
    wanted = (18.0, -12.0)
    current = (27.0, 11.0)
    source = _source_for_candidate([0.32, 0.32, 0.32], wanted, current)
    plan, _ = _plan(source, *current)

    result = sample_raster(plan, {'x': 0.5, 'y': 0.5}, (31, 21))

    assert result['solver'] == 'raster_linear'
    assert result['sampled_pixels'] == 25
    assert result['temperature'] == pytest.approx(wanted[0], abs=1e-4)
    assert result['tint'] == pytest.approx(wanted[1], abs=1e-4)


def test_chromatic_unclipped_sample_is_not_rejected_by_colorfulness():
    source = np.asarray([0.24, 0.17, 0.11], np.float64) @ SRGB_TO_PROPHOTO.astype(np.float64).T
    patch = np.broadcast_to(source, (5, 5, 3)).copy()

    result = solve_raster(patch, 0, 0)

    assert result['solver'] == 'raster_linear'
    assert -100 <= result['temperature'] <= 100
    assert -100 <= result['tint'] <= 100


def test_catalog_orientation_and_vignette_do_not_change_source_patch():
    height, width = 20, 28
    yy, xx = np.mgrid[:height, :width]
    source = np.stack([
        0.18 + xx * 0.001,
        0.21 + yy * 0.001,
        np.full((height, width), 0.24),
    ], axis=2).astype(np.float32)
    plan, _ = _plan(source, vignette=100, rotation=90, orientation=1)
    point = {'x': 0.72, 'y': 0.31}

    sampled = source_patch(plan, point, (width, height))

    decoded_rotated = np.rot90(source, -1)
    oriented = apply_array(decoded_rotated, 1)
    out_height, out_width = oriented.shape[:2]
    center_x = min(out_width - 1, int(point['x'] * out_width))
    center_y = min(out_height - 1, int(point['y'] * out_height))
    x0 = min(max(center_x - 2, 0), out_width - 5)
    y0 = min(max(center_y - 2, 0), out_height - 5)
    expected = oriented[y0:y0 + 5, x0:x0 + 5]

    # Orientation changes patch order, not its per-channel median. The strong
    # vignette would multiply edge pixels if the helper sampled the preview path.
    assert sampled.shape == (5, 5, 3)
    assert np.allclose(np.median(sampled, axis=(0, 1)),
                       np.median(expected, axis=(0, 1)), atol=1e-6)


def test_vignette_cannot_turn_an_unclipped_source_into_a_clipped_sample():
    srgb = np.asarray([0.84, 0.71, 0.58], np.float64)
    source = np.broadcast_to(srgb @ SRGB_TO_PROPHOTO.astype(np.float64).T,
                             (20, 28, 3)).copy()
    plan, _ = _plan(source, vignette=100)

    patch = source_patch(plan, {'x': 0.0, 'y': 0.0}, (28, 20))
    result = solve_raster(patch, 0, 0)

    assert result['solver'] == 'raster_linear'


def test_dark_and_clipped_points_are_rejected():
    dark = np.broadcast_to(
        np.asarray([0.001, 0.001, 0.001]) @ SRGB_TO_PROPHOTO.astype(np.float64).T,
        (5, 5, 3),
    ).copy()
    clipped = np.broadcast_to(
        np.asarray([1.0, 0.72, 0.46]) @ SRGB_TO_PROPHOTO.astype(np.float64).T,
        (5, 5, 3),
    ).copy()

    with pytest.raises(WhiteBalanceSampleError, match='brighter'):
        solve_raster(dark, 0, 0)
    with pytest.raises(WhiteBalanceSampleError, match='clipped'):
        solve_raster(clipped, 0, 0)


def test_candidate_outside_relative_model_bounds_is_not_clamped():
    green = np.broadcast_to(np.asarray([0.1, 0.8, 0.1]), (5, 5, 3)).copy()

    with pytest.raises(WhiteBalanceSampleError, match='supported WB range'):
        solve_raster(green, 0, 0)


def test_invalid_point_and_proxy_resolution_are_rejected():
    source = np.full((5, 7, 3), 0.2, np.float32)
    full_plan, _ = _plan(source)

    with pytest.raises(WhiteBalanceSampleError, match='point inside'):
        sample_raster(full_plan, {'x': 1.2, 'y': 0.5}, (7, 5))
    with pytest.raises(WhiteBalanceSampleError, match='full-resolution source'):
        sample_raster(full_plan, {'x': 0.5, 'y': 0.5}, (70, 50))


def test_isolated_black_pixels_do_not_invalidate_a_bounded_sample():
    neutral = np.broadcast_to(np.asarray([0.3, 0.3, 0.3]), (5, 5, 3)).copy()
    neutral[0, 0] = 0
    neutral[4, 4] = 0

    result = solve_raster(neutral, 0, 0)

    assert result['temperature'] == pytest.approx(0, abs=1e-10)
    assert result['tint'] == pytest.approx(0, abs=1e-10)


def test_too_many_black_border_pixels_fail_closed():
    neutral = np.zeros((5, 5, 3), np.float64)
    neutral[:2] = 0.3

    with pytest.raises(WhiteBalanceSampleError, match='too dark|cannot be solved'):
        solve_raster(neutral, 0, 0)


def test_rotated_perspective_crop_edge_windows_stay_bounded():
    height, width = 24, 32
    yy, xx = np.mgrid[:height, :width]
    source = np.stack([
        0.22 + xx * 0.0005,
        0.25 + yy * 0.0004,
        np.full((height, width), 0.29),
    ], axis=2).astype(np.float32)
    recipe = Recipe(rotation=90, crop_box=[0.08, 0.1, 0.92, 0.9],
                    straighten=3, perspective_v=4, perspective_h=-3)
    plan = OrientedPlan(RenderPlan(source, recipe, max_edge=0), 3)

    for point in ({'x': 0.0, 'y': 0.0}, {'x': 1.0, 'y': 1.0}):
        patch = source_patch(plan, point, (width, height))
        assert patch.ndim == 3 and patch.shape[2] == 3
        assert 1 <= patch.shape[0] <= 5
        assert 1 <= patch.shape[1] <= 5
        assert patch.shape[0] * patch.shape[1] <= 25


@pytest.mark.parametrize('orientation', range(8))
@pytest.mark.parametrize('geometry', [False, True])
def test_sample_matches_independently_oriented_full_geometry(orientation, geometry):
    height, width = 61, 83
    yy, xx = np.mgrid[:height, :width]
    source = np.stack([.2 + xx*.002, .23 + yy*.002, .3 + (xx+yy)*.0005], axis=2).astype(np.float32)
    recipe = Recipe(rotation=90, vignette=90)
    if geometry:
        recipe = replace(recipe, crop_box=[.09,.11,.93,.88], crop='5:4',
                         straighten=4, perspective_v=7, perspective_h=-4,
                         distortion=8, geometry_scale=1.1, ca_red=13, ca_blue=-9)
    actual_plan = OrientedPlan(RenderPlan(source, recipe, max_edge=0), orientation)
    reference_plan = RenderPlan(source, replace(recipe, vignette=0), max_edge=0)
    full = apply_array(reference_plan.sample(0, 0, reference_plan.width, reference_plan.height), orientation)
    for u, v in ((.43,.62), (0,0), (1,1)):
        actual = source_patch(actual_plan, {'x':u, 'y':v}, (width,height))
        h, w = full.shape[:2]
        x = min(max(0, min(w-1, int(u*w))-2), w-5)
        y = min(max(0, min(h-1, int(v*h))-2), h-5)
        expected = full[y:y+5, x:x+5]
        # The sampler need not reorder its tiny footprint, because per-channel
        # medians are orientation-invariant. Compare all values, not just shape.
        np.testing.assert_allclose(np.sort(actual.reshape(-1,3),axis=0),
                                   np.sort(expected.reshape(-1,3),axis=0), atol=2e-6)


def test_subpixel_crop_retains_the_renderers_one_pixel_minimum():
    source = np.full((2,2,3), .3, np.float32)
    recipe = Recipe(crop_box=[.4,.4,.6,.6])
    plan = OrientedPlan(RenderPlan(source, recipe, max_edge=0), 0)
    result = sample_raster(plan, {'x':.5,'y':.5}, (2,2))
    assert result['sampled_pixels'] == 1
