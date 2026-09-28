# Reproducing validation

All probes use explicit read-only input photographs and new disposable catalog/output directories. They never use a personal photo library by default.

## Core and service

```sh
uv sync --frozen
LUMARAW_TEST_NEF=/absolute/nikon.NEF uv run --frozen pytest -q
```

The two `test_core.py` real-RAW tests skip if that environment variable is absent. `test_service.py` verifies revision conflicts, invalid edit atomicity, all-target sync, immutable export snapshots, deduplication keys, bounded queue pages and specific receipts, memory stopping, cancellation while a worker slot is occupied, superseded UI previews, cold job recovery and newline MCP framing through real subprocesses.

The folder increment also ran the complete suite with rawpy's public
[Nikon D3S regression fixture at a pinned commit](https://github.com/letmaik/rawpy/blob/5ab750e3044b55549bf2b21ada46df815a016103/test/iss030e122639.NEF).
Its size is 10,656,312 bytes and SHA-256 is
`5922721d13f11795557d97fdeb0a60b900086c402bc82a848ff280d15b99ffd4`.
Acquire the file separately, verify its hash and pass its absolute path through
`LUMARAW_TEST_NEF`. The image and generated outputs are not distributed with this
project. One sample verifies these regression contracts, not all Nikon cameras,
HE/HE* decoding, calibrated color or Adobe pixel equivalence.

## Broker lifecycle

`tests/test_broker_lifecycle.py` uses real isolated processes to test build
negotiation, automatic newer-generation handoff, explicit same-generation switch,
legacy/newer-client rejection, active preview and export preservation, second-owner
rejection, lost handoff replies, and no retry after an uncertain command response.
It also checks one-use clean receipts, future-schema refusal, source/dependency
identity and rejecting a replaced worker before reading images or creating output.

`NativeConnectionRegression` starts from a differently tagged test broker using
`tests/broker_fixture.py`. The native Store must surface the mismatch, activate the
packaged engine, preserve the paused job and its recipe, and avoid restarting a
matching service. The runner owns only this fixture process and catalog. This is
state/IPC evidence, not rendered Settings/alert acceptance.

```sh
.venv/bin/python tests/connection_probe.py --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine --work work/connection-probe-01
```

The benchmark compares one status RPC, negotiated status RPC and full packaged CLI
startup on the same empty, warm catalog. It records 30 samples, median/p95 and RSS;
no pixels, desktop latency or speed claim about actual photo processing is included.

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
15-assertion state, 13-assertion library, 12-assertion culling, 20-assertion review,
14-assertion thumbnail, 21-assertion collection-tree, 19-assertion virtual-copy,
10-assertion service-connection, 22-assertion stack, 19-assertion auto-stack,
24-assertion folder, 25-assertion keyword, 17-assertion folder-relocation and
17-assertion folder-synchronization suites.
Each suite has its own
fresh image directory, so a relink test cannot move another suite's fixture. The library suite checks
live smart membership, text search/sort, pagination, empty-filter selection,
partial metadata writes and independent recipe/metadata conflict handling. JSON
receipts stay in the ignored work directory. Without `--engine`, it uses the
current Python environment's `lumaraw` executable.
The folder suite adds 64 copies of its own generated fixture to test locating a
photo beyond the first page; it never copies a personal photograph.

The keyword suite checks lazy hierarchy/pages, Grid/active-photo scope, mixed selection,
captured create-and-assign targets, stale revisions, parent filters, ancestor
rename, synonym lookup, external updates and empty-page polling. It exercises the
real native Store and IPC without automating the rendered desktop.

The relocation suite moves only its generated fixture directory, scans a nested
tree with a missing file and a virtual copy, applies explicitly, and checks source
IDs, native folder/photo refresh, labels, keywords, persisted-plan resume, cancel
and stale-reply rejection. `tests/test_relocations.py` additionally checks indexed
hash mismatch, path collisions, merged folders, export admission/snapshots, file
and directory replacement, source reappearance, responsive cancellation, failed
write rollback, genuine v8 migration, later pages and active-plan backup/restore.

The synchronization suite verifies native scan/review/file selection, metadata
values, import-in-place, default retention versus explicit family removal, source
refresh and durable resume/cancel through the broker. `test_folder_sync.py` adds
directory replay, subtree selection, late file/catalog changes, cancellation during
scan/final verification, image/export contention, permission/parser failures,
symlink exclusion, atomic rollback, interrupted selection recovery, active-plan
backup/restore and genuine v9
migration. `test_xmp_read.py` verifies supported RDF fields, sidecar precedence,
standard embedded TIFF/JPEG/PNG packets, bounded XML/headers, unsupported values
and unchanged source hashes. These fixtures do not prove Adobe pixel equivalence.

```sh
.venv/bin/python tests/folder_sync_probe.py --work work/folder-sync-10k --rows 10000
.venv/bin/python tests/folder_sync_probe.py --work work/folder-sync-100k --rows 100000
```

This probe uses a synthetic catalog with all but one original missing, plus 10%
new empty placeholder files. It records preparation, bounded scan requests, final
verification/atomic application, concurrent browse contention and RSS. No pixels,
content hashes, broker IPC or rendered UI are measured. Empty files are used only
for metadata performance and are not evidence of supported image decoding.

```sh
.venv/bin/python tests/folder_sync_raw_probe.py \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon.NEF --work work/folder-sync-raw-01
```

This packaged integration probe discovers a private RAW copy through folder sync,
reads a generated sidecar, reports unsupported Adobe Develop settings, and creates
a virtual copy. A later metadata sync preserves the copy's independent description
and two already-frozen exports. It checks full-size JPEG/16-bit TIFF, ICC tags,
positive Metal dispatch and unchanged fixture/copy hashes. Integration timing may
include concurrent compiler activity; it is not a controlled throughput benchmark.

```sh
.venv/bin/python tests/relocation_probe.py --work work/relocation-10k --rows 10000
.venv/bin/python tests/relocation_probe.py --work work/relocation-100k --rows 100000
```

This metadata probe stages 1,001 synthetic folders into an existing empty
replacement directory. All originals are missing, exercising full issue paging
without hashes or pixel workers. It records preparation, each 60-original scan,
final stat validation plus atomic commit, concurrent 60-photo browsing and RSS.
The concurrent reader intentionally measures catalog-lock contention. These are
in-process service timings, not disk hash throughput, RAW speed or desktop latency.

```sh
.venv/bin/python tests/relocation_raw_probe.py \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon.NEF --work work/relocation-raw-01
```

This packaged integration probe copies the explicit fixture into its new work
directory, indexes it, creates a virtual copy and pauses two frozen exports. It
moves only that private copy's folder, verifies/reconnects the folder, then exports
full-size 16-bit TIFF/JPEG with real Metal dispatch and embedded ICC profiles.
It checks source/job snapshots and hashes both the user fixture and generated copy
afterward. Hash reads are warm after copying/indexing; the pixel cache starts cold
and the second variant can reuse decoding. Timing is diagnostic, not a standalone
processing benchmark.

`tests/test_keywords.py` covers genuine v7 migration and denied-write rollback,
legacy literal names, backup/restore, duplicate leaf identities, Unicode/literal
search, subtree moves/deletion, bounded pages/depth, assignment limits, independent
virtual copies, source/smart filters and atomic create/assign conflicts. The older
collection migration fixture uses v4 SQL state rather than calling current photo
commands against tables that intentionally do not exist until upgrade.

```sh
.venv/bin/python tests/keyword_probe.py --work work/keyword-probe-01 --rows 100000 --samples 30
```

This metadata-only probe creates 1,010 tags and two direct assignments per synthetic
photo, then measures warm paged lookup, selected-tag counts, ancestor filters,
qualified photo details and five parent renames. It reports peak RSS and verifies
that no image worker ran; timings exclude IPC and desktop presentation.

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

The thumbnail suite uses real service output to verify saved crop/rotation updates,
external non-active edits, metadata reuse and cache eviction. Controlled late replies
verify generation and revision rejection. `tests/test_developed_thumbnails.py`
compares geometry/color against fitted previews with JPEG tolerances, checks
original hashes and verifies cache invalidation/reuse and client cancellation.

The collection-tree suite verifies native nesting/aggregation, Quick save/clear,
target changes, stale target rejection, subtree duplication/removal and state in
a new Store. `tests/test_collections.py` adds database migration/backup evidence,
ancestor conflicts, live aggregate membership, cycle/depth checks and pagination.
`tests/test_collection_identities.py` checks the v4-to-v5 identity rebuild,
preserved hierarchy/Quick target/membership/stacks/custom schema objects, rollback
after a denied table drop, restart and stale mutation rejection. Native collection
checks prove a stale editor cannot rename a replacement collection.
`tests/collection_probe.py --work work/collection-probe-01` measures a generated
10,000-photo catalog and 13-node set: aggregate/child/state queries, Quick save and
subtree duplication. It records median/p95, counts and RSS, excludes IPC/UI and
starts no image workers.

These probes do not establish rendered disclosure, drag/drop or B-key mixed
selection equivalence to Lightroom Classic.

## Folder navigation

`tests/test_folders.py` verifies hierarchy/coalesced roots, direct/descendant counts,
source/filter independence, labels/favorites and stale edits, copy/removal/relink
maintenance, offline folders, stack visibility scope, bounded pages and photo
location. A real v6 fixture checks migration rollback after denied writes and
backup preservation. Older collection/stack migration tests now construct genuine
v1/v3 catalogs instead of merely lowering a newer catalog's schema number.
`NativeFolderRegression` tests native source navigation, lazy pages, parent display,
metadata filters, labels, external membership polling and locating an older photo
on a later page. It uses isolated generated rasters; no desktop control occurs.

```sh
.venv/bin/python tests/folder_probe.py --work work/folder-probe-01 --rows 100000 --samples 30
```

The fixture uses 1,000 leaf directories and 10 intermediate years. Timings cover
warm tree/search queries and photo pages, including metadata filters and deep
offsets, plus metadata-only SQL insertion with production triggers. They exclude
file import/EXIF, IPC, pixel work and native UI. Counts include virtual copies and
are independent of the current photograph filters.

## Photo stacks

`tests/test_stacks.py` exercises source isolation, active covers, contiguous sort,
collapsed selection/filtering, optimistic conflicts, collection ancestor conflicts,
singleton cleanup, virtual copies, cross-folder relinking, duplication/Quick save,
bulk source visibility, selected-subset splitting and v3 migration. A 130-member stack crosses three pages
without returning more than 60 summaries or loading recipes.

`NativeStackRegression` checks the actual Store, scoped badges, visible selection,
cover changes, external polling, empty-page refresh, collection revisions and flat
views against a real engine. It does not validate rendered controls or key routing.

```sh
.venv/bin/python tests/stack_probe.py --work work/stack-probe-01 --rows 10000 --samples 30
```

The probe creates ten-photo stacks with SQL fixtures, records collapsed/expanded
pages, filters, a flat baseline and deep offsets. It measures warm in-process
service latency and peak RSS, with no image workers, photograph processing or UI.

`tests/test_capture_time.py` uses generated JPEG/PNG and both TIFF byte orders to
check EXIF offsets, exact fractions, host-timezone independence, malformed headers,
epoch/pre-epoch dates and source-family refresh. These fixtures do not establish
real-camera metadata coverage. The timezone-switching test requires POSIX `tzset`.
`tests/test_auto_stacks.py` checks strict adjacent gaps, submicrosecond boundaries,
source isolation, stale previews, unknown dates, rollback, 60-family refresh pages
and bounded examples. `NativeAutoStackRegression` uses five EXIF-tagged JPEGs to
exercise captured source, changed duration, stale confirmation, metadata progress,
folder/collection application and revision adoption through the real broker.

```sh
.venv/bin/python tests/auto_stack_probe.py --work work/auto-stack-probe-01 --rows 100000 --samples 30
```

The probe streams generated ten-photo bursts and one source-sized stack. Preview
uses 30 warm samples; replacement uses three samples and includes its preceding
preview plus the apply-time revalidation. It records RSS and zero image-worker
activity, excluding metadata I/O, IPC and rendered UI. No unit-test timing threshold
or actual RAW processing speed is implied.

## Virtual copies

`tests/test_virtual_copies.py` verifies the v2-to-v3 table rebuild preserves old
photo, history, snapshot, job, keyword and collection references, plus custom
columns/indexes. It checks independent edits, shared snapshots, master promotion,
transactional conflicts, Unicode copy-name search, source-family indexing/relink,
backup/restore and a real completed export after its copy has been removed.
`--suite NativeVirtualCopyRegression` exercises the native copy/name/master/family/
confirmation flows through the broker; no rendered UI claim is made.

```sh
.venv/bin/python tests/virtual_copy_probe.py --work work/virtual-probe-01
```

The default fixture has 10,000 physical source rows and 10,000 virtual copies.
Thirty warm samples measure 60-row pages/target capture, copy filters, a source
family and creation of 60 copies per call. Created rows remain (21,800 final rows).
The receipt includes median/p95, RSS, machine/OS and zero pixel-worker activity;
it excludes IPC, image decoding and desktop latency.

## Library organization and performance

```sh
.venv/bin/python -m pytest -q tests/test_organization.py tests/test_thumbnail_cache.py
.venv/bin/python tests/library_probe.py --work work/library-probe-01 --rows 10000
.venv/bin/python tests/library_probe.py --work work/developed-probe-01 --rows 10000 --thumbnail-kind developed
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
