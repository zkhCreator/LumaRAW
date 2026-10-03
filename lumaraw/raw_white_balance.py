"""RAW white-balance sampling in the visible Bayer sensor plane.

Purpose: map one displayed Develop point into LibRaw's visible sensor plane and
solve LibRaw's greybox auto-WB against the camera's as-shot multipliers. Inputs:
a full-resolution RenderPlan/OrientedPlan, an unpacked RawPy handle, and the
normalized full-output point. Outputs: a bounded visible-plane greybox plus a
Temperature/Tint proposal. No full-frame coordinate map, matrix guess, catalog
mutation, RAW support claim, or implicit retry. Requires greybox API 2 from the verified isolated rawpy build. Geometry shares
RenderPlan.source_uv; camera accuracy and Lightroom pixel equivalence are unverified.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Any

import numpy as np

from lumaraw.orientation import inverse_point, inverse_rect, validate as validate_orientation
from lumaraw.render import OrientedPlan, RenderPlan


GREYBOX_API_VERSION = 2
GREYBOX_EDGE = 64  # Eight-by-eight LibRaw sampling blocks, subject to RAW probes.
G2_MAX_LOG2_RESIDUAL = 0.01  # Stops; approximately 0.7% in multiplier-ratio space.
WB_MIN = -100.0
WB_MAX = 100.0


class RawWhiteBalanceError(ValueError):
    """The RAW layout, coordinate transform, or greybox result is unsupported."""


@dataclass(frozen=True)
class RawGeometry:
    visible_width: int
    visible_height: int
    decoded_width: int
    decoded_height: int
    camera_turns: int
    pixel_aspect: float
    num_colors: int
    color_desc: str
    cfa_pattern: tuple[tuple[int, int], tuple[int, int]]
    red_channel: int
    green1_channel: int
    green2_channel: int | None
    blue_channel: int


def _exact_int(value: Any) -> bool:
    return type(value) is int


def _camera_turns(flip: Any) -> int:
    # rawpy documents 3=180, 5=90 CCW, 6=90 CW. Internal orientation turns
    # are clockwise, so 5 and 6 map to 3 and 1 respectively.
    mapping = {0: 0, 3: 2, 5: 3, 6: 1}
    if type(flip) is not int or flip not in mapping:
        raise RawWhiteBalanceError("This RAW camera orientation has not been verified")
    return mapping[flip]


def _channel_layout(
    raw: Any,
    camera_make: str | None,
) -> tuple[int, str, tuple[tuple[int, int], tuple[int, int]], int, int, int | None, int]:
    if not isinstance(camera_make, str) or not camera_make.strip():
        raise RawWhiteBalanceError("RAW camera manufacturer metadata is unavailable")
    if camera_make and "FUJI" in camera_make.upper():
        raise RawWhiteBalanceError("Fujifilm RAW white-balance sampling is not supported")
    try:
        count = raw.num_colors
        pattern = np.asarray(raw.raw_pattern)
        raw_desc = raw.color_desc
    except (AttributeError, TypeError, ValueError) as exc:
        raise RawWhiteBalanceError("This RAW file does not expose a supported Bayer pattern") from exc
    if (type(count) is not int or count not in (3, 4) or pattern.shape != (2, 2) or
            not np.issubdtype(pattern.dtype, np.integer)):
        raise RawWhiteBalanceError("Only verified 2×2 Bayer RAW layouts are supported")
    try:
        desc = raw_desc.decode("ascii") if isinstance(raw_desc, bytes) else str(raw_desc)
    except UnicodeDecodeError as exc:
        raise RawWhiteBalanceError("RAW color-channel description is invalid") from exc
    desc = desc.rstrip("\x00").upper()
    channels = [int(value) for value in pattern.reshape(-1)]
    if any(value < 0 or value >= 4 or value >= len(desc) for value in channels):
        raise RawWhiteBalanceError("RAW Bayer channel indices are invalid")
    # `num_colors` is LibRaw's unique output-color count, not necessarily the
    # number of CFA slots it independently scales. A three-color RGBG Bayer
    # file may still use slots 0,1,2,3, with slot 3 as G2.
    split_green = count == 3 and 3 in channels
    slot_count = 4 if split_green else count
    if set(channels) != set(range(slot_count)):
        raise RawWhiteBalanceError("RAW Bayer pattern does not contain every active CFA slot")
    labels = [desc[index] for index in range(slot_count)]
    # The renderer's relative WB axes address R/G/B/G by numeric slot. Other
    # label orders cannot be fitted and applied correctly by that contract.
    if labels != list("RGBG"[:slot_count]):
        raise RawWhiteBalanceError("RAW channel ordering does not match the relative WB recipe")
    red = [index for index, label in enumerate(labels) if label == "R"]
    greens = [index for index, label in enumerate(labels) if label == "G"]
    blue = [index for index, label in enumerate(labels) if label == "B"]
    expected_greens = 2 if slot_count == 4 else 1
    if len(red) != 1 or len(blue) != 1 or len(greens) != expected_greens:
        raise RawWhiteBalanceError("Only RGB/RGBG Bayer channel layouts are supported")
    pattern_labels = [desc[index] for index in channels]
    if pattern_labels.count("R") != 1 or pattern_labels.count("B") != 1 or pattern_labels.count("G") != 2:
        raise RawWhiteBalanceError("RAW Bayer pattern is not one red, two green and one blue")
    cfa_pattern = tuple(tuple(int(value) for value in row) for row in pattern.tolist())
    g2 = greens[1] if slot_count == 4 else None
    return count, desc, cfa_pattern, red[0], greens[0], g2, blue[0]


def inspect_raw_geometry(raw: Any, *, camera_make: str | None = None) -> RawGeometry:
    """Fail closed unless decoded and greybox dimensions describe the same sensor.

    Greybox coordinates use rawpy/LibRaw ``sizes.width/height`` (visible sensor
    coordinates), never raw_width/raw_height. Margins are deliberately not added.
    Non-square pixels, active-area crop metadata and non-Bayer patterns are outside
    this adapter's verified boundary.
    """
    try:
        sizes = raw.sizes
        visible_width, visible_height = sizes.width, sizes.height
        aspect = float(sizes.pixel_aspect)
        flip = sizes.flip
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise RawWhiteBalanceError("RAW sensor geometry is unavailable") from exc
    if not all(_exact_int(value) and value > 0 for value in (visible_width, visible_height)):
        raise RawWhiteBalanceError("RAW visible dimensions are invalid")
    if not math.isfinite(aspect) or not math.isclose(aspect, 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise RawWhiteBalanceError("Non-square RAW pixels are not supported")
    for name in ("crop_left_margin", "crop_top_margin", "crop_width", "crop_height"):
        value = getattr(sizes, name, 0)
        if type(value) is not int or value != 0:
            raise RawWhiteBalanceError("RAW active-area crops are not supported")

    camera_turns = _camera_turns(flip)
    decoded_width, decoded_height = (
        (visible_height, visible_width) if camera_turns % 2
        else (visible_width, visible_height)
    )
    # Inspect before processing. These intermediate dimensions describe the
    # unrotated visible Bayer plane; camera flip is applied to the returned image.
    # Reject shrink/crop/aspect transforms before mapping into that plane.
    for field, expected in (("iwidth", visible_width), ("iheight", visible_height)):
        actual = getattr(sizes, field, expected)
        if type(actual) is not int or actual != expected:
            raise RawWhiteBalanceError("RAW decoded dimensions do not match the visible sensor plane")

    count, desc, cfa_pattern, red, green1, green2, blue = _channel_layout(raw, camera_make)
    return RawGeometry(
        visible_width,
        visible_height,
        decoded_width,
        decoded_height,
        camera_turns,
        aspect,
        count,
        desc,
        cfa_pattern,
        red,
        green1,
        green2,
        blue,
    )


def _output_pixel(point: Any, width: int, height: int) -> tuple[int, int]:
    try:
        u, v = point["x"], point["y"]
    except (TypeError, KeyError, IndexError):
        try:
            u, v = point
        except (TypeError, ValueError):
            raise RawWhiteBalanceError("Choose a point inside the photograph") from None
    if (isinstance(u, bool) or isinstance(v, bool) or
            not isinstance(u, (int, float)) or not isinstance(v, (int, float))):
        raise RawWhiteBalanceError("Choose a point inside the photograph")
    u, v = float(u), float(v)
    if not math.isfinite(u) or not math.isfinite(v) or not 0 <= u <= 1 or not 0 <= v <= 1:
        raise RawWhiteBalanceError("Choose a point inside the photograph")
    return min(width - 1, math.floor(u * width)), min(height - 1, math.floor(v * height))


def _box(center_x: float, center_y: float, width: int, height: int,
         edge: int = GREYBOX_EDGE) -> tuple[int, int, int, int]:
    if width < edge or height < edge:
        raise RawWhiteBalanceError("RAW image is too small for a stable white-balance sample")
    if not math.isfinite(center_x) or not math.isfinite(center_y):
        raise RawWhiteBalanceError("The selected RAW point cannot be mapped")
    if not (-0.001 < center_x < width - 1 + 0.001 and -0.001 < center_y < height - 1 + 0.001):
        raise RawWhiteBalanceError("The selected point maps outside the visible RAW image")
    center_x = min(width - 1, max(0, center_x))
    center_y = min(height - 1, max(0, center_y))
    x = min(width - edge, max(0, math.floor(center_x - edge / 2 + 0.5)))
    y = min(height - edge, max(0, math.floor(center_y - edge / 2 + 0.5)))
    return int(x), int(y), edge, edge


def _sensor_center_from_uv(u: float, v: float, *, source_width: int,
                           source_height: int, recipe_rotation: int,
                           geometry: RawGeometry) -> tuple[float, float]:
    if not math.isfinite(u) or not math.isfinite(v) or abs(u) > 1.000001 or abs(v) > 1.000001:
        raise RawWhiteBalanceError("The selected point maps outside the decoded RAW image")
    # RenderPlan coordinates are normalized source-plane centers. Convert to
    # pixel-edge coordinates before each exact orthogonal inverse transform.
    recipe_x_edge = (u + 1.0) * source_width / 2.0
    recipe_y_edge = (v + 1.0) * source_height / 2.0
    recipe_turns = (recipe_rotation // 90) % 4
    decoded_x_edge, decoded_y_edge = inverse_point(
        recipe_x_edge, recipe_y_edge, geometry.decoded_width,
        geometry.decoded_height, recipe_turns
    )
    sensor_x_edge, sensor_y_edge = inverse_point(
        decoded_x_edge, decoded_y_edge, geometry.visible_width,
        geometry.visible_height, geometry.camera_turns
    )
    return sensor_x_edge - 0.5, sensor_y_edge - 0.5


SourceUV = Callable[
    [RenderPlan, int, int, int, int],
    tuple[np.ndarray, np.ndarray, np.ndarray],
]


def greybox_for_display_point(plan: OrientedPlan, point: Any, raw: Any, *,
                              source_uv: SourceUV = RenderPlan.source_uv,
                              camera_make: str | None = None,
                              raw_geometry: RawGeometry | None = None) -> tuple[int, int, int, int]:
    """Inverse-map one full-output click and return a bounded sensor greybox.

    ``point`` is the normalized full Develop output coordinate. A native detail
    viewport must first expand its ROI-local click to that full-output coordinate.
    The injected ``source_uv`` is the exact no-CA coordinate helper shared with
    ``RenderPlan.sample``; it returns normalized source-plane coordinates for one
    output pixel, avoiding a copied transform or a frame-sized coordinate map.
    """
    if not isinstance(plan, OrientedPlan) or not isinstance(plan.base, RenderPlan):
        raise RawWhiteBalanceError("RAW sampling requires a full Develop output plan")
    geometry = raw_geometry or inspect_raw_geometry(raw, camera_make=camera_make)
    base = plan.base
    if max(base.width, base.height) > 0 and (
            base.width != max(1, round(base.crop_w)) or
            base.height != max(1, round(base.crop_h))):
        raise RawWhiteBalanceError("RAW white-balance sampling requires full-resolution geometry")
    expected_recipe_shape = (
        (geometry.decoded_height, geometry.decoded_width)
        if base.recipe.rotation % 180 == 0
        else (geometry.decoded_width, geometry.decoded_height)
    )
    if tuple(base.source.shape[:2]) != expected_recipe_shape:
        raise RawWhiteBalanceError("The displayed RAW plan is not the full-resolution decoded source")

    validate_orientation(plan.orientation)
    out_x, out_y = _output_pixel(point, plan.width, plan.height)
    canonical_x, canonical_y, _, _ = inverse_rect(
        out_x, out_y, 1, 1, base.width, base.height, plan.orientation
    )
    us, vs, radius2 = source_uv(base, canonical_x, canonical_y, 1, 1)
    if us.shape != (1, 1) or vs.shape != (1, 1) or radius2.shape != (1, 1):
        raise RawWhiteBalanceError("The shared RAW geometry coordinate helper returned an invalid shape")
    sensor_x, sensor_y = _sensor_center_from_uv(
        float(us[0, 0]), float(vs[0, 0]), source_width=base.sw,
        source_height=base.sh, recipe_rotation=base.recipe.rotation,
        geometry=geometry
    )
    return _box(sensor_x, sensor_y,
                geometry.visible_width, geometry.visible_height)


def solve_auto_white_balance(camera_wb: Any, auto_wb: Any, geometry: RawGeometry,
                             *, auto_wb_valid: bool) -> dict[str, Any]:
    """Solve the existing two relative axes from LibRaw's effective WB ratios.

    The returned pair is absolute relative to the camera-as-shot baseline, not a
    delta to add to the current recipe. The sample is user-designated neutral;
    channel hue/chroma is not grounds for rejection.
    """
    if auto_wb_valid is not True:
        raise RawWhiteBalanceError("LibRaw could not solve white balance for that point")
    try:
        camera = list(camera_wb)
        automatic = list(auto_wb)
    except TypeError as exc:
        raise RawWhiteBalanceError("Camera white-balance multipliers are unavailable") from exc
    if len(camera) != 4 or len(automatic) != 4:
        raise RawWhiteBalanceError("LibRaw returned an incomplete white-balance vector")
    used = {geometry.red_channel, geometry.green1_channel, geometry.blue_channel}
    if geometry.green2_channel is not None:
        used.add(geometry.green2_channel)
    for index in used:
        if (not 0 <= index < 4 or
                any(isinstance(vector[index], bool) or
                    not isinstance(vector[index], (int, float)) or
                    not math.isfinite(float(vector[index])) or float(vector[index]) <= 0
                    for vector in (camera, automatic))):
            raise RawWhiteBalanceError("LibRaw returned invalid white-balance multipliers")
    log_delta = {
        index: math.log2(float(automatic[index])) - math.log2(float(camera[index]))
        for index in used
    }
    if geometry.green2_channel is not None:
        g2_residual = log_delta[geometry.green2_channel] - log_delta[geometry.green1_channel]
        if abs(g2_residual) > G2_MAX_LOG2_RESIDUAL:
            raise RawWhiteBalanceError("This RAW sample needs a second-green correction the recipe cannot represent")
    a = log_delta[geometry.red_channel] - log_delta[geometry.green1_channel]
    b = log_delta[geometry.blue_channel] - log_delta[geometry.green1_channel]
    temperature = 60.0 * (a - b)
    tint = 90.0 * (a + b)
    if (not math.isfinite(temperature) or not math.isfinite(tint) or
            not WB_MIN <= temperature <= WB_MAX or not WB_MIN <= tint <= WB_MAX):
        raise RawWhiteBalanceError("The selected point needs values outside the supported WB range")
    return {"temperature": temperature, "tint": tint, "solver": "libraw_greybox"}


def sample_raw_white_balance(raw: Any, plan: OrientedPlan, point: Any, *,
                             source_uv: SourceUV = RenderPlan.source_uv, camera_make: str | None = None) -> dict[str, Any]:
    """Run on a cancellable image worker with an unpacked RAW handle.

    This adapter sets Params(use_auto_wb=True, use_camera_wb=False, greybox=box).
    Caller checks budget before unpacking and verifies source/revision before and
    after processing, and discard the reply if its client generation was canceled.
    RAW work remains a full LibRaw processing allocation; greybox bounds only the
    statistics region and does not promise low-memory or fast RAW decoding.
    """
    import rawpy

    geometry = inspect_raw_geometry(raw, camera_make=camera_make)
    box = greybox_for_display_point(plan, point, raw, source_uv=source_uv,
                                    camera_make=camera_make, raw_geometry=geometry)
    if getattr(rawpy, "GREYBOX_WB_API_VERSION", None) != GREYBOX_API_VERSION:
        raise RawWhiteBalanceError("This RAW decoder does not support verified greybox sampling")
    from lumaraw.imaging import relative_wb
    camera_wb = relative_wb(raw.camera_whitebalance, 0, 0)
    params = rawpy.Params(use_camera_wb=False, use_auto_wb=True,
                          half_size=False, no_auto_scale=False, greybox=box,
                          demosaic_algorithm=rawpy.DemosaicAlgorithm.LINEAR)
    raw.dcraw_process(params)
    return {**solve_auto_white_balance(camera_wb, raw.auto_whitebalance,
                                      geometry, auto_wb_valid=raw.auto_whitebalance_valid),
            "greybox": list(box)}
