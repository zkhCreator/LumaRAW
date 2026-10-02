#!/usr/bin/env python3
"""Build and verify the isolated greybox-capable rawpy wheel.

Purpose: orchestrate the pinned arm64/macOS 14 rawpy + LibRaw build without
changing the application environment or project dependency lock.
Inputs: this directory's reviewed patches/toolchain/hashed dependency lock,
official source archives, CPython 3.12, Apple SDK tools, and a fresh --work path.
Outputs: a private wheel, redacted build logs, and path-free provenance below
the selected work directory.
Non-goals: this does not modify .venv/uv.lock, publish a wheel, run RAW image
fixtures, establish camera accuracy, or claim bit-for-bit reproducibility.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import Iterable, Mapping


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
MINIMUM_MACOS = "14.0"
EXPECTED_WHEEL = "rawpy-0.27.1-cp312-cp312-macosx_14_0_arm64.whl"
BUILD_JOBS_LIMIT = 8


@dataclass(frozen=True)
class SourceArchive:
    filename: str
    url: str
    sha256: str
    extract_name: str


SOURCES = (
    SourceArchive(
        "rawpy-0.27.1.tar.gz",
        "https://files.pythonhosted.org/packages/f3/ae/c1c7816ed3f3cbf7ca284a37371243500f4eb39b6a32f7368b585c4ef5c4/rawpy-0.27.1.tar.gz",
        "3194d64ff690ac945e1a43237edae8a18f1f493751924de1ae2bcef473c0fb79",
        "rawpy",
    ),
    SourceArchive(
        "lcms2-2.19.1.tar.gz",
        "https://github.com/mm2/Little-CMS/releases/download/lcms2.19.1/lcms2-2.19.1.tar.gz",
        "bfc54f7bab59fbc921012014a8032e4cba4abd46db47d46b76416a8c0b2815c8",
        "lcms",
    ),
    SourceArchive(
        "libjpeg-turbo-3.2.0.tar.gz",
        "https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/3.2.0/libjpeg-turbo-3.2.0.tar.gz",
        "6f30092cef9fb839779646608f4ee14ae3cbac989c47fa05e841b0841f09878e",
        "jpeg",
    ),
    SourceArchive(
        "jasper-4.2.9.tar.gz",
        "https://github.com/jasper-software/jasper/releases/download/version-4.2.9/jasper-4.2.9.tar.gz",
        "f71cf643937a5fcaedcfeb30a22ba406912948ad4413148214df280afc425454",
        "jasper",
    ),
)


# These hashes pin the reviewed diffs, not merely the upstream versions. Keep
# the capability patch hash synchronized with its final reviewed private copy.
PATCH_SHA256 = {
    "rawpy-greybox.patch": "444590f922c74072ba3c04b17e04ea16869a36bb4a622e516d5f6cc4a353d046",
    "rawpy-cmake-toolchain.patch": "913fa9a8bc63154fdda1231b3b88d1418110b3a437e9202e9c583b52d526f51f",
    "libraw-greybox-validity.patch": "14738c53a795f0c5a0690659dfd0e47f8d9d186bbd357334bdb9e2144554d8b3",
}


class BuildFailure(RuntimeError):
    """A fail-fast build/verification error with artifacts retained for review."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_capture(args: Iterable[str]) -> str:
    command = tuple(args)
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BuildFailure(f"required host tool failed: {Path(command[0]).name}") from exc


def redact(text: str, replacements: Mapping[str, str]) -> str:
    result = text
    for value, label in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        if value:
            result = result.replace(value, label)
    # Build tools can echo compiler/SDK paths in a form that differs slightly
    # from the exact path returned by xcrun. These prefixes are host-specific.
    result = re.sub(r"/Users/[^/\s]+", "$USER", result)
    result = re.sub(r"/private/var/folders/[^/\s]+(?:/[^\s]*)?", "$TMP", result)
    result = re.sub(r"/tmp/[^\s]+", "$TMP", result)
    result = re.sub(r"/var/folders/[^/\s]+(?:/[^\s]*)?", "$TMP", result)
    result = re.sub(r"/Applications/Xcode\.app(?:/[^\s]*)?", "$XCODE", result)
    result = re.sub(r"/Library/Developer/CommandLineTools(?:/[^\s]*)?", "$CLT", result)
    return result


class BuildLog:
    """Append-only command log with known host paths removed."""

    def __init__(self, path: Path, replacements: Mapping[str, str]) -> None:
        self.path = path
        self.replacements = replacements

    def command(self, label: str, args: Iterable[str], *, cwd: Path, env: Mapping[str, str]) -> None:
        command = tuple(str(part) for part in args)
        safe_cwd = redact(str(cwd), self.replacements)
        with self.path.open("a", encoding="utf-8") as log:
            log.write(f"\n=== {label} (cwd={safe_cwd}) ===\n")
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=dict(env),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
            )
            assert process.stdout is not None
            for line in process.stdout:
                log.write(redact(line, self.replacements))
            status = process.wait()
            log.write(f"\n=== exit status: {status} ===\n")
        if status != 0:
            raise BuildFailure(f"{label} failed; inspect the redacted log under $WORK/logs")


def require_fresh_work_path(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if os.path.lexists(candidate):
        raise BuildFailure("--work must not exist; the builder never overwrites a work directory")
    candidate = candidate.resolve(strict=False)
    if candidate == Path(candidate.anchor):
        raise BuildFailure("--work must name a new, non-root directory")
    if candidate == PROJECT_ROOT or PROJECT_ROOT in candidate.parents:
        raise BuildFailure("--work must be outside the checked-out project")
    if not candidate.parent.is_dir():
        raise BuildFailure("the parent of --work must already exist")
    if os.path.lexists(candidate):
        raise BuildFailure("--work must not exist; the builder never overwrites a work directory")
    return candidate


def check_dependency_lock_inputs() -> None:
    input_path = SCRIPT_DIR / "requirements.in"
    lock_path = SCRIPT_DIR / "requirements.lock"
    if not input_path.is_file() or not lock_path.is_file():
        raise BuildFailure("requirements.in and requirements.lock are both required")

    def normalize(name: str) -> str:
        return re.sub(r"[-_.]+", "-", name).lower()

    requested: dict[str, str] = {}
    for raw_line in input_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.partition("#")[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)", line)
        if not match:
            raise BuildFailure("requirements.in accepts only exact package pins")
        requested[normalize(match.group(1))] = match.group(2)

    locked: dict[str, str] = {}
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", line)
        if match:
            locked[normalize(match.group(1))] = match.group(2)
    if not requested or any(locked.get(name) != version for name, version in requested.items()):
        raise BuildFailure("requirements.in pins do not match the hash-locked requirements.lock")


def resolve_optional_directory(raw_path: str | None, label: str) -> Path | None:
    if raw_path is None:
        return None
    try:
        path = Path(raw_path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise BuildFailure(f"{label} must name an existing directory") from exc
    if not path.is_dir():
        raise BuildFailure(f"{label} must be an existing directory")
    return path


def preflight(
    raw_work: str,
    source_cache_arg: str | None,
    wheelhouse_arg: str | None,
    offline: bool,
) -> tuple[Path, str, str, str, str, str, dict[str, str], Path | None, Path | None]:
    work = require_fresh_work_path(raw_work)
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise BuildFailure("this workflow requires a native Apple Silicon Mac")
    if platform.python_implementation() != "CPython" or sys.version_info[:2] != (3, 12):
        raise BuildFailure("run this workflow with CPython 3.12")

    required_tools = (
        "/usr/bin/xcrun", "/usr/bin/xcode-select", "/usr/bin/patch", "/usr/bin/tar", "/usr/bin/make"
    )
    for tool in required_tools:
        if not Path(tool).is_file():
            raise BuildFailure(f"required Apple/system tool is missing: {Path(tool).name}")

    sdk_path = run_capture(("/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"))
    sdk_version = run_capture(("/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-version"))
    clang = run_capture(("/usr/bin/xcrun", "--find", "clang"))
    clangxx = run_capture(("/usr/bin/xcrun", "--find", "clang++"))
    ar = run_capture(("/usr/bin/xcrun", "--find", "ar"))
    ranlib = run_capture(("/usr/bin/xcrun", "--find", "ranlib"))
    strip = run_capture(("/usr/bin/xcrun", "--find", "strip"))
    developer_dir = run_capture(("/usr/bin/xcode-select", "-p"))
    compiler_resource = run_capture((clang, "-print-resource-dir"))
    for executable in (clang, clangxx, ar, ranlib, strip):
        if not Path(executable).is_file():
            raise BuildFailure("xcrun returned a missing compiler tool")

    check_dependency_lock_inputs()
    if not (SCRIPT_DIR / "toolchain.cmake").is_file():
        raise BuildFailure("toolchain.cmake is missing")
    for filename, expected in PATCH_SHA256.items():
        patch_path = SCRIPT_DIR / "patches" / filename
        if not patch_path.is_file():
            raise BuildFailure(f"reviewed patch is missing: {filename}")
        actual = sha256_file(patch_path)
        if actual != expected:
            raise BuildFailure(f"reviewed patch hash mismatch: {filename}")

    source_cache = resolve_optional_directory(source_cache_arg, "--source-cache")
    wheelhouse = resolve_optional_directory(wheelhouse_arg, "--wheelhouse")
    if offline and (source_cache is None or wheelhouse is None):
        raise BuildFailure("--offline requires both --source-cache and --wheelhouse")
    if offline:
        assert source_cache is not None
        for source in SOURCES:
            cached = source_cache / source.filename
            if not cached.is_file():
                raise BuildFailure(f"offline source cache is missing {source.filename}")
            if sha256_file(cached) != source.sha256:
                raise BuildFailure(f"offline source cache hash mismatch: {source.filename}")

    replacements = {
        str(work): "$WORK",
        str(PROJECT_ROOT): "$PROJECT",
        str(Path(sys.executable).resolve()): "$PYTHON",
        str(Path.home()): "$HOME",
        sdk_path: "$SDK",
        developer_dir: "$DEVELOPER_DIR",
        compiler_resource: "$CLANG_RESOURCE",
        str(Path(sys.base_prefix).resolve()): "$PYTHON_BASE",
        str(Path(sys.prefix).resolve()): "$PYTHON_ENV",
        clang: "$CLANG",
        clangxx: "$CLANGXX",
        ar: "$AR",
        ranlib: "$RANLIB",
        strip: "$STRIP",
    }
    if source_cache is not None:
        replacements[str(source_cache)] = "$SOURCE_CACHE"
    if wheelhouse is not None:
        replacements[str(wheelhouse)] = "$WHEELHOUSE"
    return (
        work,
        sdk_path,
        sdk_version,
        clang,
        developer_dir,
        compiler_resource,
        replacements,
        source_cache,
        wheelhouse,
    )


def clean_environment(
    work: Path,
    sdk_path: str,
    developer_dir: str,
    clang: str,
    toolchain_path: Path,
) -> dict[str, str]:
    temporary = work / "tmp"
    temporary.mkdir()
    (work / "pip-cache").mkdir()
    venv = work / "build-env"
    env = {
        "PATH": f"{venv}/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "TMPDIR": str(temporary),
        "LANG": "en_US.UTF-8",
        "LC_ALL": "C",
        "DEPS_PREFIX": str(work / "prefix"),
        "MACOS_SDK": sdk_path,
        "SDKROOT": sdk_path,
        "CC": clang,
        "CXX": run_capture(("/usr/bin/xcrun", "--find", "clang++")),
        "AR": run_capture(("/usr/bin/xcrun", "--find", "ar")),
        "RANLIB": run_capture(("/usr/bin/xcrun", "--find", "ranlib")),
        "STRIP": run_capture(("/usr/bin/xcrun", "--find", "strip")),
        "MAKE": "/usr/bin/make",
        "ARCHFLAGS": "-arch arm64",
        "MACOSX_DEPLOYMENT_TARGET": MINIMUM_MACOS,
        "CMAKE_OSX_DEPLOYMENT_TARGET": MINIMUM_MACOS,
        "RAWPY_CMAKE_TOOLCHAIN_FILE": str(toolchain_path),
        "PIP_CACHE_DIR": str(work / "pip-cache"),
        "PIP_NO_INPUT": "1",
        "PIP_CONFIG_FILE": os.devnull,
    }
    # Preserve HOME as supplied by the caller; never redirect it to build data.
    if "HOME" in os.environ:
        env["HOME"] = os.environ["HOME"]
    prefix_pairs = (
        (str(work), "./_lumaraw_build"),
        (sdk_path, "./_apple_sdk"),
        (developer_dir, "./_apple_toolchain"),
        (run_capture((clang, "-print-resource-dir")), "./_clang_resource"),
        (str(Path(sys.base_prefix).resolve()), "./_python_base"),
        (str(Path(sys.prefix).resolve()), "./_python_env"),
        (clang, "./_clang"),
    )
    prefix_maps: dict[str, str] = {}
    for source, destination in prefix_pairs:
        prefix_maps.setdefault(source, destination)
    path_map_flags: list[str] = []
    for source, destination in sorted(prefix_maps.items(), key=lambda item: len(item[0]), reverse=True):
        path_map_flags.extend(
            (
                f"-ffile-prefix-map={source}={destination}",
                f"-fdebug-prefix-map={source}={destination}",
                f"-fmacro-prefix-map={source}={destination}",
            )
        )
    common_flags = shlex.join(("-isysroot", sdk_path, f"-mmacosx-version-min={MINIMUM_MACOS}", *path_map_flags))
    env["CFLAGS"] = common_flags
    env["CXXFLAGS"] = common_flags
    env["LDFLAGS"] = shlex.join(("-isysroot", sdk_path, f"-mmacosx-version-min={MINIMUM_MACOS}"))
    return env


def download_source(source: SourceArchive, directory: Path) -> Path:
    target = directory / source.filename
    partial = directory / f"{source.filename}.part"
    if target.exists() or partial.exists():
        raise BuildFailure("fresh work directory unexpectedly contains a source archive")
    request = urllib.request.Request(source.url, headers={"User-Agent": "LumaRAW-isolated-wheel-builder/1"})
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(request, timeout=90) as response, partial.open("xb") as output:
            if not response.geturl().startswith("https://"):
                raise BuildFailure("source download redirected away from HTTPS")
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
                output.write(block)
        if digest.hexdigest() != source.sha256:
            partial.unlink(missing_ok=True)
            raise BuildFailure(f"source archive SHA-256 mismatch: {source.filename}")
        partial.replace(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return target


def materialize_source(
    source: SourceArchive,
    directory: Path,
    *,
    source_cache: Path | None,
    offline: bool,
) -> Path:
    target = directory / source.filename
    partial = directory / f"{source.filename}.part"
    if target.exists() or partial.exists():
        raise BuildFailure("fresh work directory unexpectedly contains a source archive")

    cached = source_cache / source.filename if source_cache is not None else None
    if cached is not None and cached.is_file():
        try:
            with cached.open("rb") as source_stream, partial.open("xb") as output:
                shutil.copyfileobj(source_stream, output, length=1024 * 1024)
            if sha256_file(partial) != source.sha256:
                partial.unlink(missing_ok=True)
                raise BuildFailure(f"cached source archive SHA-256 mismatch: {source.filename}")
            partial.replace(target)
            return target
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
    if offline:
        raise BuildFailure(f"offline source cache is missing {source.filename}")
    return download_source(source, directory)


def extract_archive(
    source: Path,
    destination: Path,
    *,
    log: BuildLog,
    env: Mapping[str, str],
    work: Path,
) -> None:
    destination.mkdir()
    log.command(
        f"Extract {source.name}",
        ("/usr/bin/tar", "-xzf", str(source), "-C", str(destination), "--strip-components=1"),
        cwd=work,
        env=env,
    )


def apply_patch(patch_path: Path, source_root: Path, *, log: BuildLog, env: Mapping[str, str], work: Path) -> None:
    args = ("/usr/bin/patch", "--batch", "--forward", "-p1", "-d", str(source_root), "-i", str(patch_path))
    log.command(f"Apply reviewed patch {patch_path.name}", args, cwd=work, env=env)


def check_no_host_package_paths(roots: Iterable[Path]) -> None:
    forbidden = ("/opt/homebrew", "/usr/local/Cellar", "/opt/local")
    for root in roots:
        if not root.exists():
            continue
        candidates = [root] if root.is_file() else (
            path
            for pattern in ("CMakeCache.txt", "compile_commands.json")
            for path in root.rglob(pattern)
        )
        for path in candidates:
            if not path.is_file():
                continue
            content = path.read_bytes()
            for marker in forbidden:
                if marker.encode("utf-8") in content:
                    raise BuildFailure("host package-manager path leaked into CMake configuration")


def extract_wheel_safely(wheel: Path, destination: Path) -> None:
    """Extract a locally-built wheel only after validating every member path."""
    root = destination.resolve()
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            name = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if name.is_absolute() or ".." in name.parts or stat.S_ISLNK(mode):
                raise BuildFailure("wheel contains an unsafe archive member")
            target = (destination / Path(*name.parts)).resolve()
            if target != root and root not in target.parents:
                raise BuildFailure("wheel member escapes the extraction directory")
        archive.extractall(destination)


def check_wheel_path_leaks(
    wheel: Path,
    *,
    work: Path,
    sdk_path: str,
    host_path_prefixes: Iterable[str],
) -> None:
    markers = {
        str(work).encode("utf-8"),
        str(PROJECT_ROOT).encode("utf-8"),
        str(Path.home()).encode("utf-8"),
        sdk_path.encode("utf-8"),
        b"/opt/homebrew",
        b"/usr/local/Cellar",
        b"/opt/local",
    }
    markers.update(path.encode("utf-8") for path in host_path_prefixes if path)
    user_path = re.compile(rb"/Users/[^/\x00\s]+/")
    temp_path = re.compile(rb"/(?:private/)?var/folders/[^/\x00\s]+/")
    max_marker = max(max(map(len, markers)), 512)
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            tail = b""
            with archive.open(member) as stream:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    data = tail + chunk
                    if (
                        any(marker and marker in data for marker in markers)
                        or user_path.search(data)
                        or temp_path.search(data)
                    ):
                        raise BuildFailure("wheel contains a local build, SDK, or package-manager path")
                    tail = data[-max_marker:]


def cmake_common_args(work: Path, sdk_path: str) -> tuple[str, ...]:
    return (
        "-G",
        "Unix Makefiles",
        f"-DCMAKE_TOOLCHAIN_FILE={SCRIPT_DIR / 'toolchain.cmake'}",
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_INSTALL_PREFIX={work / 'prefix'}",
        "-DCMAKE_INSTALL_LIBDIR=lib",
        "-DCMAKE_OSX_ARCHITECTURES=arm64",
        f"-DCMAKE_OSX_DEPLOYMENT_TARGET={MINIMUM_MACOS}",
        f"-DCMAKE_OSX_SYSROOT={sdk_path}",
        "-DCMAKE_INSTALL_NAME_DIR=@rpath",
        "-DCMAKE_INSTALL_RPATH=@loader_path",
    )


def build_cmake_dependency(
    name: str,
    source: Path,
    build: Path,
    *,
    options: tuple[str, ...],
    common: tuple[str, ...],
    log: BuildLog,
    env: Mapping[str, str],
    work: Path,
    python: Path,
    jobs: int,
) -> None:
    cmake = str(python.parent / "cmake")
    build.mkdir()
    log.command(f"Configure {name}", (cmake, "-S", str(source), "-B", str(build), *common, *options), cwd=work, env=env)
    log.command(f"Build {name}", (cmake, "--build", str(build), "--parallel", str(jobs)), cwd=work, env=env)
    log.command(f"Install {name}", (cmake, "--install", str(build)), cwd=work, env=env)


def require_file(path: Path) -> None:
    if not path.is_file():
        raise BuildFailure(f"expected build output is missing: {path.name}")


def verify_importable_capability(python: Path, unpacked: Path, *, log: BuildLog, env: Mapping[str, str], work: Path) -> None:
    check_env = dict(env)
    check_env["PYTHONPATH"] = str(unpacked)
    code = (
        "import rawpy; from rawpy import _rawpy; "
        "assert getattr(_rawpy, 'GREYBOX_WB_API_VERSION', None) == 1; "
        "print('verified_rawpy=' + rawpy.__version__); "
        "print('verified_greybox_api=1')"
    )
    log.command("Import wheel and verify greybox capability marker", (str(python), "-c", code), cwd=work, env=check_env)


def write_provenance(
    work: Path,
    *,
    sdk_version: str,
    wheel: Path,
    jobs: int,
    host_macos: str,
    compiler_version: str,
    cmake_version: str,
    pip_version: str,
) -> None:
    source_records = [
        {"filename": source.filename, "sha256": source.sha256, "url": source.url}
        for source in SOURCES
    ]
    patch_records = [
        {"filename": name, "sha256": digest}
        for name, digest in PATCH_SHA256.items()
    ]
    provenance = {
        "format": 1,
        "product": "rawpy-0.27.1-greybox-wheel",
        "wheel": wheel.name,
        "wheel_sha256": sha256_file(wheel),
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "host_macos": host_macos,
        "compiler": compiler_version,
        "cmake": cmake_version,
        "pip": pip_version,
        "architecture": "arm64",
        "macos_minimum": MINIMUM_MACOS,
        "sdk_version": sdk_version,
        "build_jobs": jobs,
        "dependency_lock_sha256": sha256_file(SCRIPT_DIR / "requirements.lock"),
        "sources": source_records,
        "patches": patch_records,
        "verification": [
            "arm64-only Mach-O extensions and bundled dylibs",
            "minimum macOS version no newer than 14.0",
            "non-system dylib dependencies resolve inside the wheel",
            "greybox capability import marker equals 1",
        ],
        "path_mapping": [
            "build/source paths -> ./_lumaraw_build",
            "Apple SDK paths -> ./_apple_sdk",
            "Apple toolchain paths -> ./_apple_toolchain",
            "CPython paths -> ./_python_base and ./_python_env",
        ],
        "reproducibility": "Pinned inputs; binary output is not claimed bit-for-bit reproducible.",
    }
    target = work / "provenance.json"
    with target.open("x", encoding="utf-8") as output:
        json.dump(provenance, output, indent=2, sort_keys=True)
        output.write("\n")


def build(raw_work: str, *, source_cache_arg: str | None, wheelhouse_arg: str | None, offline: bool) -> None:
    (
        work,
        sdk_path,
        sdk_version,
        clang,
        developer_dir,
        compiler_resource,
        replacements,
        source_cache,
        wheelhouse,
    ) = preflight(raw_work, source_cache_arg, wheelhouse_arg, offline)
    work.mkdir(mode=0o700, exist_ok=False)
    for name in ("sources", "extract", "build", "prefix", "output/raw", "output/repaired", "output/unpacked", "logs"):
        (work / name).mkdir(parents=True, exist_ok=True)
    log = BuildLog(work / "logs" / "build.log", replacements)
    env = clean_environment(work, sdk_path, developer_dir, clang, SCRIPT_DIR / "toolchain.cmake")
    jobs = max(1, min(BUILD_JOBS_LIMIT, os.cpu_count() or 1))

    print("Downloading and verifying pinned source archives…")
    source_paths: dict[str, Path] = {}
    for source in SOURCES:
        source_paths[source.extract_name] = materialize_source(
            source,
            work / "sources",
            source_cache=source_cache,
            offline=offline,
        )

    venv = work / "build-env"
    log.command("Create private Python build environment", (sys.executable, "-m", "venv", str(venv)), cwd=work, env=env)
    python = venv / "bin" / "python"
    pip_args = [
        str(python), "-m", "pip", "--isolated",
        "install", "--require-hashes", "--disable-pip-version-check", "--no-input",
        "--cache-dir", str(work / "pip-cache"),
        "--only-binary=:all:",
    ]
    if offline:
        pip_args.append("--no-index")
    else:
        pip_args.extend(("--index-url", "https://pypi.org/simple"))
    if wheelhouse is not None:
        pip_args.extend(("--find-links", str(wheelhouse)))
    pip_args.extend(("-r", str(SCRIPT_DIR / "requirements.lock")))
    log.command("Install hash-locked build dependencies", pip_args, cwd=work, env=env)
    compiler_version = run_capture((clang, "--version")).splitlines()[0]
    cmake_version = run_capture((str(python.parent / "cmake"), "--version")).splitlines()[0]
    pip_version = run_capture((str(python), "-m", "pip", "--version")).split()[1]

    extract_root = work / "extract"
    extracted: dict[str, Path] = {}
    for source in SOURCES:
        destination = extract_root / source.extract_name
        extract_archive(source_paths[source.extract_name], destination, log=log, env=env, work=work)
        extracted[source.extract_name] = destination

    raw_source = extracted["rawpy"]
    require_file(raw_source / "external" / "LibRaw" / "libraw" / "libraw.h")
    patches = SCRIPT_DIR / "patches"
    apply_patch(patches / "rawpy-cmake-toolchain.patch", raw_source, log=log, env=env, work=work)
    apply_patch(patches / "rawpy-greybox.patch", raw_source, log=log, env=env, work=work)
    apply_patch(patches / "libraw-greybox-validity.patch", raw_source, log=log, env=env, work=work)

    common = cmake_common_args(work, sdk_path)
    build_root = work / "build"
    build_cmake_dependency(
        "LCMS2",
        extracted["lcms"],
        build_root / "lcms",
        options=(
            "-DLCMS2_BUILD_SHARED=ON", "-DLCMS2_BUILD_STATIC=OFF",
            "-DLCMS2_BUILD_TOOLS=OFF", "-DLCMS2_BUILD_TESTS=OFF",
        ),
        common=common, log=log, env=env, work=work, python=python, jobs=jobs,
    )
    build_cmake_dependency(
        "libjpeg-turbo",
        extracted["jpeg"],
        build_root / "jpeg",
        options=(
            "-DENABLE_SHARED=ON", "-DENABLE_STATIC=OFF", "-DWITH_JPEG8=ON",
            "-DWITH_SIMD=ON", "-DWITH_TURBOJPEG=OFF", "-DWITH_TOOLS=OFF",
            "-DWITH_TESTS=OFF", "-DWITH_FUZZ=OFF",
        ),
        common=common, log=log, env=env, work=work, python=python, jobs=jobs,
    )
    build_cmake_dependency(
        "JasPer",
        extracted["jasper"],
        build_root / "jasper",
        options=(
            "-DBUILD_SHARED_LIBS=ON", "-DJAS_ENABLE_SHARED=ON", "-DJAS_PACKAGING=ON",
            "-DJAS_ENABLE_PIC=ON", "-DJAS_ENABLE_LIBJPEG=ON", "-DJAS_ENABLE_LIBHEIF=OFF",
            "-DJAS_ENABLE_OPENGL=OFF", "-DJAS_ENABLE_DOC=OFF", "-DJAS_ENABLE_LATEX=OFF",
            "-DJAS_ENABLE_PROGRAMS=OFF", "-DJAS_ENABLE_MULTITHREADING_SUPPORT=ON",
            "-DJAS_ENABLE_CMAKE_PACKAGE_CONFIG=OFF",
        ),
        common=common, log=log, env=env, work=work, python=python, jobs=jobs,
    )

    prefix = work / "prefix"
    for relative in (
        "include/lcms2.h", "lib/liblcms2.dylib", "include/jpeglib.h", "lib/libjpeg.dylib",
        "include/jasper/jasper.h", "lib/libjasper.dylib",
    ):
        require_file(prefix / relative)
    require_file(Path(sdk_path) / "usr/include/zlib.h")
    require_file(Path(sdk_path) / "usr/lib/libz.tbd")
    check_no_host_package_paths((build_root,))

    raw_output = work / "output" / "raw"
    log.command(
        "Build rawpy wheel",
        (
            str(python), "setup.py", "bdist_wheel", "--plat-name", "macosx_14_0_arm64",
            "--dist-dir", str(raw_output),
        ),
        cwd=raw_source,
        env=env,
    )
    libraw_build = raw_source / "external" / "LibRaw-cmake" / "build"
    check_no_host_package_paths((libraw_build,))
    raw_wheel = raw_output / EXPECTED_WHEEL
    require_file(raw_wheel)

    repaired_dir = work / "output" / "repaired"
    python_bin = python.parent
    log.command(
        "Bundle non-system dylib dependencies",
        (str(python_bin / "delocate-wheel"), "-v", "--require-archs", "arm64", "-w", str(repaired_dir), str(raw_wheel)),
        cwd=work,
        env=env,
    )
    final_wheel = repaired_dir / EXPECTED_WHEEL
    require_file(final_wheel)

    unpacked = work / "output" / "unpacked"
    extract_wheel_safely(final_wheel, unpacked)
    check_wheel_path_leaks(
        final_wheel,
        work=work,
        sdk_path=sdk_path,
        host_path_prefixes=(
            str(PROJECT_ROOT),
            str(Path.home()),
            str(Path(sys.executable).resolve()),
            str(Path(sys.base_prefix).resolve()),
            str(Path(sys.prefix).resolve()),
            developer_dir,
            compiler_resource,
            clang,
        ),
    )
    log.command(
        "Verify arm64, minimum OS, and bundled dependency closure",
        (str(python), str(SCRIPT_DIR / "verify-wheel.py"), str(final_wheel), str(unpacked), sdk_version),
        cwd=work,
        env=env,
    )
    verify_importable_capability(python, unpacked, log=log, env=env, work=work)
    write_provenance(
        work,
        sdk_version=sdk_version,
        wheel=final_wheel,
        jobs=jobs,
        host_macos=platform.mac_ver()[0],
        compiler_version=compiler_version,
        cmake_version=cmake_version,
        pip_version=pip_version,
    )
    print("Wheel build and structural verification completed; artifacts remain under $WORK.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an isolated rawpy 0.27.1 arm64/macOS 14 wheel.")
    parser.add_argument("--work", required=True, help="path for a new work directory; it must not already exist")
    parser.add_argument("--source-cache", help="optional directory of pinned source archives, verified before reuse")
    parser.add_argument("--wheelhouse", help="optional directory of hash-locked Python wheels")
    parser.add_argument("--offline", action="store_true", help="disable network; requires both caches and all inputs")
    args = parser.parse_args()
    try:
        build(args.work, source_cache_arg=args.source_cache, wheelhouse_arg=args.wheelhouse, offline=args.offline)
    except BuildFailure as exc:
        print(f"Build stopped: {exc}", file=sys.stderr)
        return 2
    except (OSError, urllib.error.URLError, tarfile.TarError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        print(f"Build stopped: {type(exc).__name__}; diagnostic logs remain under $WORK/logs when available.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
