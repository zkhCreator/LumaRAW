"""Independent sensor-coordinate evidence for the RAW white-balance selector.

Purpose: compare bounded inverse click mapping with actual renderer interpolation
of sensor X/Y images. Inputs: synthetic Bayer descriptors, all camera/catalog
orthogonal transforms, and Develop geometry. Outputs: coordinate and fail-closed
assertions. No camera calibration, original I/O, or camera-support claim.
"""
import math
from types import SimpleNamespace

import numpy as np
import pytest

from lumaraw.model import Recipe
from lumaraw.orientation import apply_array
from lumaraw.render import RenderPlan, OrientedPlan
from lumaraw.raw_white_balance import inspect_raw_geometry, greybox_for_display_point, RawWhiteBalanceError




def raw_descriptor(flip=0, **changes):
    values = dict(sizes=SimpleNamespace(width=256, height=192, iwidth=256,
                  iheight=192, pixel_aspect=1.0, flip=flip), num_colors=3,
                  raw_pattern=np.array([[0, 1], [3, 2]]), color_desc=b'RGBG')
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.parametrize('flip,turns', [(0, 0), (3, 2), (5, 3), (6, 1)])
@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('orientation', range(8))
@pytest.mark.parametrize('transformed', [False, True])
def test_bounded_inverse_matches_rendered_sensor_coordinate_image(flip, turns, rotation, orientation, transformed):
    yy, xx = np.mgrid[:192, :256]
    sensor = np.stack((xx, yy, np.ones_like(xx)), axis=2).astype(np.float32)
    decoded = np.rot90(sensor, -turns)
    recipe = Recipe(rotation=rotation, **(dict(crop_box=[.07,.09,.92,.94],
        crop='3:2', straighten=7.3, perspective_h=-17, perspective_v=13,
        distortion=23, geometry_scale=1.15) if transformed else {}))
    base = RenderPlan(decoded, recipe)
    plan = OrientedPlan(base, orientation)
    point = {'x': .431, 'y': .547}
    x, y = math.floor(point['x'] * plan.width), math.floor(point['y'] * plan.height)
    # The reference follows actual interpolation plus array rotation/mirroring,
    # independently of the adapter's inverse-point/rect implementation.
    rendered = apply_array(base.sample(0, 0, base.width, base.height), orientation)
    sensor_x, sensor_y = map(float, rendered[y, x, :2])
    expected = (min(192, max(0, math.floor(sensor_x - 31.5))),
                min(128, max(0, math.floor(sensor_y - 31.5))), 64, 64)
    calls = []
    def bounded(*args):
        calls.append(args[1:])
        return RenderPlan.source_uv(*args)
    result = greybox_for_display_point(plan, point, raw_descriptor(flip),
                                      camera_make='Nikon', source_uv=bounded)
    assert result == expected
    assert len(calls) == 1 and calls[0][-2:] == (1, 1)


@pytest.mark.parametrize('count,pattern,g2', [(3, [[0,1],[3,2]], 3),
    (3, [[0,1],[1,2]], None), (4, [[0,1],[3,2]], 3)])
def test_unique_colors_and_cfa_slots_are_distinct(count, pattern, g2):
    geom = inspect_raw_geometry(raw_descriptor(num_colors=count, raw_pattern=np.array(pattern)), camera_make='Nikon')
    assert geom.green2_channel == g2


@pytest.mark.parametrize('changes,make', [({}, None), ({}, ''), ({}, 'FUJIFILM'),
    ({'raw_pattern': np.zeros((6,6), dtype=int)}, 'Nikon'),
    ({'raw_pattern': np.array([[0.,1.],[3.,2.]])}, 'Nikon'),
    ({'raw_pattern': np.array([[0,1],[3,4]])}, 'Nikon'),
    ({'color_desc': b'RGBX'}, 'Nikon'),
    ({'color_desc': b'BGRG'}, 'Nikon')])
def test_unverified_metadata_or_layout_fails_closed(changes, make):
    with pytest.raises(RawWhiteBalanceError):
        inspect_raw_geometry(raw_descriptor(**changes), camera_make=make)


@pytest.mark.parametrize('field,value', [('pixel_aspect', 1.01), ('flip', 1),
    ('iwidth', 128), ('crop_width', 128), ('crop_left_margin', 2)])
def test_unverified_sensor_geometry_fails_closed(field, value):
    raw = raw_descriptor()
    setattr(raw.sizes, field, value)
    with pytest.raises(RawWhiteBalanceError):
        inspect_raw_geometry(raw, camera_make='Nikon')


def test_black_geometry_region_is_not_retargeted_to_an_edge_sample():
    raw = raw_descriptor()
    source = np.broadcast_to(np.zeros((1,1,3), np.float32), (192,256,3))
    plan = OrientedPlan(RenderPlan(source, Recipe(straighten=20)), 0)
    with pytest.raises(RawWhiteBalanceError, match='outside'):
        greybox_for_display_point(plan, {'x':0,'y':0}, raw, camera_make='Nikon', source_uv=RenderPlan.source_uv)
