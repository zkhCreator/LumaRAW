#!/usr/bin/env python3
"""Bounded runtime check for the patched rawpy wheel.

Purpose: verify the patched greybox API and LibRaw WB status behavior on one
read-only public NEF fixture. Inputs: an isolated environment with the repaired
wheel and locked NumPy, plus a fixture path. Outputs: JSON API, feature, geometry,
WB, source-hash and child-RSS evidence, including an in-memory empty-G2 sample
case. Non-goals: no project import, output image, RAW write, camera-accuracy
claim, Lightroom comparison, or performance benchmark.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import resource
import subprocess
import sys
import time
import traceback
from pathlib import Path

TIMEOUT_SECONDS = 180.0
CPU_LIMIT_SECONDS = 150
RSS_LIMIT_BYTES = 2 * 1024 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def must_reject(label: str, operation) -> str:
    try:
        operation()
    except (TypeError, ValueError) as exc:
        return f"{label}: {type(exc).__name__}: {exc}"
    raise AssertionError(f"invalid greybox input was accepted: {label}")


def worker(raw_path: Path) -> dict[str, object]:
    import numpy as np
    import rawpy

    runtime_root = Path(sys.prefix).resolve()
    if not Path(rawpy.__file__).resolve().is_relative_to(runtime_root):
        raise AssertionError("rawpy did not import from this private runtime environment")
    if not Path(np.__file__).resolve().is_relative_to(runtime_root):
        raise AssertionError("NumPy did not import from this private runtime environment")
    if rawpy.GREYBOX_WB_API_VERSION != 1:
        raise AssertionError("patched greybox API identity is absent or unexpected")

    expected_flags = {
        "LCMS": True,
        "OPENMP": False,
        "RAWSPEED": False,
        "DEMOSAIC_PACK_GPL2": False,
        "DEMOSAIC_PACK_GPL3": False,
        "X3FTOOLS": True,
        "6BY9RPI": True,
        "REDCINECODEC": True,
        "DNGDEFLATECODEC": True,
        "DNGLOSSYCODEC": True,
    }
    if rawpy.flags is None:
        raise AssertionError("LibRaw build feature flags are unavailable")
    for key, expected in expected_flags.items():
        if rawpy.flags.get(key) is not expected:
            raise AssertionError(f"unexpected LibRaw feature flag {key}={rawpy.flags.get(key)!r}")

    invalid_inputs = [
        ("requires-auto-wb", lambda: rawpy.Params(use_auto_wb=False, greybox=(0, 0, 64, 64))),
        ("tuple-required", lambda: rawpy.Params(use_auto_wb=True, greybox=[0, 0, 64, 64])),
        ("four-values-required", lambda: rawpy.Params(use_auto_wb=True, greybox=(0, 0, 64))),
        ("bool-is-not-int", lambda: rawpy.Params(use_auto_wb=True, greybox=(True, 0, 64, 64))),
        ("negative-origin", lambda: rawpy.Params(use_auto_wb=True, greybox=(-1, 0, 64, 64))),
        ("nonpositive-dimensions", lambda: rawpy.Params(use_auto_wb=True, greybox=(0, 0, 0, 64))),
        ("uint32-overflow", lambda: rawpy.Params(use_auto_wb=True, greybox=(0, 0, 1 << 32, 64))),
    ]
    validation = [must_reject(label, operation) for label, operation in invalid_inputs]

    with rawpy.imread(str(raw_path)) as raw:
        sizes = raw.sizes
        pattern = raw.raw_pattern
        if pattern is None:
            raise AssertionError("fixture has no flat Bayer raw_pattern")
        cfa = np.asarray(pattern).tolist()
        color_desc = raw.color_desc.decode("ascii", "replace").rstrip("\x00")
        camera = list(raw.camera_whitebalance)
        pre_before = raw.auto_whitebalance
        valid_before = raw.auto_whitebalance_valid

        if pre_before is not None or valid_before is not None:
            raise AssertionError("new RawPy handle did not start with unset postprocess state")

        width, height = int(sizes.width), int(sizes.height)
        if width < 64 or height < 64:
            raise AssertionError("fixture visible RAW plane is smaller than the 64px greybox")
        roi = (max(0, (width - 64) // 2), max(0, (height - 64) // 2), 64, 64)

        # Capture CFA membership before postprocessing; LibRaw may adjust its
        # working color state during dcraw_process, while the raw pixels stay
        # attached to this handle.
        empty_g2_pixels = 0
        empty_g2_valid = None
        empty_g2_mask = None
        empty_g2_roi_raw = None
        cfa_slots = {int(value) for row in cfa for value in row}
        if raw.num_colors == 3 and color_desc.upper() == "RGBG" and 3 in cfa_slots:
            x0, y0, box_width, box_height = roi
            top_margin = int(sizes.top_margin)
            left_margin = int(sizes.left_margin)
            visible_raw = raw.raw_image_visible
            empty_g2_roi_raw = visible_raw[y0 : y0 + box_height, x0 : x0 + box_width]
            empty_g2_mask = np.zeros((box_height, box_width), dtype=np.bool_)
            for row in range(box_height):
                for column in range(box_width):
                    empty_g2_mask[row, column] = (
                        raw.raw_color(y0 + row + top_margin, x0 + column + left_margin) == 3
                    )
            empty_g2_pixels = int(np.count_nonzero(empty_g2_mask))
            if empty_g2_pixels == 0:
                raise AssertionError("fixture ROI does not contain any CFA slot 3 pixels")
            if not empty_g2_roi_raw.flags.writeable:
                raise AssertionError("in-memory RAW view is not writable for the isolated CFA test")

        def process(box):
            raw.dcraw_process(
                rawpy.Params(
                    use_auto_wb=True,
                    use_camera_wb=False,
                    no_auto_scale=False,
                    half_size=False,
                    greybox=box,
                )
            )
            return raw.auto_whitebalance_valid, raw.auto_whitebalance

        full_valid, full_multipliers = process(None)
        roi_valid, roi_multipliers = process(roi)
        repeat_valid, repeat_multipliers = process(roi)

        if not isinstance(full_valid, bool) or not isinstance(roi_valid, bool) or not isinstance(repeat_valid, bool):
            raise AssertionError("auto-WB validity did not report a boolean after auto-WB processing")
        if roi_valid is not True:
            raise AssertionError("known-good fixture ROI did not produce valid auto-WB before mutation")
        if roi_valid == repeat_valid and roi_multipliers != repeat_multipliers:
            raise AssertionError("repeated identical greybox produced different multipliers")

        # Zero only G2 raw samples in the captured in-memory view. The file
        # remains read-only and its hash is checked by the parent supervisor.
        if empty_g2_mask is not None and empty_g2_roi_raw is not None:
            empty_g2_roi_raw[empty_g2_mask] = 0
            empty_g2_valid, _empty_g2_multipliers = process(roi)
            if empty_g2_valid is not False:
                raise AssertionError("greybox with zero-valued G2 samples was reported valid")

        raw.dcraw_process(
            rawpy.Params(
                use_auto_wb=False,
                use_camera_wb=True,
                no_auto_scale=False,
                half_size=False,
            )
        )
        no_auto_valid = raw.auto_whitebalance_valid
        if no_auto_valid is not None:
            raise AssertionError("validity remained set after a non-auto-WB process")

        invalid_box_result = None
        try:
            raw.dcraw_process(
                rawpy.Params(
                    use_auto_wb=True,
                    use_camera_wb=False,
                    greybox=(width - 16, 0, 64, 64),
                )
            )
        except ValueError as exc:
            invalid_box_result = f"{type(exc).__name__}: {exc}"
        else:
            raise AssertionError("out-of-visible-bounds greybox was accepted")
        if raw.auto_whitebalance_valid is not None:
            raise AssertionError("failed process retained auto-WB validity from a prior call")

        # A fresh handle must not inherit the previous handle's status.
        with rawpy.imread(str(raw_path)) as fresh:
            fresh_valid = fresh.auto_whitebalance_valid
            fresh_auto = fresh.auto_whitebalance
        if fresh_valid is not None or fresh_auto is not None:
            raise AssertionError("fresh RawPy handle inherited postprocess status")

        dimensions = {
            name: getattr(sizes, name)
            for name in (
                "raw_width", "raw_height", "width", "height", "iwidth", "iheight",
                "left_margin", "top_margin", "crop_left_margin", "crop_top_margin",
                "crop_width", "crop_height", "pixel_aspect", "flip",
            )
        }
        labels = color_desc.upper()
        active_channels = sorted({int(value) for row in cfa for value in row})
        red = [index for index, label in enumerate(labels) if label == "R" and index in active_channels]
        greens = [index for index, label in enumerate(labels) if label == "G" and index in active_channels]
        blue = [index for index, label in enumerate(labels) if label == "B" and index in active_channels]
        camera_turns = {0: 0, 3: 2, 5: 3, 6: 1}.get(int(sizes.flip))
        expected_decoded = None if camera_turns is None else (
            (height, width) if camera_turns % 2 else (width, height)
        )
        active_set_ok = active_channels == list(range(len(labels)))
        cfa_layout_ok = (
            len(cfa) == 2
            and all(len(row) == 2 for row in cfa)
            and len(red) == 1
            and len(blue) == 1
            and len(greens) == 2
            and sum(labels[index] == "R" for index in active_channels) == 1
            and sum(labels[index] == "B" for index in active_channels) == 1
            and sum(labels[index] == "G" for index in active_channels) == 2
        )
        relative_log2 = None
        g2_residual_stops = None
        if (
            isinstance(roi_multipliers, (list, tuple))
            and len(camera) > max(active_channels, default=-1)
            and len(roi_multipliers) > max(active_channels, default=-1)
            and all(
                math.isfinite(float(camera[index]))
                and float(camera[index]) > 0
                and math.isfinite(float(roi_multipliers[index]))
                and float(roi_multipliers[index]) > 0
                for index in active_channels
            )
        ):
            relative_log2 = {
                str(index): math.log2(float(roi_multipliers[index]) / float(camera[index]))
                for index in active_channels
            }
            if len(greens) == 2:
                g2_residual_stops = relative_log2[str(greens[1])] - relative_log2[str(greens[0])]
        crop_clear = all(
            type(dimensions[name]) is int and dimensions[name] == 0
            for name in ("crop_left_margin", "crop_top_margin", "crop_width", "crop_height")
        )
        aspect_square = math.isfinite(float(sizes.pixel_aspect)) and math.isclose(
            float(sizes.pixel_aspect), 1.0, rel_tol=0.0, abs_tol=1e-6
        )
        dimensions_match = expected_decoded == (int(sizes.iwidth), int(sizes.iheight))
        adapter_geometry = {
            "supported_flip_code": camera_turns is not None,
            "camera_turns_clockwise": camera_turns,
            "expected_decoded_width_height": expected_decoded,
            "reported_iwidth_iheight": [int(sizes.iwidth), int(sizes.iheight)],
            "decoded_dimensions_match_visible_and_flip": dimensions_match,
            "pixel_aspect_is_square": aspect_square,
            "all_active_crop_values_zero": crop_clear,
            "supported_rgb_bayer_layout": cfa_layout_ok and active_set_ok,
            "fujifilm_make_check": "not available from rawpy fields captured here",
        }
        description = {
            "raw_type": str(raw.raw_type),
            "num_colors": int(raw.num_colors),
            "color_desc": color_desc,
            "cfa": cfa,
            "active_cfa_slots": active_channels,
            "cfa_slot_labels": {str(index): labels[index] for index in active_channels if index < len(labels)},
            "camera_whitebalance": camera,
            "roi": list(roi),
            "full_auto_valid": full_valid,
            "full_auto_multipliers": full_multipliers,
            "roi_auto_valid": roi_valid,
            "roi_auto_multipliers": roi_multipliers,
            "roi_relative_log2_vs_camera": relative_log2,
            "roi_green2_minus_green1_stops": g2_residual_stops,
            "green2_within_adapter_0_01_stop_tolerance": (
                None if g2_residual_stops is None else abs(g2_residual_stops) <= 0.01
            ),
            "repeat_roi_valid": repeat_valid,
            "repeat_roi_multipliers": repeat_multipliers,
            "empty_g2_pixels_zeroed_in_memory": empty_g2_pixels,
            "empty_g2_auto_valid": empty_g2_valid,
            "validity_after_no_auto": no_auto_valid,
            "validity_after_invalid_roi": raw.auto_whitebalance_valid,
            "invalid_visible_box": invalid_box_result,
            "geometry": dimensions,
            "adapter_geometry_checks": adapter_geometry,
        }
        return {
            "api_version": rawpy.GREYBOX_WB_API_VERSION,
            "python_prefix": str(runtime_root),
            "rawpy_module": str(Path(rawpy.__file__).resolve()),
            "numpy_module": str(Path(np.__file__).resolve()),
            "rawpy_version": rawpy.__version__,
            "libraw_version": rawpy.libraw_version,
            "libraw_version_compiled": rawpy.libraw_version_compiled,
            "flags": rawpy.flags,
            "invalid_inputs_rejected": validation,
            "fixture": str(raw_path),
            "fixture_size": raw_path.stat().st_size,
            "fixture_sha256": sha256(raw_path),
            "raw": description,
        }


def supervised(raw_path: Path) -> int:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop("DYLD_LIBRARY_PATH", None)
    before_hash = sha256(raw_path)
    started = time.monotonic()
    def set_child_limits() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_SECONDS, CPU_LIMIT_SECONDS))
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--worker", str(raw_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        preexec_fn=set_child_limits,
    )
    started = time.monotonic()
    sampled_max_rss = 0
    failure = None
    try:
        while process.poll() is None:
            if time.monotonic() - started > TIMEOUT_SECONDS:
                failure = f"runtime check exceeded {TIMEOUT_SECONDS:.0f}s"
                process.kill()
                break
            try:
                rss = subprocess.check_output(
                    ["/bin/ps", "-o", "rss=", "-p", str(process.pid)],
                    text=True,
                    timeout=3,
                ).strip()
                if rss:
                    sampled_max_rss = max(sampled_max_rss, int(rss) * 1024)
            except (subprocess.SubprocessError, ValueError):
                pass
            if sampled_max_rss > RSS_LIMIT_BYTES:
                failure = f"sampled RSS exceeded {RSS_LIMIT_BYTES} bytes"
                process.kill()
                break
            time.sleep(0.25)
        stdout, stderr = process.communicate(timeout=10)
    except BaseException:
        process.kill()
        process.communicate()
        raise

    exit_code = process.returncode
    child_max_rss = int(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    max_rss = max(sampled_max_rss, child_max_rss)
    if failure or exit_code != 0:
        print(json.dumps({
            "ok": False,
            "failure": failure,
            "exit_code": exit_code,
            "sampled_max_rss_bytes": sampled_max_rss,
            "child_max_rss_bytes": child_max_rss,
            "stdout": stdout[-12000:],
            "stderr": stderr[-12000:],
        }, indent=2, sort_keys=True))
        return 1

    try:
        report = json.loads(stdout)
    except json.JSONDecodeError:
        print(json.dumps({"ok": False, "stdout": stdout, "stderr": stderr}, indent=2))
        return 1
    report["ok"] = True
    after_hash = sha256(raw_path)
    report["fixture_sha256_before"] = before_hash
    report["fixture_sha256_after"] = after_hash
    report["fixture_unchanged"] = before_hash == after_hash
    if before_hash != after_hash:
        report["ok"] = False
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["sampled_max_rss_bytes"] = sampled_max_rss
    report["child_max_rss_bytes"] = max_rss
    report["rss_limit_bytes"] = RSS_LIMIT_BYTES
    report["cpu_limit_seconds"] = CPU_LIMIT_SECONDS
    report["timeout_seconds"] = TIMEOUT_SECONDS
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--worker":
        try:
            print(json.dumps(worker(Path(sys.argv[2])), sort_keys=True))
            return 0
        except BaseException:
            traceback.print_exc()
            return 1
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} RAW_FILE", file=sys.stderr)
        return 2
    raw_path = Path(sys.argv[1]).resolve(strict=True)
    if not raw_path.is_file():
        print("fixture path is not a regular file", file=sys.stderr)
        return 2
    return supervised(raw_path)


if __name__ == "__main__":
    raise SystemExit(main())
