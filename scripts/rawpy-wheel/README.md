# Isolated rawpy arm64 wheel build

This workflow builds rawpy 0.27.1 with the reviewed LibRaw greybox API and
bundles its non-system dylib dependencies for the app's macOS 14 arm64 target.
It is a build and structural-loader check, not a RAW image accuracy test.

Run it with CPython 3.12 on an Apple Silicon Mac that has Xcode or Command Line
Tools installed. The selected SDK must be available through `xcrun`. The
builder refuses other host architectures, existing work directories, and work
directories inside the checked-out project.

Use a new output directory each time:

```sh
python3.12 scripts/rawpy-wheel/build_rawpy_wheel.py \
  --work "$TMPDIR/lumaraw-rawpy-wheel-2026-10-02"
```

The parent of `--work` must already exist and the final directory must not.
The workflow keeps source archives, a build-only virtual environment, CMake
prefix, wheel, redacted logs and `provenance.json` below that directory. It does
not use or modify the application's `.venv` or `uv.lock`. Failed work is left
intact for diagnosis; choose a different fresh path for a later attempt.

The builder downloads only the four pinned HTTPS archives in its source table
and checks each SHA-256 before extraction. Python build dependencies are
version-pinned and hash-locked in `requirements.lock`, installed in the new
work directory using `pip --require-hashes`. The bootstrap `pip` comes from
the selected CPython 3.12 installation; its version is recorded in the
provenance alongside the pinned CMake and compiler versions. Pip configuration
is explicitly disabled for this command, and its cache directory is confined
below `--work`. The three reviewed source patches
are hash-checked before any build begins. Codec discovery is constrained to a
private prefix and the selected Apple SDK; host package-manager paths are
rejected from the relevant CMake configuration.

For an offline build, provide both caches and `--offline`:

```sh
python3.12 scripts/rawpy-wheel/build_rawpy_wheel.py \
  --work "$TMPDIR/lumaraw-rawpy-wheel-offline-unique" \
  --source-cache "$HOME/.cache/lumaraw-rawpy-sources" \
  --wheelhouse "$HOME/.cache/lumaraw-build-wheels" \
  --offline
```

The source cache must contain the exact pinned archive filenames; each archive
is copied into the work directory and SHA-256 checked. The wheelhouse must
contain compatible wheels for every locked dependency; pip runs with
`--no-index --require-hashes --only-binary` and will fail rather than use the
network or accept a hash mismatch. Without `--offline`, a source cache can be
used opportunistically and missing source archives are downloaded over HTTPS.

Before accepting the wheel, the workflow checks its exact CPython 3.12/macOS
14/arm64 tag, verifies every extension and bundled dylib is arm64-only with a
minimum OS no newer than 14.0, checks that non-system dylib dependencies
resolve inside the wheel, then imports the wheel and checks the greybox API
API 2 capability marker. No image is opened or decoded by this workflow.

Pinned sources and build dependencies improve reviewability, but compiler,
SDK, and signing details can still change wheel bytes. The output is not
claimed to be bit-for-bit reproducible. Keep generated wheels, archives, logs,
virtual environments, local fixtures and provenance receipts out of Git.

Only the source inputs listed in `PUBLICATION_ALLOWLIST.md` belong in this
directory. Upstream attribution is retained under `licenses/`; see the project's
`THIRD_PARTY_NOTICES.md`. The rawpy patches retain rawpy's BSD-3-Clause terms;
the LibRaw validity patch retains its upstream LGPL-2.1 route. LCMS2 core, the
IJG/Modified-BSD JPEG notices and JasPer 2.0 attribution are preserved. Optional
LCMS GPL plugins, LibRaw GPL packs, RawSpeed and OpenMP are disabled. Generated
wheels and verification receipts remain local.

`Params.greybox` accepts a checked `(x, y, width, height)` tuple in the visible
sensor plane and requires auto WB. Every processing call resets the rectangle;
`None` means the full visible plane. `auto_whitebalance_valid` is unset before
auto processing and false when any active CFA channel has no usable sums. A
three-color RGBG Bayer image still has a required second-green CFA slot. Read
the processed `auto_whitebalance` only after validity is exactly true. These
library primitives do not implement the application's RAW selector by themselves.

API 2 also exposes read-only `camera_make` directly from LibRaw after opening
the header, before unpacking. The application rejects unverified manufacturer
and sensor-layout state instead of guessing it from decoded color pixels.

For explicit read-only runtime evidence, install the exact verified wheel and
NumPy in a separate disposable environment, then run its Python interpreter on
`tests/raw_backend_probe.py` with an explicit RAW fixture. The probe checks API
validation, repeated greybox results, reset state and an in-memory empty-G2 case,
with a 2 GiB sampled RSS watchdog, 150-second CPU and 180-second wall limits.
No image output is saved. A successful Nikon fixture does not establish other
cameras, macOS 14 runtime behavior or Lightroom numerical equivalence.
