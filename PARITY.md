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

- [Hard-drive Add/Copy/Move import, Grid/Loupe and checked selection](https://helpx.adobe.com/lightroom-classic/desktop/import-photos/import-photos-video-catalog.html)
- [Duplicate criteria, preview choices and import-time options](https://helpx.adobe.com/lightroom-classic/desktop/import-photos/photo-video-import-options.html)
- [Previous Import source](https://helpx.adobe.com/lightroom-classic/desktop/viewing-photos/view-photos.html) and [automatic source selection preference](https://helpx.adobe.com/uk/lightroom-classic/desktop/import-photos/file-import-formats-settings.html)
- [Camera/card import workflow](https://helpx.adobe.com/lightroom-classic/desktop/import-photos/importing-photos-lightroom-basic-workflow.html)
- [Workspace and module responsibilities](https://helpx.adobe.com/nz/lightroom-classic/help/workspace-basics.html)
- [Collections, smart collections and collection sets](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/photo-collections.html)
- [Smart collection criteria](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/smart-collections-criteria-in-lightroom-classic.html)
- [Develop tools](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/develop-module-tools.html)
- [Tone Curve controls and channels](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/image-tone-color.html)
- [Color Mixer](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/color-mixer.html) and [Black & White Mix](https://www.adobe.com/learn/lightroom-classic/web/convert-photo-black-white)
- [Loupe, Compare and Survey](https://helpx.adobe.com/lightroom-classic/desktop/viewing-photos/browse-compare-photos.html)
- [Keyboard shortcuts](https://helpx.adobe.com/lightroom-classic/desktop/introduction-to-lightroom-classic/keyboard-shortcuts.html)
- [Photo stacks and source boundaries](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/grouping-photos-stacks.html)
- [Stacking shortcuts, Adobe's Julieanne Kost](https://jkost.com/blog/2024/07/stacking-similar-photos-in-lightroom-classic.html)
- [Folder hierarchy, subfolder inclusion and synchronization](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/create-folders.html)
- [Missing-photo and missing-folder relinking](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/locate-missing-photos.html)
- [Metadata storage and supported workflows](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/metadata-basics-actions.html)
- [Metadata presets, selective fields and Painter application](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/advanced-metadata-actions.html)
- [IPTC Photo Metadata Standard 2025.1](https://www.iptc.org/std/photometadata/specification/IPTC-PhotoMetadata-2025.1.html) and [machine-readable property mappings](https://iptc.org/std/photometadata/specification/iptc-pmd-techreference_2025.1.json)
- [XMP basic properties](https://developer.adobe.com/xmp/docs/xmp-namespaces/xmp/) and [Dublin Core properties](https://developer.adobe.com/xmp/docs/xmp-namespaces/dc/)
- [Hierarchical keywords, synonyms and export options](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/keywords.html)
- [Keyword shortcuts, Painter and keyboard behavior, Adobe's Julieanne Kost](https://jkost.com/blog/2024/07/working-with-keywords-in-lightroom-classic-2.html)
- [Rating, flag and label Painter workflows](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/flag-label-rate-photos.html)
- [Target Collection Painter, Adobe's Julieanne Kost](https://jkost.com/blog/2024/06/organizing-photos-using-collections-in-lightroom-classic.html)
- [Painter shortcuts and Option removal](https://jkost.com/blog/2019/10/using-the-painter-tool-in-lightroom-classic.html)
- [Library rotation, flipping and Painter options](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/photos.html)
- [Preset storage locations and catalog storage option](https://helpx.adobe.com/lightroom-classic/desktop/kb/preference-file-and-other-file-locations.html)
- [Develop preset creation, groups, favorites, selected settings and application](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/apply-presets.html)
- [Firsthand dictionary import behavior and preserved existing attributes](https://community.adobe.com/questions-675/importing-keywords-into-lightroom-classic-as-non-exported-keywords-1638903)
- [Firsthand CSV field layout and tab indentation](https://community.adobe.com/questions-675/lightroom-classique-15-3-unable-to-import-keywords-from-csv-file-1560047)
- [Export metadata and hierarchy settings](https://helpx.adobe.com/lightroom-classic/desktop/export-photos/export-files-disk-or-cd.html)
- [XMP specifications, including Part 3 storage and Extended JPEG](https://developer.adobe.com/xmp/docs/xmp-specifications/)

## Feature inventory

“Partial” means an implementation exists, with important workflow or verification
gaps. Nothing below is full Lightroom parity merely because historical tests pass.

| Area | Current implementation | Remaining acceptance / work |
| --- | --- | --- |
| Import and catalogs | Partial: durable Add review with checked selection, Grid/Loupe source previews, subfolder choice, suspected duplicates, bounded sorting/filtering, XMP descriptions, captured import-time Develop/metadata presets and keyword additions, cancellation/restart, durable Previous Import source with automatic navigation preference, referenced originals and backup/restore | Copy/Move/Copy as DNG, destinations/rename/backup, saved import configurations, preview policies, cards/tethering, progressive Current Import, catalog switching/merge and desktop/reference acceptance |
| Library navigation | Partial: bounded grid/filmstrip, folder tree/search/favorites/labels, durable missing-folder relocation and folder synchronization, direct/recursive sources, filters/sorting, regular/smart/Quick collections and nested sets | Multi-source selection, complete sync Import Dialog/duplicate policy, folder move/rename, relocation overlap/collision handling, collection drag/drop/color labels, full smart criteria/import-export, source-selection memory, desktop acceptance |
| Organization | Partial: duplicate/missing detection, hierarchical keywords/synonyms/export flags/Will Export preview, text/CSV vocabulary exchange and manual person tags, custom nine-slot keyword sets/recent entries/shared or catalog storage, multi-keyword shortcuts and keyword/rating/flag/label/target-collection/rotation/Develop-preset/metadata-preset Painter strokes, independent catalog rotation/flips, title/caption/copyright plus thirty IPTC fields, selective metadata presets, labels, batch metadata, virtual copies, manual/split/capture-time scoped stacks | Keyword policy/file and preset reference acceptance, built-in sets/suggestions/undo, Painter desktop acceptance, IPTC Extension and complete metadata parity, stack interaction acceptance, rename and sidecars |
| Culling | Partial: Loupe/Compare/Survey, linked detail, anchored page selection | Desktop acceptance, cross-page selection, Develop reference view, auto advance, persistent workspace state |
| Basic development | Partial: light/WB/color, eight-band HSL and B&W Mix with selective resets/sync | Calibrated absolute WB, eyedropper, texture/clarity/dehaze, targeted adjustment, Point Color, Auto B&W mix, color grading and Adobe processing/reference acceptance |
| Curves and profiles | Partial: interactive RGB/channel point curves with temporary previews, legacy luminance curve, LUT/ICC | Four-region parametric controls/splits, targeted adjustment, curve exchange, camera/profile browser, Adobe processing and rendered/reference acceptance |
| Detail and optics | Partial: noise/sharpen, manual lens | Complete manual detail controls, automatic lens profiles, bounded full-resolution acceptance |
| Geometry | Partial: crop/straighten/perspective, independent rotation/flips with attached masks and displayed crop ratios | Interactive retained handles, guided transforms, full crop state and rendered/reference parity |
| Local editing | Partial: radial/gradient/brush/luma | Mask list/edit/reorder/intersection, range masks, clone/heal, red-eye (non-AI) |
| History and presets | Partial: 50-step Develop undo, separate 50-batch orientation undo, shared named snapshots, partial Develop presets/groups/favorites/shared or local storage, batch/Painter and reviewed-import application | Unified Undo/Redo, navigable history, preset hover preview/Amount/ISO adaptation/Adobe exchange and reference acceptance |
| Preview/performance | Partial: Metal, proxies, 1:1 viewport, developed thumbnail fast path | Real-RAW catalog/slider latency, offline previews, cache controls and desktop acceptance |
| Export | Partial: JPEG/16-bit TIFF, ICC, durable jobs with frozen catalog/rights IPTC XMP and keyword hierarchy options | Presets, complete EXIF/IPTC Extension/GPS metadata policies, watermark, additional formats, publish workflows |
| External editing and video | Missing | External-editor setup and derivative round trips; supported video import/playback, frame capture, trimming and export |
| Merge | Missing | Non-AI HDR merge and panorama with bounded resources and reference acceptance |
| Map | Missing | GPS metadata, map navigation, track import, location editing with explicit persistence |
| Book | Missing | Templates, layouts, typography, PDF/JPEG output; external fulfillment is a separate integration |
| Slideshow | Missing | Layout, timing, playback, audio, slideshow export |
| Print | Missing | Contact sheets/packages, physical sizing, native print/ICC workflow |
| Web | Missing | Local gallery templates and export; publishing requires explicit destination |
| Platform/accessibility | Partial: Mac 14 target, Mac 26 historical checks | Legacy upgrade recovery, current desktop checks, macOS 14, keyboard/VoiceOver, color management; Windows remains future |

## Active increment

RGB/channel point curves, followed by further import, Library and Develop workflows.
Rendered Mac/reference acceptance,
Copy/Move/DNG, complete IPTC, Adobe exchange, unified Undo/Redo and the full inventory
stay in scope. This does not complete product parity.

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

Continue with bounded vocabulary-browser metadata, keyword sets and vocabulary exchange, complete synchronization import options, relocation edge cases, stack ordinal badges and
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

### Keyword export and frozen metadata increment

Keyword forms persist Include on Export, Export Containing Keywords and Export
Synonyms. A read-only Will Export sheet shows the active photo's resolved words
and hierarchy in 60-item pages. Excluded names/synonyms are omitted, including
from hierarchy paths; containing traversal stops at each ancestor's policy.
Duplicate words are folded consistently while assignments retain their stable IDs.
The Export sheet offers None, Copyright Only, or Catalog Descriptions and Keywords,
plus optional hierarchy. These choices do not claim complete Lightroom metadata
policy support or arbitrary checkbox-combination equivalence.

Submission freezes descriptive fields, keyword rules and resolved arrays together
with recipes/options and the idempotency receipt. Existing queued jobs migrate
with empty metadata instead of inheriting later edits. Queue pages expose compact
counts/digests rather than large packets. JPEG writes standard or Adobe Extended
XMP; TIFF writes tag 700. TIFF descriptions no longer contain internal recipes or
source/asset paths. ICC and pixel processing remain independent of metadata.
Extended JPEG reads validate identifiers, sizes, chunk continuity and checksums.
XML-invalid or overlarge snapshots fail the entire submission before image work.

Required-Metal Python regression: **298 passed, no skips**, including the pinned
Nikon D3S NEF, exact decoded-pixel/ICC comparisons, UTF-8 XMP, extension corruption,
atomic invalid-batch rollback, genuine v10 migration/rollback, backup/restore and
a snapshot larger than 256 KiB through a real image worker.

All **15 native suites passed 264 assertions against the final packaged engine**,
including 16 export-metadata checks. The macOS 14-target build and local ad-hoc
signature verification passed on macOS 26.6.2; its embedded manifest matches
generation 9 / schema 11 / 73 tools. The public source scanner checked 239 files
without findings. State/IPC checks do not establish desktop or older-OS acceptance.

The final packaged engine also passed the real Nikon D3S synchronization/copy
probe. Full-size 4284×2844 JPEG/TIFF16 retained each variant's submitted title,
rating, public keyword and synonym after later catalog changes; a private ancestor
was absent. ICC profiles and actual Metal dispatch were present, and original and
private-copy hashes stayed unchanged. Discovery/application took 25.856 ms, two
exports took 2.265 seconds, and worker peak was 275.7 MB. Metadata reads were warm,
pixels started cold and the second variant could reuse decoding. Native compilation
ran concurrently; these timings are integration diagnostics, not throughput claims.

Synthetic warm metadata/SQLite timings on macOS 26.6.2 arm64, 128 GB RAM. Both
catalogs have 1,010 keywords and two direct assignments per photo; leaf synonyms
expand exported words. Preview and queue reads use 30 samples; each submission
size uses five samples. Image jobs remain paused throughout.

| Operation | 10,000 photos median / p95 | 100,000 photos median / p95 |
| --- | ---: | ---: |
| Keyword preview | 1.541 / 1.707 ms | 1.571 / 6.840 ms |
| Hierarchy preview | 1.522 / 1.666 ms | 1.548 / 1.849 ms |
| Submit 60 frozen exports | 10.284 / 10.460 ms | 10.718 / 10.779 ms |
| Submit 1,000 frozen exports | 116.593 / 141.014 ms | 125.168 / 126.787 ms |
| Read 60 public jobs | 3.633 / 4.194 ms | 3.666 / 4.245 ms |
| Peak process RSS | 52.84 MB | 59.72 MB |

The 60-job public JSON was 43,396 / 43,522 bytes while all 5,300 submitted snapshots
used 1,664,250 bytes per catalog. No workers ran. These measurements exclude real
photographs, RAW processing, IPC and desktop latency. Reproduce with
tests/export_metadata_probe.py.

Remaining metadata parity includes camera EXIF, legacy IPTC IIM, full IPTC/contact/
GPS policies, custom labels, sidecar writing and vocabulary exchange. Large exported
synonym expansions can exceed the reader's 100 direct-keyword assignment limit;
hierarchy/flat-keyword reimport semantics still need reference acceptance. Keyword
sets, suggestions, undo and Painter remain pending. Rendered Mac interactions,
VoiceOver and macOS 14 runtime are unverified; build/state tests do not establish
those checks. The complete non-AI inventory remains in scope.

Follow-up evidence: 60 generated 4×4 PNGs, each with a valid 5,000-character XMP
caption containing four-byte Unicode, produce a ready sync plan with 60 metadata
updates. Its serialized response is 1,215,035 bytes, exceeding the 1,048,576-byte
broker limit. This is a confirmed review/transport gap, not an image-processing
failure. Keep the full scanned values in staging; provide compact list summaries
and bounded detail access before claiming this edge case is accepted.

### Bounded synchronization metadata review increment

The reproduced response-size gap now has compact summaries and explicit complete
detail access. SQLite omits patches above 4 KiB from 60-row list queries, avoiding
eager deserialization of sixty large metadata trees. The metadata_deferred marker
is explicit; the staged data is retained intact. get_folder_sync_metadata reads
one captured plan/item/revision, returning full descriptive values and twenty
complete keyword paths per page. Wrong, removed or changed plan/item references
cannot silently replace the original review. Mac review opens a read-only detail
sheet with pagination and visible errors.

The original 60-photo fixture now returns **15,875 bytes** for its summary and
**20,290 bytes** for one complete description, versus **1,215,035 bytes** for the
old summary. All sixty values remain staged, and the 5,000-character four-byte
Unicode description reads back exactly. This is response-size evidence, not a
RAW throughput or desktop responsiveness benchmark.

The full required-Metal Python run passed **300 tests, no skips**, using the pinned
real NEF. New real-broker coverage scans, reviews and applies sixty long captions,
checks unchanged originals and rejects stale/removed detail requests. Another case
pages 100 maximal 32-level, 120-character Unicode keyword paths without dropping
any values; each detail response stays below 512 KiB. The source-engine native
folder-sync suite passed **24 assertions**, including complete field/keyword
readback, pagination, wrong-response rejection and application.

The final macOS 14-target app built and passed local ad-hoc signature verification
on macOS 26.6.2. Its manifest matches generation 10 / schema 11 / 74 tools. Four
affected suites passed **65 assertions against the packaged engine**: native state,
connection/handoff, folder synchronization and export metadata. The previous
increment's 15-suite/264-assertion evidence remains historical, not a claim that
all fifteen suites were rerun for this fix. Public source checks covered 241 files
without findings.

This closes the reproduced synchronization review transport case. A follow-up
fixture with 100 maximal 32-level Unicode keyword paths applies successfully, but
get_photo expands both display paths and tag paths into **3,054,478 bytes**, above
the same broker limit. list_photos and photo_summaries remain compact at 664 and
515 bytes for that one-photo fixture. Full-photo keyword access/editing needs a
paged contract before claiming the complete extreme-keyword workflow. Full Import Dialog,
reference-app metadata semantics, rendered desktop/VoiceOver, macOS 14 runtime
and the rest of the non-AI inventory remain pending.

### Complete keyword details and identity editing increment

Photo details always retain all keyword IDs and the assignment count. Small path
arrays remain inline; a 32 KiB description budget explicitly defers large path
arrays. A numeric recursive SQL query measures escaped ancestor-name lengths
without materializing every repeated long path for routine recipe/detail reads.
Revision-bound twenty-path pages return complete names. The Mac inspector opens
the paged review, while the metadata form provides a paged keyword picker with a
local replacement draft. Additional typed paths are still supported. Only saving
the parent form changes photo assignments; unchanged single-photo assignments and
unchecked batch fields remain intact.

Identity replacement validates all photo revisions, all existing IDs, new path
ambiguity and the combined 100-assignment limit inside one transaction. Failure
rolls back new tags as well as metadata. Receipts carry compact identities and
defer state, preserving independent recipe revisions. Legacy literal names are
retained by identity instead of reparsing display separators.

The exact previously failing fixture now returns **1,968 bytes** for get_photo,
including all 100 IDs, versus **3,054,478 bytes** previously. A complete twenty-path
page is 305,619 bytes. Real-broker tests cover all five pages, recipe/rating replies,
batch replacements and new typed paths, independent virtual copies and actual
JPEG output. Required-Metal Python regression passed **303 tests, no skips**, with
the pinned Nikon D3S NEF. The source-engine native keyword-detail suite passed
**21 assertions**, including draft-only selection, complete readback, stale/wrong
reply rejection and metadata saves that preserve the local recipe revision.

The final macOS 14-target app built and passed local ad-hoc signature verification
on macOS 26.6.2. Its engine manifest matches generation 11 / schema 11 / 76 tools.
All sixteen native suites passed **292 assertions against the packaged engine**.
Build and regression logs contain no compiler warnings or errors. Public source
checks covered 246 files without findings, including the extracted source archive.
These checks do not establish rendered desktop behavior or macOS 14 runtime support.

Warm synthetic measurements on macOS 26.6.2 arm64, 128 GB RAM. Each catalog has
1,141 tags; ordinary rows have two assignments and one row has 100 maximal
32-level Unicode paths. Reads use 30 samples, sixty-photo replacements five.

| Operation | 10,000 photos median / p95 | 100,000 photos median / p95 |
| --- | ---: | ---: |
| Ordinary photo detail | 1.168 / 1.276 ms | 1.182 / 3.622 ms |
| Deep-keyword photo detail | 3.875 / 4.132 ms | 3.943 / 4.015 ms |
| First twenty-path page | 10.351 / 11.257 ms | 10.730 / 11.560 ms |
| Last twenty-path page | 14.441 / 17.431 ms | 15.120 / 18.336 ms |
| Twenty selected keyword choices | 4.118 / 4.459 ms | 4.115 / 4.353 ms |
| Name-search choices | 1.582 / 1.698 ms | 1.664 / 1.853 ms |
| Replace sixty photos, including revision read | 79.699 / 83.738 ms | 81.716 / 84.127 ms |
| Peak process RSS | 53.78 MB | 63.59 MB |

Deep photo responses were 2,110 / 2,111 bytes in those separately named fixtures;
path and picker pages stayed below 316 KiB. No image workers ran. Timings include
in-process service/SQLite work and exclude photographs, IPC and desktop rendering.
Reproduce with tests/keyword_details_probe.py. A separate valid vocabulary fixture
with sixty maximal-depth children and thirty maximal Unicode synonyms per child
produces **1,844,675 bytes** from list_keywords, above the broker limit. The new
twenty-row identity picker stays at **315,320 bytes** for those same choices.
The existing vocabulary browser/editor needs compact summaries plus complete
on-demand metadata before that separate case can be accepted.
Keyword sets, vocabulary exchange, suggestions, metadata undo and Painter remain
pending, along with rendered desktop/VoiceOver, macOS 14 runtime and the remaining
non-AI inventory.

### Complete bounded vocabulary increment

Sixty-row keyword pages retain direct counts, selection state, stable identities
and export flags. Rows above 8 KiB explicitly defer path/synonym values as null,
with abbreviated presentation labels. No stored values are shortened. get_keyword
returns complete paths, authoritative parent paths, all synonyms and options at
the captured vocabulary revision. Request-local ancestor caching avoids repeated
lookups for shared branches without caching across mutations.

Mac editing resolves full values before opening the form; a deferred summary
cannot be used to save empty synonym defaults. Parent navigation keeps one page
and fetches full labels before selection. Wrong identities/revisions, superseded
edit requests and dismissed picker reads are rejected. Full parent names are
selectable in a bounded scroll area, including legacy names containing display
separators. Editing drafts and parent browsing do not mutate catalog data.

The exact sixty-child/30-synonym fixture now returns **130,295 bytes**, compared
with **1,844,675 bytes** before this fix. Complete details for one child use
**45,579 bytes**, retaining all 32 path components and 30 synonyms. The new real
broker regression covers 67 maximal children across two pages, full detail
readback, synonym search, selected counts, rename/delete and original safety.
Source-engine native vocabulary and keyword suites passed **49 assertions**.

Warm synthetic dictionary measurements on macOS 26.6.2 arm64, 128 GB RAM; thirty
samples each. Both dictionaries add 31 shared ancestors and 61 maximal-depth
Unicode children with thirty synonyms per child to the ordinary tag count.

| Operation | 10,000 ordinary tags median / p95 | 100,000 ordinary tags median / p95 |
| --- | ---: | ---: |
| Sixty-root page | 2.427 / 2.810 ms | 4.030 / 4.640 ms |
| Sixty deep children | 5.795 / 5.897 ms | 5.837 / 6.185 ms |
| Final child page | 1.949 / 2.074 ms | 1.960 / 2.067 ms |
| Synonym substring search | 7.377 / 7.631 ms | 21.104 / 21.801 ms |
| Complete keyword detail | 1.394 / 1.604 ms | 1.391 / 1.477 ms |
| Peak process RSS | 43.03 MB | 42.72 MB |

Deep list responses remained below 131 KiB and single details below 46 KiB in
these separately named fixtures. No workers ran. These are in-process service/SQL
measurements, excluding photographs, IPC and desktop rendering. Reproduce with
tests/keyword_vocabulary_probe.py. Required-Metal Python regression passed **305
tests, no skips**, with the pinned Nikon D3S NEF.

The final macOS 14-target app built and passed local ad-hoc signature verification
on macOS 26.6.2, with a matching generation 12 / schema 11 / 77-tool engine manifest.
Five affected native suites passed **96 assertions against the packaged engine**:
complete vocabulary, keyword organization, export metadata, photo keyword details
and connection/handoff. The previous sixteen-suite/292-assertion result is retained
as historical evidence; this increment did not rerun every unaffected native suite.
No compiler warnings or errors were reported. Public source checks passed for 250
files, including the extracted source archive. A refreshed remote/branch inspection
found no branches outside the development branch's merged history.

Keyword sets and vocabulary exchange remain next, along with suggestions, Painter
and metadata undo. Adobe documents nine-slot keyword sets and preset storage
outside the catalog by default, with an explicit catalog-storage option. Preserve
that distinction when introducing a portable preset repository; do not equate
catalog-only tag groups with complete keyword-set parity. Preset selection,
recent keywords, built-in sets, rename/delete, keyboard behavior and cross-catalog
storage all need separate acceptance. Rendered desktop/VoiceOver, macOS 14 runtime
and the remaining non-AI inventory are still unverified or incomplete.

### Keyword dictionary exchange increment

The Mac Metadata menu and Keyword List expose UTF-8 dictionary import and text/CSV
export. Input is copied with size/identity checks and a SHA-256 receipt outside the
catalog lock. Disk-backed SQLite staging validates every hierarchy row, synonym
and CSV option before a single additive catalog transaction. It preserves existing
keyword IDs, spellings, synonyms, options and all photo assignments/revisions.
Repeated import of an unchanged dictionary adds nothing and does not advance the
vocabulary revision. Invalid input or a stale revision commits nothing.

Dictionary output includes the complete hierarchy and synonyms independently of
photo export filtering. CSV also retains the three export flags and manual person
classification; text represents Include on Export and reports other nondefault
options it cannot encode. Schema 12 adds the manual person flag with default false,
without running recognition. Native forms can edit that flag. Existing and symlink
destinations are preserved, and malformed/unrepresentable hierarchy data cannot
publish a partial file. Output is generated into a local snapshot under the catalog
lock, then written and atomically linked at the destination outside that lock.

Official help establishes dictionary exchange and the two formats. Firsthand
Adobe Community reports establish the English four-option CSV header, tab nesting,
and preservation of attributes/synonyms on existing tags. Generated fixtures cover
the implementation's combined format behavior; a complete Adobe-generated/exported
fixture matrix and round trip through Lightroom itself have **not** been verified.
In particular, CSV synonym-row variants, legacy delimiter-containing names and
reference-app merge edge cases remain acceptance work. Native file panels,
rendered interaction, VoiceOver and macOS 14 runtime remain unverified.

Required-Metal Python regression passed **324 tests, no skips**, using the pinned
Nikon D3S NEF. The source-engine native exchange suite passed **23 assertions**.
New tests cover complete option round trips, unchanged originals and frozen jobs,
malformed/oversized input, transaction rollback, genuine schema-11 migration,
backup/restore, collision/symlink protection, compact real-IPC receipts and source/
destination I/O that releases the catalog lock.

The final macOS 14-target app built and passed local ad-hoc signature verification
on macOS 26.6.2. Its manifest matches generation 13 / schema 12 / 79 tools. Five
related native suites passed **98 assertions against the packaged engine**:
dictionary exchange, keyword organization, complete vocabulary, export metadata
and connection/handoff. The final source/build/native logs have no compiler warnings
or errors; an earlier test-only string concatenation compile failure was corrected
before the passing source and packaged runs. Public source checks covered 255
files without findings, including the extracted source archive. Remote refresh
again found no unmerged branches.

Performance testing exposed a staging lookup that could not use its expression
index. Matching the lookup to the indexed parent expression reduced the observed
10,000-leaf parsing time from 1,739.405 ms to 67.069 ms. The slow 100,000-leaf run
was explicitly stopped before changing source; its incomplete measurements are
not reported as completed evidence.

Current measurements on macOS 26.6.2 arm64, 128 GB RAM. The freshly generated
UTF-8 file is warm in the OS cache; the initial catalog is new. Each leaf has one
synonym, and each dictionary includes one additional excluded parent.

| Operation | 10,000 leaves | 100,000 leaves |
| --- | ---: | ---: |
| Copy/hash/parse into staging, one run | 67.069 ms | 655.721 ms |
| Initial atomic apply, one run | 99.132 ms | 1,112.378 ms |
| Reimport, median of three | 104.213 ms | 1,051.043 ms |
| Text export, median of three | 41.596 ms | 395.017 ms |
| CSV export, median of three | 47.584 ms | 456.347 ms |
| Text bytes | 380,009 | 3,800,009 |
| CSV bytes | 500,097 | 5,000,097 |
| Peak process RSS | 44.58 MB | 64.38 MB |

No image workers ran. These measurements include local file and service/SQLite
work, excluding photographs, network volumes, IPC and desktop responsiveness.
The initial transaction still holds the catalog lock for its measured duration;
this is not a claim of zero interactive contention. Reproduce with
tests/keyword_exchange_probe.py. Keyword sets, suggestions, Painter, metadata
undo and the remaining non-AI feature inventory are still pending.

### Custom keyword sets and preset storage

Implemented custom nine-slot presets, recent keywords, creation from current
slots, editing/rename, explicit update/save-as-new, deletion, transient Change
drafts and additive slot application. The sidebar and Metadata menu expose
Option-number shortcuts with keypad ordering. Grid targets the captured selection;
other viewing modes use the active photo. Recent entries store nine catalog IDs,
preserving renamed and legacy literal keywords rather than reparsing their labels.
Preset deletion preserves photo assignments. Applying validates preset and photo
revisions, ambiguity and capacity before one transaction commits.

Shared presets use a portable, separately versioned SQLite repository. The
platform path adapter chooses Mac App Support or replaceable Windows/XDG paths;
tests inject isolated roots. The catalog-storage preference changes the repository
without moving existing presets. Catalog-local sets and recent entries survive
backup/restore. Shared and catalog revisions, scope, selected identity and keyword
state bind each mutation token; concurrent writers produce a visible conflict.
Native drafts retain their original token through external refresh, and selection
changes discard them. Thirty preset names and only nine selected slots cross IPC.

This increment follows Adobe's documented custom sets and storage behavior; it
does **not** establish full keyword-set parity. Built-in Outdoor/Portrait/Wedding
contents, `.lrtemplate` import/export, suggestions, Painter, cycling shortcuts,
precise recency ordering and reference-application draft semantics remain open.
Real Option-number dispatch, text-field interference, rendered controls, VoiceOver
and macOS 14 runtime were not verified. No desktop automation was attempted.

Validation: **336 Python tests passed, no skips**, with the pinned Nikon D3S NEF
and required Metal dispatch. Twelve set-specific tests cover concurrent catalogs,
scope persistence, stale tokens, legacy recency identities, malformed/ambiguous
application, capacity and injected SQL rollback, maximum slot payloads, genuine
v12 migration rollback, backup/restore and future shared-schema refusal. A test-only
variable reuse and an outdated restored-schema assertion were corrected before the
passing full suite; the initial non-escalated IPC run could not create its socket.

The Mac app builds for macOS 14 and passes local ad-hoc signature verification
on macOS 26.6.2. Generation **14**, schema **13**, **83 tools**; packaged manifest
`6f590d5d8982d816771672c1389fe8770b6064b91613a23fdf5b203a7b9d5d71`
matches source. The source-native set suite passes **29 assertions**. Five packaged
suites pass **108 assertions**: sets, keyword organization, complete photo-keyword
details, dictionary exchange and connection/handoff. No compiler warnings/errors
appear in the final build/native logs. The bundled usage guide was refreshed, the
app re-signed and its signature reverified. The keyword-set suite then passed its
29 assertions again against the final artifact. The engine manifest matches source.
Public checks covered 262 source files without findings, including the extracted
archive. Remote refresh found no unmerged branches.

Warm service/SQLite measurements, 30 samples, macOS 26.6.2 arm64 with 128 GB RAM.
Sixty generated 8×8 photos serve as metadata targets; no image worker is started.

| Operation (median / p95) | 10,000 tags / 1,000 presets | 100,000 tags / 10,000 presets |
| --- | ---: | ---: |
| First preset page | 1.165 / 1.361 ms | 1.227 / 1.420 ms |
| Last preset page | 1.181 / 1.340 ms | 1.363 / 1.567 ms |
| Reapply one tag to sixty photos | 5.386 / 5.487 ms | 5.478 / 5.691 ms |
| Recent keyword page | 1.187 / 1.530 ms | 1.390 / 1.623 ms |
| Peak process RSS | 35.58 MB | 37.98 MB |

Repeat application includes captured preset and photo-revision reads; the tag is
already assigned. Setup, first-time creation, IPC, pixels and rendered latency are
excluded. First-page responses are 1,338 / 1,339 bytes for these short labels;
the regression with nine 4,096-character Unicode slots remains below 160 KB.
Reproduce with tests/keyword_sets_probe.py. This is bounded metadata performance,
not a RAW processing or end-to-end UI speed claim.

### Keyword shortcuts and Library Painter strokes

Implemented a persistent multi-keyword shortcut, separate from nine-slot presets.
It can be configured with existing IDs and explicit text paths, assigned from a
Keyword List row, applied through photo context menus or Shift-K in a focused photo
surface, and cleared without deleting vocabulary. A plus identifies shortcut
members. All IDs remain complete; labels page at twenty, including maximal Unicode
hierarchies. Rename preserves identity and subtree deletion prunes affected entries.

Grid Painter supports keywords, ratings, flags and color labels. The native pointer
adapter reports thumbnail intersections without selecting photos; segment tests
cover fast/coalesced drags. Pending targets highlight and mouse-up submits one
transaction. Option at the start of a keyword stroke removes only the shortcut's
IDs. Other attributes clear with explicit None/Unflagged choices. Esc, changed
source/page or invalidated layout discard unsubmitted work. Deferred layout
cancellation carries a stroke identity so it cannot clear a newer gesture.
All photo revisions and assignment capacity validate before writes; each target's
metadata revision increments once. Active rating/flag display refreshes immediately
without adopting a new Develop recipe revision. Recipes, originals and frozen
exports remain unchanged; failures are never automatically replayed.

This increment remained partial Painter parity. The multi-set chooser is covered
by the following increment; inline
keyword autocomplete, metadata/Develop-preset painting, rotation, target collection,
cross-page dragging/autoscroll, precise reference eraser behavior outside keywords,
metadata undo and rendered interaction remain open. Desktop pointer/keyboard
dispatch, cursor geometry, VoiceOver, resizing and macOS 14 runtime were not
verified. The geometry/state suites do not establish those observations.

Validation: **352 Python tests passed with no skips**, using the pinned Nikon D3S
NEF and required Metal dispatch. The Painter regressions cover all four attribute
modes, identity-safe legacy paths, full hundred-keyword payloads, stale shortcut and
photo revisions, missing targets, capacity and injected-SQL rollback, invalid
options, frozen jobs/original bytes and genuine v13 migration/backup. The final
source-native Painter suite passes **36 assertions**, including immediate culling
readback, deferred-cancellation identity and zero redundant highlight publications
for one thousand repeated hits. An initial test-only Swift async
autoclosure compilation error was corrected before the passing suite.

Warm service/SQLite measurements on macOS 26.6.2 arm64, 128 GB RAM. Each catalog
contains equal photo/tag counts, sixty generated 8×8 originals and synthetic
remaining photo rows. Each stroke targets sixty photos; no image worker runs.

| Operation (median / p95, 30 samples except first add) | 10,000 photos/tags | 100,000 photos/tags |
| --- | ---: | ---: |
| Read two-keyword shortcut | 1.234 / 1.407 ms | 1.334 / 1.450 ms |
| First add two keywords, one sample | 5.871 ms | 6.451 ms |
| Reapply two keywords | 5.552 / 6.153 ms | 6.004 / 6.406 ms |
| Erase + add two keywords, two transactions | 11.661 / 12.723 ms | 12.604 / 14.529 ms |
| Read hundred-keyword shortcut | 1.342 / 1.588 ms | 1.444 / 1.656 ms |
| First add one hundred keywords, one sample | 14.949 ms | 15.462 ms |
| Reapply one hundred keywords | 11.094 / 12.255 ms | 12.045 / 15.128 ms |
| Erase + add one hundred keywords, two transactions | 29.941 / 31.132 ms | 31.932 / 35.489 ms |
| Set rating | 4.408 / 6.078 ms | 4.911 / 6.555 ms |
| Peak process RSS | 40.72 MB | 54.12 MB |

Measurements include captured shortcut/target-revision reads and commit. Reapply
uses already-assigned tags; erase/add includes two actual assignment changes.
First-add measurements create assignments to existing vocabulary, not new tags.
Short-label shortcut responses are 248 / 1,244 bytes for two / one hundred IDs.
The regression with one hundred maximal paths pages below 320 KB per response.
Setup, IPC, pixels and desktop latency are excluded. Reproduce with
tests/painter_probe.py; this is metadata performance, not RAW processing parity.

The final Mac app builds for macOS 14 and passes local ad-hoc signature verification
on macOS 26.6.2. Generation **15**, schema **14**, **86 tools**; manifest
`8639705ebe31ebfd63b627550c12392dcdd98ee6324663eb35e2ccb97c91d274`
matches source, and the bundled usage guide matches the current document. The
initial packaged candidate passed six suites / **133 assertions** (Painter,
keyword sets, keywords, complete photo-keyword details, library and connection).
After suppressing repeated highlight publications, the final artifact passes the
three affected suites / **74 assertions**: Painter 36, keywords 25 and library 13.
The portable engine is unchanged by that last native-only improvement; the 352-test
Python and earlier integration results remain applicable within their scope.
Final source/build/native logs have no compiler warnings or errors. Public source
checks cover **269 files** without findings, including the extracted source archive.
Remote refresh again found no unmerged branches. No full-parity or desktop-runtime
acceptance is claimed by these checks.

### Painter multi-set keyword chooser

The native Painter can load keywords from several nine-slot sets in one chooser.
Choose individual slots or Select All in This Set, browse another set, then review
or remove choices before Load Painter. Selection order is preserved and duplicates
are removed within the same identity/text source. The draft holds at most one
hundred choices; an over-capacity Select All preserves the entire prior draft.
The confirmation replaces the shortcut and never tags photos. Cancel, Escape or
putting Painter away invalidate unconfirmed work. Custom slot text is frozen at
selection; Recent Keywords retains stable IDs, including legacy literal separators.

The portable `get_keyword_set` contract previews any set without selecting it,
using the same shared-storage-before-catalog lock order and captured state token.
Only thirty preset names and nine slots are read. Missing/deleted presets and
changed scope, vocabulary, recent entries or preset revisions fail visibly.
Initial native reads bind the shortcut and preset snapshot to the same vocabulary
revision. Dismissal and newer requests reject late replies; a changed shortcut
cannot be overwritten by an old chooser confirmation.

The toolbar and Metadata menu expose the chooser; the Mac pointer responder
handles Shift when keyword Painter has focus. Enabling Painter requests focus,
and returning from the chooser restores it. This wiring and compilation do not
establish rendered focus/keyboard behavior. Actual Shift dispatch, dialog layout,
scrolling, VoiceOver and macOS 14 runtime remain unverified. Existing desktop
automation was not authorized, and no equivalent observation is inferred from
state/IPC tests. Inline autocomplete, built-in Adobe sets, `.lrtemplate` exchange,
remaining Painter attributes and the full module inventory remain open.

The full Python suite passes **359 tests with no skips**, including the pinned
Nikon D3S NEF and required Metal dispatch. Seven added cases cover independent
preview preservation, recent literal-name identities, five kinds of stale state,
and bounded/missing preset pages. The initial native chooser passed 17 assertions;
the final packaged chooser passes **19**, adding stale shortcut confirmation and
dismissed in-flight reads. The Mac app targets 14.0, builds and verifies its local
ad-hoc signature on macOS 26.6.2. Engine generation **16**, schema **14**, **87 tools**;
manifest `30d6907507d7559323f0ff4c8a4832c871af09faeb828b01918caa493f3ec752`
matches source, and its bundled usage guide matches the current document.

Warm service/SQLite measurements after builds/tests finished, 30 samples on the
same macOS 26.6.2 arm64/128 GB host. Sixty generated 8×8 images are metadata
targets only; no image worker runs. Setup, IPC, pixels and rendered latency are
excluded. These are bounded metadata reads, not processing-speed equivalence.

| Operation (median / p95) | 10,000 tags / 1,000 presets | 100,000 tags / 10,000 presets |
| --- | ---: | ---: |
| Preview another set without selecting it | 1.947 / 2.322 ms | 2.102 / 2.476 ms |
| Preview last preset-name page | 1.920 / 2.088 ms | 2.212 / 2.646 ms |
| Read selected preset first page | 1.558 / 1.916 ms | 1.911 / 2.278 ms |
| Read Recent Keywords | 1.623 / 2.139 ms | 1.674 / 1.877 ms |
| Peak process RSS | 38.44 MB | 41.36 MB |

Other-set responses are 1,434 / 1,436 bytes for these short labels. The selector
holds one thirty-name/nine-slot page plus its bounded local draft, regardless of
catalog size. Reproduce using the preview operations in tests/keyword_sets_probe.py.

All six final packaged native suites pass **132 assertions**: chooser 19, Painter
36, keyword sets 29, keyword organization 25, Library 13 and connection/handoff 10.
Final build/native logs contain no compiler warnings or errors. Public checks cover
**271 source files** without findings, including the clean extracted archive.
Remote refresh and local/remote ancestry checks found no unmerged branches.

### Target Collection Painter and membership performance

Painter now adds to the current regular or Quick Collection and uses Option to
remove only touched members. Each stroke captures the target ID, target-state
revision and collection revision at mouse-down, retains that destination label,
deduplicates up to sixty visible hits and submits once at mouse-up. Existing-member
add never toggles a photo off. Cancellation writes nothing. Target switches,
renames, deletion or concurrent membership edits reject the entire old stroke;
no stale gesture is redirected or automatically replayed. Photo metadata changes
are independent and do not cause an unrelated membership conflict.

The native shell reuses `target_membership`; there is no duplicate SQL or new
Painter-specific collection protocol. Membership and ancestor revisions update
in one transaction, including existing stack-cleanup triggers on removal. Virtual
copies remain independent targets. Recipes, photo metadata/revisions, originals
and frozen exports stay unchanged. Painting does not select the touched photos;
removing photos from the displayed target naturally prunes that source/selection,
including its empty state. Membership badges and sidebar state refresh afterward.

The previous membership existence check expanded complete photo details, including
deep assigned keyword paths. It now validates at most sixty IDs in one indexed
query. A regression forbids full photo-detail access for this operation; SQL fault
injection proves rollback of partial membership insertion and ancestor revisions.

Warm service/SQLite measurements on macOS 26.6.2 arm64, 128 GB RAM. Sixty generated
8×8 originals each have one hundred Unicode paths at depth 32 and long descriptive
metadata; remaining photos are synthetic rows. No image worker runs. Samples
include target-state reads and commits, excluding setup, IPC, pixels and UI.
Final optimized measurements ran serially after the earlier tests had finished.

| Operation (median / p95, 30 samples except first add) | Previous, 10,000 photos | Optimized, 10,000 photos | Optimized, 100,000 photos |
| --- | ---: | ---: | ---: |
| First add sixty members, one sample | 193.715 ms | 6.254 ms | 9.852 ms |
| Add sixty existing members | 176.204 / 183.239 ms | 4.574 / 5.147 ms | 4.624 / 5.244 ms |
| Remove + add sixty members, two transactions | 355.462 / 368.688 ms | 10.405 / 12.612 ms | 10.313 / 20.143 ms |
| Peak process RSS | 44.09 MB | 41.97 MB | 54.27 MB |

The repeat-add improvement is about **38.5×** on this specific heavy-metadata
fixture. It is not a general image-processing speed claim. State responses remain
576–578 bytes for these labels. Reproduce with tests/target_painter_probe.py.

Nine domain regressions cover preserved state/jobs/originals, no detail expansion,
four captured-state conflicts, injected failure, stack cleanup and variant scope.
The initial native target-Painter suite passes 17 assertions; a follow-up assertion
also covers the captured destination label after another client changes target.
Rendered pointer/Option behavior and macOS 14 runtime remain unverified.

Rotation follow-through remains open: Adobe documents both rotation and horizontal/
vertical flips in Painter. The current `Recipe.rotation` is a Develop parameter,
applied before crop/coordinate-based masks and cleared by Reset All Adjustments;
simply reusing it would not prove Library orientation parity. The next orientation
work must explicitly address catalog state, virtual copies, history/reset behavior,
frozen exports, thumbnail/viewport dimensions and mask/crop coordinate mapping,
with an asymmetric image fixture and bounded strip/Metal checks. No new rotation
or flip mode is claimed by this target-collection increment.

A [firsthand reference discussion](https://community.adobe.com/questions-675/lightroom-classic-reset-does-not-remove-rotations-965529)
reports that Photo Rotate/Flip survives Develop Reset and is absent from Develop
History. That observation was made on Windows; Mac behavior still needs reference
acceptance. The implementation must not silently equate Library orientation with
the existing resettable Develop rotation field. Source and developed thumbnails,
before/detail previews, export snapshots and drawing coordinates all need explicit
orientation handling; current render/cache paths were traced but are unchanged here.

Final validation: **368 Python tests passed with no skips**, including the pinned
Nikon D3S NEF and required Metal dispatch. The packaged engine passes six native
suites / **126 assertions**: target Painter 18, existing Painter 36, collections 21,
stacks 22, multi-set chooser 19 and connection/handoff 10. The Mac app builds for
14.0 and passes local ad-hoc signature verification on macOS 26.6.2. Generation
**17**, schema **14**, **87 tools**; manifest
`59562988f2119d6421fa9239830f7b37f93d7b01115777f34355788ee0ce26c8`
matches source, and the bundled guide matches the current document. Final compiler
logs contain no warnings/errors. Public checks cover **274 files** without findings,
including the clean extracted archive. Remote refresh found no unmerged branches.
No rendered desktop, macOS 14 runtime or complete Lightroom parity is claimed.

### Independent Library orientation and Rotation Painter

Photo menus now rotate left/right and flip horizontally/vertically; Grid applies
to the selection and Loupe/Compare/Survey/Develop to the active photo. Rotation
Painter captures one action plus visual revisions, deduplicates visible targets
and commits one atomic batch at mouse-up. Cancel writes nothing; any stale target
rejects the whole gesture without retry. Painting preserves the existing selection.

Schema 15 stores orientation separately from Develop recipes and metadata. It
survives Reset and recipe import, stays out of Develop history, and is inherited
then independently editable by virtual copies. Export jobs freeze orientation
when queued; old jobs migrate to identity without changing their stored recipes.
The separate Undo Last Rotation or Flip action restores the latest batch while
preserving subsequent Develop edits. It keeps fifty batches, checks the global
history revision, and rejects missing targets atomically. Unified Command-Z/Redo
and Mac Lightroom reference acceptance remain open.

The renderer maps each oriented strip/viewport into canonical Develop coordinates,
then losslessly rotates/flips the returned tile and gamut mask. Existing crop,
geometry and local masks follow the photograph without a full-frame transformed
allocation or additional resampling. Source/developed thumbnail and preview cache
identities include orientation; linear decode caches stay shared. Before/detail
previews and TIFF/JPEG export use the same adapter. Preview geometry reports the
effective crop separately from source-family EXIF. Native crop bounds/ratios and
mask coordinates follow display orientation; drawing requires a matched fitted
preview. Full recipe JSON remains canonical, and chart calibration still addresses
full EXIF-oriented source pixels before Library/Develop transforms.

Tests cover every orthogonal orientation and composition, asymmetric pixels,
CPU/Metal strip versus viewport agreement with geometry and three mask kinds,
portrait/landscape crop ratios, source-byte safety, independent reset/undo, variants,
stale batches/history, SQL rollback, genuine schema-14 migration rollback/retry,
backup/restore, cache invalidation and frozen queued exports. Native state/IPC
checks cover selection scope, pending-edit guards, captured/cancelled/conflicting
Painter gestures, undo conflicts, current preview geometry and eight coordinate
mappings. Rendered drawing, menu/keyboard/pointer dispatch, accessibility and the
macOS 14 runtime remain unverified. These checks do not establish Adobe color or
pixel equivalence.

Final Python validation: **404 passed, no skips**, including the pinned Nikon D3S
NEF and required Metal dispatch. The source-native orientation suite passes 48
assertions; the final packaged suite adds thumbnail and Compare/Survey dimension
checks for **51**. Seven packaged suites pass **165 assertions**: orientation 51,
state races 15, review 20, thumbnails 14, virtual copies 19, Painter 36 and engine
connection/handoff 10. The app builds for macOS 14.0 and passes local ad-hoc signature
verification on macOS 26.6.2. Engine generation **18**, schema **15**, **90 tools**;
manifest `f08f02ede6cf8b78dd9a534c84b3a28eaac2c7a9f5ba187db695082eecb25769`
matches final engine source, and the bundled guide matches the current document.
Final build/native logs contain no compiler warnings/errors. Fresh remote and
local/remote ancestry checks found no unmerged branches.

Packaged-worker performance used the pinned **4284×2844 Nikon D3S NEF** on this
macOS 26.6.2 arm64 / 128 GB host. Workers ran sequentially after all builds/tests
finished. A priming export warmed the shared linear cache; three timed samples per
recipe/orientation alternated order and include startup plus full-size ProPhoto
16-bit TIFF encoding. RSS is sampled every 20 ms and is not an allocation bound.

| Recipe | Identity median | Clockwise median | Identity / clockwise peak sampled worker RSS |
| --- | ---: | ---: | ---: |
| Neutral, Metal grading/output | 0.653 s | 0.772 s | 211.59 / 189.83 MB |
| Crop, straighten, radial/linear masks, noise reduction, sharpening; CPU + Metal output | 3.844 s | 3.901 s | 247.95 / 201.56 MB |

All six TIFF pairs were **bit-identical after an orthogonal rotation** (maximum
16-bit code difference zero); the source SHA-256 stayed unchanged. Neutral output
dimensions swap from 4284×2844 to 2844×4284; cropped output swaps 3684×2417 to
2417×3684. Actual Metal dispatch was recorded in every worker. Rotation adds about
0.12 s for this neutral fixture and 0.06 s for this masked fixture; these small-sample
warm measurements are not a general throughput, cold-disk or Adobe-equivalence
claim. Reproduce with `tests/orientation_probe.py`.

The public source audit covers **279 files** with no findings. Generated images,
catalogs, outputs, performance receipts and signed app bundles remain local and
outside the source publication allowlist.

### Partial Develop presets and captured Painter application

Adobe's preset documentation describes creating presets from selected settings,
updating from the current photograph, groups, favorites, storage choice and
additional preview/Amount/ISO/file-exchange workflows. This increment implements
the first group of workflows using LumaRAW's existing recipe contract; it does not
establish Adobe parameter or rendering equivalence.

Schema 16 adds catalog-local presets, groups and revisions. Default shared storage
uses a separate SQLite repository behind the existing platform path adapter and
injectable test root. Switching scope preserves both libraries. Bounded pages
return thirty preset summaries and thirty groups, without recipe patches. Native
menus/inspector expose create/update with individual field selection, Check All/
None, search, favorites, group filtering/visibility/rename, duplicate/rename/move/
delete, explicit duplicate-name policy, and shared/catalog storage. The five
existing LumaRAW looks are immutable built-ins that can be duplicated or favorited.

Application merges saved fields into each captured target recipe in one atomic
transaction. It preserves unchecked settings, metadata, independent orientation,
original bytes and frozen jobs, records ordinary Develop history for changed
photos and skips equal recipes. Grid uses selected photos; other views use the
active photo. Painter captures the preset-library token and touched photo visual
revisions, deduplicates hits and submits once at mouse-up without changing the
selection. Refresh does not rebase loaded presets or open editors. Concurrent
preset/scope/photo edits reject the entire action with no automatic replay.

Immutable, checksum-addressed LUTs are retained with saved presets and copied into
the target catalog when applying. Asset I/O runs outside SQL locks; source/preset/
target revisions are rechecked afterward. Corrupt/replaced assets fail without
overwriting an existing file. Catalog backup/restore includes local presets and
rebinds LUT paths. Camera-bound profile presets require compatible target identity.

Hover preview, Amount scaling, ISO-adaptive presets, Adobe XMP/legacy preset import
and export, group deletion/export, import-time application and complete reference
preset content remain open. No desktop automation was performed: actual rendered
dialogs, pointer/shortcut dispatch, VoiceOver, macOS 14 runtime and Lightroom
Classic Mac reference acceptance remain unverified. This is not full preset parity.

Final verification: **416 Python tests passed, no skips**, including the fixed
Nikon D3S NEF and required Metal checks. Twelve preset tests cover the domain,
assets and schema migration. The source-native preset suite passes **28 assertions**.
Seven suites against the self-contained packaged engine pass **187 assertions**:
presets 28, state races 15, Painter 36, orientation 51, keyword sets 29, target
Painter 18 and connection/handoff 10. The macOS 14.0-target app builds and passes
local ad-hoc signature verification on macOS 26.6.2; build/native logs contain no
compiler warnings or errors. Generation **19**, schema **16**, **95 tools**; digest
`95a2cdc60e719870f04408a874c78863cf9d37f729919c6bd9b27f9b3f791561`
matches final engine source, and the packaged usage guide matches its source.

Performance was measured sequentially after builds/tests on the same arm64,
128 GB host with warm SQLite, sixty generated 8×8 originals, and one hundred
depth-32 Unicode keyword assignments per target. Synthetic catalog rows and
1,000/10,000 custom presets are setup, excluded from timing. Each repeated measure
uses thirty samples. Application includes captured preset-token and visual-revision
reads, two validation passes and atomic recipe/history writes; it does not read
full photo metadata. These are in-process service/SQL timings, excluding IPC,
image rendering, LUT copying and desktop latency.

| Operation (median / p95) | 10,000 photos / 1,000 custom presets | 100,000 photos / 10,000 custom presets |
| --- | ---: | ---: |
| First preset page | 2.812 / 4.820 ms | 3.081 / 3.454 ms |
| Last preset page | 2.952 / 4.353 ms | 3.252 / 3.933 ms |
| Name search | 2.621 / 3.005 ms | 4.497 / 5.057 ms |
| Equal reapplication to 60 photos | 14.167 / 16.028 ms | 15.344 / 16.631 ms |
| Two different applications to 60 photos | 34.779 / 37.188 ms | 37.460 / 42.220 ms |

The first changed application took **16.640 / 19.241 ms** respectively (one sample
per catalog, not a distribution). Peak process RSS was **47.53 / 58.62 MB** and
image-worker memory was zero. First-page responses were **6,400 / 6,401 bytes**;
history remained bounded and metadata, orientation and original hashes were
unchanged. Reproduce with `tests/develop_preset_probe.py`; these measurements do
not establish cold-storage or real-RAW preview throughput.

Current public source audit covers **285 files**, with no findings. Local/remote
ancestry checks after fetching found no unmerged branches. Generated fixtures,
catalogs, receipts and app bundles remain excluded from publication.

### Selective metadata presets and descriptive IPTC

Schema 17 adds thirty descriptive IPTC fields covering creators/contact, content
and accessibility descriptions, image location, status/credit/instructions and
rights. The portable schema defines forms and named XMP mappings; native code
does not own metadata encoding. Partial updates preserve absent fields, distinguish
explicit empty values and enforce the merged 64 KiB UTF-8 limit per photo. Date
Created preserves entered precision and offset without changing source capture
time. Virtual copies remain independent and backups preserve all values.

Schema 18 adds named metadata presets with stable identities and revision tokens.
Native users can create blank/from-photo presets, check individual fields or All/
None/Filled, edit, duplicate, rename, delete, search and page thirty names. Shared
storage is default; catalog storage uses an independent preference and preserves
both repositories. Keywords append; scalar/array selections replace only checked
values. Saving creates no vocabulary and changes no photograph. Application
validates the preset/scope/vocabulary token, all target metadata revisions, rating
state when selected, keyword capacity and merged IPTC before one atomic write.
No-op reapplication creates no revisions. Recipes, orientation, history, original
bytes and queued export snapshots are preserved.

Grid applies to the selection, other views to the active photo. Painter captures
the preset and target states at stroke start, deduplicates hits and submits once
at mouse-up. Acknowledged own keyword additions advance only that same loaded
preset token for the next stroke. External refresh does not rebase loaded presets,
pending strokes or open editors. Metadata refresh preserves in-flight Develop
edits. Forms keep one value per line for lists, including commas inside creator
names, and preserve a trailing newline while the user types.

XMP covers structured creator contact, ordered creator lists, subject/scene bags,
x-default language alternatives, rights URI/status and named scalar properties.
Sidecars override only present IPTC properties. Folder sync changes master metadata
without overwriting virtual copies and detects unchanged rereads. Export snapshots
freeze IPTC; Copyright projects only rights fields and Catalog includes all
supported values. Large descriptive JPEG packets move into verified Extended XMP.
Twelve keyword paths per detail page when IPTC is present keep even worst-case
escaped content below the broker limit without truncation.

Remaining work includes IPTC Extension structures, legacy IIM, controlled-vocabulary
browsing, multilingual alternatives, custom textual color labels, Adobe metadata
preset exchange, import-time application and metadata Undo. Desktop automation was
not performed: rendered forms, actual pointer/keyboard dispatch, VoiceOver, macOS 14
runtime and Lightroom Classic Mac reference acceptance remain unverified.

The complete Python suite passes **432 tests with no skips**, including the fixed
Nikon D3S NEF and required Metal checks. Source-native metadata preset state tests
pass **32 assertions**. Regression evidence includes independent XMP fixtures,
Extended XMP, genuine schema-16/17 migration rollback/retry, frozen jobs, copy
independence, merged-size/capacity/SQL all-target rollback, worst-case wire budgets,
captured editor/Painter conflicts, no-op writes and unchanged originals.

Eight native suites against the packaged engine pass **174 assertions**: metadata
presets 32, library 13, state races 15, Painter 36, folder sync 24, export metadata
16, Develop presets 28 and connection/handoff 10. The macOS 14-target app builds
and passes local ad-hoc signature verification on macOS 26.6.2. Build and native
logs have no compiler warnings/errors. Engine generation **20**, schema **18**,
**101 tools** and digest
`ed62f45bce9601667ffa3422eb45df5a67bebe643001557afbaa75ae251b8694`
match final source; the bundled usage guide also matches.

Warm in-process performance was measured sequentially after builds/tests on the
same arm64, 128 GB Mac. Each of sixty generated 8×8 targets carries **60,090 bytes**
of identical IPTC plus ninety-nine depth-32 Unicode keyword assignments; the first
application adds one tag. Catalog and preset setup is excluded. Thirty samples
measure each repeated operation, including preset-token and captured target reads,
validation and writes. No pixel worker, decoding, IPC or desktop latency is included.

| Operation (median / p95) | 10,000 photos / 1,000 presets | 100,000 photos / 10,000 presets |
| --- | ---: | ---: |
| First preset page | 1.906 / 2.395 ms | 2.407 / 2.734 ms |
| Last preset page | 2.074 / 3.442 ms | 2.823 / 3.119 ms |
| Name search | 2.052 / 3.846 ms | 2.812 / 3.174 ms |
| Equal application to 60 photos | 20.538 / 26.018 ms | 21.035 / 23.526 ms |
| Two different applications to 60 photos | 53.477 / 64.091 ms | 56.887 / 68.174 ms |

The first changed applications took **38.928 / 61.531 ms** respectively (one
sample each). Peak process RSS was **68.75 / 79.67 MB**, image-worker memory zero,
and first-page responses **5,946 / 5,947 bytes**. A same-fixture 10k baseline before
per-batch exact-value reuse measured **92.992 ms** equal reapplication and
**208.623 ms** for two changed applications (medians); distinct IPTC values still
receive their own validation. The bounded cache retains at most sixty entries,
and scalar-only presets do not parse unrelated IPTC. This result does not establish
cold-storage or real-photo rendering speed. Reproduce with
`tests/metadata_preset_probe.py`; original hashes, recipes, history and orientation
are asserted unchanged.

The public source audit covers **294 files**, with no findings. Generated images,
catalogs, app bundles and raw receipts remain outside publication. Module commits
must be pushed to the authorized remote and the remote revision verified before
describing them as remotely backed up.

### Durable Add import review

Mac Import, drag/drop and Finder file-open now stage a review before adding photos.
Users choose subfolder inclusion, scan, inspect thumbnail/Grid or fitted Loupe,
filter/sort bounded pages, check individual photos or a category across pages,
change suspected-duplicate exclusion, and explicitly apply. Focus and check state
are separate. Existing catalog paths cannot be reimported. Duplicate classification
uses original filename, byte size and known precise capture time; unknown dates
never substitute file modification time. Original names persist through schema 19.
No claim is made about Adobe's undocumented case/clock/container edge cases.

Scanning reads at most 256 directory entries or 60 file observations per command,
outside catalog locks. Restart replays directory entries into unique staging paths
and retains checked choices. Active catalog/cache directories are excluded.
Previews use the existing bounded image worker with separate client generations,
without creating a catalog photo. Application rechecks selected originals,
sidecars and scanned directories, then creates the checked references and supported
XMP descriptions in one transaction. Bulk SQL and aggregate folder counts avoid
per-photo ancestor work; cancellation inside SQL rolls the whole transaction back.
Completed receipts cannot be cancelled or applied again. Closing/reopening, backup
and restore retain pending reviews; uncertain native responses are read back.

The full Python suite passes **451 tests with no skips**, including the fixed
Nikon D3S fixture and required Metal checks. Nineteen import cases cover precise
duplicate rules, XMP, unchanged originals, changed sources/catalogs, late duplicate
conflicts, 601-entry directory restart, cache exclusion, checked selection, rollback
of folder counts/maintenance during cancellation, backup/restore and genuine
schema-18 migration rollback/retry. Fresh remote references still contain only
`origin/main`; it and local `main` are already ancestors of this development branch.

Eight native suites against the packaged engine pass **159 assertions**: import
22, library 13, state races 15, folders 24, folder synchronization 24, virtual copies
19, metadata presets 32 and service connection/handoff 10. The Mac app targets
macOS 14, builds and passes local ad-hoc signature verification on macOS 26.6.2.
Build and native logs contain no compiler warnings/errors. Engine generation
**21**, catalog schema **19**, **109 tools** and digest
`51695ad3db91cde29d84b239fb5c887d6e6f32797ea0d625b3c33bd1d00bcb5e`
match final source, as does the bundled usage guide. The source publication check
covers **301 files** with no findings; generated photographs, catalogs, application
bundles and raw receipts are excluded. These checks do not scan Git history or
establish remote backup.

Performance on the same arm64 macOS 26.6.2, 128 GB Mac uses a synthetic existing
catalog and candidate review, plus sixty generated 8×8 PNG originals. Warm SQLite
page queries have thirty samples; scan, real-file application and synthetic bulk
application each have one. Setup, image decoding, IPC and UI are excluded. The
synthetic bulk figure additionally excludes filesystem verification and measures
only the final SQL transaction; it is not end-to-end photographic import speed.

| Operation (median / p95 for repeated pages) | 10,000 photos / candidates | 100,000 photos / candidates |
| --- | ---: | ---: |
| First page | 2.268 / 2.627 ms | 1.864 / 1.995 ms |
| Last page | 2.474 / 2.668 ms | 4.822 / 5.286 ms |
| Checked page | 2.206 / 2.422 ms | 1.900 / 2.227 ms |
| Capture-time sort | 2.188 / 2.554 ms | 1.905 / 2.237 ms |
| File-type sort | 2.203 / 2.395 ms | 1.892 / 2.126 ms |
| Scan sixty real files (one sample) | 12.693 ms | 11.238 ms |
| Apply sixty real files / discard review (one sample) | 47.435 ms | 352.858 ms |
| Synthetic bulk SQL application (one sample) | 205.240 ms | 1,892.811 ms |
| Peak process RSS | 48.64 MB | 76.67 MB |

Workers consumed zero memory in this metadata/SQL probe; original hashes, catalog
counts, folder aggregates and enabled maintenance are asserted. First-page replies
were 20,866 / 20,928 bytes. A same-size 10k pre-optimization transaction took
1,612.452 ms; the optimized transaction is about 7.9 times faster for this synthetic
single-sample comparison. Reproduce with `tests/import_review_probe.py` after other
tests/builds finish. The 100k transaction still holds the catalog lock for about
1.9 seconds, with cancellation checks; further throughput work remains.

This completes the reviewed Add implementation increment, not import parity.
Copy/Move/Copy as DNG, destination naming/backup, import presets and import-time
metadata/Develop application, preview policies, cards/tethering, previous-import
source and catalog switching/merge remain. Desktop automation was not performed:
rendered interaction, actual pointer/keyboard dispatch, VoiceOver, macOS 14 runtime
and Lightroom Classic Mac reference acceptance remain unverified.

### Apply During Import

Schema 20 adds per-review captured Develop/metadata presets and additional keyword
choices. The Mac panel supports None, search and thirty-item pages, new metadata
presets with selected fields, comma-separated keywords and explicit draft saving.
Choosing settings creates neither photos nor vocabulary. Local drafts survive
conflicts; only acknowledged own writes advance an editor's plan revision.
Refreshing preset lists never substitutes newer contents for an existing choice.
Closing/reopening and catalog backup retain pending settings independently of
later preset edits/deletion. Full presets stay off list/review wire responses.

Metadata presets and their keyword meanings are read in one shared/catalog
transaction. A rollback-only resolution records exact hierarchy segments, so a
new XMP leaf or concurrent keyword edit cannot retarget a captured root/branch.
Application imports file descriptions, replaces only the preset's checked fields,
then unions keyword assignments. Empty checked scalars clear only those fields;
empty additions do not remove file tags. Merged IPTC and keyword capacity failures
roll back all new photos, vocabulary, folder counts and maintenance state.

Captured Develop fields initialize the new recipe over defaults and update the
review thumbnail/Loupe through the existing worker/cache. Camera profiles must
match checked source metadata both at choice and application. LUTs stage outside
SQL locks, are revalidated before import and rebind by content address on restore.
No artificial pre-import edit history is created. Existing catalog photos, virtual
copies, original bytes and frozen export jobs are outside the import mutation.

Thirteen new Python cases cover snapshot/None/omission semantics, checked scope,
file/preset/additional keyword unions, deletion after capture, stale plan/preset
tokens, ambiguous and oversized keyword input, concurrent vocabulary changes,
root/leaf preservation, camera selection changes, SQL/capacity rollback, LUT
corruption/staging races, backup rebinding and genuine schema-19 rollback/retry.
A real worker test verifies a generated gray image's import thumbnail changes
under exposure and returns to its cached source version after clearing the preset.
Source-native checks pass **22 assertions**, covering drafts, New/None, conflicts,
list refresh, closing/reopening, chosen photo values and unchanged originals.

The final full Python suite passes **464 tests with no skips**, including the fixed
Nikon D3S NEF and required Metal checks. The Mac app builds for macOS 14 and passes
local ad-hoc signature verification on macOS 26.6.2. Engine generation **22**,
catalog schema **20**, **111 tools**, bundled usage guide and source digest
`8a1bb3ea082c9831fb75b0bb734e9a39a267c2e554b1d1ecdd3d8d9e5542f2e5`
match the final application package.

The final packaged application passes **189 native assertions** across import
settings (22), import review (22), metadata presets (32), Develop presets (28),
folder synchronization (24), Painter (36), state conflicts (15) and connection
handoff (10). Both build and native compilation logs contain no compiler warnings
or errors. These are native state/service checks; they do not establish desktop
interaction acceptance.

The current-source/index publication check and the extracted source-only archive
each pass with **306 files and zero findings**. This check excludes Git history
and is not a historical secret audit or desktop validation.

Warm performance was measured sequentially with no concurrent tests/builds on
the arm64 macOS 26.6.2, 128 GB Mac. Each imported photo receives exposure/contrast,
title/rating, **31,560 UTF-8 bytes** of IPTC and three keyword paths. Sixty originals
are generated 8×8 PNGs; remaining catalog/candidate rows are synthetic. Setup,
pixels, IPC and UI are excluded; synthetic bulk also excludes file verification.
Pages have thirty samples, and scan/application figures each have one.

| Operation (median / p95 for repeated pages) | 10,000 catalog / 1,000 candidates | 100,000 catalog / 10,000 candidates |
| --- | ---: | ---: |
| First page | 1.794 / 1.858 ms | 2.118 / 2.579 ms |
| Last page | 1.738 / 1.794 ms | 2.297 / 2.545 ms |
| Checked page | 1.840 / 2.122 ms | 2.102 / 2.280 ms |
| Capture-time sort | 1.769 / 1.830 ms | 2.067 / 2.236 ms |
| File-type sort | 1.768 / 1.876 ms | 2.082 / 2.624 ms |
| Scan sixty real files (one sample) | 10.019 ms | 11.799 ms |
| Apply sixty real files (one sample) | 29.038 ms | 66.147 ms |
| Synthetic bulk transaction (one sample) | 168.969 ms | 2,474.835 ms |
| Peak process RSS | 42.64 MB | 62.30 MB |

First-page replies are 21,357 / 21,420 bytes, independent of preset metadata size;
image-worker memory is zero. Probes assert original hashes, recipes, keyword totals,
folder aggregates and maintenance state. Metadata applies in sixty-target batches,
and exact keyword paths resolve once per transaction with a bounded prefix cache.
The later vocabulary-capture race fix changes setup only, outside these timings.
The bulk figure measures an atomic SQL lock period, not complete RAW import speed.

Remaining import work includes saved/remembered import configurations, Copy/Move/
DNG, renaming/destinations/second-copy backup, preview policies, cards/tethering,
previous-import source and catalog switching/merge. Adobe preset-file translation,
complete camera profiles and IPTC, sidecar writes and unified Undo also remain in
the full objective. Rendered desktop interaction, actual keyboard/pointer dispatch,
VoiceOver, macOS 14 runtime and Lightroom Classic Mac reference acceptance are
unverified; this increment does not establish complete import or product parity.

### Previous Import source and navigation

Schema 21 records the latest committed batch by stable source identity. Reviewed
Add, direct import and folder synchronization share the same membership; choosing
Previous Import filters the normal paginated Library query. Virtual copies and
master-role changes retain family membership, and relinking does not depend on
the old path. Removing the final family member removes its entry. No-op imports,
cancelled reviews and failed atomic applications preserve the prior batch. Legacy
direct import retains its actual committed hundred-entry subsets after a later
failure. Upgrades do not guess lost import history from photo timestamps.

The Mac sidebar and toolbar expose Previous Import. Completed local imports open
Library Grid with cleared filters by default. A catalog-persisted Settings toggle
keeps the current source and filters when disabled. External-client imports refresh
an already viewed source without stealing navigation, including empty filtered
pages. Source changes supersede pending automatic focus; stale settings reads do
not overwrite newer acknowledged preference changes.

Nine new Python regressions cover checked membership, rollback after capture,
folder sync/import-versus-metadata semantics, cleanup, copies/promotion/relinking,
backup/restart, filtering/paging/source exclusivity, partial commits and genuine
schema-20 migration failure/retry. Targeted regressions pass **92 tests**; the full
fixed-RAW/required-Metal suite passes **473 tests with no skips**. Initial
source-native coverage passes **17 assertions**.

The final Mac package builds with macOS 14 as its minimum and passes local ad-hoc
signature verification on macOS 26.6.2. Engine generation **23**, catalog schema
**21**, **111 tools**, bundled guide and source digest
`06304e1c322ae24575f5d5a0ef4d6d47981fcb6ace98bdce2e8c9931c53ab682`
match the package. This does not establish runtime compatibility on macOS 14.

The final packaged engine passes **207 native assertions** across Previous Import
(19), import review (22), import settings (22), synchronization (24), folders (24),
relocation (17), Library (13), state conflicts (15), virtual copies (19), stacks
(22) and connection handoff (10). Build and native compilation logs contain no
compiler warnings or errors. The current-source/index check and extracted
source-only archive each pass **311 files with zero findings**; these checks do
not scan Git history or prove rendered desktop behavior.

Warm synthetic measurements run sequentially without concurrent builds/tests on
the arm64 macOS 26.6.2, 128 GB Mac. Page/sort/filter/state queries use thirty
samples; replacement is one atomic SQL membership transaction. Setup, filesystem
verification, image decoding, IPC and desktop time are excluded.

| Operation (median / p95) | 10,000 photos / 1,000 imported sources | 100,000 photos / 10,000 imported sources |
| --- | ---: | ---: |
| First page | 4.490 / 4.789 ms | 6.942 / 7.205 ms |
| Last page | 5.563 / 5.683 ms | 17.617 / 19.168 ms |
| Filename sort | 5.765 / 6.118 ms | 18.441 / 22.003 ms |
| Capture-time sort | 5.675 / 5.973 ms | 18.586 / 19.694 ms |
| Rating filter | 4.936 / 5.199 ms | 11.364 / 12.636 ms |
| Source-state poll | 1.178 / 1.498 ms | 1.173 / 1.275 ms |
| Replace membership (one sample) | 2.252 ms | 6.071 ms |
| Peak process RSS | 43.42 MB | 62.19 MB |

First-page replies are 32,573 / 32,876 bytes; no image workers run. Query plans use
the covering photo-source index and the membership primary key. Probes assert
bounded pages, exact batch scope and absent recipe/decoder payloads. These figures
do not measure image-processing throughput or complete import latency.

This completes the current persisted-source implementation, not import parity.
Progressive Current Import, application-wide import preferences, saved configurations,
Copy/Move/DNG, destinations,
renaming/backup, preview policies, cards/tethering and catalog switching/merge
remain. Source-family behavior and stack/filter combinations still require
Lightroom Classic Mac reference acceptance. Rendered desktop interaction, actual
keyboard/pointer dispatch, VoiceOver and macOS 14 runtime are unverified.

## Eight-band HSL and Black & White Mix

The Mac inspector now exposes red, orange, yellow, green, aqua, blue, purple and
magenta in Hue, Saturation, Luminance and All views, plus selection by color. Each
band has an independent black-and-white brightness control. Color/B&W treatment
switches retain both mixes. Reset Shown clears one component or band; the panel
reset clears only the current treatment's mix. Native edits share the ordinary
revision barrier, coalesced history, undo and stale-write recovery.

The portable recipe adds 24 zero-default fields while retaining v2 and the four
existing bands' hue/saturation semantics. Mac hue sliders display -100 to 100 but
continue to store -30 to 30 degrees. Old JSON is normalized before selective sync,
including old recipes that lack every new key. Color sync includes all HSL fields
and treatment; Black & White Mix independently copies eight brightness values.
All eleven groups can be synchronized together. Full 69-field presets are accepted
by the expanded bounded API and the native preset editor. Undo, snapshots, bundles,
backups, import settings and frozen export jobs keep their shared recipe boundary.

CPU and Metal use the same eight overlapping Oklab bands; luminance and B&W gains
protect neutrals and operate within bounded strips. The legacy HSL-then-monochrome
order is retained. Ordinary mixer recipes use fused GPU grading, without moving
LibRaw decoding onto the GPU or introducing a full-frame mixer allocation.

Synthetic tests verify every channel's direction, neutral protection, hue wrapping,
negative/HDR finiteness, no input mutation, strip/detail identity and frozen legacy
CPU pixels. Persistence cases cover all-field presets, selective/all-group sync,
stale-target rollback, undo, frozen jobs and backup/recipe round trips. Required
Metal tests cover all four output spaces; `METAL.md` states the near-black Adobe
RGB numerical allowance and the additional decoded-linear bounds. These are
CPU/GPU consistency checks, not Adobe color calibration.

The final full Python run passes **501 tests without skips**, including the pinned
Nikon D3S RAW and required actual Metal. The source-engine native mixer workflow
passes **24 assertions**.

The Mac app builds and passes local ad-hoc signature verification on macOS 26.6.2,
targeting macOS 14. Engine generation **24**, schema **21**, **111 tools**, bundled
guide and source digest
`1632c0a0fb1977ee80a89c0391356dc4ad9b35aee70c961e49f9fd157465400c`
match the package. PyInstaller reports an absent `scipy.special._cdflib`
hidden import; the packaged RAW processing runs below pass. This is not runtime
verification on macOS 14.

The final packaged engine passes **118 assertions in six native suites**: Color
Mixer (24), Develop presets (28), state conflicts (15), import settings (22),
virtual copies (19) and connection handoff (10). Swift compilation has no warnings
or errors. Current-source/index scanning covers **314 files with zero findings**;
generated catalogs, photographs, outputs and raw receipts remain outside source.
These checks do not inspect Git history or establish desktop interaction parity.

Sequential packaged-worker measurements use the pinned 4284×2844 Nikon D3S NEF
on an Apple M3 Max, 128 GB, arm64 macOS 26.6.2. Each treatment includes all eight
HSL bands; the B&W recipe additionally enables all eight B&W controls. The probe
records one empty-application-cache preview, two warm previews, one full-size
ProPhoto 16-bit TIFF and one 1280×900 detail pair. Warm rows are medians of two,
not p95 measurements. Empty application caches do not imply cold OS/shader caches.
Wall times include worker startup, Metal initialization/copies and encoding;
desktop drawing and IPC are excluded. No tests or builds ran concurrently.

| Recipe / operation | CPU wall | Metal wall | CPU / Metal peak RSS |
| --- | ---: | ---: | ---: |
| HSL cold preview, 1680×1115 | 2.443 s | 1.090 s | 165.67 / 159.48 MB |
| HSL warm preview | 1.640 s | 0.641 s | 164.00 / 145.69 MB |
| HSL full-size TIFF | 5.493 s | 1.165 s | 300.56 / 245.86 MB |
| HSL detail viewport | 1.183 s | 0.530 s | 150.08 / 140.25 MB |
| B&W cold preview, 1680×1115 | 2.386 s | 0.933 s | 166.94 / 150.95 MB |
| B&W warm preview | 2.002 s | 0.684 s | 168.25 / 146.58 MB |
| B&W full-size TIFF | 7.224 s | 1.048 s | 297.28 / 215.61 MB |
| B&W detail viewport | 1.402 s | 0.545 s | 150.09 / 141.83 MB |

All Metal workers report actual grading with no fallback: 18 tiles per preview,
23 per export and 16 per detail request; peak shared buffers are 19.61 MB.
Each CPU/Metal pair differs by at most
**one code value**, including the full 16-bit exports (eight-code limit). Export
mean differences are 0.002296 HSL and 0.002797 B&W code values. Original hashes
remain unchanged. The measured export speedups are **4.716×** and **6.892×**;
one camera file and these recipes do not establish general throughput, slider
latency, calibrated color or reference processing parity.

This delivers eight-band controls and their persistent processing path, not full
Color Mixer parity. Targeted adjustment, Point Color, Auto B&W mix, Color Grading,
Adobe-compatible parameters and reference pixel/treatment acceptance remain.
Rendered desktop interaction, keyboard/pointer dispatch, VoiceOver and macOS 14
runtime are still unverified. No Adobe processing equivalence is claimed.

## RGB and channel point curves

The Mac Tone Curve panel adds RGB, Red, Green and Blue graphs, direct point
insertion/movement, numerical Input/Output controls in 0–255 units, point selection,
deletion, arrow adjustments, per-channel/all-RGB resets and three domain-supplied
presets. A gesture captures the photo, revision and starting points. Temporary
photo previews do not save edits; release saves once, Escape cancels, and another
photo or a newer revision invalidates the gesture. One pending draft is coalesced
behind one in-flight image request. Preset names follow the familiar control
workflow, but their values are LumaRAW-owned, not recovered Adobe parameters.

The portable recipe adds four identity-default arrays without rewriting older
catalog rows. Curves accept 2–16 normalized points, strictly ascending inputs with
minimum spacing 1/65535, arbitrary outputs, movable endpoints and flat extensions.
[PCHIP interpolation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.PchipInterpolator.html)
provides shape-preserving segments. Master RGB precedes independent channels in
encoded working RGB, after the unchanged legacy luminance curve and before HSL.
Active curves are SDR; exact identity preserves negative/HDR values. Legacy
`curve_points` and the three region sliders retain their original semantics and
frozen CPU outputs. Active older curves remain accessible as Legacy Luminance.
Tone Curve sync includes all new fields. Full presets now contain 73 editable
fields, within the existing 128-field contract. Undo, bundles, backups, import
presets, snapshots and frozen export jobs share the same recipe boundary.

CPU and Metal consume the same cached normalized spline coefficients. Ordinary
curves remain fused. Segments with maximum slope above 32 use CPU grading and
Metal output with an explicit hybrid reason; their shape is preserved. The v2
Metal ABI checks a 640-float parameter layout before reading buffers, safely
rejecting an old adapter. No full-frame allocation or persistent pixel worker
is introduced by the curve control.

The full Python suite passes **526 tests, no skips**, with the pinned Nikon D3S
NEF and required Metal execution. Cases include independent spline comparison,
segment bounds, inversion/endpoint movement, unaffected channels, frozen legacy
pixels, strip/detail consistency, old JSON, partial presets, atomic sync conflicts,
undo, frozen exports and backup/bundle round trips. Real temporary previews change
pixels and restore the saved result without changing recipe/history or queued
recipes. Invalid/stale drafts fail before image work. Metal covers all four output
spaces, fused curves, steep hybrid behavior and Python/C ABI size guards.

The source-engine native probe passes **28 assertions**. Its graph evaluator
differs from engine-generated samples by at most **9.537e-8** normalized units,
including narrow segments. State/IPC checks cover engine presets, point bounds,
temporary previews, single-step saves, reset/undo, stale writes, pending edits,
photo switches, selective sync and unchanged originals. These are not desktop
pointer, keyboard or VoiceOver dispatch checks.

The standalone app builds and passes local ad-hoc signature verification on
macOS 26.6.2 with a macOS 14 deployment target. Generation **25**, catalog schema
**21**, **111 tools**, 73 editable recipe fields and the bundled guide match the
source. The engine source digest is
`3db1f06aa9c7190b5004609107bd25035470fc06c5687cd637de1deb0ed17102`.
PyInstaller again warns about the absent `scipy.special._cdflib` hidden import;
this warning is retained rather than classified as a warning-free build.

The final packaged engine passes **146 assertions in seven native suites**:
point curves (28), Color Mixer (24), Develop presets (28), state conflicts (15),
import settings (22), virtual copies (19) and connection handoff (10). Native
compilation produces no warnings or errors. Source/packaged checks retain their
separate identities; no previous module's native receipt is reused for this build.

Sequential packaged-worker measurements use the pinned 4284×2844 Nikon D3S NEF
on an Apple M3 Max, 128 GB, arm64 macOS 26.6.2. The recipe enables all four point
curves plus exposure/tone/vibrance and existing color adjustments. No test or build
runs concurrently. There is one empty-application-cache preview, two warm previews,
one full-size ProPhoto 16-bit TIFF and one 1280×900 detail pair. Warm wall values
are medians of two; RSS is the maximum sample for that row. Empty app cache does
not imply cold OS/shader cache. Wall time includes startup, initialization/copies
and encoding; IPC and desktop drawing are excluded.

| Operation | CPU wall | Metal wall | CPU / Metal peak RSS |
| --- | ---: | ---: | ---: |
| Cold preview, 1680×1115 | 2.045 s | 1.180 s | 212.12 / 167.97 MB |
| Warm preview | 1.792 s | 0.740 s | 206.03 / 163.33 MB |
| Full-size TIFF | 6.546 s | 1.264 s | 498.00 / 258.92 MB |
| Detail viewport | 1.362 s | 0.640 s | 190.94 / 160.89 MB |

All Metal workers report fused grading without fallback: 18 tiles per fitted
preview, 23 per export and 16 per detail request; peak shared buffers are 19.61 MB.
Every pair differs by at most **one code value**, including the 16-bit export
(eight-code limit, mean difference 0.001850 codes). The original hash is unchanged.
The measured full-export speedup is **5.176×**. One RAW and one recipe do not
establish general throughput, interactive drag latency or Adobe image equivalence.
The generated preview was also inspected as an image; this is not desktop UI
acceptance or a reference color comparison.

Public-source and extracted strict-archive checks cover **319 files with zero
findings**. Private photographs, catalogs, generated outputs and raw receipts stay
outside committed source. These scans do not inspect Git history or prove the
absence of every possible secret.

Four-region parametric curves and split controls, targeted adjustment, curve-only
exchange, Adobe processing/working-space equivalence and reference acceptance
remain unfinished. Rendered desktop interaction, keyboard/pointer dispatch,
VoiceOver and macOS 14 runtime remain unverified; this is not full Tone Curve or
Lightroom Classic parity.
