#!/usr/bin/env python3
"""Verify isolated wheel tag, Mach-O architectures, minimum OS, and load paths.

Purpose: inspect a finished wheel without importing rawpy or decoding images.
Inputs: repaired wheel path, extracted wheel root, SDK version string.
Outputs: fail-fast structural checks for this macOS arm64 build.
Non-goals: this is not a runtime, RAW correctness, or Lightroom parity test.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)


def main() -> int:
    wheel_path = Path(sys.argv[1])
    unpack_root = Path(sys.argv[2])
    sdk_version = sys.argv[3]
    expected_name = "rawpy-0.27.1-cp312-cp312-macosx_14_0_arm64.whl"
    if wheel_path.name != expected_name:
        raise SystemExit(f"unexpected wheel tag/name: {wheel_path.name}")

    binaries = sorted(
        path
        for path in (unpack_root / "rawpy").rglob("*")
        if path.is_file() and (path.name.endswith(".so") or path.name.endswith(".dylib"))
    )
    if not binaries:
        raise SystemExit("wheel contains no rawpy extension or dylibs")

    external_count = 0
    for binary in binaries:
        archs = run("/usr/bin/lipo", "-archs", str(binary)).strip().split()
        if archs != ["arm64"]:
            raise SystemExit(f"{binary}: expected arm64-only Mach-O, got {archs}")

        build = run("/usr/bin/xcrun", "vtool", "-show-build", str(binary))
        minimums = re.findall(r"\bminos\s+(\d+)\.(\d+)", build)
        if not minimums:
            raise SystemExit(f"{binary}: vtool reported no minimum OS version")
        for major, minor in minimums:
            if (int(major), int(minor)) > (14, 0):
                raise SystemExit(f"{binary}: minimum macOS {major}.{minor} exceeds 14.0")

        dependency_lines = run("/usr/bin/otool", "-L", str(binary)).splitlines()[1:]
        # For dylibs, otool -L includes the LC_ID_DYLIB install name as its
        # first entry. delocate 0.13.0 deliberately rewrites copied library
        # IDs to its /DLC/<wheel-relative-path> namespace; this is not a load
        # dependency. Validate actual dependency commands separately.
        install_id_output = run("/usr/bin/otool", "-D", str(binary)).splitlines()
        install_id = install_id_output[1].strip() if len(install_id_output) > 1 else None
        for line in dependency_lines:
            match = re.match(r"\s*(\S+)\s+\(", line)
            if not match:
                continue
            name = match.group(1)
            if name == install_id:
                continue
            if name.startswith("/usr/lib/") or name.startswith("/System/Library/"):
                continue
            if not name.startswith("@loader_path/"):
                raise SystemExit(f"{binary}: non-system dependency is not @loader_path-relative: {name}")
            target = (binary.parent / name.removeprefix("@loader_path/")).resolve()
            package_root = (unpack_root / "rawpy").resolve()
            if not target.is_relative_to(package_root) or not target.is_file():
                raise SystemExit(f"{binary}: dependency does not resolve inside wheel: {name}")
            external_count += 1

        if install_id and install_id.startswith("/DLC/"):
            expected_suffix = str(binary.relative_to(unpack_root))
            if install_id != f"/DLC/{expected_suffix}":
                raise SystemExit(f"{binary}: unexpected delocate install ID: {install_id}")
        elif install_id and not install_id.startswith("@rpath/"):
            raise SystemExit(f"{binary}: unexpected install ID: {install_id}")

        print(f"mach_o={binary.relative_to(unpack_root)} arch=arm64 minos<={14.0} sdk={sdk_version}")

    if external_count < 1:
        raise SystemExit("no bundled non-system dylib dependencies were found")
    print(f"verified_mach_o_count={len(binaries)}")
    print(f"verified_loader_path_dependency_count={external_count}")
    print(f"verified_resolved_loader_path_dependency_count={external_count}")
    print("verified_tag=cp312-cp312-macosx_14_0_arm64")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
