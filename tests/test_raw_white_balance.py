"""Algebra and fail-closed regressions for the RAW WB sensor adapter.

Purpose: verify the two-axis inversion against synthetic camera/auto multipliers
and reject results that require unsupported G2 or invalid numeric state. Inputs:
synthetic multiplier vectors and immutable RAW channel-layout descriptors. Outputs:
deterministic unit assertions only. No RAW fixtures, decode, package import or build.
"""
import math
from dataclasses import replace

import pytest

from lumaraw.raw_white_balance import (
    RawGeometry,
    RawWhiteBalanceError,
    _box,
    _sensor_center_from_uv,
    solve_auto_white_balance,
)
from lumaraw.orientation import inverse_rect


def geometry(*, green2=3):
    return RawGeometry(
        visible_width=6000,
        visible_height=4000,
        decoded_width=6000,
        decoded_height=4000,
        camera_turns=0,
        pixel_aspect=1.0,
        num_colors=4,
        color_desc="RGBG",
        cfa_pattern=((0, 1), (3, 2)),
        red_channel=0,
        green1_channel=1,
        green2_channel=green2,
        blue_channel=2,
    )


def test_two_axis_relative_solver_recovers_temperature_and_tint():
    temperature, tint = 20.0, -30.0
    # LumaRAW's relative gains are R=2^(T/120), G=2^(-I/180),
    # B=2^(-T/120), with the same tint gain for both green phases.
    delta = [temperature / 120,
             -tint / 180,
             -temperature / 120,
             -tint / 180]
    camera = [2.0, 3.0, 4.0, 5.0]
    auto = [base * 2 ** change for base, change in zip(camera, delta)]

    result = solve_auto_white_balance(camera, auto, geometry(), auto_wb_valid=True)

    assert result["temperature"] == pytest.approx(temperature, abs=1e-12)
    assert result["tint"] == pytest.approx(tint, abs=1e-12)
    assert result["solver"] == "libraw_greybox"


def test_solver_rejects_a_second_green_change_outside_the_recipe_model():
    camera = [1.0, 1.0, 1.0, 1.0]
    auto = [1.2, 1.0, 0.8, 1.04]

    with pytest.raises(RawWhiteBalanceError, match="second-green"):
        solve_auto_white_balance(camera, auto, geometry(), auto_wb_valid=True)


def test_three_color_layout_ignores_unused_fourth_multiplier():
    temperature, tint = 20.0, -30.0
    delta = [temperature / 120, -tint / 180, -temperature / 120, 0.0]
    camera = [2.0, 3.0, 4.0, 0.0]
    auto = [base * 2 ** change for base, change in zip(camera, delta)]
    layout = replace(geometry(green2=None), num_colors=3)

    result = solve_auto_white_balance(camera, auto, layout, auto_wb_valid=True)

    assert result["temperature"] == pytest.approx(temperature, abs=1e-12)
    assert result["tint"] == pytest.approx(tint, abs=1e-12)


@pytest.mark.parametrize(
    "camera,auto,valid",
    [
        ([1.0] * 4, [1.0] * 4, False),
        ([1.0, 0.0, 1.0, 1.0], [1.0] * 4, True),
        ([1.0] * 4, [1.0, math.nan, 1.0, 1.0], True),
    ],
)
def test_solver_rejects_unavailable_or_nonfinite_greybox_multipliers(camera, auto, valid):
    with pytest.raises(RawWhiteBalanceError):
        solve_auto_white_balance(camera, auto, geometry(), auto_wb_valid=valid)


def test_solver_refuses_values_outside_existing_recipe_limits():
    camera = [1.0] * 4
    # T=120, I=0 requires a value outside the existing +/-100 recipe range.
    temperature, tint = 120.0, 0.0
    delta = [temperature / 120,
             -tint / 180,
             -temperature / 120,
             -tint / 180]
    auto = [2 ** change for change in delta]

    with pytest.raises(RawWhiteBalanceError, match="outside the supported WB range"):
        solve_auto_white_balance(camera, auto, geometry(), auto_wb_valid=True)


@pytest.mark.parametrize(
    "sensor_xy,visible_size,camera_turns,decoded_xy,decoded_size,recipe_rotation,source_xy,source_size",
    [
        ((20, 30), (100, 80), 0, (20, 30), (100, 80), 0, (20, 30), (100, 80)),
        # rawpy flip 6: sensor → decoded is 90° clockwise; inverse must recover
        # the visible sensor coordinate, with dimensions swapped.
        ((20, 30), (100, 80), 1, (49, 20), (80, 100), 0, (49, 20), (80, 100)),
        # Develop rotation 90° clockwise is applied after LibRaw's camera flip.
        ((20, 30), (100, 80), 0, (20, 30), (100, 80), 90, (49, 20), (80, 100)),
        # rawpy flip 5: sensor → decoded is 90° counterclockwise.
        ((20, 30), (100, 80), 3, (30, 79), (80, 100), 0, (30, 79), (80, 100)),
    ],
)
def test_pixel_center_inverse_maps_recipe_rotation_and_camera_flip(
    sensor_xy, visible_size, camera_turns, decoded_xy, decoded_size,
    recipe_rotation, source_xy, source_size,
):
    visible_width, visible_height = visible_size
    decoded_width, decoded_height = decoded_size
    source_x, source_y = source_xy
    source_width, source_height = source_size
    geom = RawGeometry(
        visible_width=visible_width,
        visible_height=visible_height,
        decoded_width=decoded_width,
        decoded_height=decoded_height,
        camera_turns=camera_turns,
        pixel_aspect=1.0,
        num_colors=3,
        color_desc="RGBG",
        cfa_pattern=((0, 1), (1, 2)),
        red_channel=0,
        green1_channel=1,
        green2_channel=None,
        blue_channel=2,
    )
    uv = (2 * (source_x + 0.5) / source_width - 1,
          2 * (source_y + 0.5) / source_height - 1)

    result = _sensor_center_from_uv(
        *uv, source_width=source_width, source_height=source_height,
        recipe_rotation=recipe_rotation, geometry=geom,
    )

    assert result == pytest.approx(sensor_xy, abs=1e-12)


def test_catalog_orientation_is_removed_with_existing_bounded_rect_transform():
    # A 100×80 Develop output rotates CW. The final canvas pixel (49,20) is the
    # canonical Develop pixel (20,30); no full coordinate map is needed.
    assert inverse_rect(49, 20, 1, 1, 100, 80, 1) == (20, 30, 1, 1)


@pytest.mark.parametrize("point", [(0, 10), (5936, 10), (10, 3936), (5936, 3936)])
def test_fixed_greybox_is_clamped_inside_visible_sensor(point):
    x, y, width, height = _box(point[0], point[1], 6000, 4000)
    assert width == height == 64
    assert 0 <= x <= 6000 - width
    assert 0 <= y <= 4000 - height
    assert x <= point[0] < x + width
    assert y <= point[1] < y + height
