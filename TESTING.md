# Reproducing validation

All probes use explicit read-only input photographs and new disposable catalog/output directories. They never use a personal photo library by default.

## Core and service

```sh
uv sync --frozen
LUMARAW_TEST_NEF=/absolute/nikon.NEF uv run --frozen pytest -q
```

The two `test_core.py` real-RAW tests skip if that environment variable is absent. `test_service.py` verifies revision conflicts, invalid edit atomicity, all-target sync, immutable export snapshots, deduplication keys, bounded queue pages and specific receipts, memory stopping, cancellation while a worker slot is occupied, superseded UI previews, cold job recovery and newline MCP framing through real subprocesses.

## Packaged engine

```sh
uv run --frozen python tests/bundle_probe.py \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --work /absolute/new-probe-directory --count 60 --max-edge 1024 \
  /absolute/nikon-d3s.NEF /absolute/nikon-d4.NEF /absolute/synthetic-45mp.dng
```

Use `--max-edge 0` for full-size outputs. The stress probe alternates TIFF/JPEG, output spaces and edit snapshots; it samples the known broker PID and asserts at most one direct image child. Cached sources may be reused, so repeated outputs are not independent camera samples.

```sh
uv run --frozen python tests/recovery_probe.py \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --work /absolute/new-recovery-directory --fixture /absolute/large.dng
```

The recovery probe deliberately SIGKILLs its own broker while an export runs. It preserves `unknown_effect`, checks orphan-worker termination and cold `interrupted` state, and never automatically retries or deletes possibly published files.

## Official MCP client

```sh
LUMARAW_ENGINE=/absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
LUMARAW_PROBE_ROOT=/absolute/new-mcp-directory \
LUMARAW_PROBE_NEF=/absolute/nikon.NEF \
uv run --with mcp python tests/mcp_sdk_probe.py
```

The independent Python MCP SDK verifies handshake, tool schemas, edits, full-resolution preview and queue completion, not just raw JSON exchanges. MCP remains a 2025-11-25 tool server; no claim is made about every client version or unimplemented protocol extensions.

## Native integration

Compile `native/*.swift` except `LumaRAWApp.swift`, plus `tests/NativeHarness.swift`, with Swift 5 mode and macOS 14 deployment target. Set `LUMARAW_ENGINE`, `LUMARAW_CATALOG`, `LUMARAW_TEST_OUTPUT`, and `LUMARAW_TEST_FIXTURE` to explicit test paths before running.

The harness exercises the real native Store and JSON transport: import, RAW preview, save, service readback and external-edit polling. Its NSHostingView snapshots are not desktop evidence; offscreen system material layers may render differently. Run real keyboard, VoiceOver, resize, toolbar/inspector and display-color tests on an unlocked Mac before any release acceptance.


## Current native state and library regression

```sh
.venv/bin/python tests/run_native.py --work work/native-check-01 \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine
```

The runner compiles all native files except the app entry point, generates five
small raster files and separate disposable catalogs, then runs the
15-assertion state, 13-assertion library, 12-assertion culling and 20-assertion review suites. The library suite checks
live smart membership, text search/sort, pagination, empty-filter selection,
partial metadata writes and independent recipe/metadata conflict handling. JSON
receipts stay in the ignored work directory. Without `--engine`, it uses the
current Python environment's `lumaraw` executable.

The culling suite uses five generated images to check anchored Shift selection,
Command toggling, visible-page selection, all-target batch flags/ratings, recipe
revision preservation and Develop active-photo scope. Single-key shortcuts are
scoped to photo views so metadata/search text fields retain text input; rendered
keyboard routing still needs desktop acceptance.

The review suite checks fixed Select/candidate roles, swap/promotion, linked and
independent viewports, retained frames, stale asynchronous replies, active-photo
actions and non-destructive Survey deselection. `--suite NativeReviewRegression`
runs only that suite. `tests/test_review.py` checks optional baseline omission,
identical edited pixels, bounded fitted output, exact viewport crops, lightweight
summaries and cancellation isolation using real worker processes.

The synthetic preview benchmark is `tests/review_probe.py --work work/review-probe-01
--backend cpu`. It records cold decode separately and uses five uncached recipe
outputs per warm-decode scenario, including worker startup/encoding, dimensions,
actual backend dispatch and sampled memory. It excludes UI and IPC latency.

## Library organization and performance

```sh
.venv/bin/python -m pytest -q tests/test_organization.py tests/test_thumbnail_cache.py
.venv/bin/python tests/library_probe.py --work work/library-probe-01 --rows 10000
```

Organization tests cover legacy migrations, many-to-many membership, live all/any
rules, atomic batch conflicts, Unicode literal search, bounded stable pagination
and backup/restore. Cache tests verify real cold-worker output, worker-free warm
reads, source-stat invalidation and partial/symlink rejection. The benchmark
reports sample count, median/p95, machine/OS, memory and dimensions. Its synthetic
catalog does not establish large RAW library or desktop latency. Its warm-worker
baseline deliberately repeats the prior per-photo process path. Desktop inspection
still requires permission to control the test application.

## Historical native selection regression (0.3.1)

Compile `native/Backend.swift`, `native/Store.swift` and `tests/NativeStateRegression.swift` with `xcrun swiftc -swift-version 5 -parse-as-library`. Set `LUMARAW_ENGINE` to the packaged engine, `LUMARAW_CATALOG` to a new disposable directory, and `LUMARAW_TEST_FIXTURES` to two absolute image paths separated by `|`. The executable reports 15 assertions for selection, empty export, pending edits, rating/external revision conflicts and undo. This is not a substitute for actual UI testing.

Private desktop receipts are intentionally excluded from public source. See `VERIFICATION.md` for the scoped historical summary.


## Metal 0.4

Build the optional backend with `uv run python scripts/build_metal.py`; `scripts/build_macos.py` does this automatically. Use `LUMARAW_REQUIRE_METAL=1` for a non-skipping GPU test run. `test_metal.py` covers all four spaces, curves/hue mixing, negative/out-of-gamut pixels, profiles, complex mask/LUT hybrid output, strips/viewport seams, simulated initialization/dispatch failure and bounded buffers.

`tests/acceleration_probe.py --engine ... --fixture ... --work <new-dir>` compares CPU/Metal with a creative recipe; add `--preset neutral` for defaults. Each run preserves its own image before another render can replace cache paths. `tests/bundle_probe.py --require-metal ...` asserts GPU dispatch for every completed export. The official MCP SDK probe now explicitly requests Metal and inspects actual preview/job processing receipts. See `METAL.md`.

## Public source check

```sh
python3 scripts/check_public.py
uv run --frozen pytest -q tests/test_public_release.py
```

`--strict` additionally rejects untracked build artifacts, environments and caches; use it on the clean extracted source archive. Never upload raw probe output without review: it can contain absolute photo/catalog paths and EXIF. The package script does not include those receipts.
