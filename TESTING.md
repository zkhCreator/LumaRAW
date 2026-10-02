# Reproducing validation

All probes use explicit read-only input photographs and new disposable catalog/output directories. They never use a personal photo library by default.

## Native culling shortcuts

`NativeCullingShiftRegression` uses five generated originals and catalog-only
virtual copies to exercise the documented rating/flag/color key mappings,
single-photo Grid/Loupe advance, active-only Compare/Survey writes and captured
Grid batches. Check Stars/Keepers/Rejects, filters, smart/set membership, sorting,
no successor and the 61-to-60 filtered page clamp. Rows and focus must remain
coherent when a query changes membership or a later view/source action supersedes
its reply. Gate real command replies to cover late same-field writes, independent
rating/flag fields and partially overlapping batches. Cover both orders of an
older successful acknowledgment and a newer failed attempt, plus a third success
before the old reply arrives. Use distinct initial values so failure to adopt
cannot pass accidentally; preserve newer error/status without moving focus.
A real node move with a
failed page read supplies a pending aggregate-set invalidation; culling its final
smart member must clear focus and consume only the successful refresh generation.

```sh
.venv/bin/python tests/run_native.py --work work/new-culling-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeCullingShiftRegression --suite NativeLibraryRegression \
  --suite NativeSelectionRegression --suite NativeReviewRegression \
  --suite NativeReferenceRegression --suite NativeCollectionNodeDevelopDropRegression \
  --suite NativeMetadataPresetRegression --suite NativePainterRegression \
  --suite NativeResponsivenessRegression
```

The pure key mapping and native Store probes do not dispatch desktop key events,
verify text-input focus routing, establish keyboard-layout/VoiceOver acceptance,
or prove Lightroom's exact sorted/filter-removal/selection behavior. Keep those
checks separate on macOS 14 and the current supported macOS.

## Native collection photo drops

`NativeCollectionDropRegression` exercises captured visible-page photo drags,
regular/Quick admission, rejected foreign/malformed/stale-page payloads,
selection changes after capture and stale collection revisions through the real
packaged service. Keep original bytes, photographic state and existing memberships
unchanged while adding the captured IDs. The Reference suite checks that its
single-anchor behavior is preserved when the shared payload includes a selection.
Quick drops must keep their captured destination when the configurable Target
changes, preserve membership on repeated adds with a fresh revision, and reject
a stale Quick revision without replaying the mutation.
Do not infer mouse drag recognition, hover feedback or VoiceOver behavior from
state checks or offscreen snapshots; those require desktop acceptance separately.

```sh
.venv/bin/python tests/run_native.py --work work/new-collection-drop-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeCollectionDropRegression --suite NativeCollectionRegression \
  --suite NativeReferenceRegression --suite NativeResponsivenessRegression
```

## Native collection-node moves

`NativeCollectionNodeDropRegression` exercises the separate node payload, regular/
smart/set moves, unchanged fields/memberships and original bytes, same-parent
no-ops, and stale/cycle/depth rejection. It gates actual save calls while navigation
enters an unrelated or affected set, then checks the current source, selection,
photo page and total. Moving a child out of or into the open set must update that
set's aggregate results. Depth fixtures expand ancestors sequentially, as a user
does; they must not flood transport admission to test an unrelated failure mode.
Decoder metadata caches may fill during preview; authored metadata and recipes
must remain unchanged. The app's Info.plist must export both photo and node UTIs.

`NativeCollectionNodeDevelopDropRegression` gates real saves while the selected
photo's child collection moves out of its set, then enters Develop or Reference.
The active photo, saved recipe and independent locked reference must survive;
returning to Library must refresh the set without a test-side manual refresh.
Also gate page replies to exercise view-transition invalidation, failed reads
and newer pending generations. Compare/Survey must initialize from fresh rows.

```sh
.venv/bin/python tests/run_native.py --work work/new-collection-node-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeCollectionNodeDropRegression --suite NativeCollectionDropRegression \
  --suite NativeCollectionNodeDevelopDropRegression --suite NativeReviewRegression \
  --suite NativeCollectionRegression --suite NativeLibraryRegression \
  --suite NativeSelectionRegression --suite NativeReferenceRegression \
  --suite NativeResponsivenessRegression
```

Inspect generated sidebar snapshots as offscreen layout evidence only. Native
drag recognition, hover, drop hit regions, keyboard alternatives and VoiceOver
still require desktop acceptance on macOS 14 and the current supported macOS.
Root moves remain available through the existing Edit / Move location picker.

## Multiple-preset export batches

`test_export_batch.py` covers captured shared/catalog preset revisions, individual
and parent-folder destinations, the photo/preset product limit, all-target
preflight, transactional batch/job/receipt insertion, replay after preset changes
and method-separated request keys. Migration starts from genuine schema 35;
rollback and product backup/restore preserve prior jobs and Previous settings.
Batch pages and scoped cancellation/retry must remain independent of unrelated
jobs. Generated raster outputs check multiple preset variants, immutable snapshots,
Unicode filename bounds and collision preservation.

`NativeExportBatchRegression` uses the packaged service for captured across-page
preset selection, destination forms, stale rejection, guarded submission and batch
history/details. Any generated view snapshots are offscreen layout evidence only.
Desktop input, native folder panels and VoiceOver require separate acceptance.

```sh
.venv/bin/python -m pytest -q tests/test_export_batch.py tests/test_previous_export.py \
  tests/test_export_presets.py tests/test_export_metadata.py tests/test_service.py
.venv/bin/python tests/run_native.py --work work/new-export-batch-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeExportBatchRegression --suite NativePreviousExportRegression \
  --suite NativeExportPresetRegression --suite NativeResponsivenessRegression
```

Run `tests/export_batch_probe.py` separately from tests/builds. The probe measures
bounded in-process submission and SQL work on generated catalogs with keyword
load, recording first/repeated calls and sampled process RSS. It excludes image
processing and desktop rendering; these figures cannot establish UI frame rate or
end-to-end photo export throughput.

```sh
.venv/bin/python tests/export_batch_probe.py --work work/new-export-batch-scale \
  --photos 100 --preset-counts 1 5 10 --keywords-per-photo 100
```

`test_export_batch_metadata_cache.py` checks batch-local metadata reuse against
fresh snapshot bytes and receipts, policy separation, unchanged job ordering,
bounded retention and oversized-item fallback. Separate submissions must observe
intervening metadata/keyword edits; exact request replay must do no new snapshot
work. Ordinary export must retain its independent preparation path. Compare the
same scale probe in fresh directories before and after an optimization, without
concurrent tests/builds or workers.

## Export with Previous

`test_previous_export.py` exercises genuine schema-34 upgrades, initial absence,
atomic queue/settings/request receipts, all-target validation, captured conflicts,
current photo snapshots and replay after later configuration changes. Existing
ordinary export request digests remain compatible with migrated receipts. Previous
requests use a separate method-bound digest; cross-command key reuse fails.
Generated raster output checks exercise the accepted pipeline without establishing
camera accuracy or Lightroom pixel equivalence.

`NativePreviousExportRegression` uses the real packaged service for manual and
preset-derived submissions, captured selection, pending edits and the Previous
action. Availability travels in existing queue polls; unchanged polling must not
publish the workspace again. Native state probes do not establish desktop shortcut
dispatch, folder-panel behavior or VoiceOver acceptance.

```sh
.venv/bin/python -m pytest -q tests/test_previous_export.py tests/test_export_presets.py \
  tests/test_export_metadata.py tests/test_service.py
.venv/bin/python tests/run_native.py --work work/new-previous-export-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativePreviousExportRegression --suite NativeExportPresetRegression \
  --suite NativeExportMetadataRegression --suite NativeResponsivenessRegression
```

## Saved export settings

`test_export_presets.py` exercises complete/default settings, literal destinations
without destination filesystem IO, normalized unique names, captured revisions,
shared/local storage boundaries, additive schema-33 upgrades and frozen queue
snapshots. Generated raster exports check dimensions, formats, ICC profiles and
collision preservation; they do not establish camera accuracy or Adobe processing
equivalence. All shared preset storage uses disposable injected roots.

`NativeExportPresetRegression` uses the real packaged relay for preset management,
independent loaded drafts, stale updates, storage and explicit queue submission.
Its offscreen renders establish layout only; desktop input, native folder panels
and VoiceOver require separate acceptance.

```sh
.venv/bin/python -m pytest -q tests/test_export_presets.py tests/test_service.py
.venv/bin/python tests/run_native.py --work work/new-export-preset-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeExportPresetRegression --suite NativeExportMetadataRegression \
  --suite NativeResponsivenessRegression
.venv/bin/python tests/export_preset_probe.py --work work/new-export-preset-scale \
  --rows 10000 100000
```

Run the scale probe after other validation stops. It seeds synthetic shared
preset rows, then measures an initial call and five warm repeats for first/deep
pages and a sparse literal search. Timings include Service validation, SQLite
connections/transactions, token reads and count/page queries. IPC, native UI,
images and seed work are excluded; OS caches are warm. Separate VM counters cover
individual SQL components at 100-instruction granularity, with query plans and
5 ms process RSS samples. Deep OFFSET and substring search still scan index
entries; bounded replies do not imply constant-time searches.

## Core and service

```sh
uv sync --frozen
LUMARAW_TEST_NEF=/absolute/nikon.NEF uv run --frozen pytest -q
```

The two `test_core.py` real-RAW tests skip if that environment variable is absent. `test_service.py` verifies revision conflicts, invalid edit atomicity, all-target sync, immutable export snapshots, deduplication keys, bounded queue pages and specific receipts, memory stopping, cancellation while a worker slot is occupied, superseded UI previews, cold job recovery and newline MCP framing through real subprocesses.

## Copy imports

`test_import_copy.py` uses disposable real files and destinations. It verifies
flat/source/date organization, civil-date boundaries and unknown dates, exact
original/XMP bytes and mtime, shared sidecars, captured presets, folder counts and
Previous Import. Collision preflight covers existing files, symlinks, case-folded
names and sidecars. Fault injection exercises writing/sealed/linked/published
crash points, unrecorded ownership, disk write failure, modified checksums with
preserved stat fields, cancellation while catalog reads remain available, SQL
rollback/resume, restored-catalog isolation and atomic schema-25 upgrades. A
125-file case checks bounded review/receipt paging.

`NativeImportRegression` covers Copy option capture, destination previews without
writes, an existing-target collision, explicit Resume Copy, exact copied bytes and
retained receipts alongside Add workflows. Its offscreen sheet PNGs permit limited
layout inspection only; they do not validate desktop input or native file panels.

```sh
.venv/bin/python -m pytest -q tests/test_import_copy.py tests/test_import_review.py \
  tests/test_import_processing.py tests/test_capture_time.py
.venv/bin/python tests/run_native.py --work work/new-copy-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeImportRegression --suite NativeImportProcessingRegression \
  --suite NativePreviousImportRegression --suite NativeResponsivenessRegression
.venv/bin/python tests/import_copy_probe.py --work work/new-copy-throughput \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon.NEF --files 24
```

Run the throughput probe after tests/builds stop. It generates source clones before
measurement and runs three fresh catalog/destination batches through the packaged
relay, recording bytes, dimensions, scan/apply time, throughput, sampled broker
RSS, concurrent control median/p95/max and byte checks. OS source caches are warm;
there is no pixel/GPU work. This does not establish SSD-independent throughput,
desktop frame rate, removable-media behavior or untested filesystem support.

## Original-state second copies

`test_import_backup.py` uses disposable photos and XMP to verify original names,
bytes and mtime despite primary naming/presets, checked scope, distinct progress,
main-only catalog/Previous Import membership, destination boundaries, all-target
collision preflight, absent/replaced roots and shared sidecars. Fault injection
covers writing/sealed/linked/published interruptions for each role, cancellation
with live control reads, catalog rollback/retry and restored-catalog ownership.
Migration uses a genuine schema-27 journal, checks atomic rollback and preserves
old transfers as primary with no backup enabled.

`NativeImportBackupRegression` covers choosing before scan and after review,
clearing, stale changes, checked-row previews, primary renaming with original-name
backups, collision preservation, explicit resume, per-role receipts and final bytes.
Its options/ready/interrupted renders are offscreen layout evidence only.

```sh
.venv/bin/python -m pytest -q tests/test_import_backup.py tests/test_import_copy.py
.venv/bin/python tests/run_native.py --work work/new-backup-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeImportBackupRegression --suite NativeImportNamingRegression
.venv/bin/python tests/import_copy_probe.py --work work/new-backup-throughput \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon.NEF --files 24 --second-copy
```

Run throughput probes after tests/builds stop. With `--second-copy`, output bytes
and throughput count both complete copies; original count still denotes selected
sources. Both destinations are byte-checked, with independent catalog runs and
sampled broker RSS/concurrent control latency. Local generated folders on one
filesystem do not validate multiple physical drives, external-volume disconnects,
power loss, desktop input or cold disk performance.

## Copy filename templates

`test_import_naming.py` checks captured templates, Unicode, local EXIF clock tokens,
selected-only sequence and x-of-y counts, independent review sorting, missing
metadata, unsafe/overlong names, collisions before writes, XMP stem correspondence,
original-name duplicate identity, template revision conflicts/deletion, backup,
copy crash recovery and an atomic genuine schema-26 migration. A deterministic
SQLite VM-work bound covers different-name and same-name rank queries; cancellation
rolls back a bulk rank freeze before copying.

`NativeImportNamingRegression` uses real engine IPC to verify drafts, previews,
library refresh without stale-draft rebasing, preset deletion, plan conflicts,
saved names, final catalog original/destination identities and untouched bytes.
Its offscreen editor PNG is layout evidence only, not desktop acceptance.

```sh
.venv/bin/python -m pytest -q tests/test_import_naming.py tests/test_import_copy.py
.venv/bin/python tests/run_native.py --work work/new-naming-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeImportNamingRegression --suite NativeImportRegression
.venv/bin/python tests/import_naming_probe.py --work work/new-naming-scale
```

Run the scale probe after builds/tests stop. It stages 10,000 and 100,000 synthetic
SQL rows without photograph files. For first/middle/last sixty-item pages it records
first and five warm calls, serialized size and SQLite VM instructions, followed by
one cancellable rank freeze and sampled process peak RSS at 5 ms. The first call
uses a newly opened connection but OS caches remain warm from setup; no cold-disk,
broker IPC, pixels, real-photo accuracy or desktop latency is established.

## Native responsiveness

`test_preview_cache.py` uses real workers for completed Fit/detail/Before replies,
histograms and every auxiliary map. It checks restart/base-cache eviction,
render-option/engine/backend/source/asset keys, revision and cancellation races,
busy-worker bypass, corrupt/truncated/symlink/traversal rejection and genuine map
body reconstruction. Concurrent LRU touches and atomic file replacement must not
purge valid maps. A separate process proves the cache adapter imports no pixel
libraries. `preview_cache_hit` and `worker_spawned` distinguish lookup from image
processing; zero worker peak/work on a hit is not zero broker memory/CPU use.

`test_native_client.py` verifies bounded relay admission, reserved control
capacity, out-of-order correlation, malformed frames, duplicate IDs, EOF draining
and failure responses without mutation replay. `NativeTransportRegression`
exercises the Swift pipe client against an adversarial peer and the real broker,
including split UTF-8 responses, relay replacement and a deliberately lost
mutation response. Its warm-call timings exclude image processing and rendering.

`NativeResponsivenessRegression` subscribes to Store invalidations: unchanged
job, photo, reference and snapshot polls must publish zero changes, while real
catalog and snapshot changes still propagate.
It checks background image preparation, dimensions/color-space retention, main
actor progress, and unchanged recipes/originals. A heartbeat is evidence that
the actor can run during decoding, not a desktop frame-rate measurement.

```sh
.venv/bin/python -m pytest -q tests/test_native_client.py
.venv/bin/python tests/native_transport_probe.py --work work/new-native-transport \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine --samples 30
.venv/bin/python tests/run_native.py --work work/new-native-responsiveness \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeTransportRegression --suite NativeResponsivenessRegression \
  --suite NativeStateRegression --suite NativeConnectionRegression \
  --suite NativeThumbnailRegression --suite NativeReferenceRegression \
  --suite NativeSnapshotsRegression
```

For latency comparisons, run probes without competing tests/builds, use the same
packaged engine and an explicit fresh catalog, and separate first launch from
warm calls. Preserve unverified desktop scrolling/slider/keyboard interaction,
VoiceOver and macOS 14 acceptance in the evidence log.

## Develop Reference View

`test_color_readouts.py` covers analytic D50 neutrals, SDR endpoints, bounded binary
maps, eight orientations with crop/geometry, full-resolution viewports, proofing
isolation, Before cache reuse, real revision-bound workers and CPU/Metal values.
The fused readout checks cover all eight orientations on CPU and Metal, clipping
and Lab branch boundaries, the complete ordinary recipe test set, output-space
independence, one-dispatch grading, ROI/halo conversion, memory admission and C
buffer-layout changes. Injected GPU failures must return complete CPU reference
outputs with accurate counters, never a partially written readout map.
`NativeColorReadoutRegression` checks RGB/Lab switching, both Reference/Active
directions, mismatched cropped dimensions, Before assignment, settled off-viewport
samples and late cancellation. Its repeated pointer tests require zero Store
publications; repeated identical values must not republish the readout view either.

```sh
LUMARAW_REQUIRE_METAL=1 .venv/bin/python -m pytest -q tests/test_color_readouts.py
.venv/bin/python tests/run_native.py --work work/new-color-readouts-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeColorReadoutRegression --suite NativeResponsivenessRegression
.venv/bin/python tests/color_readout_probe.py --work work/new-color-readouts-raw \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon.NEF
```

The RAW readout probe compares ordinary/readout previews, first/warm map caches,
both color-map roles and CPU/Metal values through the persistent native relay.
Run without other builds/tests. Record actual execution counters, elapsed time,
dimensions and sampled worker peak RSS. Synthetic and real-RAW numerical agreement
does not establish Adobe color equivalence or rendered hover behavior.

For a processing optimization, retain both built engines and run this same probe
three times per engine in alternating old/new, new/old, old/new order, each with
a new catalog directory. Report median and range, both ordinary-preview controls
and first/warm maps. The first-map case has a warm decoded source and creates both
After and Before maps; it is not cold RAW decoding. Compare cached maps between
versions as well as CPU versus Metal. Keep builds and other tests stopped during
timing; native state checks may follow once measurement finishes.

`test_reference_preview.py` checks revision-bound ordinary previews, rejection
before and after worker execution, metadata-only changes, bounded geometry,
legacy reads, ICC-tagged output and preserved recipes/history/original bytes.
`NativeReferenceRegression` covers active-only edits, independent viewports,
reference frame reuse, lock and module transitions, crop confirmation, custom
drop validation, virtual copies, off-page references, removed-photo errors and
same-photo roles. A controlled late-reply transport proves cancellation and
revision receipt rejection separately from actual engine renders.

```sh
.venv/bin/python -m pytest -q tests/test_reference_preview.py tests/test_review.py
.venv/bin/python tests/run_native.py --work work/new-reference-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeReferenceRegression --suite NativeReviewRegression \
  --suite NativeComparisonLayoutRegression --suite NativeBeforeAfterRegression
.venv/bin/python tests/reference_probe.py --work work/new-reference-raw \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon.NEF
```

Native state probes do not establish actual drag/drop, keyboard dispatch, alert
presentation, rendered overlay alignment, VoiceOver or macOS 14 runtime behavior.
Keep those explicit acceptance gaps. Readout numerical/reference acceptance, HDR
readouts and expanded zoom tools remain part of the full parity scope.

Run the RAW probe with other builds/tests stopped. It includes packaged CLI/IPC,
captured ordinary-preview revisions and sequential CPU/Metal workers for two
variants of one physical source. Empty application caches do not imply cold OS
or GPU caches. Record per-case dimensions, wall time, actual Metal dispatch and
sampled worker RSS; compare CPU/Metal pixels without inferring camera accuracy.
Unchanged reference frames are retained by native state instead of submitting
these repeated probe requests during ordinary active-photo edits.

## Shared named snapshots

`test_snapshot_status.py` covers shared first/last presence, live all/any and
nested smart collections, folder/Previous Import/search scope, bounded pages,
recipe-free indexed SQL, boolean validation, rollback, bulk removal and source
reassignment, genuine schema-24 upgrade failure/retry and restored triggers.
`NativeSnapshotFilterRegression` checks the Any/Have/No form mapping, empty-page
polling, live smart/set membership, deferred refresh while editing or naming a
snapshot, preserved source navigation, stale tokens and original bytes.

```sh
.venv/bin/python -m pytest -q tests/test_snapshot_status.py
.venv/bin/python tests/run_native.py --work work/new-snapshot-filter-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeSnapshotFilterRegression --suite NativeSnapshotsRegression \
  --suite NativeLibraryRegression --suite NativeCollectionRegression
.venv/bin/python tests/snapshot_filter_probe.py --work work/new-status-1k --rows 1000
.venv/bin/python tests/snapshot_filter_probe.py --work work/new-status-100k --rows 100000
```

Run the status probes sequentially with other tests/builds stopped. One fifth of
synthetic source families have snapshots. They measure warm service SQL counts
and pages, deep paging, smart/rating combinations and compact state polling with
minimal recipes. Setup, IPC, pixels and UI are excluded; record JSON bytes and
RSS. Rendered filter forms and macOS 14 runtime remain separate acceptance work.
Query-shape regressions compare dense and indexed pages in both directions,
deep offsets and all/any smart rules. Sparse results, other sorts and actual
stack projection retain indexed membership. The probe includes dense default
stack visibility without groups, sparse presence and no matches; do not infer
universal latency from one selectivity or image distribution.

`test_snapshots.py` covers current/history capture, original/copy sharing,
rename/update/delete/restore and copy-to-Before, photo/snapshot conflicts, name
normalization, no-op counters, preserved legacy commands, alphabetical keysets,
compact conditional refresh, recipe-free SQL reads, rollback, non-reused IDs and
genuine schema-23 migration failure/retry with legacy duplicates. Snapshot-only
LUT backup restores payloads, revisions, name keys and identity counters.

`NativeSnapshotsRegression` checks captured forms/actions, explicit conflict
refresh, shared copy state, frozen Before, history capture without selection,
bounded alphabetical pages, conditional polling, pending-edit barriers and
original bytes through real Store/IPC calls. It does not establish native event
routing, rendered sheets/context menus, VoiceOver or macOS 14 runtime behavior.

```sh
.venv/bin/python -m pytest -q tests/test_snapshots.py
.venv/bin/python tests/run_native.py --work work/new-snapshots-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeSnapshotsRegression --suite NativeVirtualCopyRegression \
  --suite NativeHistoryRegression --suite NativeBeforeAfterRegression
.venv/bin/python tests/snapshot_probe.py --work work/new-snapshots-1k --rows 1000
.venv/bin/python tests/snapshot_probe.py --work work/new-snapshots-100k --rows 100000
```

Run catalog probes sequentially after other checks stop. They measure warm
in-process service reads/writes with connection/validation/commit costs included.
Synthetic setup, broker IPC, image work and native interaction are excluded.
Record page/unchanged bytes and peak process RSS; no preview or RAW throughput
claim follows from catalog timings.

## Persistent Before / After

`test_before_after.py` checks full-recipe copy/swap, history assignment without
cursor movement, retained redo, clear/branch/restart isolation, virtual-copy
initialization, import presets, stale/invalid actions, transactional rollback,
Before-only LUT restoration and genuine schema-22 migration failure/retry.
Generated pixels check effective geometry and all eight orientations at 1:1,
independent cache hits/invalidation, corrupt PNG repair, omitted Before work and
source replacement rejection. Real workers verify stored baseline pixels/labels.

`NativeBeforeAfterRegression` checks actual Store/IPC state, on-demand loading,
unchanged-view reuse, split/detail transitions, full-recipe actions, captured
history/selection guards, pending edits, stale writes and read-only originals.
It does not establish rendered controls, actual pointer/key events or VoiceOver.

```sh
.venv/bin/python -m pytest -q tests/test_before_after.py
.venv/bin/python tests/run_native.py --work work/new-before-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeBeforeAfterRegression
.venv/bin/python tests/before_after_probe.py --work work/new-before-nef \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon.NEF
```

Run the RAW probe after builds/tests finish. Separate CPU/Metal caches and
sequential workers cover empty-cache fit, two warm fits, After light/geometry
changes, cold/warm 1280×900 detail and After-only requests. Preserve each image
before reusing paths, record actual Metal dispatch, stage times, 20 ms sampled RSS
and unchanged original hashes. Both sides retain a maximum one-code 8-bit CPU/
Metal difference; After-only pixels must equal the matching comparison request.
Wall times include worker launch and encoding, not desktop latency. Empty app
caches do not imply cold OS/GPU caches. Single-fixture results are not a camera
accuracy or Lightroom processing claim.

`NativeComparisonLayoutRegression` uses generated 2400×1800 originals and actual
worker replies. It checks equal whole-image panes, aspect-preserving fit,
image-relative split boundaries, physical Retina scale, reuse on fitted layout
changes, all four layouts at 1:1, bounded resizing, shared ROI panning, edge
clamping, invalid values and stale layout/photo/viewport events. Shortcut routing
is exercised through Store, not actual keyboard dispatch. View changes must leave
the photo revision, Develop history and original bytes unchanged.

```sh
.venv/bin/python tests/run_native.py --work work/new-comparison-layouts \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeComparisonLayoutRegression --suite NativeBeforeAfterRegression \
  --suite NativeReviewRegression --suite NativeCurveTargetRegression \
  --suite NativeMixerTargetRegression --suite NativeStateRegression
```

Compilation and these geometry/state tests do not verify rendered desktop pane
layout, actual mouse/key input, VoiceOver or behavior on macOS 14.

## Eight-band color and black-and-white mixer

`test_color_mixer.py` uses a synthetic Oklab color ring to test every band's hue,
saturation, luminance and B&W direction, neutral protection, hue wrapping,
negative/HDR finiteness and input immutability. A frozen four-band output fixture
checks pre-expansion CPU pixels independently of the new implementation. Other
cases cover old stored JSON defaults, selective/all-group sync, atomic conflicts,
undo, all preset fields, frozen exports, portable recipes and catalog backup.

`test_metal.py` exercises the new HSL and B&W recipes in all four output spaces on
real Metal. It also bounds decoded-linear error; the explicit near-black Adobe
RGB encoding allowance is documented in `METAL.md`. Synthetic fixtures establish
numerical behavior, not photographic or Adobe calibration.

`NativeColorMixerRegression` compiles the actual SwiftUI controls and exercises
Store/IPC unit conversion, coalesced edits, component/color/panel resets, treatment
retention, undo, invalid inputs, selective sync, full-preset creation and stale
edits. It does not verify rendered controls, gestures, layout or VoiceOver.

```sh
.venv/bin/python tests/run_native.py --work work/native-color-mixer-01 \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeColorMixerRegression
.venv/bin/python tests/acceleration_probe.py --preset mixer \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon.NEF --work work/color-mixer-nef-01
.venv/bin/python tests/acceleration_probe.py --preset bw_mixer \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon.NEF --work work/bw-mixer-nef-01
```

Run those RAW probes sequentially without concurrent builds/tests. Each compares
CPU and Metal cold/warm fitted previews, a full-size ProPhoto 16-bit TIFF and a
1280×900 detail viewport, with stage times, sampled RSS, actual dispatch and source
hashes. Retain the one/eight-code preview/TIFF parity limits. Reference acceptance
still needs Lightroom fixtures, desktop interaction and the minimum supported OS.

## RGB and channel point curves

`test_point_curves.py` compares the float32 evaluator to an independent SciPy
PCHIP calculation, checks endpoint movement, inversion, segment bounds, identity
negative/HDR preservation, untouched channels, and frozen legacy CPU pixels.
Service coverage includes old JSON, presets, selective sync, conflicts, undo,
portable recipes, backup, frozen jobs and real temporary-preview pixels without
recipe/history mutation or cache contamination. Metal cases cover all four spaces,
ordinary fused curves, sharp-curve hybrid fallback and Python/C ABI size guards.

`NativePointCurveRegression` compiles the controls and exercises Store/IPC units,
engine preset loading, insertion/movement/deletion bounds, captured gestures,
temporary previews, one-step saves, cancellation state, resets, undo, stale writes,
photo switching and sync. Native plot samples are compared with engine-generated
fixtures, including narrow segments. This does not dispatch real pointer/key or
VoiceOver events and does not verify rendered desktop layout.

```sh
.venv/bin/python tests/run_native.py --work work/native-point-curves-01 \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativePointCurveRegression
.venv/bin/python tests/acceleration_probe.py --preset point_curves \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon.NEF --work work/point-curves-nef-01
```

Run the RAW probe without concurrent builds/tests; its limits and timing scope
match the mixer probe above. Steep curves are tested separately because this probe
requires actual fused grading. Adobe pixel equivalence, rendered interaction and
macOS 14 runtime remain separate acceptance work.

## Four-region parametric curves

`test_parametric.py` tests every region's sign and support, known center outputs,
all sixteen extreme amount combinations with ordinary and one-percent-wide
regions, monotonicity, smooth joins and bounded derivatives. It verifies exact
identity/unused-region pixels, color-ratio preservation, unchanged black/white and
out-of-SDR luminance, strip/viewport identity with point curves, old JSON, full
presets, partial sync, atomic conflicts, undo, bundles/backups, frozen jobs and
temporary-preview restoration. Required Metal tests combine parametric, point and
HSL curves in all four spaces. Gamut-marker boundary uncertainty is stated in
`METAL.md`; encoded and decoded color tolerances remain unchanged.

`NativeParametricCurveRegression` checks drawing geometry against engine fixtures,
region selection and split bounds, draft-only previews, one pending request behind
an in-flight image, latest-draft coalescing, cancellation, one-step saves, reset
independence, undo, revision conflicts, selection/pending-edit barriers and sync.
Rerun `NativePointCurveRegression` after changing their shared scheduler. These are
Store/IPC tests; real slider, pointer, keyboard, focus and VoiceOver acceptance
still require a rendered desktop session.

```sh
.venv/bin/python tests/run_native.py --work work/native-parametric-01 \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeParametricCurveRegression --suite NativePointCurveRegression
.venv/bin/python tests/acceleration_probe.py --preset parametric \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon.NEF --work work/parametric-nef-01
```

This RAW preset exercises all four regions with moved splits, all RGB point
curves, legacy tone and color controls. Run it alone after builds and regressions,
retaining the same dimensions, cache states, peak RSS and CPU/Metal parity limits
as the other acceleration probes. It measures workers, not desktop drag latency.

## Reference RAW fixture

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
24-assertion folder-synchronization, 16-assertion export-metadata, and
21-assertion photo-keyword-detail, 24-assertion complete-vocabulary and 23-assertion
dictionary-exchange suites, plus the keyword-set and Painter suites described below.
Each suite has its own
fresh image directory, so a relink test cannot move another suite's fixture. The library suite checks
live smart membership, text search/sort, pagination, empty-filter selection,
partial metadata writes and independent recipe/metadata conflict handling. JSON
receipts stay in the ignored work directory. Without `--engine`, it uses the
current Python environment's `lumaraw` executable.
Every suite sets an isolated `LUMARAW_PRESETS_ROOT` as well as its catalog path.
When using the standalone harness outside this runner, set this override too;
the keyword sidebar initializes shared preset storage on first use.
The folder suite adds 64 copies of its own generated fixture to test locating a
photo beyond the first page; it never copies a personal photograph.

The keyword suite checks lazy hierarchy/pages, Grid/active-photo scope, mixed selection,
captured create-and-assign targets, stale revisions, parent filters, ancestor
rename, synonym lookup, external updates and empty-page polling. It exercises the
real native Store and IPC without automating the rendered desktop.

`test_keyword_sets.py` covers shared/cross-catalog and local storage, persistence,
rename/delete, transient application, nine-slot recency with legacy IDs, all-target
and capacity rollback, concurrent writers, bounded large-preset pages, genuine
v12 migration rollback, catalog backup and newer shared-schema refusal. Path
adapter checks mock Windows/XDG locations; they do not verify either OS runtime.
`NativeKeywordSetRegression` exercises native state over real IPC, including
Grid/active-photo application, saved versus draft slots, scope switching, stale
draft/editor protection, recent-to-preset creation and paged selection. Rendered
forms, Option-number dispatch, typing interference and VoiceOver remain unverified.

```sh
.venv/bin/python tests/run_native.py --work work/native-keyword-sets-01 --suite NativeKeywordSetRegression
.venv/bin/python tests/keyword_sets_probe.py --work work/keyword-sets-10k --tags 10000 --sets 1000 --samples 30
.venv/bin/python tests/keyword_sets_probe.py --work work/keyword-sets-100k --tags 100000 --sets 10000 --samples 30
```

The set probe uses sixty generated 8×8 photos and isolated preset storage. It
measures warm service/SQL reads and repeat application of an already assigned tag,
including state and photo-revision reads. Setup, IPC, pixels and desktop latency
are excluded; peak process RSS and zero worker usage are recorded separately.

`test_library_painter.py` validates shortcut configuration, identity-preserving
legacy rename/delete, bounded maximum paths, revision-bound reads, all-target and
capacity rollback, injected SQL abort, ratings/flags/labels and explicit clearing,
unchanged recipes/originals/frozen jobs, and genuine v13 migration/backup.
`NativePainterRegression` checks native shortcut/editor state, touched-ID dedup,
mouse-up submission boundaries, cancellation/source changes, deferred cancellation
identity, preserved selection, immediate culling readback and stale batch failure.
One thousand repeated hits produce no redundant highlight publications.
Its segment/rectangle tests cover coalesced drag geometry, stationary clicks and
misses. They do not dispatch desktop events or verify rendered pointer placement.

```sh
.venv/bin/python tests/run_native.py --work work/native-painter-01 --suite NativePainterRegression
.venv/bin/python tests/painter_probe.py --work work/painter-10k --rows 10000 --samples 30
.venv/bin/python tests/painter_probe.py --work work/painter-100k --rows 100000 --samples 30
```

The Painter probe seeds equal photo/tag counts, sixty generated 8×8 originals and
synthetic remaining photo rows. Warm measurements include state and target-revision
reads. Two-/hundred-keyword strokes measure initial add, already-assigned reapply,
and a two-transaction erase/add cycle; rating uses one sixty-photo transaction.
No pixel worker is started. Setup, IPC, desktop dispatch and rendered latency are
excluded. Unlocked-desktop mouse/keyboard/VoiceOver and macOS 14 runtime acceptance
remain required independently of these state, geometry and service measurements.

The vocabulary suite exercises maximal Unicode paths and synonyms through real
IPC, complete editor/parent initialization, preserved export options, sixty-row
parent paging, and stale, wrong, superseded or dismissed detail responses.
test_keyword_vocabulary.py covers full reads for 67 maximal child rows, synonym
search, selected counts, safe rename/delete, legacy parent names and unchanged
originals. The standalone probe isolates warm service/SQL work with a large
synthetic dictionary; it does not measure IPC, pixels or rendered responsiveness:

```sh
.venv/bin/python tests/keyword_vocabulary_probe.py --work work/keyword-vocabulary-10k --tags 10000 --samples 30
.venv/bin/python tests/keyword_vocabulary_probe.py --work work/keyword-vocabulary-100k --tags 100000 --samples 30
```

`test_keyword_exchange.py` checks additive text/CSV import, unchanged existing
options/synonyms/assignments and frozen jobs, full option round trips, malformed
input and transaction rollback, real v11 migration and backup/restore, collision
and symlink safety, source/destination I/O outside the catalog lock, and compact
real-broker receipts. Generated format fixtures establish internal behavior, not
an Adobe-produced/imported-file acceptance claim. Native exchange checks use
real files and IPC; native file panels and rendered interactions are unverified.

```sh
.venv/bin/python tests/keyword_exchange_probe.py --work work/keyword-exchange-10k --tags 10000
.venv/bin/python tests/keyword_exchange_probe.py --work work/keyword-exchange-100k --tags 100000
```

The probe separates disk-backed parsing and initial SQL transaction time, then
measures repeated imports and text/CSV exports. Files are freshly generated and
warm in the OS cache; the initial catalog is new. It uses no photos or image
workers and does not measure network volumes or desktop responsiveness.

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

`test_folder_sync_duplicates.py` adds catalog and within-plan suspected duplicates,
precise/unknown clocks, original-name identity, selection/inclusion gates, final
transaction conflict rejection and unchanged import provenance. Genuine schema-36
plans exercise additive migration and legacy-plan behavior instead of relabeling
current tables as old. Use the existing sync suites for removal, metadata refresh,
cancel/recovery and source-file preservation alongside these checks.

```sh
.venv/bin/python -m pytest -q tests/test_folder_sync_duplicates.py \
  tests/test_folder_sync.py tests/test_folder_sync_metadata.py \
  tests/test_import_sequence.py tests/test_import_review.py tests/test_xmp_read.py
.venv/bin/python tests/run_native.py --work work/new-folder-sync-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeFolderSyncRegression --suite NativeImportSequenceRegression \
  --suite NativePreviousImportRegression --suite NativeResponsivenessRegression
```

The native sync fixture contains a same-name/size/capture-time JPEG pair in
different folders. It checks default exclusion, explicit inclusion, preserved
selection, the new-photo gate and stale readback without retry. Its sheet snapshot
is offscreen evidence; it does not exercise desktop input or VoiceOver.

`test_folder_sync_apply.py` checks mixed selected/unselected state updates,
unchanged-photo availability recovery after indexing, full source/file conflict
guards, and bounded apply candidates over a large synthetic plan. Changes-page
query plans must use the partial index without sorting the whole plan.

Run the apply-only probe separately from checks/builds, before and after changing
the transaction. It seeds real SQLite catalog/staging rows with absent image paths,
simulates completed observations, and calls the actual domain transaction. It
deliberately excludes filesystem scanning/revalidation, IPC and image processing.
Each case measures one first and five warm applications of new plans; seeding and
plan preparation are outside the timer. Process-wide peak RSS includes setup and
earlier trials. Pair it with the existing sync probe for the broader scan/apply
path using synthetic missing originals and empty discovered files.

```sh
.venv/bin/python tests/folder_sync_apply_probe.py --work work/new-sync-apply-scale \
  --rows 10000 100000
.venv/bin/python tests/folder_sync_probe.py --work work/new-sync-mixed-scale \
  --rows 100000
```

The sync metadata detail checks exercise complete long descriptions, twenty-path
paging, wrong-item/plan/revision rejection and full application. The two
`test_folder_sync_metadata.py` cases reproduce 60 long Unicode descriptions through
a real broker and page 100 maximal 32-level keyword paths. Responses stay bounded
without truncating staged values; changed plans cannot silently replace a detail
view's captured revision.

The export-metadata native suite covers keyword flags, read-only preview paging
and revisions, metadata choices, immutable submitted receipts and an actual JPEG
containing the submitted keywords after later catalog edits. `test_keyword_exports.py`
adds genuine v10 migration/rollback, intermediate ancestor policy boundaries,
batch XML failure rollback, backup/restore and a snapshot larger than 256 KiB
through a real worker. `test_export_metadata.py` verifies JPEG Extended XMP
reassembly/checksums and TIFF tag 700, Unicode text, malformed/bounded payloads,
unchanged source hashes and identical decoded pixels/ICC with and without metadata.
These are format and application contracts; current Lightroom checkbox combinations
and full metadata round trips still require reference-app acceptance.

```sh
.venv/bin/python tests/export_metadata_probe.py --work work/export-metadata-10k --rows 10000 --samples 30
.venv/bin/python tests/export_metadata_probe.py --work work/export-metadata-100k --rows 100000 --samples 30
```

This warm metadata-only probe measures preview pages and frozen export submission
against synthetic catalogs with 1,010 tags and two assignments per photo. It
samples 60- and 1,000-photo submissions five times, previews/queue pages 30 times,
and checks compact public receipts, snapshot storage and RSS. Jobs stay paused;
there are no image workers, actual photographs, IPC or rendered UI measurements.

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
and two already-frozen exports. Exported XMP must retain each variant's submitted
title and keywords/synonyms while excluding a private ancestor. It checks full-size JPEG/16-bit TIFF, ICC tags,
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

`test_keyword_details.py` sends maximal Unicode hierarchy data through a real
broker, then checks paged reads, compact recipe/rating/metadata replies, ID-based
replacement, new typed paths, independent copies and actual JPEG export. Invalid
identities, ambiguous additions, overlarge combined sets and stale revisions roll
back without leaking new tags. The native keyword-detail suite covers all five
pages, captured revisions, local selection drafts, batch forms, ID receipts and
preserved recipe revisions; it does not inspect rendered controls.

```sh
.venv/bin/python tests/keyword_details_probe.py --work work/keyword-details-10k --rows 10000 --samples 30
.venv/bin/python tests/keyword_details_probe.py --work work/keyword-details-100k --rows 100000 --samples 30
```

The synthetic catalog has 1,141 tags. Ordinary photos start with two assignments;
one photo has 100 maximal 32-level Unicode paths. Warm reads use 30 samples and
60-photo identity replacements use five samples, including their revision read.
The probe records response bytes and RSS, without photographs, image workers,
IPC or rendered UI. Absolute path lengths can slightly change response byte counts.

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
views against a real engine. Expanded badges use full-stack ordinals through
reordering, splitting and filtering. Two offscreen renders cover collapsed count
and expanded ordinal presentation; desktop key/pointer routing is not verified.

`tests/test_stack_ordinals.py` covers negative/sparse positions, filtering and
paging, source scopes and membership changes. Rank work is checked with SQLite
VM steps, not a fragile elapsed-time assertion. The scale probe compares full
60-row pages with isolated ordinal annotation for 10,000 and 100,000-member stacks,
including first/middle/last pages and sparse matches. It reports first/warm times,
VM steps, reply bytes and RSS sampled every 5 ms. Deep pages may count a large
prefix once; no constant-time rank claim is made.

```sh
.venv/bin/python -m pytest -q tests/test_stack_ordinals.py tests/test_stacks.py tests/test_auto_stacks.py
.venv/bin/python tests/stack_ordinals_probe.py --work work/new-stack-ordinals-scale --rows 10000 100000
```

The scale probe uses a fresh SQL connection after seeding with warm OS caches.
It times no photographs, image processing, broker IPC or desktop rendering.
Run without competing tests or builds; the full page timing excludes total-count
queries. Isolated annotation timing excludes page retrieval.

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

## Painter keyword-set chooser

`NativePainterKeywordPickerRegression` uses the real engine to exercise multi-set
accumulation, select-all deduplication/capacity, cancellation, recent identities,
stale preset previews and one shortcut confirmation without tagging photos.
`test_keyword_sets.py` additionally checks legacy literal labels, missing presets,
scope/vocabulary/recent revision changes and bounded preview-name pages. Run with:

```sh
.venv/bin/python tests/run_native.py --work work/new-painter-picker-check --suite NativePainterKeywordPickerRegression
```

These are state/IPC checks. Shift dispatch, focus after enabling Painter, the
rendered dialog, native accessibility and macOS 14 runtime need desktop acceptance.
The picker extension in `tests/keyword_sets_probe.py` measures previewing other
sets without changing the active preset; setup, IPC, images and UI are excluded.

## Target Collection Painter

`test_target_painter.py` verifies repeated add without toggle, removal, captured
target/collection conflicts, all-or-nothing SQL failure, ancestor revisions, stack
cleanup, virtual copies and preserved metadata/recipes/jobs/originals. Its existence
check regression forbids full photo-detail reads. `NativeTargetPainterRegression`
uses real IPC to verify mouse-down/mouse-up state boundaries, touched-ID dedup,
cancellation, target changes during a stroke and empty displayed-target refresh.

```sh
.venv/bin/python tests/run_native.py --work work/new-target-painter-check --suite NativeTargetPainterRegression
.venv/bin/python tests/target_painter_probe.py --work work/new-target-painter-probe --rows 100000
```

The performance fixture gives sixty generated 8×8 targets one hundred Unicode
keyword paths each at depth 32. The rest of the catalog is synthetic. Timings
include captured target-state reads and transaction commits, excluding setup,
IPC, pixels and desktop presentation. Compare the same fixture before/after edits;
do not turn machine timing into an assertion. Rendered Option-pointer dispatch and
macOS 14 runtime remain separate acceptance requirements.

## Independent photo orientation

`test_orientation.py` verifies all eight orthogonal states, action composition,
CPU/required-Metal strip and ROI equivalence with masks/crops/lens geometry, portrait
and landscape ratios, Reset/Develop undo independence, original bytes, virtual
copies, bounded batch undo, stale targets, injected SQL rollback, genuine schema-14
migration failure/retry, backup/restore, cache keys and queued export snapshots.
Asymmetric generated pixels establish orientation behavior, not Adobe processing.

`NativeOrientationRegression` checks real IPC, Grid versus active-photo scope,
busy/pending-edit guards, captured Painter actions, cancellation, stale batch/undo
failure, preview geometry and all eight coordinate mappings. These are native
state checks, not desktop pointer/shortcut/accessibility acceptance.

```sh
LUMARAW_REQUIRE_METAL=1 .venv/bin/python -m pytest -q tests/test_orientation.py
.venv/bin/python tests/run_native.py --work work/new-orientation-native --suite NativeOrientationRegression
.venv/bin/python tests/orientation_probe.py --engine /path/to/LumaRAWEngine --fixture /path/to/chart.NEF --work work/new-orientation-probe
```

The packaged-worker probe alternates identity/clockwise orientation sequentially
after a priming export. It compares full-size 16-bit TIFFs for neutral and masked
recipes, records real Metal dispatch, includes startup/encoding in elapsed time
and samples worker RSS every 20 ms. Priming timings are excluded from warm medians;
an application-cache warmup does not establish cold OS/disk/GPU behavior. Use an
explicit read-only RAW and new output directory. Do not run benchmarks alongside
other tests/builds. macOS 14 runtime and Lightroom Mac reference remain separate.

## Develop presets

`test_develop_presets.py` covers partial fields/no-op/history, group/favorite/name
policies, shared/catalog-local scope, genuine schema-15 rollback/retry, captured
revisions, all-target and injected SQL rollback, bounded pages without full photo
materialization, camera compatibility and LUT backup/restore. Asset tests change
source/target/storage between validation passes, prove catalog reads remain
available while staging, and reject corrupt source/destination or symlink assets
without overwriting files or editing any target.

`NativeDevelopPresetRegression` checks real IPC and immutable editor/Painter
captures, Grid/active scope, busy and pending-edit guards, no-op reapply, mouse-up
state submission, cancellation, stale batch rejection, filters and storage. Its
state-driven gestures do not establish actual pointer/keyboard dispatch or rendered
desktop, VoiceOver, Lightroom reference or macOS 14 runtime acceptance.

```sh
.venv/bin/python -m pytest -q tests/test_develop_presets.py
.venv/bin/python tests/run_native.py --work work/new-develop-preset-native --suite NativeDevelopPresetRegression
.venv/bin/python tests/develop_preset_probe.py --work work/new-develop-preset-probe --photos 100000 --presets 10000 --samples 30
```

The probe uses sixty generated 8×8 originals, one hundred depth-32 Unicode keyword
assignments per target and synthetic catalog/preset rows. It measures bounded
first/last/search pages, one changed application, equal reapplication and two
alternating changed applications; capture reads are included. It verifies bounded
history, unchanged metadata/originals and zero image workers. Setup, IPC, LUT I/O,
preview rendering and UI latency are excluded. Run after builds/tests finish.

## Metadata presets and IPTC

`test_metadata_presets.py` checks selective clearing/omission, additive keywords,
metadata and independent rating conflicts, no-op writes, Unicode names, paging,
shared/catalog scope, backup/restore and genuine schema-17 migration rollback.
`test_iptc.py` uses independent namespace/contact fixtures, empty values, ISO date
precision, extended JPEG packets, sidecar precedence, copy independence and frozen
export policies. Merged-size and injected SQL failures must roll back every target
and new keyword. Schema-16 upgrades preserve existing recipes and orientation.
`test_folder_sync_metadata.py` covers worst-case escaped IPTC plus one hundred
depth-32 keyword paths, respecting the broker frame while preserving every value.

`NativeMetadataPresetRegression` drives real IPC through forms, captured selections,
Grid/Loupe scope, no-op application, Painter cancellation and consecutive strokes.
It verifies acknowledged vocabulary changes can advance only the same loaded
preset, stale drafts/strokes fail, metadata refresh preserves pending Develop
edits, and ordinary IPTC partial receipts preserve unrelated values. It does not
verify rendered controls, actual pointer/shortcut dispatch or accessibility.

```sh
.venv/bin/python -m pytest -q tests/test_metadata_presets.py tests/test_iptc.py tests/test_folder_sync_metadata.py
.venv/bin/python tests/run_native.py --work work/new-metadata-preset-native --suite NativeMetadataPresetRegression
.venv/bin/python tests/metadata_preset_probe.py --work work/new-metadata-preset-probe --photos 100000 --presets 10000 --samples 30
```

Run the probe after builds/tests finish. Sixty generated 8×8 originals carry
60,090 bytes of descriptive IPTC and ninety-nine depth-32 Unicode tags before
application adds one tag. It measures bounded preset pages, first/equal application
and alternating changes to sixty photos. Capture reads are included; setup, IPC,
pixels and desktop latency are excluded. Repeated identical IPTC is validated once
per batch through a bounded exact-value cache; distinct per-photo values still
receive individual validation. Originals, recipes, history and orientation are
asserted unchanged. Timings are observations, not hardware-specific test gates.

## Reviewed Add imports

`test_import_review.py` covers checked-only atomic imports, original-name/precise
capture duplicate classification, unknown dates, include-subfolder/overlapping
sources, XMP descriptions, source/sidecar/directory/catalog changes, late duplicate
conflicts, injected SQL rollback, cancellation during I/O and bulk SQL, maintenance
flag/count/root restoration, and previews rejecting changed originals before work.
It checks 601-entry directory restart/replay without duplicates, compact pages,
active-catalog cache exclusion, persistent checks, backup/restore and genuine
schema-18 migration failure/retry. Source files remain byte-identical.

`NativeImportRegression` checks real IPC and file-backed previews before catalog
import, per-item/filter check scope, stale option conflicts, immutable completed
receipts, closing/reopening a pending review, cancellation and coalesced Finder
sources. The suite uses five generated 160×100 raster files. It is native state
evidence; rendered sheets, pointer/keyboard dispatch, VoiceOver, macOS 14 and
Lightroom Mac reference acceptance remain separate.

```sh
.venv/bin/python -m pytest -q tests/test_import_review.py
.venv/bin/python tests/run_native.py --work work/new-import-native --suite NativeImportRegression
.venv/bin/python tests/import_review_probe.py --work work/new-import-probe --photos 100000 --candidates 100000 --samples 30
```

Run the probe with no concurrent tests/builds. It seeds a synthetic existing catalog
and candidate review, scans sixty generated 8×8 PNG originals once, samples bounded
first/last/checked/capture/type pages thirty times, and applies those sixty real
files once. A separate one-sample bulk transaction inserts the candidate count
from explicitly synthetic, already-verified rows, excluding filesystem checks.
The latter isolates SQL lock duration and is not end-to-end import throughput.
Report warm-cache timings, sample counts, RSS, response bytes and zero image
workers. Setup, RAW/JPEG decoding, IPC and desktop latency are excluded. Assert
original hashes, photo totals, folder counts and maintenance state after apply.

## Apply During Import

`test_import_processing.py` checks captured Develop/metadata presets, independent
None/omission/keyword clearing, file/preset keyword unions, preset deletion after
capture, stale plan/library tokens, exact root/leaf identity, ambiguous keyword
rejection, vocabulary edits between preset capture and plan persistence,
additional-text limits, camera revalidation after check changes, merged
capacity and SQL rollback, LUT staging conflicts/corruption, backup rebinding and
genuine schema-19 upgrade rollback/retry. Large metadata stays out of wire replies.
A generated gray PNG goes through real image workers to verify a chosen Develop
exposure changes the import thumbnail before a catalog photo exists; clearing the
choice reuses the original thumbnail. This is algorithm evidence, not Adobe pixels.

`NativeImportProcessingRegression` uses real IPC and five generated originals to
exercise paged preset choices, New/None, unsaved keyword drafts, explicit saves,
captured revision conflicts, close/reopen, preset deletion, preview identity and
the applied photo values. It does not drive the desktop or establish macOS 14,
VoiceOver, actual keyboard dispatch or Lightroom reference acceptance.

```sh
.venv/bin/python -m pytest -q tests/test_import_processing.py
.venv/bin/python tests/run_native.py --work work/new-import-processing-native --suite NativeImportProcessingRegression
.venv/bin/python tests/import_review_probe.py --work work/new-import-processing-probe --photos 100000 --candidates 10000 --processing
```

The optional probe mode captures exposure/contrast and a metadata preset containing
31,560 UTF-8 bytes of descriptive IPTC, title/rating and three keyword paths. It
measures the same bounded pages and sixty real-file application as the Add probe,
then seeds a separate synthetic bulk transaction with those settings. All changed
recipes, photo/keyword totals, folder counts, maintenance state and original hashes
are asserted. Warm pages use thirty samples; scan and both applications use one.
No decoding, IPC or UI timings are included; synthetic bulk additionally excludes
source verification. Run after tests/builds finish and report RSS and wire sizes.

## Previous Import

`test_previous_import.py` verifies reviewed/direct/folder-sync membership,
checked scope, no-op/cancel/failure preservation, late transaction rollback,
source-family copies/promotion/relinking, deletion cleanup, backup/restart,
bounded filters/pages, source exclusivity, genuine schema-20 migration and legacy
incremental import cancellation/failure. Legacy migration fixtures seed the old
photo schema directly rather than calling the current importer on an old schema.

`NativePreviousImportRegression` uses real IPC to verify automatic focus, persisted
preferences, retained folder/filter state when disabled, pending-edit saving,
selection clearing and external changes from populated/empty sources. It also
checks folder synchronization uses the same preference without repeated focus.
It does not drive the desktop or verify macOS 14 runtime and VoiceOver behavior.

```sh
.venv/bin/python -m pytest -q tests/test_previous_import.py
.venv/bin/python tests/run_native.py --work work/new-previous-import-native --suite NativePreviousImportRegression
.venv/bin/python tests/previous_import_probe.py --work work/new-previous-import-probe --photos 100000 --batch 10000
```

The performance probe creates synthetic catalog rows and replaces membership in
one transaction. Repeated page/sort/filter/state queries use thirty warm samples;
replacement uses one sample. Report median/p95, RSS, response size and indexed
query plan. It excludes setup, file verification, decoding, IPC and desktop timing.

## Photograph-targeted parametric curves

`test_curve_targeting.py` verifies all eight catalog orientations, recipe rotation,
crop/aspect/straighten/perspective/lens geometry, detail ROIs, upstream invalidation,
downstream cache reuse, bounded binary maps and read-only real-worker drafts.
`NativeCurveTargetRegression` checks binary parsing, fitted/Retina coordinate
rectangles, temporary edits, one revision per release, cancellation, keyboard state,
stale zoom/pan, before/split guards, external conflicts and photo changes via IPC.
These checks do not drive actual pointer/keyboard dispatch or the desktop.

```sh
.venv/bin/python -m pytest -q tests/test_curve_targeting.py
.venv/bin/python tests/run_native.py --work work/new-target-native --suite NativeCurveTargetRegression
.venv/bin/python tests/acceleration_probe.py --preset parametric --curve-tones \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon.NEF --work work/new-target-nef
```

The optional map probe omits before images, as interactive drafts do. It asserts
identical CPU/Metal map bytes, matching dimensions, first-capture and warm-reuse
receipts, and absence of capture work on warm runs. Record map sizes, per-stage
time, wall time and RSS. Run sequentially with no tests/builds in progress. Worker
timing excludes broker IPC, pointer dispatch and display; it is not drag latency.

## Photograph-targeted HSL and Black & White Mix

`test_mixer_targeting.py` checks dense-reference versus sparse supports around the
entire color circle, three-way overlaps, neutral protection, directional changes,
pre-HSL/pre-B&W ordering, all orientations, crop/detail geometry, cache boundaries
and real-worker draft contracts. For whole-frame versus strip comparisons, the
float32 color-transform error must produce less than 0.01 display-control units
over a 200-unit gesture. Map transport itself preserves exact float32 bits.
`NativeMixerTargetRegression` verifies malformed maps, neighboring-band edits,
stored hue units, previews, one-step history, cancellation, treatment changes,
undo, zoom/pan, conflicts, selection changes and mutual exclusion with curve tools.
These are domain/native-state checks, not rendered desktop acceptance.

```sh
.venv/bin/python -m pytest -q tests/test_mixer_targeting.py
.venv/bin/python tests/run_native.py --work work/new-mixer-target-native --suite NativeMixerTargetRegression
.venv/bin/python tests/acceleration_probe.py --preset parametric --mixer-target hsl \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon.NEF --work work/new-hsl-target-nef
.venv/bin/python tests/acceleration_probe.py --preset bw_mixer --mixer-target bw \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon.NEF --work work/new-bw-target-nef
```

Run the probes sequentially after builds/tests finish. They assert dimensions,
finite bounded weights, counts/IDs, matching CPU/Metal map hashes, output parity,
cold capture and warm reuse without a capture stage. Report worker wall time,
capture time, RSS and map size; these exclude broker/desktop interaction latency.

## Public source check

```sh
python3 scripts/check_public.py
uv run --frozen pytest -q tests/test_public_release.py
```

`--strict` additionally rejects untracked build artifacts, environments and caches; use it on the clean extracted source archive. Never upload raw probe output without review: it can contain absolute photo/catalog paths and EXIF. The package script does not include those receipts.

## Durable Develop history

`test_develop_history.py` exercises restart-visible undo/redo, selection and
branching, no-op retention, all command revision barriers, payload-free keyset
pages, stable step IDs, rename/clear, source/job/snapshot safety, private copy
baselines, transaction rollback and LUT backup rebinding. The migration fixture
runs the genuine schema-21 chain and injects a failure after recipe conversion;
rollback must restore both schema and original payloads before a successful retry.

`NativeHistoryRegression` uses the actual broker to verify menu availability,
state selection, redo, coalesced edits, pending-action exclusion, stale forms,
external conflicts, photo switches, paging, clear and reload. It does not verify
rendered controls, mouse/key dispatch or VoiceOver. macOS 14 runtime acceptance
remains separate from compiling for its deployment target.

```sh
.venv/bin/python -m pytest -q tests/test_develop_history.py
.venv/bin/python tests/run_native.py --work work/new-history-native --suite NativeHistoryRegression
.venv/bin/python tests/history_probe.py --steps 100000 --samples 30 --work work/new-history-probe
```

Run the probe after builds/tests finish. It creates a synthetic long timeline and
measures warm service reads and committed writes, reporting median/p95, response
size and process RSS. It also times one replacement of half the future branch and
one clear of the remaining timeline; those single observations are not latency
distributions. Setup, IPC, image workers and desktop latency are excluded;
assert no image work and unchanged original bytes. Do not use it to claim preview
or full interaction performance.


## Saved import configurations

Run `tests/test_import_presets.py` with the existing import, naming, processing and
second-copy suites. Cover frozen settings after source-preset deletion, source-neutral
choices, destination/backup overrides, Add/Copy/recursion rescans, stale plan and
library changes during unlocked validation, SQL rollback, missing/symlink/overlapping
roots, interrupted-copy rejection, catalog restore with nested LUTs, genuine schema-28
migration and bounded name-only pagination. All originals and catalogs are generated.

```sh
.venv/bin/python -m pytest -q tests/test_import_presets.py
.venv/bin/python tests/run_native.py --work work/import-presets-native \
  --engine build/mac-import-presets/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeImportPresetRegression --suite NativeImportBackupRegression \
  --suite NativeImportNamingRegression --suite NativeImportProcessingRegression \
  --suite NativeImportRegression --suite NativeResponsivenessRegression
```

The native preset suite covers save/update/rename/delete, captured stale drafts after
pagination, explicit reload, source-preserving rescans, pre-scan option overrides,
retained settings after deletion and exact original bytes. Inspect generated preset
library and ready-review offscreen renders. These are model/IPC and layout checks,
not actual desktop inputs, file panels or VoiceOver. Record unavailable OS runtimes.

For preset-library responsiveness, run the packaged engine without concurrent tests
or builds. `tests/import_preset_probe.py --engine <engine> --work <new-directory>`
seeds 100 and 5,000 configurations from a valid captured 100-keyword snapshot before
measurement, then measures name pages and compact detail reads through native IPC.
Record reply bytes, first/warm timing distributions, 5 ms sampled broker RSS and
worker count. Generated catalogs warm the OS cache; this does not measure RAW,
desktop frame latency or cold filesystem performance. The native preset sheet must
release after replacement so long scans expose cancellation on the parent review.

## Catalog import and image numbering

`tests/test_import_sequence.py` verifies shared counters across reviewed Add,
direct and folder-sync imports, no-op/virtual/sidecar exclusions, numeric bounds,
genuine schema-29 migration rollback, Copy preview revisions, collisions before
reservation, concurrent counter changes, frozen ranges and explicit recovery.
Run it with existing naming/Copy/backup/preset/previous-import/folder-sync tests.
Do not replace a genuine old migration fixture by lowering a current schema number.

The packaged `NativeImportSequenceRegression` uses generated photos to exercise
counter editing, stale draft preservation, explicit reload and revised Copy names
through real Backend IPC. Its Settings and counter-sheet PNGs are offscreen layout
evidence only. Run existing naming, import, presets and responsiveness suites too;
record unavailable desktop input/VoiceOver and macOS 14 runtime explicitly.

```sh
.venv/bin/python -m pytest -q tests/test_import_sequence.py
.venv/bin/python tests/run_native.py --work work/new-import-sequence-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeImportSequenceRegression --suite NativeImportNamingRegression \
  --suite NativeImportRegression --suite NativeImportPresetRegression \
  --suite NativeResponsivenessRegression
.venv/bin/python tests/import_naming_probe.py --catalog-counters \
  --work work/new-import-sequence-scale --rows 10000 100000
```

The scale probe uses only generated SQLite rows and warmed OS caches, with a new
connection for the first read. Record first/warm page times, VM work, reply size,
rank-freeze elapsed time and 5 ms sampled RSS. No pixel dimensions/backend are
applicable; no image workers, IPC or desktop frames are timed. Run separately from
compilation and test activity. Numeric preview correctness does not establish
Adobe failure/cancellation/reset semantics or gapless numbering.

## Copy date-folder layouts

`tests/test_import_dates.py` covers the three numeric layouts, explicit defaults,
EXIF civil dates across UTC day boundaries, unknown dates without mtime fallback,
subfolders/XMP, collisions, frozen preset choices and genuine schema-30 migration.
Run it with Copy, naming, sequence/recovery and import-preset tests. The existing
schema-29 journal recovery fixture inserts the old columns directly; current
capture APIs must not be called on a partially upgraded catalog.

`NativeImportDateRegression` receives generated 160 × 100 PNGs with EXIF civil
date `2026:09:28 00:15:00` and `+14:00` offset. The directory stays September 28
even though the normalized timestamp is September 27. It exercises captured
choices and preset reuse through packaged Backend IPC. Offscreen options evidence
does not establish desktop interaction or Adobe's full localized format menu.

For large-review work, the naming probe accepts `--date-format year_month_day`
alongside `--catalog-counters --rows 10000 100000`. It verifies every returned
parent path from captured civil fields while timing the same bounded 60-row
preview and selected ranks. Report synthetic fixtures, warm OS cache, no pixels/
workers, elapsed times and sampled RSS; do not claim RAW or desktop throughput.

## Copy destination-folder preview

`tests/test_import_destinations.py` exercises captured folder layouts, checked
selection and duplicate policy, original-only counts, separate backups, cursor
paging, stale revisions and genuine schema-31 migration. Folder reads must neither
write files nor parse all stored clocks or naming ranks. Migration preserves
retained transfer paths and uses bounded batches rather than materializing reviews.

`NativeImportDestinationRegression` uses five generated PNG originals through
Backend IPC. Its folder sheet checks explicit reload after review changes and
separate backup counts, with offscreen rendering for layout inspection. It does
not establish pointer/keyboard behavior, native file panels or VoiceOver support.

```sh
.venv/bin/python tests/run_native.py --work work/new-destinations-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeImportDestinationRegression --suite NativeImportRegression \
  --suite NativeResponsivenessRegression
.venv/bin/python tests/import_destinations_probe.py \
  --work work/new-destinations-scale --rows 10000 100000
```

Run the scale probe after tests/builds stop. It seeds one original per directory
to stress group cardinality and compares first/middle/last cursor pages. A second
phase leaves 99% of groups duplicate-only, checking that new-only reads skip them
through the partial index. It also unchecks/rechecks one original six times and
bounds SQLite work so an individual checkbox cannot recount the whole review.
Record first/warm times, VM steps, reply bytes and RSS
sampled every 5 ms. New connections retain warm OS caches from seeding; there are
no real photos, image dimensions, pixels, GPU work, IPC or desktop frames timed.

## Import Loupe full-resolution regions

`tests/test_import_loupe.py` validates the explicit `detail=true` plus complete
`viewport` contract, legacy thumbnail/Fit behavior, pixel-coordinate crop results,
edge clamps, small images and captured Develop settings. Cache reuse must avoid a
new worker even while image work is occupied. Both cache-hit and newly rendered
paths must reject changed source, plan revision or cancellation generation.

`NativeImportLoupeRegression` receives five generated 2400 x 1800 PNGs with labeled
100-pixel color-grid cells. It exercises Fit and 100% physical display scaling,
pan/edge positions, stale frames/gestures, source safety and offscreen layout.
These images establish viewport mechanics, not camera color or Adobe pixel parity.
Offscreen PNGs do not establish desktop drag, keyboard or VoiceOver acceptance.

```sh
.venv/bin/python tests/run_native.py --work work/new-import-loupe-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeImportLoupeRegression --suite NativeImportRegression \
  --suite NativeResponsivenessRegression
.venv/bin/python tests/import_loupe_probe.py --work work/new-import-loupe-raw \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon.NEF
```

Run the RAW probe without competing tests/builds. It uses a fresh catalog per CPU
and Metal backend, one first request plus five exact repeats for Fit, central
800 x 600 ROI and a panned ROI. First Fit has cold application caches; the first
ROI populates the full-resolution linear base, and OS caches remain warm. Record
relay elapsed time, actual dispatched tiles, exact-repeat pixel identity, CPU/
Metal code differences, worker RSS and broker RSS sampled every 5 ms. These are
separate peaks, not whole-app memory; native display decoding and UI frames are
outside the measurement. The probe previews only and leaves the catalog empty.
For a comparable Fit baseline, `--legacy-fit` omits viewport requests and requires
every repeated Fit request to spawn work; run it against the previous packaged
engine. Use a separate new work directory and report both executable hashes.

## Collection color labels

`tests/test_collection_labels.py` covers additive schema-32 upgrades, independent
tree and target-state revisions, atomic batch validation, ancestor conflicts,
no-op labels, Quick exclusion, label-preserving duplication and bounded global
color filtering. Old-catalog evidence must construct the old schema rather than
only lower a newer database's version. Invalid or stale targets leave every row
unchanged; labels never edit photos or recipes.

`NativeCollectionRegression` exercises the same contracts through packaged IPC,
including filtered pages, preserved tree expansion, captured multi-page label
selections, external tree changes and unchanged polling. Inspect its offscreen
sidebar and batch-sheet PNGs for layout only; these do not verify desktop input,
VoiceOver or the macOS 14 runtime.

```sh
.venv/bin/python -m pytest -q tests/test_collection_labels.py tests/test_collections.py \
  tests/test_collection_identities.py tests/test_target_painter.py
.venv/bin/python tests/run_native.py --work work/new-collection-labels-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeCollectionRegression --suite NativeLibraryRegression \
  --suite NativeTargetPainterRegression --suite NativeResponsivenessRegression
.venv/bin/python tests/collection_labels_probe.py \
  --work work/new-collection-labels-scale --rows 10000 100000
```

Run the scale probe without other tests/builds. Synthetic collection rows establish
SQL paging and compact state-poll costs, not photographic processing or desktop
frame rate. Record complete count-plus-page requests, first and repeated timings,
query plans/VM work, reply sizes and sampled RSS. A newly opened SQL connection
still has warm OS caches after seeding; do not describe it as a cold disk test.

## Thumbnail publication during catalog actions

`NativeThumbnailPublicationRegression` uses gated cache/direct replies and real
Store publishers to check unchanged-state suppression, forced cache validation,
error clearing, image replacement, page clearing and obsolete-response rejection.
The existing `NativeThumbnailRegression` supplies separate live-engine evidence
for recipe changes, relinking and cache eviction.

```sh
.venv/bin/python tests/run_native.py --work work/new-thumbnail-publication-native \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --suite NativeThumbnailPublicationRegression --suite NativeThumbnailRegression \
  --suite NativeResponsivenessRegression
.venv/bin/python tests/run_thumbnail_probe.py --work work/new-thumbnail-publication-probe \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine
```

Run the measurement separately from tests and builds. It compiles current native
sources and uses five and sixty generated 160 by 100 PNGs in separate disposable
catalogs. Warm-up completes before collection membership and metadata-title
actions. Report renderer callbacks, Store publications, cache/cancellation/direct
thumbnail calls, worker flags and retained image identities. The 100-ms stable
window is a synchronization barrier, excluded from reported operation times;
those action times do not guarantee thumbnail completion or displayed latency.
RSS is the native probe's process-lifetime high-water mark, including warm-up,
not per-action or whole-app memory. No periodic Store polling is started.
This is state/IPC evidence, not RAW throughput, desktop frame rate, VoiceOver or
macOS 14 runtime acceptance. Counts are regression evidence; one action sample
per page size does not establish a repeatable elapsed-time improvement.

## Library read snapshots during catalog writes

`tests/test_catalog_read.py` checks current-catalog query parity across Unicode
names and URI-safe catalog paths, source predicates, stack projections and page
clamping. A write committed after the exact count cannot alter that request's
page or revision fields; the next request must see it. Event-gated write/read
threads verify that an uncommitted writer holding Service.lock does not block
the photo-list command and that its changes appear only after commit. This is a
dependency assertion, not a latency budget. Read connections must reject writes
even with query_only disabled, avoid Catalog construction, preserve schema and
refuse absent or mismatched catalogs. A genuine schema-32 catalog verifies normal
Service startup migration before read access.

```sh
.venv/bin/python -m pytest -q tests/test_catalog_read.py tests/test_organization.py \
  tests/test_stacks.py tests/test_folders.py tests/test_snapshot_status.py \
  tests/test_folder_sync_apply.py
.venv/bin/python tests/folder_sync_probe.py --work work/new-library-read-scale --rows 100000
```

Run the existing synchronization probe alone, against each frozen engine source.
Its concurrent list reader sees either the full pre-commit or post-commit count;
record request median/p95/maximum, sample count, complete apply and atomic SQL
timings, cache conditions and process RSS. Synthetic missing originals and empty
new PNG placeholders exercise SQL/stat work, without hashes, pixels, IPC or UI.
Do not describe reduced list waiting as a fix for every native refresh: conditional
folder/keyword pages, photo details and image work still use their existing locks.
Slow filters and broker admission can also delay reads.

`tests/test_library_state_read.py` extends the snapshot checks to `library_state`,
`photo_summaries`, `collection_state` and `orientation_state`. Each must read the
old committed state while a writer holds Service.lock, then see the new state
after commit. Real import, rating, membership and rotation commits between response
components must not mix revision fields, summaries, membership or undo history.
Summary ID bounds, ascending order, duplicate handling and response keys remain
compatible with ordinary Catalog callers.

```sh
.venv/bin/python -m pytest -q tests/test_catalog_read.py tests/test_library_state_read.py \
  tests/test_collections.py tests/test_orientation.py tests/test_previous_import.py
.venv/bin/python tests/library_state_probe.py --work work/new-library-state-scale --rows 100000
```

The rotation suite requires access to the selected CPU/Metal backends. Run the
refresh-chain probe alone against a frozen engine. It times photo list, collection
state, orientation state, photo summaries and Library state sequentially during
the same synthetic folder scan/apply. Each response is checked independently;
separate commands may see different commits. JSON receipts retain the first 1,000
chains with per-command timings and revision vectors, and explicitly count any
omitted chains. Reported statistics cover only retained chains; do not present a
truncated run as full-phase coverage. This is not Store.refresh timing: conditional
detail/folder/keyword loads, thumbnail tasks, IPC and desktop rendering are absent.
