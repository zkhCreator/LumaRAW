# Lightroom Classic for Mac: parity ledger

## Scope and baseline

Reference: Adobe Lightroom Classic for Mac, excluding AI functionality. Functional
workflow completeness and processing performance take priority over exact chrome.
Pixel identity to Adobe's proprietary RAW engine is **not established**. A control
with the same name requires behavior/fixture verification before parity acceptance.

At baseline `dabb127` (0.4.1), a remote refresh found only `origin/main`, equal to
local `main`; there were no additional local branches, remote branches or worktrees
to merge. Development continues on `codex/lightroom-classic-mac`.

Official references checked September 2026:

- [Workspace and module responsibilities](https://helpx.adobe.com/nz/lightroom-classic/help/workspace-basics.html)
- [Collections, smart collections and collection sets](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/photo-collections.html)
- [Smart collection criteria](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/smart-collections-criteria-in-lightroom-classic.html)
- [Develop tools](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/develop-module-tools.html)
- [Loupe, Compare and Survey](https://helpx.adobe.com/lightroom-classic/desktop/viewing-photos/browse-compare-photos.html)
- [Keyboard shortcuts](https://helpx.adobe.com/lightroom-classic/desktop/introduction-to-lightroom-classic/keyboard-shortcuts.html)
- [Photo stacks and source boundaries](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/grouping-photos-stacks.html)
- [Stacking shortcuts, Adobe's Julieanne Kost](https://jkost.com/blog/2024/07/stacking-similar-photos-in-lightroom-classic.html)
- [Folder hierarchy, subfolder inclusion and synchronization](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/create-folders.html)
- [Missing-photo and missing-folder relinking](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/locate-missing-photos.html)
- [Metadata storage and supported workflows](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/metadata-basics-actions.html)
- [XMP basic properties](https://developer.adobe.com/xmp/docs/xmp-namespaces/xmp/) and [Dublin Core properties](https://developer.adobe.com/xmp/docs/xmp-namespaces/dc/)
- [Hierarchical keywords, synonyms and export options](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/keywords.html)

## Feature inventory

“Partial” means an implementation exists, with important workflow or verification
gaps. Nothing below is full Lightroom parity merely because historical tests pass.

| Area | Current implementation | Remaining acceptance / work |
| --- | --- | --- |
| Import and catalogs | Partial: referenced originals, backup/restore | Import preview/selection, copy workflows, metadata/develop presets, tethered capture, catalog switching/merge |
| Library navigation | Partial: bounded grid/filmstrip, folder tree/search/favorites/labels, durable missing-folder relocation and folder synchronization, direct/recursive sources, filters/sorting, regular/smart/Quick collections and nested sets | Multi-source selection, complete sync Import Dialog/duplicate policy, folder move/rename, relocation overlap/collision handling, collection drag/drop/color labels, full smart criteria/import-export, source-selection memory, desktop acceptance |
| Organization | Partial: duplicate/missing detection, hierarchical keywords/synonyms, title/caption/copyright, labels, batch metadata, virtual copies, manual/split/capture-time scoped stacks | Keyword export policies/sets/import-export/undo/Painter, complete IPTC, stack interaction acceptance, rename and sidecars |
| Culling | Partial: Loupe/Compare/Survey, linked detail, anchored page selection | Desktop acceptance, cross-page selection, Develop reference view, auto advance, persistent workspace state |
| Basic development | Partial: light/WB/color | Calibrated absolute WB, eyedropper, texture/clarity/dehaze, complete HSL/B&W and color grading |
| Curves and profiles | Partial: custom composite curve, LUT/ICC | Interactive RGB curves, camera/profile browser, compatible preset import/export |
| Detail and optics | Partial: noise/sharpen, manual lens | Complete manual detail controls, automatic lens profiles, bounded full-resolution acceptance |
| Geometry | Partial: crop/rotate/straighten/perspective | Interactive retained handles/ratios/flip, guided transforms, crop state parity |
| Local editing | Partial: radial/gradient/brush/luma | Mask list/edit/reorder/intersection, range masks, clone/heal, red-eye (non-AI) |
| History and presets | Partial: 50-step undo, shared named snapshots | Redo, navigable history, preset management and import-time/batch application |
| Preview/performance | Partial: Metal, proxies, 1:1 viewport, developed thumbnail fast path | Real-RAW catalog/slider latency, offline previews, cache controls and desktop acceptance |
| Export | Partial: JPEG/16-bit TIFF, ICC, durable jobs | Presets, metadata policies, watermark, additional formats, publish workflows |
| External editing and video | Missing | External-editor setup and derivative round trips; supported video import/playback, frame capture, trimming and export |
| Merge | Missing | Non-AI HDR merge and panorama with bounded resources and reference acceptance |
| Map | Missing | GPS metadata, map navigation, track import, location editing with explicit persistence |
| Book | Missing | Templates, layouts, typography, PDF/JPEG output; external fulfillment is a separate integration |
| Slideshow | Missing | Layout, timing, playback, audio, slideshow export |
| Print | Missing | Contact sheets/packages, physical sizing, native print/ICC workflow |
| Web | Missing | Local gallery templates and export; publishing requires explicit destination |
| Platform/accessibility | Partial: Mac 14 target, Mac 26 historical checks | Legacy upgrade recovery, current desktop checks, macOS 14, keyboard/VoiceOver, color management; Windows remains future |

## Active increment

Durable folder synchronization, selectable recursive imports, missing-family
catalog removal, supported external metadata reads and large-catalog performance.
Keyword export workflows follow; the remaining inventory stays in scope.

## Evidence log

### Library organization increment

Implemented regular collections, live flat all/any smart rules, title/caption/
copyright, normalized flat keywords, five color labels, atomic metadata revisions,
SQL query/count/sort and bounded collection pagination. Native sidebar, forms,
menus, filter empty state and metadata readback are wired to the shared contracts.
Grid queries avoid recipe/EXIF payloads. Warm thumbnail pages use one cache request
with no image workers; cold thumbnails remain source previews.

Current evidence on Apple Silicon, macOS 26.6.2:

- `LUMARAW_REQUIRE_METAL=1` Python suite: **110 passed, 2 skipped**. The skips
  require a real NEF fixture, which was not supplied. GPU tests actually ran.
- Actual packaged-engine/native state integration: **28 assertions passed**
  (15 existing selection/revision assertions and 13 library assertions).
- macOS 14 deployment-target compile, self-contained app packaging and local
  ad-hoc signature verification passed. Compilation does not establish macOS 14
  runtime compatibility; only macOS 26.6.2 is available here.
- Public source scanner: 158 files, no findings. Local builds/fixtures/receipts
  remain ignored and excluded from source publication.
- Desktop automation was not approved to control the isolated QA app. Therefore
  rendered UI, mouse interactions and VoiceOver remain **unverified**. No screenshot
  or Lightroom visual/behavioral acceptance is claimed.

Synthetic catalog probe (10,000 rows; 30 query samples; 128 GB arm64 Mac):

| Query/operation | Median | p95 | Scope |
| --- | ---: | ---: | --- |
| Default 60-photo page | 2.93 ms | 3.45 ms | In-process service + SQLite |
| Filename sort | 3.05 ms | 3.39 ms | Stable SQL order |
| Rating filter | 3.02 ms | 3.36 ms | SQL count + page |
| Smart collection | 5.57 ms | 6.70 ms | 832 matching rows |
| Literal text search | 14.51 ms | 15.87 ms | Unicode text + keyword predicates |
| Warm 12-thumbnail page, previous worker path | 1,608.56 ms | 1,664.12 ms | 3 page samples, cached JPEGs |
| Warm 12-thumbnail page, bulk cache lookup | 1.93 ms | 2.64 ms | 30 page samples, no workers |

Thumbnail sources were generated 600×400 rasters, CPU mode. Cold generation took
1,854 ms for the 12-photo page (one sample). Broker RSS was about 66 MB and sampled
worker peak about 42 MB. These are cache/query results, not RAW development speed,
whole-desktop latency, or performance guarantees on other hardware. Reproduce via
`tests/library_probe.py`; private receipts stay under the ignored `work` directory.

### Next work

Continue with keyword export workflows, complete synchronization import options, relocation edge cases, stack ordinal badges and
cross-page cover focus. Offline preview caches,
cache-size controls and native polling/process-startup costs remain pending. Then close Develop and
export gaps in the inventory. Preserve pending desktop/older-OS acceptance rather
than removing it from the completion criteria.

Folder navigation acceptance includes imported-directory hierarchy, alphabetical
children, bounded counts/pages, optional inclusion of descendants, and locating a
selected photo's folder. Source navigation must remain distinct from metadata
filters. Favorites, labels, missing-folder relinking, synchronization and explicit
filesystem rename/move workflows need distinct acceptance; a tree alone does not
complete folder parity. Navigation/favorites/labels, missing-folder relocation and
the synchronization increment are implemented below; their remaining gaps and
filesystem move/rename workflows stay in scope.

Full completion still requires closing all non-AI gaps above. Historical receipts
in `VERIFICATION.md` do not validate this increment.

### Range selection and batch culling increment

Implemented anchored Shift ranges within the visible page, Command toggling,
focused-grid Select All, atomic batch ratings/flags and active-photo-only Develop
culling. Single-key photo commands are scoped to grid/filmstrip/canvas, preserving
normal text-field input routing. Selection remains bounded to a 60-photo page;
cross-page selections, Compare/Survey and auto-advance are still pending.

The new 12-assertion native culling suite passed alongside the existing 28 checks
against both source and final packaged engines (**40 assertions**). The final
required-Metal Python run passed **112 tests, with 2 real-NEF tests skipped**.
The updated Mac app built and passed ad-hoc signature verification. The source
scanner passed all **160 files**, and the extracted source archive passed its
strict check. Service regressions verify missing-target rollback,
batch deduplication and preserved recipe/metadata revisions. Smart “any” predicates
also accept disjoint ranges (for example, rating >= 5 OR rating <= 1).
Rendered keyboard event routing remains pending desktop access; state tests do
not establish that evidence.

### Loupe, Compare and Survey increment

Implemented distinct Library views and G/E/C/N/D shortcuts, fixed Select and
Candidate roles, candidate navigation, swap/promotion, linked/independent zoom and
pan, synchronization, Survey tiles and non-destructive deselection. Metadata,
ratings and labels affect only the active photo outside Grid. Entering Library
clears Develop drawing/baseline modes. Collection saves now await their page
refresh, fixing a race exposed by the combined native regression run. Comparison keeps unchanged revision-keyed
frames; Survey fits up to the current 60-photo page using 512-pixel previews.

The shared preview contract can omit the unused baseline and bound fitted output.
Client-scoped cancellation and generation checks prevent stale preview repainting
without cancelling exports. Lightweight summary polling refreshes external edits.
Python regressions passed **117 tests, 2 real-NEF tests skipped**, with Metal
required. All four native suites passed against the packaged engine: **60 assertions**,
including 20 review checks for role/viewport transitions, stale replies, frame
retention, action scope and safe Survey removal. The final Mac app compiled,
packaged and passed ad-hoc signature verification. The 167-file source archive
also passed the extracted strict source scan. Desktop events, physical
display-scale rendering and macOS 14 runtime remain unverified.

Synthetic CPU preview probe, 1600 × 1067 generated raster, warm linear-source cache
and five distinct recipe outputs per case (128 GB arm64 Mac, macOS 26.6.2):

| Complete service/worker request | Median | p95 | Output dimensions |
| --- | ---: | ---: | --- |
| Preview with baseline | 869.59 ms | 891.36 ms | 1600 × 1067, two images |
| Compare preview without baseline | 577.54 ms | 586.88 ms | 1600 × 1067, one image |
| Fitted Survey preview | 303.20 ms | 350.82 ms | 512 × 341, one image |

A separate cold-decode default request took 997.85 ms (one sample). Broker RSS
was 54.62 MB; sampled worker peak across cases was 146.14 MB. The comparison
request reduced measured median time by about 34%; this includes startup and
encoding but excludes IPC and desktop presentation, and is not a RAW performance
claim. Reproduce with `tests/review_probe.py`; private receipts remain ignored.

### Developed grid and filmstrip thumbnails

The Mac app now uses edited 320-pixel thumbnails from the shared render pipeline,
including geometry, color and masks. The default CLI/MCP source thumbnail behavior
is preserved; explicit `kind: developed` opts into recipe-aware results. Atomic
ICC-tagged JPEG publication, original/LUT stat identity, recipe hashes and reported
source/revision keep stale content separate. Undo can reuse an earlier image;
metadata changes reuse existing pixels.

The native loader retains unchanged images, rejects old generations and mismatched
source/revision replies, and cancels obsolete page workers independently of exports.
Lightweight visible-page polling detects external edits to non-active photographs.
The active inspector retains its optimistic-edit barrier. Relinking an original
also invalidates native image state even when the recipe revision is unchanged.
Refresh rechecks sources, retries failures and regenerates evicted cache entries.

Python suite with Metal required: **125 passed, 2 real-NEF tests skipped**. Eight
new Python cases verify fitted-preview color/geometry within JPEG tolerances,
original hashes, metadata independence, undo reuse, source/LUT invalidation,
mid-render source changes, captured revisions and cancellation. Fourteen new
native checks cover the real Store/engine flow plus deterministic delayed replies.
All five native suites passed against the packaged engine (**74 assertions**).
The final app compiled without Swift warnings, packaged and passed ad-hoc signature
verification. Its 171-file extracted source archive passed the strict source check.
Desktop interaction, macOS 14 runtime and offline-source thumbnail lookup remain
unverified or incomplete; this is not full Library parity.

Synthetic CPU cache probe: 12 generated 600 × 400 images in a 10,000-row catalog,
128 GB arm64 Mac, macOS 26.6.2. Cold developed-page generation took **3866.21 ms**
(one sample). Warm page requests that intentionally start workers took **2877.17 ms**
median / **2909.83 ms** p95 (three samples); the bulk cache path took **2.37 ms**
median / **2.79 ms** p95 (30 samples). Broker RSS was 49.00 MB; sampled worker peak
was 76.23 MB. These are service/worker timings, excluding IPC and desktop drawing,
and do not establish camera RAW speed. Reproduce with the library probe's
`--thumbnail-kind developed` option.

### Collection sets and Quick/target workflow

Schema version 2 preserves existing IDs, adds parent links and creates one durable
Quick Collection. Collection sets support nested regular/smart/set children,
combined photo views, moves, subtree duplication and deletion. A parent revision
changes with descendant mutations, so stale subtree deletion/copy fails. New
regular collections can include the selected photos in their creation transaction.

Quick can be saved as a regular collection, optionally clearing in the same
transaction. Target collection choice is durable and has a separate revision.
Target membership checks both the captured target and its membership revision;
concurrent target changes fail visibly instead of redirecting the action. Deleting
a target or an enclosing set resets the target to Quick and leaves photos intact.

The native sidebar lazily expands 60-child pages, releases collapsed branches,
marks the target with a plus and provides edit/move/duplicate actions. B and
thumbnail-circle actions add/remove target members. Delete in a focused photo
view removes regular/Quick membership. Forms support nested creation, initial
selection and Quick save/clear, with explicit subtree-delete confirmation.

New evidence: eight Python workflow tests cover nested live aggregation, invalid
parents/cycles/depth, initial-member atomicity, ancestor conflicts, safe subtree
removal, Quick save/clear, target conflicts, duplication, v1 migration, backup and
pagination. Seventeen new native assertions passed through the real broker. The
full required-Metal Python run passed **133 tests, 2 real-NEF tests skipped**.

Explicit resource bounds: 32 nesting levels; 128 smart collections per set
aggregate; 1,000 collection nodes per duplication. These are current limits, not
Lightroom limits. Collection drag/drop, color labels on collections, smart-rule
import/export, source-selection memory, rendered disclosure/keyboard acceptance
and macOS 14 runtime remain incomplete. B currently removes a fully included
selection and otherwise adds it; mixed-selection equivalence to Lightroom has
not been independently verified. These gaps remain part of the full goal.

Synthetic collection probe (10,000 catalog rows, 13-node set, macOS 26.6.2 arm64,
128 GB RAM; no image workers): aggregate 60-photo page **8.96 ms** median /
**9.82 ms** p95, child page **1.13 / 1.26 ms**, target page state **1.10 / 1.20 ms**
(30 samples each). Saving a 10,000-member Quick Collection took **11.82 / 11.85 ms**
and duplicating the 13-node subtree with those memberships **17.03 / 19.12 ms**
(three samples each). Broker RSS was 39.45 MB. These measure synthetic SQLite and
service commands, excluding CLI startup, IPC and desktop drawing. Reproduce with
`tests/collection_probe.py`.

All six native suites passed against the final packaged engine (**91 assertions**).
The Mac app built without Swift warnings and passed ad-hoc signature verification.
The 177-file source archive passed the extracted strict source scan. Desktop UI
and older-OS acceptance remain explicitly unverified.


### Virtual-copy increment

Reference behavior: [Adobe’s virtual-copy documentation](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/photos.html)
and [Julieanne Kost’s virtual-copy workflow](https://jkost.com/blog/2024/08/working-with-virtual-copies-in-lightroom-classic.html).
Copies reference one original, have independent adjustments and metadata, support
copy names and master promotion, and expose shared source snapshots. Native menu,
contextual grid/filmstrip actions, badges, family navigation, filters, metadata
naming and removal confirmation are implemented. Batch creation captures at most
60 summaries in one service call; it does not load 60 full recipes through IPC.

Schema v3 preserves existing IDs/references when removing the old unique-path
constraint and makes deleted photo IDs non-reusable. Family identity survives
master changes and copy removal. Indexing reads each physical source once, copies
do not count as physical duplicates, and relinking updates every variant plus
eligible frozen jobs, including jobs from a removed copy. Removal keeps original
files, shared snapshots and already-submitted exports.

Synthetic service timings on macOS 26.6.2 arm64 / 128 GB: 10,000 physical source
rows + 10,000 copies, warm SQLite, 30 samples per operation. No image workers, IPC
or desktop latency are included.

| Operation | Median | p95 |
| --- | ---: | ---: |
| Read a 60-photo page | 3.080 ms | 3.320 ms |
| Filter virtual copies | 3.284 ms | 3.407 ms |
| Read one source family | 2.813 ms | 2.971 ms |
| Capture 60 summary targets | 1.291 ms | 1.388 ms |
| Create 60 virtual copies | 6.625 ms | 10.612 ms |

The creation probe retained all 1,800 new rows; final count 21,800. Broker RSS was
39.55 MB, sampled worker peak zero. These are catalog timings, not RAW processing
or native perceived latency.

Final evidence: required-Metal Python suite **142 passed, 2 real-NEF tests skipped**.
All seven native state suites passed against the final packaged engine, totaling
**110 assertions**, including 19 virtual-copy assertions. The Mac app built
without Swift warnings and passed ad-hoc signature verification. The 183-file
source archive passed the extracted strict source scan. These receipts are not
desktop UI evidence.

Remaining parity: default folder stacks/collapse/order and master stack counts,
stack behavior in collection contexts, copy-name export template tokens and exact
shortcut/rendered interaction acceptance. This increment does not make those
behaviors or the broader application 1:1 complete. Real NEF fixtures, macOS 14
runtime, current desktop UI and VoiceOver evidence remain unavailable.

Upgrade issue found during this increment: previously, a client reused any broker
for its catalog. The following increment adds negotiation and safe handoff. No
existing user broker was terminated.


### Broker compatibility increment

Engine protocol/generation/build/schema identities are negotiated before each
command and verified again at admission. A lifetime owner lock prevents a second
broker from unlinking the live endpoint. Newer generations can hand off when idle;
same-generation different builds need the native Settings/connection action.
Newer schema/generation downgrades are rejected. Active requests include response
delivery, and both foreground preview work and reserved/running exports defer a
switch without cancellation.

A clean handoff seals admission and queue acquisition, writes a durable exact-target
receipt and retires the old process. Its matching successor consumes the receipt
once, retaining pending job snapshots and pause state. Ordinary crashes and wrong
targets still require interrupted-job recovery. Lost handoff replies finish safely;
uncertain mutation replies are not retried. Workers check the expected engine before
opening pixels/output; in-place engine replacement interrupts the affected export
and pauses the remaining queue.

The Mac startup error offers explicit reconnection, Settings exposes the same
action, and startup can recover after a mismatch. Legacy pre-handshake brokers are
detected before mutations and left to finish/exit naturally. Their existing code
cannot perform the new clean handoff; this is a documented upgrade boundary,
not an automatic legacy-process termination policy. Windows locking/named-pipe
branches, rendered connection alerts, VoiceOver and macOS 14 remain unverified.


Required-Metal Python verification: **155 passed, 2 real-NEF tests skipped**.
Thirteen broker lifecycle tests cover real process switches, active preview/export
preservation, ownership, lost responses and conservative recovery. The new native
connection suite adds ten assertions for startup recovery and unchanged job state.

Packaged-engine connection probe: empty catalog, warm broker, macOS 26.6.2 arm64,
128 GB, 30 samples per path. Single status RPC measured **0.883 ms median /
1.122 ms p95**; negotiated status **0.877 / 1.091 ms**; complete packaged CLI launch
plus negotiated status **53.034 / 54.059 ms**. The near-equal RPC results do not
establish a speedup; this probe overlapped native compilation and is a latency
observation, not a controlled comparative benchmark. Broker RSS was 34.56 MB and
no image workers ran. Photo processing and rendered UI latency are excluded.


All eight native suites passed against the packaged engine: **120 assertions**.
The app built without Swift warnings and passed ad-hoc signature verification after
the bundled service-compatibility instructions were updated. The 189-file source
archive passed the extracted strict source check. Desktop alerts/Settings and
macOS 14 runtime still require separate verification.

### Manual photo stacks increment

Folder and regular/Quick collection stacks now have separate persistent membership.
New groups use the active photo as cover, then display order; expanded members stay
contiguous under every sort. Grouping collapsed covers moves only the selected
cover from another stack. Group/unstack, expand/collapse, remove, cover selection,
up/down and source-wide visibility are available through shared APIs and Mac menus.
Count badges and scoped S/Shift-S/bracket actions are wired to these commands.

New virtual copies join an expanded folder stack, including creation inside a
collection. Collection removal, copy removal and cross-folder relinking clean up
membership; singleton stacks dissolve without deleting photos. Collection duplicate
and Quick save preserve independent stack organization. Stack changes use a
catalog-wide revision; collection/ancestor revisions protect subtree operations.
Deleting even an unstacked collection invalidates captured stack requests, including
when the legacy collection schema reuses its ID for a new collection. Stable IDs
for other collection commands remain a follow-up.
Schema v4 preserves old photos and leaves existing variants ungrouped on migration.

Collapsed children are excluded from filtered pages and selection. The explicit
flat-view option exposes them without changing saved stack visibility; family
navigation uses this view. External stack changes refresh native pages, including
an empty page. This filter policy, Quick-stack behavior and collection stack copy
behavior still need direct Lightroom desktop comparison.

Queries select at most 60 narrow IDs/sort keys before fetching summaries. All Photos
uses maintained stack sizes for counting; empty stack sources use the existing
indexed path. Warm synthetic measurements on macOS 26.6.2 arm64, 128 GB, 30 samples,
ten photos per stack, with no image work or concurrent build/test workload:

| Operation | 10,000 photos median / p95 | 100,000 photos median / p95 |
| --- | ---: | ---: |
| Collapsed page | 7.561 / 7.789 ms | 50.151 / 51.153 ms |
| Collapsed filename sort | 7.450 / 8.092 ms | 49.491 / 50.257 ms |
| Collapsed rating filter | 7.814 / 8.448 ms | 55.775 / 57.947 ms |
| Expanded page | 9.565 / 9.949 ms | 71.218 / 72.133 ms |
| Expanded final page | 11.500 / 11.922 ms | 102.479 / 107.480 ms |
| Flat baseline | 3.357 / 3.467 ms | 3.603 / 3.689 ms |

Process peak RSS was 44.44 MB / 73.06 MB respectively; worker peak was zero.
The initial 100k implementation measured 187.405 ms median for an expanded page
and 274.431 ms for its final page on the same host/fixture configuration. The
narrow page and count changes reduced these observed costs. These are in-process
service/SQLite measurements, excluding IPC, RAW processing and desktop latency.

Remaining stack work: capture-time auto stacking, splitting, ordinal member badges,
cross-page cover focus and direct Lightroom interaction acceptance. Rendered Mac
controls, shortcuts, VoiceOver and macOS 14 runtime remain unverified.

Required-Metal Python verification: **168 passed, 2 real-NEF tests skipped**.
Thirteen stack tests cover migration, ordering, source isolation, stale commands,
cleanup, duplication, bulk visibility and legacy collection-ID reuse. The native
runner now generates a fresh image directory for every suite: the thumbnail
relink test previously moved a shared fixture, which caused a later suite to
import four photos instead of five. The stack suite explicitly checks all five
imports before testing its workflows. No personal catalog or source was touched.

A fresh remote audit still found only `origin/main` at the baseline; no additional
branches or worktrees needed integration. Development changes remain on the
`codex/lightroom-classic-mac` branch.

All nine native suites passed against the final self-contained engine: **140
assertions**, including 20 stack assertions. The Mac app built without Swift
warnings and passed ad-hoc signature verification. The bundled engine manifest
matches the final engine source. Native state checks are not rendered desktop,
keyboard routing, VoiceOver or macOS 14 runtime evidence.
The 195-file source-only archive also passed its extracted strict public check.

### Capture-time stacks and stable collection identities increment

Schema v5 preserves live collection IDs, hierarchy, target state, memberships,
indexes and triggers while preventing future identifier reuse. Deleting the
highest collection and restarting or restoring a backup no longer lets stale
native editors rename a replacement collection. Failed rebuilds roll back. IDs
already deleted before this upgrade cannot be reconstructed from old catalogs.

Schema v6 adds precise capture clocks: integer microseconds and exact finer decimal
digits, including epoch/pre-epoch dates. Bounded read-only TIFF-family, JPEG and
PNG EXIF readers obtain camera model, original/digitized/fallback date, fraction
and offset without opening a pixel decoder or hashing files. Explicit offsets
normalize to UTC; absent offsets keep marked camera wall time independent of the
host timezone. Unsupported containers, BigTIFF and malformed metadata stay unknown.
Old integer timestamps remain on migration; precise clocks require refresh.
Generated TIFF headers are not evidence of actual Nikon metadata coverage.

Auto-Stack by Capture Time previews the entire explicit folder (excluding child
folders) or regular/Quick collection, ignoring selection and filters. Adjacent gaps
strictly below 0–3600 seconds join groups; equality starts a new group and zero
leaves photos unstacked. Preview examples are capped at 20. Application rechecks
the preview fingerprint before atomically replacing that source's stacks. Changed
clocks, membership, duration or stack revision reject the old plan. Unknown dates
remain unstacked; an entirely unknown source cannot erase existing stacks. Recipe
changes are preserved. Split moves a proper selected subset of an expanded stack
in its existing order; singletons become unstacked.

Native confirmation captures source and duration, clears stale plans and reports
conflicts without automatic retry. Capture refresh pages at 60 physical originals,
updates all virtual-copy clocks and exposes progress/Stop between pages. Refresh
does not hash photos or run image workers. Dismissing the sheet discards late
previews. Mixed camera/UTC clocks, existing-stack replacement details and exact
Split behavior still require direct Lightroom comparison; no desktop parity is
claimed from matching the published descriptions alone.

Warm synthetic timings on macOS 26.6.2 arm64, 128 GB, with no concurrent build or
test workload. Previews use 30 samples; replacement uses three samples and includes
the preceding preview and apply-time revalidation:

| Operation | 10,000 photos median / p95 | 100,000 photos median / p95 |
| --- | ---: | ---: |
| Folder preview | 29.719 / 32.887 ms | 292.696 / 296.435 ms |
| Collection preview | 29.401 / 30.322 ms | 305.416 / 323.433 ms |
| Folder replacement, ten-photo groups | 258.500 / 267.989 ms | 2693.146 / 2700.447 ms |
| Collection replacement, ten-photo groups | 258.329 / 264.071 ms | 2762.498 / 2776.028 ms |
| One source-sized stack replacement | 236.382 / 238.452 ms | 2483.035 / 2489.030 ms |

Peak process RSS was 48.47 / 79.27 MB; worker peak was zero. Groups stream through
SQL cursors and update their cached size once rather than recounting on each
insertion. These timings exclude EXIF I/O, IPC, RAW processing and rendered UI.
`tests/auto_stack_probe.py` reproduces the synthetic workload.

Final required-Metal Python run: **194 passed, 2 real-NEF tests skipped**. Capture,
auto-stack, split and identity tests cover exact boundaries, scope, stale plans,
unknown dates, migration rollback, backup/restore and non-reused collection IDs.
All ten native suites passed against the self-contained packaged engine: **165
assertions**, including 19 auto-stack, 22 stack and 21 collection checks. The Mac
app built without Swift warnings and passed ad-hoc signature verification. Its
engine manifest matches the final source (generation 4, catalog schema 6, 52 tools).
Rendered desktop interaction, VoiceOver, macOS 14 runtime and real-camera/Adobe
reference acceptance remain unverified. Folder navigation, keyword hierarchy and
the full non-AI feature inventory remain unfinished.

### Folder navigation and source counts increment

Schema v7 adds a relational folder/photo index with maintained direct/descendant
counts. Imports, virtual copies, removal and relinking update it transactionally;
no image decoding or recursive filesystem scan is used. The upgrade preserves
existing photo rows and rolls back a denied write. Backup/restore retains the tree,
labels and favorites. Legacy collection/stack migration fixtures now build genuine
v1/v3 databases instead of lowering the schema number of a newer database that
still contained newer tables.

The Mac sidebar exposes paged folder roots/children, text/favorite/color filtering,
unavailable-directory indicators, catalog labels and Show/Hide Parent. Imported
parents coalesce descendant roots; hiding a parent with direct photos fails
explicitly. Availability is checked when a folder page is read, including explicit
refresh; disk-watch automation is not implemented. Counts include virtual copies
and do not change with photograph metadata filters.

Folder sources are independent of metadata filters and mutually exclusive with
collection sources. Descendant inclusion defaults to true; exact-folder views and
stack visibility respect its toggle. External folder revisions refresh native
pages and sidebar counts, including a previously empty filtered result. Navigation
flushes edits and rejects superseded source requests. Go to Folder clears filters,
shows individual photos in import order, computes the correct photo/tree pages
and reveals the containing branch. It changes the current flat-view preference,
without rewriting saved stack visibility. Exact preservation of Lightroom view
preferences on this action still needs direct comparison.

Synthetic warm timings on macOS 26.6.2 arm64, 128 GB, 1,000 leaf folders under ten
intermediate year folders, 30 samples, no concurrent test/build workload:

| Operation | 10,000 photos median / p95 | 100,000 photos median / p95 |
| --- | ---: | ---: |
| Folder root page | 1.500 / 1.648 ms | 1.545 / 3.140 ms |
| Child folder page | 1.543 / 1.601 ms | 1.600 / 1.756 ms |
| Folder name search | 4.527 / 4.610 ms | 4.629 / 4.937 ms |
| Descendant photo page | 8.306 / 8.658 ms | 40.458 / 43.191 ms |
| Descendant rating filter | 12.692 / 13.496 ms | 94.382 / 96.495 ms |
| Direct leaf photo page | 3.448 / 3.509 ms | 3.923 / 4.322 ms |
| Descendant final page | 10.537 / 11.386 ms | 68.708 / 70.045 ms |
| Photo's folder/offset | 1.182 / 1.417 ms | 1.251 / 1.450 ms |

Peak process RSS was 41.12 / 67.59 MB; no image worker ran. Metadata-only insertion
with production triggers took 1.343 / 14.579 seconds (one setup sample), excluding
file import and EXIF reads. Initial 100k descendant/final pages measured 91.347 /
120.821 ms median. Maintained totals minus hidden stack children avoid rescanning
all members for unfiltered counts; filtered queries retain exact SQL counts. These
measurements exclude IPC, image processing and desktop latency. Reproduce using
`tests/folder_probe.py`; long metadata imports and indexing still need persistent
jobs to avoid holding the service lock for their duration.

Remaining folder parity includes multi-folder selection, grouped favorite sources,
volume/display modes, synchronization, missing-folder bulk relocation, safe physical
rename/move and empty-folder creation/import. Rendered controls, keyboard/VoiceOver,
macOS 14 runtime and direct Lightroom workflow acceptance remain unverified.

Final required-Metal verification initially passed **202 tests with 2 real-NEF
skips**. A separately acquired upstream fixture then enabled the entire suite:
**204 tests passed, no skips**. The pinned
[rawpy D3S sample](https://github.com/letmaik/rawpy/blob/5ab750e3044b55549bf2b21ada46df815a016103/test/iss030e122639.NEF)
is 10,656,312 bytes with SHA-256
`5922721d13f11795557d97fdeb0a60b900086c402bc82a848ff280d15b99ffd4`.
It stays in an ignored test directory and is not redistributed. Real-RAW tests
verify bounded previews, full-size 16-bit TIFF/ICC, unchanged source hashes and
color-matrix agreement with LibRaw's own sRGB reference, not Adobe processing.
The capture reader used 818 header bytes and matched the independently read EXIF
original date/fraction (`2012:03:04 17:20:59`, `06`) as camera wall time. Broader
camera/HE/HE* coverage remains pending.

All eleven native suites passed against the final self-contained engine: **189
assertions**, including 24 folder checks and later-page photo location. The Mac
app compiled without Swift warnings, passed local ad-hoc signature verification,
and embeds a manifest matching the final engine source (generation 5, schema 7,
57 tools). These state/IPC checks do not establish rendered desktop acceptance.

The packaged engine additionally completed six full-size 4284 × 2844 D3S exports,
alternating JPEG/16-bit TIFF and four output spaces, in **9.09 seconds** on Apple
M3 Max. The run includes queue/worker startup and encoding; five source decodes
were uncached for their white-balance settings and the sixth reused a source cache.
All jobs reported actual Metal grading (23 tiles each), with LibRaw CPU decoding,
no fallback and at most one image child. Broker RSS peaked at **42.97 MB**, sampled
worker RSS at **282 MB**, Metal shared buffers at **19.61 MB**. Original hashes
were unchanged and no partial export files remained. Six repeated exports of one
sample are process/resource evidence, not six independent camera samples or an
Adobe color-fidelity benchmark.

### Hierarchical keyword increment

Schema 8 gives tags stable IDs, scoped sibling names, nested parents, synonyms and
independent photo assignments. Equal names in different branches remain distinct.
Create-and-assign, add/remove, rename/move and subtree deletion are atomic and
revision checked. Ancestor edits invalidate affected photo metadata revisions
without touching recipes. Virtual copies preserve IDs on creation and keep later
assignments independent. ID/name/synonym filters include descendants and intersect
folder/collection sources and smart criteria. List counts and mixed-selection
indicators describe direct assignments. Pages hold at most 60 tags; paths are
limited to 32 levels and each photo to 100 direct tags.

The Mac sidebar includes lazy branches, synonym search, contextual editing and
parent picking, Grid batch actions and active-photo-only actions outside Grid.
Show Photos filters the library independently of previous sources. New-keyword
forms capture their selection. Metadata forms retain untouched structured tags
instead of splitting old literal commas while editing another field. Genuine v7
migration preserves legacy separator names, while ambiguous textual collisions
fail without changing assignments; ID-based checkbox commands remain usable.

The final required-Metal Python suite passed **214 tests, no skips**, using the
same pinned read-only D3S fixture documented above. New cases cover migration
rollback/backup, duplicate names, legacy path round trips, Unicode, atomic target
conflicts, subtree edits, bounded pages/depth, independent copies and smart/source
filters. An old v4 fixture initially called current photo code before keyword
migration; it now constructs genuine v4 SQL state. A native run was also rejected
by the compiler because a form changed during compilation; that incomplete run
is retained privately and excluded from final evidence.

Keyword export flags/XMP/image metadata, vocabulary import/export, sets,
suggestions, persistent default-parent/shortcut actions, drag/drop/Painter,
unused-tag purge and metadata undo remain pending. Direct Lightroom behavior,
rendered desktop, VoiceOver and macOS 14 runtime remain unverified. Folder sync
and bulk missing-folder relocation are still next in the Library workstream;
they must preserve photo/copy identities, recipes, memberships and folder metadata
and explicitly handle partial availability and destination conflicts.

After freezing the final sources, all twelve native suites passed against the
final packaged engine: **214 assertions**, including 25 keyword checks. The Mac
app targets macOS 14, compiled without Swift warnings and passed ad-hoc signature
verification. Its embedded manifest matches engine generation 6 / catalog schema
8, exposing 61 shared commands. Compilation/state/IPC evidence does not establish
rendered desktop or older-OS compatibility. The current 215-file source scan also
reported no findings; generated fixtures, binaries and receipts remain private.

Warm keyword probe on the same M3 Max / 128 GB / macOS 26.6.2 host, run after
compilation and native regressions completed: 1,010 tags and two assignments per
synthetic photo; 30 read samples and five parent renames. No photographs or workers.

| Complete service/SQL request | 10k photos median / p95 | 100k photos median / p95 |
| --- | ---: | ---: |
| Root tags/counts | 1.700 / 1.862 ms | 1.716 / 3.089 ms |
| Child page and 60-photo selection state | 2.687 / 2.863 ms | 3.007 / 3.182 ms |
| Flat tag search | 2.063 / 2.255 ms | 2.281 / 2.513 ms |
| Parent-tag photo page | 5.436 / 5.893 ms | 20.373 / 21.195 ms |
| Final tagged-photo page | 5.887 / 6.277 ms | 27.495 / 28.494 ms |
| Keyword-name photo filter | 5.509 / 5.881 ms | 20.576 / 21.840 ms |
| Qualified photo metadata | 1.079 / 1.195 ms | 1.067 / 1.116 ms |
| Parent rename with affected photo revisions | 25.180 / 30.191 ms | 286.228 / 395.111 ms |

Renames affect 1,000 / 10,000 photos respectively. Peak process RSS was 40.77 /
58.08 MB, with zero worker RSS. Metadata-only setup through production triggers
took 1.598 / 15.907 seconds (one sample), excluding file import and EXIF. Query
plans use the parent and assignment covering indexes. These measurements exclude
IPC, desktop presentation and RAW processing; large metadata writes still need
background jobs. Reproduce with `tests/keyword_probe.py`.

### Missing-folder relocation increment

Schema v9 stages a complete missing folder subtree into durable, indexed plans.
Each scan processes at most 60 physical originals outside the catalog lock,
verifying known content hashes and reporting unindexed files, absent files and
destination collisions separately. Native **Find Missing Folder…** provides a
replacement directory picker, scan progress, paged issues, explicit application,
cancellation and **Resume Folder Relocation…** after closing/restarting.

Before application, bounded stat checks compare the scanned inode/device/size/mtime
and directory identity. Source-family/index/folder revisions are revalidated. One
transaction remaps paths and counts while preserving photo/copy IDs, recipes,
keywords, folder/collection stacks, versions and frozen export settings. Eligible
job source paths follow the family; an affected running export or occupied image
slot defers application for explicit retry. Original files are read-only. New
folder locations inherit IDs; existing destination nodes retain their IDs and
merge favorites, preferring existing color labels. One active plan and 32 terminal
receipts are retained; staging is removed when a plan finishes or is cancelled.

The final Python suite passed **230 tests, no skips**, including required actual
Metal execution and the pinned real NEF fixture. Sixteen relocation tests cover
hash mismatch, destination collisions, merge/counts, copies/metadata/stacks/jobs,
late file changes, source reappearance, export admission, responsive scan/final
validation cancellation, commit rollback, populated v8 migration rollback,
interrupted scans and a 129-original plan backed up/resumed across page boundaries.
Native source-engine validation passed **17 assertions** for the new workflow.

All **13 native suites passed 231 assertions against the final packaged engine**.
The self-contained Mac build compiled with a macOS 14 deployment target, passed
ad-hoc signature verification and embedded the exact final source digest (engine
generation 7, catalog schema 9, 66 tools). Public source audit passed for 222 files;
catalogs, photographs, binaries and private receipts remain excluded. These checks
do not establish macOS 14 runtime or rendered desktop acceptance.

A separate final packaged-engine probe reconnected a generated copy of the pinned
10,656,312-byte Nikon D3S NEF, including its virtual copy and two already queued
export snapshots. Both full-size 4284×2844 outputs (16-bit TIFF and JPEG) completed
with embedded ICC profiles and positive Metal tile counters. The original fixture
and generated source hashes stayed identical. The two exports plus validation
took 2.272 seconds and the reported worker peak was 275.4 MB; native regression
compilation was running concurrently, so this is integration evidence rather than
a controlled throughput comparison. Hash verification took 7.753 ms with warm OS
cache after copying/indexing. The pixel cache started cold and could be reused by
the second variant. Reproduce with `tests/relocation_raw_probe.py`.

Synthetic metadata results on M3 Max / 128 GB / macOS 26.6.2, with no concurrent
build/test workload. Each catalog has 1,001 folders; the replacement root exists
but all photos are missing, so no hashes or pixels are read. A concurrent reader
requests a 60-photo page every 20 ms after its previous response:

| Measurement | 10k originals | 100k originals |
| --- | ---: | ---: |
| Stage plan (one sample) | 26.543 ms | 288.143 ms |
| Complete scan | 673.469 ms | 15,047.709 ms |
| Scan page median / p95 | 3.527 / 7.125 ms | 8.665 / 11.605 ms |
| Apply with final validation | 492.346 ms | 6,469.708 ms |
| Atomic SQL commit, included above | 153.194 ms | 3,093.090 ms |
| Concurrent browse median / p95 | 4.745 / 5.628 ms | 5.474 / 10.546 ms |
| Longest concurrent browse wait | 140.600 ms | 3,094.158 ms |
| Peak process RSS | 41.42 MB | 74.78 MB |

The scan comprised 167 / 1,667 requests; concurrent reads numbered 33 / 554.
Worker RSS remained zero. Metadata setup took 2.392 / 23.319 seconds. The final
commit necessarily holds the catalog lock and creates a visible multi-second
pause at 100k scale; responsiveness during scanning must not conceal that tail.
Maintained issue counts and a partial issue index avoid repeatedly counting or
walking the complete staged tree. The earlier 100k implementation took 17.354
seconds for scanning; these are single runs, not a statistical throughput claim.
Reproduce with `tests/relocation_probe.py`. No RAW, hash throughput, IPC or desktop
performance is inferred from these results.

Remaining acceptance includes rendered picker/sheet interactions, keyboard and
VoiceOver, macOS 14 runtime, Lightroom comparisons, overlapping old/new trees,
catalog photo collision resolution and external-client source recovery after a
folder ID is merged away. The initiating native source falls back to the result
root when merged. Folder synchronization, physical move/rename and empty-folder
workflows remain separate incomplete features. This increment is not full folder
or Lightroom parity.


### Folder synchronization increment

Schema v10 adds a durable recursive scan and review plan. The native folder menu
starts **Synchronize Folder…**; individual files, a change category or a folder
subtree can be selected. New files are referenced in place, missing source families
can explicitly be removed from the catalog, and supported external metadata can
be read onto masters. Removal defaults off and removes copies/edits/snapshots/
memberships together; original files and export snapshots/receipts are preserved.
Copies retain independent descriptive metadata and recipes. Capture clocks remain
source-wide, including timezone provenance and exact fractional precision.

Directory discovery is capped at 256 entries per request; file scans and review
pages at 60 originals. Filesystem and XMP reads run outside the catalog lock.
Restarted directory iterations replay into unique staging rows, and explicit
file deselections survive interrupted application and backup/restore. Late file,
directory, sidecar, source-family and applicable edit changes prevent application.
Read errors are distinct from missing files. Image/export contention retains the
review for explicit retry. Cancellation discards staging unless the final atomic
transaction already committed; uncertain native responses read back the receipt.

Read-only XMP supports title, caption, copyright, integer rating, standard color
labels and hierarchical/flat keywords. Standard TIFF/JPEG/PNG packets and adjacent
sidecars are bounded; sidecar properties override embedded properties and absent
properties do not clear catalog fields. Unsupported custom labels and Adobe
Develop settings are shown as notes. XML document types/entities and malformed or
unrepresentable supported values are rejected. No pixel workers or hashes are
required for synchronization.

Final Python regression: **276 passed, no skips**, with the pinned real NEF and
required Metal execution. All **14 native suites passed 248 assertions against
the final packaged engine**, including 17 folder-sync checks. Coverage includes
file selection, complete camera-clock/fraction presentation, independent copy
metadata, default retention versus explicit family removal, resume/cancel and
stale-response rejection. The Mac 14-target build and local ad-hoc signature
verification passed; the embedded source manifest matches generation 8 / schema
10 / 72 tools. Public source and extracted source-only archive checks passed for
232 files. These state/IPC checks do not verify rendered desktop interaction.

A packaged-engine probe used the same pinned Nikon D3S NEF from the relocation
increment, copied into a private generated directory. Synchronization discovered
the RAW and read a generated XMP sidecar; Adobe Develop settings were reported and
left unapplied. A second sync changed the master's title while preserving copy
metadata and frozen export jobs. Full-size 4284×2844 TIFF16/JPEG exports had ICC
profiles and positive Metal dispatch, and fixture/copy hashes stayed identical.
Discovery plus application took 26.980 ms; two exports took 2.156 seconds with
275.0 MB worker peak. Metadata reads were warm, pixels started cold and the second
variant could reuse decoded data. Native compilation ran concurrently, so these
are integration diagnostics, not controlled processing benchmarks. Reproduce with
`tests/folder_sync_raw_probe.py`.

Synthetic warm measurements on the same macOS 26.6.2 arm64 / 128 GB host, without
concurrent build/test workloads. Each input catalog has 1,000 missing leaf folders,
all originals missing except one empty placeholder, and 10% new empty PNG
placeholders. The probe explicitly imports all new files and removes all missing
families, while a concurrent reader requests a 60-photo page every 20 ms.

| Operation | 10,000 originals + 1,000 new | 100,000 originals + 10,000 new |
| --- | ---: | ---: |
| Prepare plan | 35.919 ms | 608.872 ms |
| Complete scan | 1331.938 ms | 13682.675 ms |
| Scan request median / p95 | 5.922 / 10.444 ms | 6.106 / 10.839 ms |
| Validate and apply | 647.841 ms | 7306.886 ms |
| Atomic catalog transaction | 229.364 ms | 3190.742 ms |
| Concurrent browse median / p95 | 5.028 / 7.715 ms | 5.597 / 7.229 ms |
| Worst concurrent browse | 224.826 ms | 3200.638 ms |
| Peak process RSS | 43.73 MB | 70.16 MB |
| Image-worker memory | 0 | 0 |

Scan request counts were 189 / 1,875; browse samples were 55 / 545. SQL profiling
identified repeated staging-page sorting: dedicated plan/ID indexes reduced
the 100,000-row transaction from 10.880 to 3.191 seconds and complete application
from 24.637 to 7.307 seconds. The final transaction still blocks catalog reads for
about 3.2 seconds at this scale. This remains a performance gap; short scan pages
do not establish nonblocking application. Reproduce with tests/folder_sync_probe.py.
These are metadata/stat/SQLite timings, not RAW decode speed, IPC or desktop latency.

Remaining synchronization parity includes the full Import Dialog with thumbnail
selection and duplicate policy, missing-empty-folder removal, all supported image
containers, extended JPEG XMP, complete IPTC/ACR/Adobe Develop metadata, custom label
sets and XMP writing. Extreme metadata payloads across broker pages still need
acceptance. Rendered desktop, keyboard/VoiceOver and macOS 14 runtime remain
unverified. Physical folder move/rename and the rest of the non-AI inventory stay
in scope.
