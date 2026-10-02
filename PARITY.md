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
- [Filename templates and token editor](https://helpx.adobe.com/lightroom-classic/desktop/import-photos/filename-template-editor-text-template.html) (rechecked October 2026)
- [Original-state second copies, Adobe's Julieanne Kost](https://jkost.com/blog/2024/07/tips-for-importing-files-into-lightroom-classic.html) (rechecked October 2026)
- [Previous Import source](https://helpx.adobe.com/lightroom-classic/desktop/viewing-photos/view-photos.html) and [automatic source selection preference](https://helpx.adobe.com/uk/lightroom-classic/desktop/import-photos/file-import-formats-settings.html)
- [Camera/card import workflow](https://helpx.adobe.com/lightroom-classic/desktop/import-photos/importing-photos-lightroom-basic-workflow.html)
- [Workspace and module responsibilities](https://helpx.adobe.com/nz/lightroom-classic/help/workspace-basics.html)
- [Collections, smart collections, sets and their color labels](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/photo-collections.html) (rechecked October 2026)
- [Smart collection criteria](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/smart-collections-criteria-in-lightroom-classic.html)
- [Develop tools](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/develop-module-tools.html)
- [Reference View selection, locking and crop exit, Adobe's Julieanne Kost](https://jkost.com/blog/2024/08/reference-view-in-lightroom-classic.html)
- [History state selection, naming, clearing and snapshots](https://helpx.adobe.com/uk/lightroom-classic/desktop/process-and-develop-photos/develop-module-options.html)
- [Snapshot creation, update, sharing and Before assignment, Adobe's Julieanne Kost](https://jkost.com/blog/2024/08/working-with-snapshots-in-lightroom-classic-and-photoshop.html)
- [Tone Curve controls and channels](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/image-tone-color.html)
- [Color Mixer](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/color-mixer.html) and [Black & White Mix](https://www.adobe.com/learn/lightroom-classic/web/convert-photo-black-white)
- [Loupe, Compare and Survey](https://helpx.adobe.com/lightroom-classic/desktop/viewing-photos/browse-compare-photos.html)
- [Keyboard shortcuts](https://helpx.adobe.com/lightroom-classic/desktop/introduction-to-lightroom-classic/keyboard-shortcuts.html)
- [Photo stacks and source boundaries](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/grouping-photos-stacks.html)
- [Stacking shortcuts, Adobe's Julieanne Kost](https://jkost.com/blog/2024/07/stacking-similar-photos-in-lightroom-classic.html)
- [Folder hierarchy, subfolder inclusion and synchronization](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/create-folders.html) (reviewed-import distinction rechecked October 2026)
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
- [Export presets](https://helpx.adobe.com/nz/lightroom-classic/desktop/export-photos/export-presets-settings-plug-ins.html) and [single/multi-preset export workflow](https://helpx.adobe.com/lightroom-classic/desktop/export-photos/exporting-photos-basic-workflow.html) (checked October 2026)
- [XMP specifications, including Part 3 storage and Extended JPEG](https://developer.adobe.com/xmp/docs/xmp-specifications/)

## Feature inventory

“Partial” means an implementation exists, with important workflow or verification
gaps. Nothing below is full Lightroom parity merely because historical tests pass.

| Area | Current implementation | Remaining acceptance / work |
| --- | --- | --- |
| Import and catalogs | Partial: durable Add/Copy review with checked selection, Grid/Loupe source previews with on-demand Fit/100% regions and completed-preview reuse, suspected duplicates, bounded sorting/filtering, captured import-time presets and keywords, Copy destination/subfolder and flat/source/date organization with three numeric date layouts and paged destination photo counts, filename token editor and catalog-local templates with checked-sequence and catalog Import/Image numbering, byte-verified original/XMP transfers, optional original-state second copies, catalog-local saved import configurations with explicit rescans, explicit crash recovery and retained-copy cancellation, Previous Import navigation and catalog backup/restore | Move/Copy as DNG, destination-tree grouping and more date formats, numbering edge-case reference acceptance and wider EXIF/shared templates, shared/Adobe import-preset exchange and interaction acceptance, preview policies, cards/tethering, progressive Current Import, catalog switching/merge and desktop/reference acceptance |
| Library navigation | Partial: bounded grid/filmstrip, folder tree/search/favorites/labels, durable missing-folder relocation and folder synchronization with reviewed suspected-duplicate inclusion, direct/recursive sources, filters/sorting including live snapshot status, regular/smart/Quick collections and nested sets, photo drops into regular and Quick collections, collection-node moves into sets, single/batch collection color labels and global color filtering | Multi-source selection, complete sync Import Dialog, folder move/rename, relocation overlap/collision handling, collection-node drag/drop desktop/reference acceptance, custom label names/sets and sidebar multi-selection interaction, full smart criteria/import-export, source-selection memory, desktop/reference acceptance |
| Organization | Partial: duplicate/missing detection, hierarchical keywords/synonyms/export flags/Will Export preview, text/CSV vocabulary exchange and manual person tags, custom nine-slot keyword sets/recent entries/shared or catalog storage, multi-keyword shortcuts and keyword/rating/flag/label/target-collection/rotation/Develop-preset/metadata-preset Painter strokes, independent catalog rotation/flips, title/caption/copyright plus thirty IPTC fields, selective metadata presets, labels, batch metadata, virtual copies, manual/split/capture-time scoped stacks | Keyword policy/file and preset reference acceptance, built-in sets/suggestions/undo, Painter desktop acceptance, IPTC Extension and complete metadata parity, stack interaction acceptance, rename and sidecars |
| Culling | Partial: Loupe/Compare/Survey, linked detail, anchored page selection, rating/flag/color keys with guarded Shift advance in single-target Grid/Loupe, Develop Reference/Active pairs with independent Fit/1:1 viewports, session lock and RGB/LAB readouts | Desktop and numerical reference acceptance, exact sorted/filter-removal behavior, HDR readouts, scrubby/box zoom, cross-page selection, Auto Advance preference/Caps Lock, persistent workspace state |
| Basic development | Partial: light/WB/color, source-bound one-shot raster neutral-point selection, eight-band HSL and B&W Mix with photo-targeted adjustment and selective resets/sync | RAW selector, calibrated absolute WB, selector loupe/scale/hover/Auto Dismiss options, texture/clarity/dehaze, Point Color, Auto B&W mix, color grading and Adobe processing/reference acceptance |
| Curves and profiles | Partial: four-region parametric curves with movable splits and photo-targeted adjustment, interactive RGB/channel point curves, shared temporary previews, legacy luminance curve, LUT/ICC | Point/channel targeting, curve exchange, camera/profile browser, Adobe processing and rendered/reference acceptance |
| Detail and optics | Partial: noise/sharpen, manual lens | Complete manual detail controls, automatic lens profiles, bounded full-resolution acceptance |
| Geometry | Partial: crop/straighten/perspective, independent rotation/flips with attached masks and displayed crop ratios | Interactive retained handles, guided transforms, full crop state and rendered/reference parity |
| Local editing | Partial: radial/gradient/brush/luma | Mask list/edit/reorder/intersection, range masks, clone/heal, red-eye (non-AI) |
| History and presets | Partial: durable paged Develop history with undo/redo, state selection/rename/clear, persistent Before assignment/copy/swap, separate 50-batch orientation undo, alphabetical shared snapshots with current/history capture, rename/update/delete and Before copy, partial Develop presets/groups/favorites/shared or local storage, batch/Painter and reviewed-import application | Unified application Undo/Redo, history/snapshot hover, preset hover preview/Amount/ISO adaptation/Adobe exchange and rendered reference acceptance |
| Preview/performance | Partial: Metal, proxies, 1:1 viewport, developed thumbnail fast path, on-demand Before with independent cache, four paired layouts, persistent command relay, snapshot-based Library reads, background image preparation, quiet polling, fused readout maps and validated completed-preview reuse | Real-RAW catalog/slider latency, offline previews, cache controls and desktop/reference acceptance |
| Export | Partial: JPEG/16-bit TIFF, ICC, shared or catalog-local saved export settings with optional destinations, multiple-preset batches with individual/parent destinations and paged receipts, catalog-local Export with Previous, durable jobs with frozen catalog/rights IPTC XMP and keyword hierarchy options | Full batch naming/reference acceptance, Adobe preset exchange, complete EXIF/IPTC Extension/GPS metadata policies, watermark, additional formats, publish workflows |
| External editing and video | Missing | External-editor setup and derivative round trips; supported video import/playback, frame capture, trimming and export |
| Merge | Missing | Non-AI HDR merge and panorama with bounded resources and reference acceptance |
| Map | Missing | GPS metadata, map navigation, track import, location editing with explicit persistence |
| Book | Missing | Templates, layouts, typography, PDF/JPEG output; external fulfillment is a separate integration |
| Slideshow | Missing | Layout, timing, playback, audio, slideshow export |
| Print | Missing | Contact sheets/packages, physical sizing, native print/ICC workflow |
| Web | Missing | Local gallery templates and export; publishing requires explicit destination |
| Platform/accessibility | Partial: Mac 14 target, Mac 26 historical checks | Legacy upgrade recovery, current desktop checks, macOS 14, keyboard/VoiceOver, color management; Windows remains future |

## Active increment

Continue complete import, Library, Develop and export workflows while preserving the
validated command/preview responsiveness and fused RGB/LAB processing changes.
RAW slider/selection latency and desktop interaction remain performance acceptance
work; the first-map optimization is recorded below rather than treated as full
interactive performance acceptance.
The full feature inventory above remains the acceptance scope.
Rendered Mac/reference acceptance,
Copy refinements, Move/DNG, complete IPTC, Adobe exchange, unified Undo/Redo and the full inventory
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

Continue with bounded vocabulary-browser metadata, keyword sets and vocabulary exchange, complete synchronization import options, relocation edge cases and
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

Remaining synchronization parity includes the complete Adobe Import Dialog with
thumbnail selection and its duplicate-policy workflow; the later suspected-duplicate
increment below adds that review policy to LumaRAW's existing sheet. Other gaps are
missing-empty-folder removal, all supported image
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

## Four-region parametric curves

The Mac Tone Curve panel now switches between Parametric and Point editors.
Parametric mode exposes Highlights, Lights, Darks and Shadows, graph-region
highlighting, vertical curve dragging, three draggable split handles and numeric
split percentages. Sliders and graph/split gestures preview temporary changes and
save one captured edit on release; Escape cancels. Graph dragging solves for the
requested output at the captured input, bounded by the selected region's amount
limits. Keyboard/numeric controls expose the same values. Reset Splits preserves
amounts; Reset Parametric Curve restores both while preserving all point curves.
Older three-region adjustments remain in a separate Legacy Region Adjustments
disclosure, with an indication when active. Their stored meaning is unchanged.

Five neutral-default fields extend Recipe v2: four amounts in -100…100 and three
normalized splits in one array. Default boundaries are 0.25/0.5/0.75; each region
must be at least one percent wide. Amounts and boundaries stay independent.
The transform composes four C1 smoothstep warps in dark-to-light order. Region
centers set their peaks; adjacent centers bound their overlapping support. Each
map has positive slope even at extreme amounts, so composition cannot reverse
tonal order. Encoded luminance maps to one linear RGB gain before the separate
RGB point curves. Black, white, out-of-SDR luminance and unchanged regions retain
their input pixels; all-zero amounts bypass the stage even with custom splits.
This is a documented LumaRAW equation, not Adobe's proprietary processing.

Sixteen cached floats fit in the existing 640-float Metal v2 parameter buffer.
Parametric, point and ordinary HSL combinations remain fused. CPU reference,
strip/viewport behavior and the shared preview/export path remain intact. Tone
Curve sync includes all new fields; full presets now contain 78 editable fields.
Old JSON defaults on read without rewriting source recipes. Partial presets,
undo, import settings, snapshots, bundles/backups and frozen jobs use the shared
recipe contract. Both native curve editors use one coalescing preview scheduler;
a pending request reads its latest draft only when current image work finishes.

The full Python run passes **560 tests, no skips**, including the pinned Nikon
D3S NEF and required Metal. New tests cover every region's direction/support,
known center outputs, all sixteen extreme sign combinations across four split
layouts including 1% regions, monotonicity, smooth joins and bounded derivatives.
Other cases cover exact unused pixels, color ratios, strip/detail consistency,
old JSON, complete presets, sync conflicts, undo, frozen exports, backup/bundles,
temporary-preview restoration and original hashes. Existing frozen legacy pixel
fixtures still pass. Metal covers the combined curves in all four output spaces.

Regression exposed avoidable encode/decode rounding on unchanged white pixels;
both backends now bypass that round trip for unchanged tones. A combined-curve
fixture also placed many ProPhoto channels on the gamut-warning threshold:
37 binary markers initially differed, each within 7.153e-7 linear units of that
threshold. Production thresholds remain unchanged. Regression now requires every
marker disagreement to be within 1e-6 of a reference boundary, replacing the
previous arbitrary count allowance. Encoded/decoded color bounds remain unchanged;
this is a stated marker uncertainty, not bit-identical gamut classification.

The app builds and passes local ad-hoc signature verification on macOS 26.6.2,
targeting macOS 14. Engine generation **26**, schema **21**, **111 tools**, 78
editable recipe fields and the bundled guide match the current source. Its engine
source digest is
`687ae9e462da5edb2241f6d97c08bf96ec824aa081890c500303988775f49367`.
PyInstaller retains the known absent `scipy.special._cdflib` hidden-import warning;
Swift compilation has no warnings or errors. Before this increment a remote
refresh found no branches outside the ancestry of the development branch.

The final packaged engine passes **133 assertions in six native suites**:
parametric curves (30), point curves (28), Develop presets (28), state conflicts
(15), import settings (22) and connection handoff (10). Parametric graph samples
differ from the engine by at most **1.078e-7** normalized units, including narrow
regions. Tests also verify output-following graph drags and unreachable endpoints,
latest-draft scheduling, pending-request cancellation, one-step history, reset
independence, undo, stale edits, photo switches and preservation of originals.
These are native state/IPC results; rendered interactions are not inferred.

Sequential packaged-worker measurements use the pinned 4284×2844 Nikon D3S NEF
on Apple M3 Max, 128 GB, arm64 macOS 26.6.2. The recipe combines all four regions,
custom splits, all four RGB point curves, legacy tone and color adjustments. One
empty-application-cache preview, two warm previews, one full-size ProPhoto 16-bit
TIFF and one 1280×900 detail pair are compared. Warm wall values are medians of
two; RSS is the maximum sampled value for each row. No tests/builds run concurrently.
Wall time includes startup, initialization/copies and encoding, excluding IPC and
desktop drawing. Empty application cache does not imply cold OS/shader caches.

| Operation | CPU wall | Metal wall | CPU / Metal peak RSS |
| --- | ---: | ---: | ---: |
| Cold preview, 1680×1115 | 2.240 s | 1.240 s | 213.52 / 167.62 MiB |
| Warm preview | 1.976 s | 0.794 s | 206.81 / 163.62 MiB |
| Full-size TIFF | 7.255 s | 1.203 s | 491.27 / 231.08 MiB |
| Detail viewport | 1.489 s | 0.692 s | 191.11 / 160.95 MiB |

Each GPU worker reports fused grading without fallback: 18 tiles per fitted
preview, 23 per export and 16 per detail. Shared buffers peak at 19.61 MiB. All
CPU/Metal pairs differ by at most **one code value**, including the full 16-bit
export (eight-code limit; mean difference 0.001957 codes). The original hash is
unchanged. Full-export wall speedup is **6.031×** for this fixture/recipe; these
samples do not establish general speedups or interactive drag latency. A generated
preview was inspected as an image, not as desktop or Adobe-reference evidence.

Public-source and extracted strict-archive gates cover **325 files with zero
findings**. Private test photographs, catalogs, processing outputs and raw receipts
remain excluded from source. This checks the current source/index and archive,
not Git history or every possible credential format.

Targeted adjustment on the photograph, curve-only exchange, Adobe processing and
reference acceptance remain open. Desktop slider/graph/divider gestures, focus,
keyboard dispatch, VoiceOver and macOS 14 runtime remain unverified. Implemented
region controls and numerical consistency do not complete Lightroom parity.

### Photograph-targeted parametric curves

The Mac Parametric panel's **Adjust in Photo** action and Tools menu now enable
photo-space tone targeting. Hover shows the corresponding curve input and region;
an upward/downward drag changes that region through temporary previews. Release
saves one revision, Escape restores saved settings, and a click without movement
creates no edit. Up/Down adjust the selected region after its preview is ready.
Fit uses the centered image rectangle; 1:1 attaches to the actual Retina-scaled
image inside the scroll view. Before/split comparison, pending edits and stale
photo/revision/viewport captures cannot be used to submit a targeted edit.

The engine optionally produces a geometry-aligned pre-parametric luminance map
while processing preview strips. Source stat identity, upstream recipe settings
and actual geometry define its cache key. Parametric/RGB curves, color mixing,
masks, LUTs and display proofing do not invalidate this input stage. Repeated
pointer events use a bounded native map lookup with no worker request; subsequent
curve previews reuse the map. The portable binary contract has explicit byte
order, dimensions and stage, with a maximum 12 MiB pixel payload. The shell
validates its size/header and rejects invalid samples. Ordinary previews/exports
do not capture extra tones. Originals remain read-only and no migration is added.

The complete Python suite passes **589 tests, no skips**, including the fixed
Nikon D3S NEF and required Metal. New coverage includes all eight catalog
orientations, legacy recipe rotation, crop/aspect/straighten/perspective/lens
geometry, reduced fits and detail ROIs, upstream invalidation, downstream and
display-warning cache reuse, binary bounds/corruption, temporary-worker previews,
revision conflicts and unchanged source hashes. The synthetic coordinate cases
compare independent full-image transforms with strip/ROI maps.

The Mac app builds and passes ad-hoc signature verification for the macOS 14
target on macOS 26.6.2. Engine generation **27**, schema **21**, **111 tools** and
78 editable recipe fields remain consistent; the bundled guide matches source.
Source digest:
`894f5aa631d1e3d40f8c7c9a4859c0f81625fc3b0fd58e13c011c3f4fccfee28`.
The existing PyInstaller `scipy.special._cdflib` hidden-import warning remains;
there are no Swift compilation warnings/errors. The remote refresh found no
unmerged branches before this increment.

The packaged engine passes **167 assertions in six native suites**: targeted
curves (33), parametric curves (30), point curves (28), orientation (51), shared
state (15) and connection compatibility (10). Targeted cases include bounded
binary decoding, top-left/edge samples, fitted/Retina rectangles, temporary values,
one release/one revision, click-only no-op, retained keyboard target, cancellation,
stale zoom/pan, before/split guards, service conflicts and photo switching. Tests
use isolated generated photographs and actual IPC; originals retain their bytes.

Sequential packaged workers use the same pinned 4284×2844 Nikon D3S NEF and the
previous increment's combined parametric/RGB/legacy/color recipe, on Apple M3
Max, 128 GB, arm64 macOS 26.6.2. Here previews request tone maps and omit before
images, matching draft processing. There is one empty-application-cache preview,
two warm previews, one full-size ProPhoto 16-bit export and one 1280×900 detail
pair. Warm timings are medians of two; RSS is the maximum sampled per row. Tests
and builds had finished before these sequential runs.

| Operation | CPU wall | Metal wall | CPU / Metal peak RSS |
| --- | ---: | ---: | ---: |
| First preview and tone map, 1680×1115 | 1.943 s | 1.084 s | 186.97 / 158.34 MiB |
| Warm preview with map reuse | 1.537 s | 0.610 s | 176.27 / 136.70 MiB |
| Full-size TIFF | 7.108 s | 1.166 s | 402.67 / 233.91 MiB |
| Detail with first viewport map | 1.288 s | 0.667 s | 167.23 / 144.50 MiB |

Map payloads plus headers are 7,492,816 bytes fitted and 4,608,016 bytes detail.
The first Metal-worker capture stages take 0.156 s fitted and 0.096 s detail;
warm receipts reuse the file and contain no capture stage. CPU/Metal maps have
identical hashes. GPU grading remains fused (9 fitted, 23 export, 8 detail tiles)
with no fallback. All output pairs differ by at most one code value; the 16-bit
export's mean difference is 0.001957 codes. Source SHA-256 is unchanged. The
full-export wall ratio is 6.094× for this sample. These timings include process
startup/encoding but exclude broker IPC and desktop events, and are not pointer
latency or a general speed claim. Empty application cache is not cold OS/shader
cache. The generated preview was inspected as an image, not as a desktop test.

Public-source and extracted strict-archive gates cover **330 files with zero
findings**; ignored photographs, catalogs, logs and raw receipts remain private.

The coordinate/state checks do not establish rendered Mac interaction, actual
pointer/keyboard/VoiceOver dispatch or macOS 14 runtime behavior. Desktop
automation was unavailable for this increment. Point/channel targeting, curve
exchange, Adobe processing/reference acceptance and the wider feature inventory
remain open. This workflow does not complete Lightroom parity.

### Photograph-targeted Color Mixer and Black & White Mix

The Mac Color Mixer now offers photo-targeted Hue, Saturation and Luminance;
Black & White Mix has its own target. A sampled color can move up to three
contributing bands together, preserving stored hue-degree units and displaying
temporary slider values. Dragging previews without changing the recipe; release
saves one multi-band revision. Escape, tool/photo/viewport changes and conflicts
discard or reject stale captures. Click-only gestures produce no edit. Up/Down
adjust the retained target after its preview is ready. Neutral areas are excluded.
Both fitted and 1:1 views reuse the photograph-aligned coordinate model.

The portable engine captures existing circular band supports before HSL or, for
B&W targeting, after HSL and before monochrome conversion. It divides weights by
the strongest band and retains the existing neutral protection. This is LumaRAW
control behavior, not a recovered Adobe transform. At most three bands overlap;
a 16-byte record retains IDs/count and three float32 weights without quantization.
The maximum map payload is 48 MiB, half a dense eight-weight map. Strip processing
and direct buffer writes avoid a second full byte copy. Cached input maps survive
downstream edits; HSL edits invalidate B&W input maps. Normal rendering does not
request these maps. Native pointer events read the map without image-worker IPC.

`mixer_patch` previews only the 32 existing mixer fields at a captured revision;
it is mutually exclusive with `curve_patch`. It does not write history, recipes
or originals. The shared coalescing scheduler now serves both draft types.
No new recipe fields or catalog migration are added. Engine generation **28**,
schema **21**, **111 tools**, 78 editable recipe fields and bundled guide agree.
The source digest is
`f1441c0f7c81c7309f8dc156d435de3e737d69d5195df8abda7d8d2892ab59d0`.
Mac compilation and ad-hoc signature verification pass; the existing PyInstaller
`scipy.special._cdflib` hidden-import warning remains. The pre-increment remote
refresh found no unmerged branches.

The complete Python suite passes **612 tests, no skips**, including required
Metal and the pinned Nikon D3S NEF. New tests compare sparse weights with an
independent dense color-circle reference, exercise three-way support/neutral
protection and all four adjustment directions, and check pipeline-stage order,
all orientations, crop/detail coordinates, cache boundaries, binary limits and
real-worker draft/history/source safety. Circular float32 versus float64 arithmetic
differs by up to 1.413e-6 in the dense fixture. Whole-image versus SIMD strip-edge
color evaluation initially exposed up to 2.349e-5 weight differences. Acceptance
now explicitly bounds the resulting 200-unit gesture error below 0.01 control
units, rather than requiring packed-integer equality. Transport preserves the
float32 values; production processing and its existing pixel tolerances are unchanged.

The final packaged engine passes **188 assertions in seven native suites**:
mixer targeting (48), existing Color Mixer (24), curve targeting (33), parametric
curves (30), point curves (28), shared state (15) and connection compatibility
(10). New checks cover exact sparse decoding, neutral/invalid samples, neighboring
band contributions, hue display/storage conversion, transient sliders/previews,
one multi-band history step, keyboard weights, cancellation, treatment-aware
sampling, undo, stale zoom/pan, external conflicts, photo/tool switches and source
bytes. The packaged guide and manifest match the source used by these checks.

Sequential packaged-worker probes use the pinned 4284×2844 Nikon D3S NEF on Apple
M3 Max, 128 GB, arm64 macOS 26.6.2, after all tests/builds finish. HSL uses the
combined parametric/RGB/legacy/color recipe; B&W uses the existing eight-band
color-and-monochrome recipe. Each has one empty-application-cache preview, two
warm previews, one full-size ProPhoto 16-bit TIFF and one 1280×900 detail pair.
Preview requests include maps and omit baseline images. Warm times are medians
of two; RSS is the maximum sampled per row.

| Target / operation | CPU wall | Metal wall | CPU / Metal peak RSS |
| --- | ---: | ---: | ---: |
| HSL first preview, 1680×1115 | 2.592 s | 1.664 s | 215.16 / 206.89 MiB |
| HSL warm preview | 1.557 s | 0.618 s | 177.19 / 137.34 MiB |
| HSL recipe full-size TIFF | 7.273 s | 1.291 s | 405.44 / 229.72 MiB |
| HSL detail with first map | 1.752 s | 1.107 s | 184.66 / 179.47 MiB |
| B&W first preview, 1680×1115 | 2.692 s | 1.692 s | 168.58 / 175.31 MiB |
| B&W warm preview | 1.489 s | 0.484 s | 129.56 / 119.56 MiB |
| B&W recipe full-size TIFF | 7.151 s | 1.148 s | 283.45 / 213.25 MiB |
| B&W detail with first map | 1.641 s | 0.956 s | 146.28 / 147.53 MiB |

Maps including headers occupy 29,971,216 bytes fitted and 18,432,016 bytes detail.
First Metal-worker capture stages take 0.778/0.888 s fitted (HSL/B&W) and
0.493/0.512 s detail. This remains a CPU capture cost on a new input/viewport;
warm receipts reuse the map and execute no capture stage. CPU/Metal map hashes
match exactly, including three-band overlaps. All output pairs differ by at most
one code value, including full 16-bit exports. GPU grading stays fused with no
fallback (9 fitted, 23 export, 8 detail tiles), and source hashes are unchanged.
Worker timing includes startup/encoding but excludes broker IPC and display;
it is not mouse-drag latency or a general speed guarantee. Empty application
cache does not imply cold OS/shader caches. The monochrome output was inspected
as a generated image, not as desktop or Adobe-reference evidence.

Public source/index and strict extracted-archive checks cover **335 files with
zero findings**. Private photographs, catalogs, process logs and raw receipts
remain excluded from publication.

Rendered Mac target controls, actual mouse/key dispatch, VoiceOver and macOS 14
runtime remain unverified; desktop automation was unavailable. Adobe color,
interaction/reference acceptance, Point Color and the wider inventory remain
open. These additions do not complete Lightroom parity.

## Durable Develop history and redo (September 29, 2026)

This increment replaces the destructive fifty-step undo stack with a persistent
per-photo timeline. The Develop inspector lists sixty summaries at a time with
Older Steps/Latest navigation, a current-state marker, action labels/values and
timestamps. Selecting an earlier state preserves later states; an actual new edit
replaces only that future branch. Command-Z and Shift-Command-Z navigate Develop
states. Right-click rename and confirmed Clear History preserve current pixels;
clear establishes a new baseline and cannot itself be undone. Named snapshots,
orientation history and frozen export jobs remain independent.

The baseline includes import presets or a virtual copy's inherited recipe.
Schema 22 preserves every legacy history ID, action label, timestamp and remaining
recipe through an atomic conversion; steps discarded by older versions cannot be
recovered. Step identities are not reused after branching or clear. Normalized
no-op edits/preset applications preserve redo. Direct edits, selective sync,
recipe/snapshot restoration and preset application share one transaction-aware
writer. History summaries avoid full recipes and photo/keyword payloads, using
indexed keyset pages. Backup restore rebinds LUT assets in both states and the
initial recipe. The portable service owns these rules; the Mac shell only presents
captured revisions and rejects stale actions without replay.

A refreshed remote inspection found no unmerged branches before implementation.
The isolated Apple Silicon app builds for macOS 14 and passes ad-hoc signature
verification on macOS 26.6.2. Engine generation **29**, schema **22**, **116 tools**,
78 editable recipe fields, bundled usage guide and source digest
`63e292635ac9972604bf64907d85d5f6999f5062683fe2c932cb04fa72ea022c`
agree. The packaged engine executable SHA-256 is
`75d599fcdc8eed62a1a04a9412e76f24e8dad9450f062448abf501cf0da13b24`.
No image-processing equation or tolerance changed in this increment.

The full Python suite passes **627 tests without skips**, including the
fixed Nikon D3S NEF and required Metal execution. New cases cover retained redo,
branching/no-ops, all revision barriers, complete bounded pagination, payload-free
reads, rename/clear, copy isolation, import-preset baselines, snapshots/jobs/source
safety, transactional rollback and backup assets. Genuine schema-21 migration
failure injection rolls back both payload conversion and added schema; retry and
idempotence preserve all surviving steps.

Initial verification exposed two issues, retained in private receipts: a legacy
schema-8 fixture invoked the current editor instead of seeding its published SQL
shape, and a queued automatic native refresh could supersede an explicit history
read. The fixture now uses the actual old history representation. Native refresh
coalesces the same photo/revision and leaves active explicit reads intact. The
new native source probe then passed 23 state assertions. Before the final MCP
effects-only annotation, the packaged engine passed **192 native assertions across
eight suites**: History (23), Develop
Presets (28), Virtual Copies (19), Import Processing (22), Orientation (51), Color
Mixer (24), State (15) and Connection (10). The final metadata-only change marks
`clear_history` as destructive for MCP clients; **35 targeted Python history and
service tests** pass afterward, including the new annotation check. The final
packaged MCP handshake/tools listing confirms all 116 tools and that declaration.
Catalog/native behavior and the measured processing paths are unchanged by it.

Isolated catalog measurements use generated 64×48 PNG originals, one synthetic
photo timeline, and sequential service processes on Apple M3 Max / 128 GiB,
arm64 macOS 26.6.2. Each repeated operation has 30 warm samples. Timings include
schema/connection checks, service validation and SQLite commits, excluding setup,
broker IPC, image work and the desktop. These are not slider-to-preview timings.

| Operation, median / p95 | 1,000 steps | 100,000 steps |
| --- | ---: | ---: |
| Newest 60 summaries | 1.494 / 1.646 ms | 1.476 / 1.664 ms |
| Deep 60-summary page | 1.542 / 1.806 ms | 1.470 / 1.537 ms |
| Undo then redo | 3.683 / 4.219 ms | 3.512 / 4.045 ms |
| Jump to baseline then latest | 3.793 / 4.494 ms | 3.643 / 4.291 ms |
| Append one changed edit | 2.230 / 2.337 ms | 2.079 / 2.164 ms |

The page responses are 4,364 / 4,730 bytes and peak process RSS is 40.17 / 40.47
MiB. A single replacement of the future half took 2.676 / 38.827 ms; a subsequent
single clear took 2.157 / 42.389 ms. Those deletion observations are not percentile
distributions; deletion cost grows with affected steps. Both runs started zero
image workers and retained identical original hashes. No per-machine timing limit
is embedded in the regression suite.

Rendered desktop History controls, actual menu/key dispatch, VoiceOver, and the
macOS 14 runtime remain unverified. Global application undo, hover previews,
copying a History state to Before, and full snapshot management remain gaps.
The module retains the existing PyInstaller warning about optional
`scipy.special._cdflib`; no Swift compiler diagnostics occurred. This increment
and these synthetic catalog results do not complete Lightroom parity.

The final package additionally passes History (23) and Connection (10) again:
**33 assertions revalidated after the annotation change**. Source/index and strict
extracted-archive publication checks cover **340 files with zero findings**.
Generated originals, catalogs, builds, timing receipts and process logs remain
private and excluded from the source checkpoint.

## Persistent Before / After and independent cache (September 29, 2026)

A refreshed remote inspection found no unmerged branches before implementation.
The Apple Silicon app builds for macOS 14 and passes ad-hoc signature verification
on macOS 26.6.2. Engine generation **30**, schema **23**, **117 tools**, 78 editable
recipe fields, bundled guide and source digest
`a861d2b98054ddd4a0f43e0eb51bb0c2799ed82eca6bbd01bbb28946fee782ef`
agree. The packaged executable SHA-256 is
`3b551a961280b90ccfb0dec79a0e82ed0ceec7a4fa0604780d821ed5a9dc2f94`.
The actual packaged MCP handshake/list verifies the new action schema. Swift
compilation has no diagnostics; the existing optional PyInstaller
`scipy.special._cdflib` hidden-import warning remains.

Before now stores its own per-photo recipe, initially the imported settings
including presets, or a virtual copy's inherited settings. The native Before /
After menu provides After Only, Before Only, Left/Right Split and complete-recipe
copy/swap actions. A History context action copies any retained step to Before
without selecting it. Restart, history branching and Clear History retain the
chosen Before. Copying to After and swapping produce ordinary Develop edits;
Before-only assignments preserve the cursor and redo branch. Develop undo affects
After only. Swap writes both sides atomically, and stale actions fail without replay.

Schema 23 seeds existing photos from their earliest retained history baseline;
it cannot reconstruct discarded import settings. Transactional insert/delete
triggers keep imported photos and virtual copies independent. Backup restore
rebinds assets referenced only by Before. The portable service captures both
recipes under its catalog lock before starting image work. No public preview
parameter can replace the stored baseline.

Before keeps its own light/color/detail settings but previews through current
After geometry, preserving the existing aligned-comparison boundary. The full
stored recipe is still transferred by copy/swap. Hidden Before omits its image
work; unchanged Before uses an independent source/recipe/viewport/orientation/
display cache. After light changes therefore avoid grading Before again, while
geometry changes invalidate it. Cache hits validate the entire PNG; misses use
atomic replacement. Source identity changes during rendering fail visibly.
The native shell captures photo/revision/view context before reusing a loaded
Before image. Processing equations and numerical tolerances remain unchanged.

The final Python suite passes **649 tests without skips**, including the fixed
Nikon D3S NEF and required Metal execution. New coverage includes all four actions,
full copied geometry/masks, no-op behavior, persistent labels, history independence,
virtual copies, frozen jobs/originals, stale/invalid actions, swap rollback,
Before-only LUT restoration and genuine schema-22 migration failure/retry.
Generated reference pixels cover cache hit/repair/skip behavior, source replacement
and all eight orientation mappings in full-resolution viewports. A real-worker
case verifies persisted Before pixels and cache receipt. Initial targeted failures
were two test cleanup calls using an unsupported Catalog context manager; those
fixtures now use explicit closing and all targeted/full runs pass afterward.

The final package passes **221 native assertions across eight suites**:
Before/After (19), History (23), Import Processing (22), Orientation (51), Curve
Targeting (33), Mixer Targeting (48), State (15) and Connection (10). New state
coverage exercises on-demand Before, loaded-image reuse, fit split/detail state,
copy/swap/history actions, photo switching, pending edits, stale writes and
original bytes. These probes compile the real native controls and use the broker
and packaged workers; they do not dispatch desktop input.

The sequential RAW probe uses the fixed public Nikon D3S NEF (4284×2844,
10,656,312 bytes, SHA-256
`5922721d13f11795557d97fdeb0a60b900086c402bc82a848ff280d15b99ffd4`)
on Apple M3 Max / 128 GiB, arm64 macOS 26.6.2. Fitted outputs are 1680×1115;
detail outputs are 1280×900. Each row is one observation, except warm fit, which
shows two samples. All builds/tests had finished. Times include worker launch,
decode/cache, processing and PNG encoding; they exclude IPC/native interaction.
An empty application cache is not a cold OS/GPU cache.

| Request | CPU wall | Metal wall | Before cache |
| --- | ---: | ---: | --- |
| Empty-cache fit | 1.905 s | 0.961 s | Miss |
| Warm fit, two observations | 1.280 / 1.276 s | 0.572 / 0.567 s | Hit |
| After exposure change | 1.275 s | 0.574 s | Hit |
| After straighten change | 2.064 s | 1.134 s | Miss |
| First full-resolution detail | 1.952 s | 1.191 s | Miss |
| Warm detail | 0.998 s | 0.526 s | Hit |
| After only | 1.370 s | 0.594 s | Omitted |

The first fitted Metal request dispatches eighteen grade tiles; warm fit and
changed exposure dispatch nine, with no Before-render stage. Detail drops from
sixteen to eight. Geometry changes dispatch both sides again. These stage/cache
receipts establish avoided work; the noisy single After-only wall observation is
not a comparative speed claim. Maximum sampled process RSS across all cases is
483.67 MiB CPU / 367.19 MiB Metal (20 ms sampling). Both sides differ by at most
one 8-bit code between CPU and Metal. After-only pixels equal the corresponding
comparison After, and exposure changes retain the same Before PNG. Original
hashes are unchanged. Generated fitted Before/After images were inspected; this
is output-image inspection, not a desktop screenshot or Adobe accuracy check.

Whole-image pairs, top/bottom layouts, history hover previews, global undo of
Before assignments and complete snapshot management remain gaps. Rendered Mac
controls, actual pointer/key dispatch, VoiceOver, macOS 14 runtime and Adobe
reference/pixel acceptance remain unverified. These limitations are not replaced
by state probes or build success; full Lightroom parity is not complete.

## Four comparison layouts and shared detail viewport (September 29, 2026)

The Mac Before/After menu now offers whole-image Left/Right and Top/Bottom pairs,
and Left/Right and Top/Bottom splits. One mode value replaces contradictory
Before-only/paired flags. Each side displays the same captured photo, revision,
orientation, proof options and viewport, with explicit Before/After labels.
Split boundaries use the actual image rectangle, including letterboxing.
Fitted layout changes and the divider slider reuse loaded images.

All four modes retain Fit or 1:1 Detail zoom. Detail pane dimensions convert from
points to physical pixels and are bounded by the existing 2048×1536 contract.
Dragging either side moves both displayed images; release requests one shared
engine viewport. Panning starts from the returned ROI center, so out-of-range
requested centers do not cause sticky edges. Captured photo/revision/viewport
and mode guards reject old drags. The existing Inspector position sliders also
move both sides. Y, Option-Y and Shift-Y route through the focused photo surface
to the horizontal, vertical and corresponding split layouts; repeating a choice
returns to After. Crop/mask and photo-targeted editing still leave comparison.
D returns to the normal Develop After view and exits drawing tools.

This increment changes native presentation and its test harness only. Portable
engine, recipes, schema, API and numerical processing are byte-for-byte unchanged
from the preceding module. Engine generation **30**, schema **23**, **117 tools**
and source digest
`a861d2b98054ddd4a0f43e0eb51bb0c2799ed82eca6bbd01bbb28946fee782ef`
remain valid. The preceding module's 649 Python checks and RAW timings belong to
that unchanged engine; they are not rerun or claimed as desktop layout timing.
The final Apple Silicon application builds for macOS 14 and passes ad-hoc
signature verification on macOS 26.6.2. Its packaged engine executable remains
byte-identical (SHA-256
`3b551a961280b90ccfb0dec79a0e82ed0ceec7a4fa0604780d821ed5a9dc2f94`).
The new native executable SHA-256 is
`deaec38ef730c037bc5faba6d1f4637b701cb2cdb88ede9eb4a28cf408b39a67`.
Bundled guide and manifest checks pass. There are no Swift compiler diagnostics;
the existing optional PyInstaller `scipy.special._cdflib` warning remains.

The new source-level native probe passes **38 assertions** with generated
2400×1800 originals. Coverage includes equal panes, aspect fit, image-relative
splits, Retina scale, reuse of loaded fit images, all modes at 1:1, bounded pane
resizing, actual ROI panning, edge clamps, invalid numbers, stale mode/photo/
viewport captures, shortcut routing, history/revision isolation and original
bytes. Initial test compilation failed on one missing operator space and use of
a private preview counter; tests now observe image reuse and published state
without weakening source encapsulation. Final package checks additionally cover
rotated output dimensions and displayed-coordinate panning.

Before the final D-entry correction, the packaged app passes **175 assertions
across six native suites**: Comparison Layouts (40), Before/After (19), Library
Review (20), Curve Targeting (33), Mixer Targeting (48) and State (15). Source
review found that the old Develop entry retained paired/drawing modes; D now
returns to ordinary After and leaves drawing tools, with two additional checks.
The final package then passes **77 assertions** across Comparison Layouts (42),
Library Review (20) and State (15). Remote refresh again finds no unmerged branches.

Actual mouse/key dispatch, rendered desktop layouts, VoiceOver, multi-monitor
scale transitions and the macOS 14 runtime remain unverified. Native geometry/
state probes are not desktop acceptance. Reference matching, history hover,
global undo of Before assignment and the full product inventory remain open.

## Shared snapshot management (September 29, 2026)

The self-contained arm64 Mac app builds for the macOS 14 deployment target and
passes local ad-hoc signature validation on macOS 26.6.2. Engine generation
**31**, catalog schema **24**, **120 tools**; packaged MCP schemas and the bundled
guide match current source. The engine manifest digest is
`4d37ea21d0248a98906eb66bbec7c141d3f7e7bb06fa8d3c121603ac543e1369`.
Packaged engine SHA-256 is
`84660806a730f14078bcc3a069f9bf727ec875bf0ce0ea2503e56c68106b299e`;
native executable SHA-256 is
`46dc8a757996e0840b68a72183a1c5033b2382a49d30955602f7293cb8d05c15`.

Snapshots now support named current settings and retained history-step capture,
alphabetical pages, rename, Update with Current Settings, explicit deletion,
restore, and Copy Snapshot Settings to Before. The Mac inspector has a Snapshots
panel, a separate browser, captured name forms, context/row menus and a Develop
Command-N entry. Update/delete confirmations explain the shared scope and lack
of Develop undo. A history snapshot does not select that state or truncate redo.
Snapshots stay shared after master promotion or removal of their creating copy.

Schema 24 preserves old IDs, recipe payloads, duplicate names and creation times,
adds non-reused identity allocation, per-snapshot revisions and source-family
list revisions, and indexes normalized alphabetical keys. Sixty-row keyset pages
avoid recipe/metadata reads and full-list materialization. Compact unchanged
polling retains the native page; a list mutation invalidates old cursors.
New names use NFC/casefold collision checks; duplicate creation never overwrites
stored settings. Existing duplicate legacy names remain distinguishable by ID.

Create/update/restore/Before assignment check the captured photo revision as
applicable; snapshot updates, restores, renames, deletion and Before assignment
check the snapshot revision. Native forms retain captured tokens when polling or
selection changes. Mutations and identity/list counters commit together; stale
or uncertain replies are never automatically retried. Current recipes, private
history, copied Before and frozen exports stay independent of snapshot CRUD.
Restoration creates an ordinary Develop step; Before receives a separate complete
recipe. Backups preserve revisions/counters and rebind snapshot-only LUT assets.

The existing command names remain available. Older save callers may omit the
photo revision, and older restore callers may omit the new snapshot revision;
the Mac client supplies the relevant captured values. List replies keep the
`versions` field but now return alphabetical summary pages of sixty with cursors,
rather than the legacy newest-first list capped at one hundred.

Snapshot hover/Navigator previews, snapshot-status Library/smart filters, Adobe
sidecar exchange, global snapshot undo and rendered reference acceptance remain
open. No Adobe pixel-equivalence claim follows from saved recipe restoration.

### Snapshot regression and catalog measurements

The full required-Metal Python run passes **663 tests in 57.02 s, no skips**,
including the fixed public Nikon D3S NEF fixture used by preceding increments.
Fourteen snapshot cases cover shared/current/history behavior, preserved frozen
values, conflicts, legacy commands, recipe-free pages, name rules, transactional
failure injection, identity persistence and schema-23 upgrade rollback/retry.
A snapshot-only LUT backup also retains IDs/revisions/counters and restored asset
bytes. Initial targeted failures used an incorrect virtual-copy response key;
the first full run exposed a v8 migration fixture calling the new snapshot writer.
The fixtures now use the existing `photos` response and the actual old schema;
no migration-preservation assertion was removed.

Sequential warm catalog probes on Apple M3 Max / 128 GiB / macOS 26.6.2 use one
generated 64×48 original and 1,000 or 100,000 seeded snapshot rows. Thirty samples
per operation include in-process service validation, SQLite opens and commits;
setup, IPC, image processing, cold OS caches and native interaction are excluded.

| Operation | 1,000 rows median / p95 | 100,000 rows median / p95 |
| --- | ---: | ---: |
| First 60 summaries | 1.621 / 1.938 ms | 1.562 / 3.704 ms |
| Deep keyset page | 1.623 / 1.685 ms | 1.625 / 1.871 ms |
| Conditional unchanged read | 1.473 / 1.560 ms | 1.483 / 1.742 ms |
| Rename | 1.862 / 1.981 ms | 1.943 / 2.821 ms |
| Update settings | 1.913 / 2.004 ms | 1.917 / 2.102 ms |
| Create + delete pair | 3.709 / 4.035 ms | 3.787 / 5.205 ms |

Summary pages are 6,405 / 6,407 bytes and unchanged receipts 99 / 101 bytes.
Peak process RSS is 37.88 / 39.06 MiB; no image worker starts and original hashes
remain unchanged. Reproduce with `tests/snapshot_probe.py`. These measurements
establish bounded catalog behavior, not RAW or desktop responsiveness.

The final packaged engine passes **161 assertions across seven native suites**:
Snapshots (33), Virtual Copies (19), History (23), Before/After (19), Comparison
Layouts (42), State (15) and Connection (10). New coverage includes captured
forms, snapshot/photo conflicts, explicit refresh without rebasing, conflict
messages surviving background polling, shared-copy deletion, frozen Before,
history capture, bounded alphabetical paging and pending-edit barriers. The
initial source probe read before asynchronous virtual-copy selection finished;
its fixture now awaits the existing selection lifecycle. Source checks then
passed 32 assertions, with the polling-error assertion added for the final
33-assertion packaged run.

Swift compilation and native logs have no warnings/errors. Packaging retains the
existing optional SciPy `_cdflib` hidden-import warning; exercised processing
checks passed. Current source/index and extracted strict archive checks cover
**353 public files with zero findings**. A remote refresh before this increment
found no unmerged branches; local main and remote main remain ancestors of the
development branch.

Actual desktop sheets/menus/Command-N routing, mouse interaction, VoiceOver and
macOS 14 runtime are **not verified**. Native Store/IPC tests and compilation do
not replace those acceptance checks. Private catalogs, photographs, outputs,
builds and detailed receipts remain excluded from source publication.

## Snapshot-status Library and smart filters (September 29, 2026)

Library filters and smart-collection forms now offer Any, Have snapshots and
No snapshots. The shared `has_snapshots` boolean composes with All/Any rules,
nested collection sets, folder/subfolder sources, Previous Import, search and
sorting. Originals and virtual copies share presence; retained history, Before
settings and presets do not count as named snapshots. This implements the
documented criterion, not the complete Lightroom metadata-filter interface or
all smart-collection criteria.

Schema 25 backfills indexed family counts without rewriting snapshot payloads.
Insert/delete/source-change triggers keep counts and a compact first/last-change
revision in the same transaction, including bulk catalog removal. Additional
snapshots, renaming and settings updates do not invalidate presence. Library
replies carry the revision so empty pages and off-page changes can be observed
without an extra polling request. Native filtered/collection sources refresh
without changing their source configuration; pending edits, active history or
snapshot commands, and captured snapshot forms defer the refresh. Unfiltered
catalog pages avoid unnecessary queries.

Counts retain indexed source membership. Import-order pages with at least sixty
matches and 5% catalog density use correlated family checks, avoiding a sort of
every matching family. Sparse results, other sort orders and actual stack
projections keep indexed membership. Both forms produce the same ordered pages;
the optimization does not change filtering or stack semantics.

The final required-Metal Python suite passes **671 tests in 70.44 s, no skips**,
including the existing fixed public Nikon D3S NEF. Eight new cases cover shared
presence, live scopes and collections, bounded recipe-free queries, strict
booleans, injected transaction failure, adaptive ordering, bulk deletion/moves,
schema-24 upgrade rollback/retry and restored triggers. The old-schema fixture
uses the published row layout rather than the current writer. A source-level
native probe passes **25 assertions**, including empty-list recovery, captured
form/pending-edit guards, nested-set updates and original-byte preservation.

### Snapshot-filter catalog measurements

Sequential warm probes use Apple M3 Max / 128 GiB / macOS 26.6.2, one generated
64×48 original and 1,000 or 100,000 catalog rows with minimal recipes. Initially
one fifth of source families have snapshots. Thirty samples include service
validation, SQLite opens, exact counts and bounded pages; setup, IPC, pixels,
cold OS caches and desktop interaction are excluded. Sparse and empty phases
then remove snapshots in the same disposable catalog.

| Operation | 1,000 photos median / p95 | 100,000 photos median / p95 |
| --- | ---: | ---: |
| Have snapshots, first 60 | 4.812 / 5.330 ms | 10.913 / 12.787 ms |
| No snapshots, first 60 | 4.910 / 8.091 ms | 25.187 / 26.614 ms |
| Have snapshots, deep page | 4.744 / 6.128 ms | 23.199 / 24.374 ms |
| Smart collection | 4.718 / 5.099 ms | 10.944 / 12.847 ms |
| Presence plus rating | 4.838 / 5.447 ms | 17.372 / 20.880 ms |
| Stack visibility enabled, no groups | 5.503 / 21.926 ms | 10.541 / 12.020 ms |
| Sparse presence (1 / 100 matches) | 4.211 / 4.636 ms | 5.130 / 5.536 ms |
| Empty presence | 4.157 / 4.500 ms | 4.276 / 4.855 ms |
| Compact state poll | 1.282 / 1.515 ms | 1.342 / 1.644 ms |

Before the adaptive query change, the 100,000-photo first-page medians were
14.468 ms for Have snapshots and 44.187 ms for No snapshots, versus 10.913 and
25.187 ms afterward. These sequential synthetic measurements establish a query
improvement for this distribution, not a universal performance guarantee. Deep
offsets still incur traversal cost; small-catalog timings do not show the same
improvement. Full unstacked pages are 24,917–24,921 / 25,523–25,527 bytes;
state replies are 201 / 205 bytes. Peak process RSS is 47.61 / 91.45 MiB,
including probe setup and all phases. No image worker starts and original hashes
remain unchanged. Reproduce with `tests/snapshot_filter_probe.py`.

The arm64 Mac app builds for the macOS 14 deployment target and passes local
ad-hoc signature verification on macOS 26.6.2. Engine generation **32**, schema
**25**, **120 tools**; all packaged MCP schemas and the bundled guide match the
current source. Engine manifest digest:
`1ffeef484b9292833d909a83cbf05b596155787ebbc350d51c4b19d237900ddf`.
Engine executable SHA-256:
`a0f0ae4f346ccca22bc36146776cd9272a29d3599eb075eb7394eef49e07720d`.
Native executable SHA-256:
`2a99709a348e0a4f7e309b7c2641b73f581ce44870630bcce04ed2f8777c8ad8`.
Swift compilation has no diagnostics. The existing optional PyInstaller
`scipy.special._cdflib` hidden-import warning remains.

The final packaged engine passes **181 assertions across nine native suites**:
Snapshot Filters (25), Snapshots (33), Library (13), Collections (21), Thumbnails
(14), Previous Import (19), Folder Synchronization (24), Connection (10) and
Stacks (22). Logs have no Swift warnings/errors. These checks exercise native
state against the actual packaged engine, including safe pending-edit deferral,
original preservation and compatibility with existing organization workflows.

Current source/index and extracted strict archive checks cover **357 public
files with zero findings**. A remote refresh found no unmerged local or remote
branches; main remains an ancestor of the development branch. Generated catalogs,
photographs, build outputs and detailed receipts remain private and ignored.

Rendered filter forms, real desktop mouse/menu events, VoiceOver and the macOS 14
runtime remain **not verified**. Native state/IPC tests and a macOS 14 deployment
target do not establish desktop or older-OS acceptance. Complete metadata filter
facets, all smart criteria, snapshot hover and the full non-AI inventory remain
open; this increment does not complete Lightroom Classic parity.

## Develop Reference/Active comparison (September 29, 2026)

The Mac shell now exposes Photo > Open in Reference View, a Develop toolbar
entry and focused Shift-R routing. Assign a reference from Grid/filmstrip menus
or an in-app photo drag; select or drop another active photo without changing
reference identity. Left/Right and Top/Bottom pairs have independent Fit/1:1
controls, click-to-zoom and ROI-based panning. Letterbox clicks are ignored.
The active pane retains the inspector, local drawing and targeted curve/mixer
overlays, and can show its saved Before. Paired Before/After exits Reference View.

The session lock retains reference identity when leaving Develop; an unlocked
reference clears. D/Done returns to ordinary Develop without clearing assignment.
Crop selection offers a captured Continue/Cancel exit, rejecting a confirmation
after the active photo changes. Custom drag values contain only a session token
and one visible catalog ID; foreign sessions, unknown IDs and multiple items are
rejected. The app declares its custom data type in Info.plist as required by
Apple's Transferable contract. File URL drops keep their existing import workflow.

Reference identity is independent of the visible page and source-family roles.
Virtual copies can be references with their own saved edits. A removed reference
reports an error instead of silently choosing a replacement. Locking does not
freeze a recipe: bounded summary polling follows saved edits, including when
Reference and Active show the same photo. Ordinary multi-selection edits still
target Active, while explicit Sync retains its existing multi-photo behavior.

One independently cancellable reference frame is retained. Unchanged active
edits and fitted layout changes reuse it; hiding the view releases it. Detail
requests are bounded to 2048 by 1536 physical pixels and pans start from the
returned ROI, including at image edges. The reference omits Before work and uses
the same display/proof parameters as Active. The optional existing
`preview_photo.expected_revision` now checks ordinary previews before and after
processing, and compares path/size/mtime source fingerprints. Conflicts never
return the obsolete result or write its metadata receipt. These checks do not
hash the entire source or freeze files against subsequent external modification.

Engine generation **33**, catalog schema **25**, **120 tools**. Reference roles
are session presentation state, so no catalog migration or recipe changes are
introduced. App, CLI and MCP share the preview contract and bounded worker
pipeline; the portable engine gains no SwiftUI/AppKit dependency.

### Reference regression evidence

The full required-Metal Python suite passes **677 tests in 68.58 s, no skips**,
including the fixed public Nikon D3S NEF. Six new preview cases cover stale
revisions before work, edits and source changes during work, metadata-only
changes, Fit/detail geometry, ICC output, legacy commands and preservation of
recipes/history/originals. Related processing checks pass **84 tests**.

The final source-level Reference probe passes **51 assertions** with generated
2400 by 1800 originals. It covers roles, active-only edits, retained reference
pixels, independent zoom/pan, physical-scale bounds, edge reversal, stale drags,
Before toggling, drop validation, crop confirmation, module lock, source filtering,
virtual-copy removal, same-photo roles and late/mismatched preview replies.
Initial compilation exposed an ambiguous NaN in a test; it now uses CGFloat.
The first running probe exposed that Fit replies intentionally have no ROI;
native frames now use the whole proxy for Fit and require a real ROI for detail.
No assertion was removed to accommodate either correction.

Against the final packaged engine, nine native state/IPC suites pass **257
assertions**: Reference 51, Library Review 20, Comparison Layout 42, Before/After
19, Curve Target 33, Mixer Target 48, State 15, Connection 10 and Previous Import
19. These compile the final native source with the probe entry points, then use
the bundled engine; they do not drive the app executable's desktop controls.

### Reference processing evidence

The final packaged engine was measured on Apple M3 Max, 128 GiB, macOS 26.6.2,
using the public Nikon D3S NEF (4284 by 2844, 10,656,312 bytes, SHA-256
`5922721d13f11795557d97fdeb0a60b900086c402bc82a848ff280d15b99ffd4`).
Reference retains the original recipe; Active is a virtual copy with exposure,
shadows and blue-hue edits. Each backend has a fresh catalog/cache. Times below
are one sample per case, including CLI startup, IPC and worker processing; they
are not median or tail latency, and do not include native display. Cold means
application cache, not cold filesystem or GPU state. RSS is the sampled worker
peak, not total app memory.

| Preview | Output pixels | CPU ms / RSS MiB | Metal ms / RSS MiB | Actual Metal tiles |
| --- | --- | --- | --- | --- |
| Reference cold Fit | 1680 × 1115 | 991.1 / 334.8 | 832.0 / 292.6 | 9 |
| Active Fit | 1680 × 1115 | 1090.5 / 358.1 | 554.2 / 176.2 | 9 |
| Reference warm Fit | 1680 × 1115 | 724.3 / 237.1 | 561.8 / 176.0 | 9 |
| Reference cold detail | 800 × 600 | 1265.9 / 334.0 | 1138.6 / 333.0 | 5 |
| Reference warm detail | 800 × 600 | 451.9 / 125.3 | 449.6 / 95.8 | 5 |
| Active detail | 800 × 600 | 557.3 / 103.0 | 458.2 / 100.8 | 5 |

CPU/Metal output differs by at most one 8-bit code value per channel in every
case. Same-backend cold/warm pixels are identical; all outputs carry ICC data,
and the original hash is unchanged. Reference/Active Fit outputs were inspected
as generated images. This is not camera-color accuracy, Lightroom pixel matching
or desktop interaction evidence. The benchmark deliberately requests frames;
the separate native assertions establish that active edits reuse the retained
reference frame without another reference request.

### Reference package verification

The final macOS 14-targeted arm64 app builds without Swift diagnostics and passes
deep/strict local code-signature verification. Its exported internal photo data
type conforms to public.data. Packaged MCP initialization and all **120 complete
tool schemas** match source; the bundled guide is byte-identical. The source
identity matches the packaged generation-33 manifest:

- Source digest: `6571f57651dab7285f502bcccec1170c0136f35f5ecbf8e9f286d67e534597f0`
- Engine SHA-256: `ba35829d4ebef2801d46f6da30ef9680a66d8e68d0333899d69e5058dfe42671`
- Native executable SHA-256: `464858adf46dc228569d8e4c88177cc4bd090f6b1cdc8349ab75e8061e7fa695`

PyInstaller retains the previously documented optional `scipy.special._cdflib`
collection warning. The packaged RAW processing checks above pass; this does
not establish functionality of that optional SciPy submodule.

Reference RGB/LAB paired readouts, box/scrubby zoom and Lightroom-specific visual
or pixel matching remain open. Actual Mac drag/drop, keyboard dispatch, rendered
target/drawing overlay alignment, crop alert behavior, VoiceOver and macOS 14
runtime behavior remain **not verified**. State/IPC checks and generated image
inspection do not replace desktop acceptance. Reference comparison is a partial
vertical workflow in the full non-AI inventory, not completed product parity.

Current source/index and the extracted strict source archive cover **363 public
files with zero findings**. A remote refresh found no unmerged local or remote
branches; main remains an ancestor. Generated photographs, catalogs, packaged
binaries and private receipts stay ignored and excluded from the module commit.

## Native interaction responsiveness (September 30, 2026)

The app no longer launches a fresh engine executable for every button action,
poll, cancellation or preview command. A persistent correlated stdio relay keeps
the existing broker preflight and command contracts, and permits out-of-order
replies. Ordinary requests and cancellation/connection controls have separate
bounded admission and worker capacity. No failed or uncertain mutation is replayed
when a stream closes; a later new call can establish a replacement relay.

Native command serialization, pipe IO and JSON parsing occur on background queues.
There is one bounded watchdog for pending commands, not one long-lived timer per
call. Service version activation and active-work handoff retain the existing
broker rules. Engine generation is **34**, catalog schema remains **25**, and
the public command/MCP inventory remains **120 tools**.

Preview, Before, reference, Library comparison, thumbnail and import-review images
now load through a shared ImageIO preparation queue with two active decodes. The
[immediate decode option](https://developer.apple.com/documentation/imageio/kcgimagesourceshouldcacheimmediately)
is set before images reach the main actor; the embedded color space is preserved.
An explicit bitmap representation retains actual raster dimensions on Retina.
Frame owners validate their generation again after loading, preventing a late
decode from painting a different selected photo. Oversized or malformed images
are rejected without downsampling or silently changing 1:1 geometry.

Unchanged jobs/pause state, collection target/membership state, orientation state,
photo-family summaries and reference summaries retain their current presentation
values. Real catalog revisions and membership changes still publish updates.
Conditional snapshot reads coalesce without toggling published loading state or
reassigning an unchanged page. Explicit snapshot reads retain visible progress;
new family versions and changed photo revision captures still propagate.
Polling cadence and conflict barriers are preserved.

### Responsiveness regression evidence

The first transport probe exposed that macOS `read(upToCount:)` can wait to fill
its requested pipe length. A one-second stack sample confirmed the blocking read;
that isolated probe was deliberately stopped and the reader changed to consume
available bytes. The next probe passed transport checks but detected that
`NSImage(cgImage:size:)` reported a 2400 by 1800 fixture as 4800 by 3600 through
its snapshot representation on Retina. An explicit `NSBitmapImageRep` fixes the
representation; the assertion was retained. Neither initial probe is counted as
a passing run.

Before the final snapshot-poll refinement, the corrected source run passes
**65 native state/IPC assertions**: Responsiveness
14, Transport 26, State 15 and Connection 10. Ten unchanged background poll cycles
publish **zero Store updates**, while an external rating change still propagates.
Five unchanged reference refreshes also publish zero changes. The image checks
cover five generated 2400 by 1800 rasters, retained dimensions/color-space data,
invalid files, main-actor progress during loading and unchanged recipes/originals.
These simple solid-color fixtures establish behavior, not photographic decode
throughput or a frame-rate guarantee.

The Swift transport checks one reused relay PID, split UTF-8 frames, out-of-order
response IDs, typed activation errors, malformed/oversized replies, replacement
after failure and a simulated mutation committed immediately before process exit.
That mutation is recorded once and never resubmitted. The final source warm-status
probe records 30 samples: median **1.635 ms**, p95 **1.847 ms**, excluding pixels
and desktop rendering. Final packaged-engine measurements are separate evidence.

The full Python run passes **684 tests in 61.26 seconds with no skips**, with
required Metal dispatch and the fixed public Nikon D3S NEF. The final snapshot
refinement changes native polling only; it does not change the tested engine.

The final packaged generation-34 engine was measured without concurrent builds
or tests on macOS 26.6.2, Apple M3 Max, 128 GiB RAM. A new disposable catalog holds
one generated 160 by 100 PNG, with image jobs paused. Thirty sequential warm
samples per method alternate one-shot CLI and the persistent relay against the
same negotiated broker; no pixel work is included:

| Command | One-shot median / p95 | Persistent median / p95 |
| --- | --- | --- |
| Status | 54.481 / 62.541 ms | 2.182 / 2.384 ms |
| Photo read | 53.991 / 55.667 ms | 2.346 / 2.603 ms |

Median command overhead falls by about **96%**. The test uses one relay process
versus 62 CLI launches including setup. First CLI plus cold broker startup takes
805.977 ms; first relay command against the warm broker takes 59.106 ms. Relay RSS
at the end is 29.05 MiB; this is a point-in-time reading, not peak memory. Original
bytes and photo responses match. These numbers do not establish desktop frame
rate, slider-to-preview latency or RAW processing throughput.

The final Mac app builds for the macOS 14 deployment target and passes deep/strict
local code-signature verification. Packaged MCP initialization and all **120 full
tool schemas** match source, and the bundled guide is byte-identical. The manifest
matches the source identity:

- Source digest: `e67a3d5a47ae3a6529a9161b2aec5b305a307f1fbb8d56f19331659970c514b0`
- Engine SHA-256: `5fd02e075d7ab9746ac175371ae49b6fb58fd214391aef822561330a7301475e`
- Native executable SHA-256: `75f6e1a7b437401c94ede85e12c32586f57aaa2ccd4595d9f0767f6e3001e1e1`

The prior optional PyInstaller `scipy.special._cdflib` collection warning remains;
no new Swift compiler warnings or errors were reported. Actual desktop scrolling,
slider/zoom input, display rendering, VoiceOver and macOS 14 runtime acceptance
remain **not verified**. Desktop automation was previously denied and was not
retried. Native state/IPC checks cannot establish that the user's particular
installed app or photo library is now smooth.

The final packaged-engine run passes **268 native state/IPC assertions across
11 suites**: Transport 26, Responsiveness 16, State 15, Connection 10, Thumbnail
14, Reference 51, Review 20, Comparison Layout 42, Before/After 19, Import 22 and
Snapshots 33. The completed runner exits successfully with no Swift warnings.
The final responsiveness run retains zero publications for unchanged job/photo,
reference and snapshot polls, with real external rating and snapshot changes
still visible. Snapshot conflict, pagination and captured-photo revision checks
pass after the polling change. These are current state/IPC results, not desktop
screenshots or interaction acceptance.

The source/index and extracted strict source archive cover **371 public files
with zero findings**. Generated test photos, catalogs, app bundles, private
receipts and the separate unfinished RGB/LAB prototype remain excluded from this
performance module. No pixel algorithm or existing recipe is changed by it.

## Develop RGB/LAB readouts (September 30, 2026)

The native inspector now presents RGB percentages or Lab below the histogram,
with the histogram's Show Lab Color Values context action. Ordinary Fit/1:1,
Before-only, paired/split Before/After and Reference/Active canvases supply photo
coordinates. Equal full-resolution cropped dimensions show both Reference/Active
roles at the matching position; otherwise the other role remains `--`. Active
Before follows its stored snapshot. These interaction rules follow
[Adobe's readout documentation](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/image-tone-color.html).

Optional engine maps carry RGB percentages with ProPhoto D50 primaries and the
sRGB transfer curve, plus CIELAB D50 using the documented
[XYZ/Lab conversion](https://www.w3.org/TR/css-color-4/#color-conversion-code).
The SDR ProPhoto cube is clipped before conversion. Sampling precedes soft proof
and gamut overlays; it does not inspect display pixels. These explicit LumaRAW
equations do not prove Adobe numerical equivalence. Fit samples the fitted
preview; 1:1 samples full-resolution processed pixels. HDR readouts remain open.

Maps use six float32 channels, explicit dimensions/format/white-point metadata,
bounded geometry and atomic cache publication. Full cropped dimensions derive
from decoder dimensions rather than rounded proxy sizes. Before maps have an
independent cache identity; source/recipe/LUT/geometry changes invalidate them.
The optional flag leaves the public inventory at 120 commands. Engine generation
is 35 and catalog schema remains 25; no catalog migration or recipe edit is needed.

Background loaders validate and read maps before use. Pointer movement reads
retained memory and publishes only a dedicated readout view's state. A 160-ms
settled-pointer request samples a single counterpart pixel only when an independent
detail viewport does not contain it. Its captured result is reused, and generation
checks discard replies after hover/selection/revision changes. Cache trimming caps
both bytes and 4096 entries, preserving current receipts, so small point requests
cannot leave an unbounded number of artifacts.

Ordinary Metal grading can return linear work once for display and readout
conversion, with CPU output work explicitly counted as hybrid execution. Complex
recipes retain the CPU-graded work already needed by masks/LUTs and keep the actual
Metal output conversion. The feature does not repeat full grading merely to obtain
RGB/Lab values. Warm maps bypass the additional conversion.

Initial focused Python checks pass 108 cases. The first full run passes 706 tests
with required Metal and the fixed NEF, before the final cache-count refinement.
Initial native Color Readout and Responsiveness probes pass 17 and 16 assertions;
the refined native readout probe passes 18, including repeated off-viewport sample
reuse. These source state/IPC checks do not constitute desktop mouse acceptance.
Final full-suite, packaged-engine and real-RAW evidence follows after validation.

The final full Python run passes **707 tests in 72.75 seconds, with no skips**,
requiring real Metal and the fixed public NEF. It includes preservation of pinned
cache receipts and originals when many tiny files exceed the new count bound.

### Packaged real-RAW measurements

The isolated packaged probe uses the same Nikon D3S NEF (4284 by 2844 decoded
pixels, 10,656,312 bytes; SHA-256
`5922721d13f11795557d97fdeb0a60b900086c402bc82a848ff280d15b99ffd4`)
on macOS 26.6.2, Apple M3 Max, 128 GiB RAM. No competing builds/tests run during
measurement. Sequential single samples include persistent negotiated IPC and
worker startup; they exclude native display and do not clear the OS file cache.
Both After and Before are requested. Fit is 1680 by 1115; detail is 800 by 600.

| Backend / view | First ordinary, cold application cache | First maps, warm decoded source | Warm maps | Warm ordinary |
| --- | ---: | ---: | ---: | ---: |
| CPU Fit | 1631.960 ms | 1662.252 ms | 953.564 ms | 974.671 ms |
| CPU detail | 1075.982 ms | 669.309 ms | 489.246 ms | 485.797 ms |
| Metal Fit | 1211.427 ms | 1380.235 ms | 486.729 ms | 498.175 ms |
| Metal detail | 1097.168 ms | 617.938 ms | 376.871 ms | 370.611 ms |

The first-map cases create both role maps and must generate Before samples even
when a Before display image was already cached. They are not cold-decode speed
comparisons. Readout conversion itself totals about 251–252 ms for both fitted
maps and 62–63 ms for both detail maps. First-map worker peaks are 329.0/176.4 MiB
for CPU Fit/detail and 368.4/202.1 MiB for Metal. Warm-map peaks are respectively
137.8/103.9 and 141.8/107.2 MiB. These are sampled worker peaks, not native app or
whole-system peak memory. First-map CPU conversion and file generation remain
processing optimization candidates; warm-map reuse removes that conversion stage.

All 16 cases pass. Ordinary/readout previews differ by at most one 8-bit code,
and cached maps retain exact float32 values. CPU/Metal readout maxima are below
0.000218 percentage points for RGB and 0.000691 Lab units; Before maxima are below
0.000008. Originals remain byte-identical. Metal first-map runs record actual
18/10 grading dispatches for Fit/detail and explicit CPU readout/output conversion
counts; warm-map runs record 9/5 grading dispatches without readout conversion.
None of these measurements establishes Lightroom color accuracy or UI frame rate.

The RGB and Lab components were separately rendered with synthetic paired values
at 280 by 84 points, 2x scale, and visually inspected. Role labels, negative Lab
values and paired numbers are visible without overlap or truncation. These are
offscreen component checks, not desktop screenshots or actual hover acceptance.

### Final package checks

The final packaged-engine run passes **189 assertions across seven native
state/IPC/component suites**: Color Readout 20, Responsiveness 16, Reference 51,
Comparison Layout 42, Before/After 19, Transport 26 and State 15. Repeated local
hover and RGB/Lab mode changes publish no Store invalidations. Identical values
do not republish the small readout component; 300 repeated off-viewport samples
reuse the retained matching value without another worker. Unchanged background
polls remain quiet, while real external changes still propagate.

The Mac app builds for macOS 14 and passes deep/strict local code-signature
verification. MCP initialization and all 120 full schemas match source. A guide
wording clarification was copied into the bundle after testing and its root
resource seal refreshed; the tested engine bytes stayed identical. The final
bundled guide matches source byte for byte. The source identity matches the
generation-35 manifest:

- Source digest: `0e5b0bbbd5f2b06648da448304f4deb1bcbd6b4663aef50b21b44d6e29c1b5a5`
- Engine SHA-256: `4e97eee0685c0f33c9c86027dd905647912461f817c303c8f41ac5cc6dc80bee`
- Native executable SHA-256: `7103ec57ac39ee54810c428b28af86e7c02005b1150f59a1c7958e619a8601bb`

The known optional PyInstaller `scipy.special._cdflib` collection warning remains;
native compilation reports no new warnings or errors. Current source/index and
the extracted strict source archive cover **376 public files with zero findings**.
Generated photos, catalogs, app bundles, screenshots and private receipts are
excluded from the commit. Desktop automation was not retried after its earlier
denial; actual hover/keyboard/VoiceOver, full-window rendering, macOS 14 runtime
and Adobe numerical/visual equivalence remain **not verified**. The full non-AI
feature inventory remains incomplete.

## Fused Develop readout processing (October 1, 2026)

The first-map bottleneck was CPU display and RGB/Lab conversion after an otherwise
completed Metal grade. The optional six-channel readout output now shares that
same GPU dispatch with display conversion. Complex masks/LUTs/steep curves retain
CPU grading, followed by fused Metal output/readouts. The CPU reference equations,
map format, cache keys, recipes, originals and native interaction remain unchanged.
Engine generation is **36**, catalog schema remains **25**, and all **120** command
schemas remain compatible. Windows continues to use the portable CPU adapter.

The v3 C adapter validates the optional buffer before use and counts all 49 bytes
per pixel against the shared-buffer budget, including the six extra floats.
Layout changes release previous buffers before replacement; no partial results
are exposed after failure. Automatic fallback regenerates complete outputs from
the original input. The ordinary v2 entry point remains usable and was separately
checked against CPU RGB/gamut. New counters distinguish actual Metal readout work
from CPU reference conversion; the ordinary fused path no longer claims hybrid
CPU output work. CPU conversion still excludes neighborhood-filter halos.

### Correctness and native evidence

The initial targeted run passes **102 tests**. The final full run passes **742
Python tests in 76.66 seconds, with no skips**, requiring actual Metal and the
fixed NEF. It covers all eight orientations with/without crop geometry on both
backends, full recipe combinations, SDR clipping/Lab branches, display-space
independence, one-dispatch grading, ROI alignment, buffer bounds/layout switches,
old adapter rejection and complete failure fallback. CPU equations retain their
higher precision Lab intermediates; the existing 0.002 readout error bound is
unchanged. This bound does not establish Adobe numerical equivalence.

The final packaged engine passes **106 assertions** across four native suites:
Color Readout 20, Responsiveness 16, Reference 51 and Before/After 19. Repeated
hover remains local, unchanged polling publishes no Store updates, independent
roles/Before state remain correct, and stale/cancelled replies stay hidden.
These are native state/IPC/component checks, not desktop event acceptance.

### Packaged old/new RAW comparison

Three repetitions per engine alternate old/new, new/old, old/new, with fresh
catalogs and no competing build/test process during timing. All **96 scenarios**
pass. Both engines use the same Nikon D3S NEF, 4284 by 2844 decoded pixels,
10,656,312 bytes, SHA-256
`5922721d13f11795557d97fdeb0a60b900086c402bc82a848ff280d15b99ffd4`,
on macOS 26.6.2, Apple M3 Max, 128 GiB RAM. Fit is 1680 by 1115; detail is
800 by 600. Both After and Before maps are requested. Wall time includes
negotiated persistent IPC and worker startup, excluding desktop rendering.
First maps use a warm decoded source; neither this nor an empty application
cache implies a cold OS/GPU cache.

| Case | Previous median / range | Fused median / range | Median reduction |
| --- | ---: | ---: | ---: |
| Metal first Fit maps | 1093.364 / 1064.864–1458.676 ms | 648.266 / 610.214–658.649 ms | 40.71% |
| Metal first detail maps | 549.407 / 544.064–1425.006 ms | 427.513 / 414.265–432.785 ms | 22.19% |
| Metal warm Fit maps | 490.211 / 436.816–554.389 ms | 481.809 / 436.640–482.551 ms | 1.71% |
| Metal warm detail maps | 371.621 / 368.875–446.895 ms | 367.124 / 353.178–374.233 ms | 1.21% |
| CPU first Fit maps | 1598.080 / 1555.140–1753.315 ms | 1579.858 / 1546.807–2505.214 ms | 1.14% |
| CPU first detail maps | 658.393 / 655.629–673.053 ms | 651.636 / 617.122–662.431 ms | 1.03% |

Ordinary warm Metal preview medians are 491.990 to 477.061 ms for Fit and
367.486 to 371.328 ms for detail. CPU ordinary controls and warm maps are also
approximately unchanged. The few-percent control differences and outliers are
reported as sampling variation, not a claim that unchanged paths were optimized.
Three samples on one system do not establish general latency percentiles.

First-map sampled worker peak medians fall from 487.3 to 330.5 MiB for Metal Fit
(ranges 410.6–490.6 and 308.6–333.0) and 194.9 to 149.9 MiB for detail (ranges
191.6–209.1 and 135.6–166.3). Shared GPU buffers increase from 7.690 to 15.073 MiB
for Fit and 3.955 to 7.752 MiB for detail; fewer CPU intermediates reduce observed
worker RSS. RSS is sampled process memory, not a whole-app/system peak guarantee.
Successful first-map Metal receipts record 18/10 fused grade/readout dispatches
and zero CPU readout/output tiles. Warm maps record zero readout dispatches.

CPU maps are exactly equal across versions over four maps and 4,706,400 pixels.
Metal version differences are at most 0.00001526 RGB percentage points and
0.00004960 Lab units. New CPU/Metal differences stay below 0.000218 RGB percentage
points and 0.000687 Lab units. Display previews differ by at most one 8-bit code;
warm maps retain exact values and originals remain byte-identical.

### Package identity and limits

The Mac app builds for macOS 14 and passes deep/strict local signature checks.
Initialization, all 120 full MCP schemas and the bundled guide match source.
The tested package has:

- Source digest: `20609f05c48b955db952cea3f09938d0db7e6fd23fcd4a51e24f6b2ff83222ca`
- Engine SHA-256: `b2910b0969ca0db579e1388566efb7473ee9bad96fe5316e9ee6540d974cebc6`
- Native executable SHA-256: `c90d4eedf4c8acd1b7b73524812b279c7d2a5292e945d43cadedcaab402483cb`

The known optional PyInstaller `scipy.special._cdflib` warning remains, with no
new native warnings/errors. Desktop automation was not retried after its earlier
denial. Real slider/scroll/hover interaction, VoiceOver, macOS 14 runtime and Adobe
processing equivalence remain **not verified**. Full non-AI parity is incomplete.


## Completed preview reuse (October 1, 2026)

Previously every After preview started an image worker and repeated grading and
PNG encoding, even when the source, recipe and viewport were unchanged. The
broker now reuses a completed preview after bounded integrity checks. This covers
Fit/detail, Before, histogram/geometry, curve input maps, mixer weights and RGB/Lab
maps, including captured temporary recipes. Hits bypass image-worker admission,
so an existing preview is available while an unrelated export holds that slot.

The receipt key includes engine build, compute policy, source and external asset
stat identities, full After/Before recipes and every render option. Stat identity
is not a content hash of the original. Artifact checksums cover full contents in
1-MiB chunks, with cancellation checkpoints, bounded receipt/file sizes, recognized
filenames and no symlink/path traversal. The broker imports no pixel libraries.
Revisions, source/asset identity and request generations are checked again before
returning; metadata-only changes do not create false visual conflicts.

Workers publish After PNGs and receipts atomically. Corrupt map bodies cause
associated disposable maps to be removed under the image-writer lock, preventing
the older header-only map caches from reusing bad data during regeneration.
Originals/images are not removed by this repair. Valid reads never acquire that
lock. Concurrent LRU touches remain valid, while atomic file replacement causes a
transient miss without deleting valid maps. Missing decoded-source arrays do not
prevent a completed hit. Cache files remain bounded by the existing byte/count
policy; this is not offline-preview support or a cache-management UI.

A replaced Before-only LUT now invalidates its independent image/readout cache
before immutable-asset validation, instead of showing old Before pixels. The
portable service owns reuse; SwiftUI has no new SQL, file hashing or pixel logic.
The engine generation is **37**, catalog schema **25**, with **120 commands**.
Cached replies report `preview_cache_hit=true`, `worker_spawned=false`, backend
`cache`, zero worker/GPU work and measured lookup time. They never replay old GPU
counters as evidence of new dispatch. The last actual processing report remains
available in settings.

### Regression scope

The initial focused run passes 110 checks. A full run exposes two compatibility
issues: cached replies omitted the legacy success field, and direct workers with
an omitted recipe failed. Both are corrected. Map-body recovery and concurrency
checks then bring the full run to **773 tests in 80.10 seconds, with no skips**,
requiring actual Metal and the fixed NEF. Adding the final publication timing
stage changes no rendering/cache behavior; the affected cache/service/reference
suites subsequently pass **56 tests in 23.89 seconds**.

Tests exercise restart, decoded-base eviction, all render-option keys, engine and
backend changes, source/LUT/proof changes, revision/Before/source/cancellation
races, busy-worker bypass, corrupt/missing/truncated/symlink/traversal cases, actual
map reconstruction, concurrent touches/replacement and pixel-library isolation.
Original bytes and catalog recipes/history remain unchanged by preview reuse.

### Packaged RAW measurements

The initial candidate is compared with generation 36 in three alternating rounds
(old/new, new/old, old/new), with fresh catalogs and no competing builds/test runs.
All **96 scenarios** pass. The final candidate adds only the publication timing
stage and independently passes **16 further scenarios**. All use the same Nikon
D3S NEF, 4284 by 2844 decoded pixels, 10,656,312 bytes, SHA-256
`5922721d13f11795557d97fdeb0a60b900086c402bc82a848ff280d15b99ffd4`,
on macOS 26.6.2, Apple M3 Max, 128 GiB RAM. Fit is 1680 by 1115 and detail is
800 by 600. After and Before are both requested. Measurements include persistent
negotiated IPC and any worker startup, excluding native rendering and cold OS/GPU
cache guarantees. Three samples are not general latency percentiles.

| Repeated request | Previous median / range | Completed-cache median / range |
| --- | ---: | ---: |
| Metal Fit with readouts | 472.313 / 471.733–490.592 ms | 51.084 / 50.631–52.735 ms |
| Metal detail with readouts | 374.150 / 361.602–415.456 ms | 24.193 / 24.092–54.389 ms |
| Metal ordinary Fit | 473.243 / 465.941–482.446 ms | 17.149 / 16.424–17.213 ms |
| Metal ordinary detail | 360.966 / 343.757–379.015 ms | 14.891 / 14.699–15.459 ms |
| CPU Fit with readouts | 1004.956 / 914.818–1004.961 ms | 50.528 / 50.307–53.824 ms |
| CPU detail with readouts | 489.888 / 479.755–514.332 ms | 23.402 / 22.917–25.133 ms |
| CPU ordinary Fit | 989.702 / 946.515–1006.686 ms | 16.635 / 16.135–18.896 ms |
| CPU ordinary detail | 473.420 / 469.774–485.095 ms | 13.910 / 13.840–14.271 ms |

All repeated candidate requests hit completed receipts and start no worker. The
final timing candidate independently measures 50.319/23.401 ms for Metal Fit/detail
with readouts and 17.010/13.261 ms without them. Cache lookup itself takes about
36.8/9.9 ms with readouts; full map hashing accounts for most of that work.

First generation has a cost and is not claimed faster. In the initial comparison,
Metal first-map medians increase from 880.597 to 1145.492 ms for Fit and 489.864 to
548.797 ms for detail; CPU first-map medians increase from 1766.514 to 1999.981 ms
and 653.495 to 722.463 ms. First-map sources are already decoded; ordinary first
previews separately pay decoding. Instrumenting the final package measures
publication at **37.379 ms for Metal Fit and 10.008 ms for detail** (CPU 37.661 and
9.932 ms). Its first-map wall times are 692.708/477.280 ms for Metal, demonstrating
substantial other cold-path variation. The earlier increases cannot all be
attributed to checksum publication. No first-interaction or slider-speed claim
is inferred from warm cache results; new recipes/viewports still need processing.

Broker RSS is sampled every 5 ms, separately from worker RSS. In the three-round
comparison, warm candidate broker peaks span 49.4–60.2 MiB, versus 46.0–51.9 MiB
previously. The final candidate's warm broker peaks span 49.8–55.8 MiB. Cached
worker peaks are zero because no worker exists, not because total app memory is
zero. Previous warm Metal workers peak at 98.0–153.8 MiB; first generation still
requires ordinary worker memory. Neither measure is whole-app/system peak RSS.

Cached values remain exact across repeat reads. Final CPU/Metal map differences
stay below 0.000218 RGB percentage points and 0.000687 Lab units; ordinary/readout
previews differ by at most one 8-bit code. Originals remain byte-identical.

### Final package identity

The final app builds for macOS 14 and passes deep/strict local signature checks.
MCP initialization and all 120 full schemas match source, as does the bundled
guide. The final packaged-engine run passes **132 native assertions**: Color
Readout 20, Responsiveness 16, Reference 51, Before/After 19 and Transport 26.
All suite checks pass, including quiet unchanged polling, local hover, stale
reply rejection and persistent command correlation. These remain state/IPC and
offscreen component checks, not desktop input acceptance.
The publication timing stage is present in the tested generation-37 build:

- Source digest: `907a84ada4a13c3b421b43d37172e9e8fc23435006ca501dbe38f6b0734e5638`
- Engine SHA-256: `7a35c8be5ad4da33a8f4b69df4645d05a3a8e5004d4ec1df42f00056fece8dde`
- Native executable SHA-256: `eb09c4265531f71301ed448cbbd53a05df2c0ca6d50f8305d3ba87f3aeb2b8b3`

The known optional PyInstaller `scipy.special._cdflib` warning remains. Desktop
automation was not retried after its earlier denial. Actual desktop input, macOS
14 runtime, VoiceOver and Adobe rendering equivalence remain **not verified**.
Full non-AI parity remains incomplete.

### Reviewed Copy destinations and durable transfer recovery

Generation 38/schema 26 extends the reviewed import workflow with Copy. The native
dialog captures a destination, optional subfolder and flat/original-folder/date
organization, displays computed target paths, and keeps preset/metadata/keyword
application and Previous Import navigation. Original-folder organization includes
the selected root; date folders use the original EXIF civil date in
`YYYY/YYYY-MM-DD`, with an explicit Unknown Date fallback. Checked originals and
recognized XMP sidecars copy byte-for-byte; shared sidecars are transferred once
per target. This is a functional increment, not completed Lightroom import parity.

The new filesystem adapter streams 1 MiB blocks outside catalog locks. Entire
target scope is preflighted; exclusive publication still rejects a later collision.
The journal distinguishes planned, writing, sealed and published copies, retaining
ownership and SHA-256 evidence. Explicit recovery validates owned files and never
adopts an unrelated equal-byte target. Source/destination replacement, changed
content, uncertain scratch ownership and unsupported publication filesystems fail
visibly. Cancellation removes only owned scratch links and keeps completed files.
One final catalog transaction applies destination references, descriptions,
captured presets, folder counts and Previous Import together. Restored catalogs
cannot resume/clean another catalog's filesystem transfer.

Validation includes **804 Python tests in 92.61 seconds**, no skips, with the
existing real NEF and required Metal checks. A final directory-fsync ordering
refinement passes all **71 affected import/capture tests in 8.41 seconds**. The
initial full run found an obsolete schema-25 assertion in a schema-24 migration
test; updating it to the current catalog version preserves its actual rollback
and payload checks. An initial native navigation run correctly received a
no-mutation busy refusal from folder synchronization while a preview was active.
The harness now permits bounded retries only for that exact documented refusal,
checking that no photos were imported; other/uncertain failures are not replayed.

The final engine passes **86 native assertions** across Import (29), Import
Processing (22), Previous Import (19) and Responsiveness (16). Offscreen Copy
options/interruption renders exposed a wrapped view label; the layout now hides
that redundant visible label while retaining its accessibility name. The final
UI also disables checks while Copy is interrupted and exposes Resume Copy without
the unrelated Resume Scan button. These are component/state/IPC checks, not
desktop file-panel, input or VoiceOver acceptance.

#### Packaged filesystem measurements

Measured on Apple M3 Max, 128 GiB, macOS 26.6.2, after tests/builds stopped. Each of
three rounds copies 24 disposable clones of the same Nikon D3S NEF: 4284x2844,
10,656,312 bytes each, 255,751,488 bytes per batch (about 244 MiB). Each round has
a fresh catalog/destination; source/OS caches are warm and no app preview exists.
The timer includes IPC, collision preflight, streaming, SHA-256 verification,
fsync and catalog application; source generation and desktop rendering are excluded.

| Round | Apply | Throughput | Concurrent control median / p95 / max | Sampled broker peak |
| --- | --- | --- | --- | --- |
| 1 | 1847.290 ms | 132.03 MiB/s | 1.891 / 3.673 / 9.409 ms (113 calls) | 54.86 MiB |
| 2 | 1690.053 ms | 144.32 MiB/s | 1.887 / 3.115 / 12.276 ms (104 calls) | 52.56 MiB |
| 3 | 1651.254 ms | 147.71 MiB/s | 2.131 / 7.562 / 15.731 ms (97 calls) | 67.17 MiB |

Metadata scan times are 18.208, 17.568 and 19.659 ms. All 72 copies match the
input SHA-256, originals remain unchanged, and no scratch files remain. Worker
peak is zero because no image worker/GPU work is needed; broker memory is sampled
separately every 5 ms. This is local filesystem throughput and service latency,
not a desktop frame-rate, cold-disk, card-reader or multi-camera claim.

The engine identity is shared by the measured package and final native-only
layout rebuild; the engine executable remains byte-identical:

- Source digest: `e8b18d751cc6961d6043d71583f94dc9ed12b794a37c16ad17a33b8546050d07`
- Engine SHA-256: `08eabab0b799e7d30925fc2cc3a577c911080e6d90b2acf21b9cdf07d85b30fe`
- Final native executable SHA-256: `42ca7c6589b97f2328bdd1fbd2a5da392e8ba581e5047223dca6d40057fbc163`
- RAW SHA-256: `5922721d13f11795557d97fdeb0a60b900086c402bc82a848ff280d15b99ffd4`

All 122 full MCP schemas, initialization and the bundled guide match source through
the packaged stdio protocol. The optional official Python MCP SDK is unavailable
in this environment; this increment does not claim a new SDK-client run. Local
deep/strict ad-hoc signature checks pass; the known optional PyInstaller
`scipy.special._cdflib` warning remains.

Move, DNG conversion, rename templates, second-copy backup, additional date formats,
destination-tree grouping and preview policies remain open. Copy currently requires
hard-link publication support and does not preserve Finder tags, resource forks,
ACLs or all extended attributes. Power-loss hardware testing, removable/network
volumes, macOS 14 runtime, actual desktop input/VoiceOver and Lightroom reference
acceptance remain unverified. Desktop automation was not retried after its prior
denial. The complete non-AI inventory remains the goal.

### Copy filename templates and bounded naming previews

Engine generation 39 / catalog schema 27 adds explicit Copy filename renaming.
The native editor provides nine built-in templates, ordered editable tokens,
custom/shoot text, padded sequence and position/total, original filename/number,
folder, local capture date/time and camera model, plus extension case. Users can
preview sixty checked destinations without saving and save import settings
separately from named catalog-local templates. Templates support create, update,
rename and delete at captured revisions; later library changes cannot retarget
an import or silently rebase a loaded native draft.

Sequence order is checked eligible filename (ASCII-NOCASE) then stable item ID,
independent of review sorting, filtering and paging. Missing metadata is explicit;
there is no mtime substitution, silent sanitization or byte truncation. All names
and collisions are validated before copying. XMP uses the new stem, verified
destination basenames become catalog names, and retained original names still
identify suspected duplicates. Copy interruption, cancellation, ownership and
restored-catalog isolation retain the previous module's guarantees.

The first large-plan probe exposed a query-plan failure: SQLite used a covering
index but did not seek collated tuple bounds, causing repeated scans. Explicit
filename ranges and separate equal-name ID ranges removed the repeated work.
A deterministic VM-instruction regression now covers both ordinary and all-equal
filenames. Frozen application ranks are calculated once in cancellable SQL;
ordinary Copy imports with renaming disabled do not pay for this step.

On the Apple M3 Max / 128 GiB / macOS 26.6.2 host, a final isolated synthetic
SQLite probe measured the following sixty-item preview pages. These are engine
domain calls, with no pixels, broker IPC or desktop rendering. Each page has one
first call and five warm calls; OS caches remain warm after staging. The first
10,000-row call, including first-use Python/validation overhead, took 33.257 ms.

| Staged rows / page offset | Warm median / max | First call | Reply bytes |
| --- | --- | --- | --- |
| 10,000 / 0 | 4.008 / 4.135 ms | 33.257 ms | 7,264 |
| 10,000 / 5,000 | 4.426 / 4.589 ms | 4.482 ms | 7,395 |
| 10,000 / 9,940 | 4.751 / 5.118 ms | 5.125 ms | 7,268 |
| 100,000 / 0 | 4.042 / 4.091 ms | 4.213 ms | 7,325 |
| 100,000 / 50,000 | 9.267 / 10.064 ms | 11.531 ms | 7,577 |
| 100,000 / 99,940 | 15.855 / 16.406 ms | 15.186 ms | 7,390 |

Before the query correction, the same 100,000-row page offsets had warm medians
581.546 / 515.550 / 440.446 ms and about 89.6 / 78.0 / 66.4 million SQLite VM
instructions. Final work is approximately 5,000 / 555,000 / 1.105 million
instructions. This comparison corrects an unreleased naming implementation; it
does not measure an improvement in previously shipped desktop frame rate.
One-time cancellable rank freezing took 13.902 / 171.854 ms for 10,000 / 100,000
rows. Process peak RSS sampled every 5 ms during preview/freeze was 36.80 / 47.05
MiB. Synthetic staged rows contain no photograph dimensions or RAW pixels; this
is not a camera throughput, cold-disk, full-app memory or UI-latency measurement.

Validation includes **834 passed** in the complete Python suite (90.88 s), with
the required Metal backend and the existing real Nikon NEF fixture enabled; no
tests skipped. Coverage includes Unicode and UTF-8 basename limits, unavailable
tokens, original/XMP bytes, checked-only numbering, preview immutability, collision
preflight, original-name duplicate detection, shared sidecars after distinct
renaming, captured-template deletion/backup, stale edits, crash/resume, cancelled
rank freezing and atomic migration from a genuine schema-26 catalog. Migration
keeps old Copy plans disabled for renaming and preserves existing photo state.

The final packaged engine passed **97 native assertions**: Naming 30, Add/Copy
29, Apply During Import 22 and Responsiveness 16. The naming editor's offscreen
960 × 810-point render was inspected, including persistent text-field labels,
token order, saved templates, draft previews and explicit save/cancel actions.
No desktop input, window fitting on other displays or accessibility acceptance
is inferred from those state probes and offscreen images.

The Mac 14 deployment-target app builds and passes local deep/strict ad-hoc
signature verification. All **129 full MCP schemas**, initialization and the
updated bundled guide match source through the packaged stdio protocol. This is
not a new official Python MCP SDK client run. The known optional PyInstaller
`scipy.special._cdflib` warning remains. Build identities:

- Source digest: `e73fa63f881cb8e2448d37dac17d118dc7f23d1812f742916c2c44b1cdb6094f`
- Engine SHA-256: `45945af0410c3d7d691528c4be97067736c8a56b0ca5c732dcadd8d9291e3b60`
- Native SHA-256: `ed9eced7b76876e12a5fb6aa2dbc200f7b16e62519ff3c6f956d575165619e72`

Remaining naming scope includes catalog-wide Import/Image counters, additional
EXIF tokens, shared preset storage and Adobe template exchange, Library renaming,
export reuse and exact Lightroom reference acceptance. Filename ordering and
invalid-name policy are explicit LumaRAW contracts, not claimed to reproduce
every Adobe edge case. Move/DNG, backup copies, saved import configurations and
the complete inventory remain open. Actual desktop input/VoiceOver, macOS 14,
removable/network filesystems and Lightroom-rendered reference acceptance remain
unverified; denied desktop automation was not retried.

### Original-state second copies during reviewed import

Engine generation 40 / schema 28 adds Make a Second Copy To before scanning and
on ready Copy reviews. The engine captures an existing, separate destination,
its filesystem identity and an `Imported on YYYY-MM-DD` subfolder. Backup files
retain original names, bytes, modification time and recognized XMP independently
of primary renaming, destination organization and import presets. They never
become catalog photos, folder counts or Previous Import members.

Both roles use the existing bounded, no-follow, exclusive publication journal.
All collisions and both destinations are preflighted before writes, and both
copies must verify before main photos are cataloged. Interrupted work retains
destinations/ownership for explicit resume; it cannot silently disable or redirect
a required backup. Cancellation keeps published files in both locations. Missing
or replaced roots, stale choices and unowned files fail visibly. Restored catalogs
cannot resume or clean the original operation. Main and backup counters/receipts
are distinct, and shared RAW/JPEG XMP is deduplicated per destination.

Native controls support explicit enable/choose/change/disable before application,
checked-row destination previews, same-filesystem information and per-role transfer
details. Grid cards now prioritize actual output filenames with full-path help,
and align thumbnails at the top despite unchecked rows having fewer details.
These changes make original backup names visibly distinct from renamed main files.

The complete Python suite passed **864 tests in 94.22 s**, including required
Metal and the real Nikon NEF fixture, with no skips. New regressions exercise:

- Original filenames/bytes/XMP/mtime with simultaneous main renaming and metadata
  presets, checked scope, role counters and main-only catalog membership.
- Separate source/catalog/destination boundaries, existing primary/backup/XMP
  targets, normalized duplicate names and all-target no-write preflight.
- Writing/sealed/linked/published crash points in both roles, immutable restart
  destinations, absent/replaced/symlink roots, SQL rollback/retry and shared XMP.
- Cancellation while service reads remain available, retained published files,
  restored-catalog ownership and stale changes during filesystem inspection.
- Atomic migration of a genuine schema-27 catalog/journal; old transfers remain
  primary and backup stays disabled without changing existing photo state.

The final package passed **101 native assertions**: Second Copy 26, Naming 30,
Add/Copy 29 and Responsiveness 16. Final options/ready/interrupted offscreen
1060 × 800-point renders were inspected. Named outputs remain readable, primary
progress excludes backup transfers, and a backup collision preserves the existing
file and leaves the primary destination untouched. These probes do not establish
actual desktop input, native file-panel behavior or VoiceOver acceptance.

A real-RAW throughput probe used the Apple M3 Max / 128 GiB / macOS 26.6.2 host
and a Nikon D3S NEF (4284 × 2844, 10,656,312 bytes; SHA-256
`5922721d13f11795557d97fdeb0a60b900086c402bc82a848ff280d15b99ffd4`). Each round
copied 24 source clones into a fresh catalog/destination; dual rounds added a
second folder on the same local filesystem. Source/OS caches were warm, with no
app previews, image workers or GPU work. Timing includes packaged IPC, preflight,
streaming, hashing/readback, fsync and catalog application, excluding fixture
generation and desktop rendering. No tests/builds ran concurrently.

| Mode / round | Written bytes | Apply | Output throughput | Control median / p95 / max | Sampled broker peak |
| --- | --- | --- | --- | --- | --- |
| Main only / 1 | 255,751,488 | 637.495 ms | 382.60 MiB/s | 2.066 / 3.736 / 4.309 ms (44 calls) | 58.28 MiB |
| Main only / 2 | 255,751,488 | 642.737 ms | 379.48 MiB/s | 1.981 / 2.652 / 4.162 ms (46 calls) | 58.05 MiB |
| Main only / 3 | 255,751,488 | 593.722 ms | 410.80 MiB/s | 1.815 / 3.150 / 7.388 ms (42 calls) | 52.14 MiB |
| Main + second / 1 | 511,502,976 | 1197.083 ms | 407.50 MiB/s | 1.855 / 3.267 / 6.001 ms (84 calls) | 54.50 MiB |
| Main + second / 2 | 511,502,976 | 1156.143 ms | 421.93 MiB/s | 1.776 / 2.683 / 9.203 ms (81 calls) | 56.31 MiB |
| Main + second / 3 | 511,502,976 | 1161.860 ms | 419.85 MiB/s | 1.806 / 3.048 / 11.228 ms (82 calls) | 52.30 MiB |

Dual throughput counts both outputs, not twice as many original photographs.
All 216 output files match the fixture bytes, the original is unchanged and no
scratch files remain. Peak broker RSS was sampled every 5 ms; worker peak is zero
because no image processing occurs. The earlier Copy module's different wall times
are not an optimization baseline for this change. Local warm-cache filesystem
results do not establish card-reader, cold-disk, separate-drive or UI frame latency.

The Mac 14 deployment-target app builds, with deep/strict local ad-hoc signature
verification. All **130 full MCP schemas**, initialization and the bundled guide
match source through packaged stdio. The optional official Python MCP SDK is not
installed; no new SDK-client run is claimed. The known optional PyInstaller
`scipy.special._cdflib` warning remains. Build identities:

- Source digest: `f78c73111f2b10e5ab4e5aa00db1b3a621a9770b984cc8a9cf7604b4e1e4f861`
- Engine SHA-256: `ad3e219461bc26045d756a412f3151cf71da4bf20c2d55553fa199f392b2670c`
- Native SHA-256: `bfb8924d4f17235e3f9eef6827a45497f681a2145bf6fd14dc4bdf40eb7f7ed2`

This is one-time original-state backup, not ongoing photo/catalog backup or proof
of independent physical storage. The ISO dated flat folder, nonoverlapping roots,
refusal of colliding original names and atomic catalog policy are explicit
LumaRAW contracts; exact Adobe edge-case/reference acceptance remains open.
Hard-link publication support is still required; Finder tags, resource forks,
ACLs and other extended attributes are not preserved. Removable/network volumes,
power-loss hardware tests, desktop input/VoiceOver and macOS 14 runtime remain
unverified. Desktop automation was not retried. Move/DNG, import configurations,
preview policies, catalog-wide numbering and the complete non-AI inventory remain
the active goal.


### Saved import configurations and explicit rescans

A fresh fetch before implementation found no unmerged local or remote branches;
work continued from `2d18e62` on `codex/lightroom-classic-mac` in the sole worktree.

Engine generation 41 / schema 29 adds catalog-local import configurations with
save-as-new, update, rename, delete and bounded native browsing. Snapshots contain
the implemented method, recursion/duplicate policy, destinations/organization,
second-copy choice, naming values, captured Develop/metadata patches and keyword
segments. They exclude sources, checked rows, transfer identities and backup dates.
Later preset edits/deletion do not alter a prepared review. This follows the
[documented import-preset lifecycle](https://helpx.adobe.com/lightroom-classic/desktop/import-photos/photo-video-import-options.html),
not Adobe preset file interoperability or exact interaction equivalence.

Choose before scanning new sources and override visible destination options if
needed. On a ready review, Use & Rescan explicitly replaces the plan from its
stored source selection and resets checked rows. Fresh destination identities and
LUT checks occur outside the catalog lock; captured library and ready-plan revisions
are rechecked in the final transaction. Missing/symlink/overlapping roots, conflicts
and SQL failures preserve the old review. Interrupted transfers cannot be retargeted.
The preset sheet releases after replacement so the parent shows scan progress and
cancellation. No copying occurs before Import Checked.

Names/methods occupy separate columns from the bounded settings payload, with
thirty-row indexed pages. Source receipts are separate from repeatedly returned
review summaries. Pagination never rebases captured native drafts. Catalog restore
rebinds nested LUT snapshots into restored assets, rejecting corrupt/missing assets
without falling back to the original catalog. Schema-28 migration is additive and
atomic; older reviews keep their state but cannot infer missing source selections.

The complete required-Metal/real-NEF Python suite passed **880 tests in 96.05 s**
with no skips. Regressions cover source-neutral snapshot reuse, independent original
backups and naming, deleted source-preset libraries, overrides, Add/Copy/recursion
changes, stale choices, changes during unlocked validation, failed-rescan rollback,
interrupted-copy rejection, restart persistence, name uniqueness, bounded payloads,
LUT restore/corruption and a genuine schema-28 rollback/idempotency upgrade.

Six packaged-engine native suites passed **144 assertions**: presets 21, second
copies 26, naming 30, processing 22, Add/Copy 29 and responsiveness 16. After the
native-only scan-window release fix, the final package passed the three affected
suites again: **68 assertions** (presets 23, Add/Copy 29, responsiveness 16).
The engine bytes are identical across both packages. Final preset-library
800 × 510-point and ready-review 1060 × 840-point offscreen renders were inspected;
management actions, destination organization, backup names and rescan guidance
remain readable. Actual sheet dismissal/cancel gestures still need desktop acceptance.

A packaged relay probe seeded valid 100-keyword configuration snapshots (56,267
bytes each) into 100-row and 5,000-row libraries. Fixtures are generated 16 × 12
rasters used only to construct a valid review before measurement; no photos are
processed in timed operations. Host: Apple M3 Max, 128 GiB, macOS 26.6.2. Each page
has one first read plus 30 warm reads, and each detail result has 30 reads. Timing
includes native relay IPC, service/SQLite and JSON, excluding seeding, process
startup and desktop rendering. Catalog generation warms the OS cache; all tests
and builds had ended before measurement. No GPU or image workers were used.

| Library / page offset | First request | Warm median / p95 / max | Reply bytes |
| --- | --- | --- | --- |
| 100 / 0 | 2.826 ms | 1.768 / 2.257 / 2.369 ms | 1,672 |
| 100 / 50 | 1.682 ms | 1.663 / 1.803 / 1.851 ms | 1,683 |
| 100 / 70 | 1.634 ms | 1.614 / 1.916 / 2.022 ms | 1,683 |
| 5,000 / 0 | 2.770 ms | 1.830 / 4.215 / 7.005 ms | 1,673 |
| 5,000 / 2,500 | 1.715 ms | 1.681 / 2.769 / 5.708 ms | 1,746 |
| 5,000 / 4,970 | 1.727 ms | 1.705 / 4.197 / 5.191 ms | 1,746 |

Compact detail median/p95/max was 1.759/2.006/2.401 ms (100 rows, 350-byte reply)
and 1.812/5.891/7.642 ms (5,000 rows, 352-byte reply). Broker RSS sampled every
5 ms peaked at 36.98 and 38.50 MiB respectively; zero worker peak means no image
work, not zero total app memory. This verifies bounded browsing with sizable saved
payloads, not RAW/slider latency, a cold disk or desktop frame rate.

The final Mac 14 deployment-target package builds and passes deep/strict local
ad-hoc signature verification. Packaged stdio initialization, **135 full MCP
schemas** and the bundled guide match source. The optional official Python MCP
SDK remains unavailable; no SDK-client execution is claimed. The known optional
PyInstaller `scipy.special._cdflib` warning remains. Build identities:

- Source digest: `b43e9a5e58dccc371c1cd3fec1e98cf27311028827a418f6b06f9caf384477ca`
- Engine SHA-256: `1ba63f663df30fb92fa8e7c1247061e0796ac466e1614cd98f6d5fd65bb5e0cf`
- Native SHA-256: `526a043358e92f6ac14867de9da29e52ba64ba39bca52568ccb802663bcc6b28`

Shared import-preset storage, Adobe preset exchange, preset editing of full
processing/naming before scanning, preservation of manual checks across setting
changes, Lightroom-rendered interaction acceptance and pre-29 source-receipt recovery
remain open. Move/DNG, preview policies, catalog-wide numbering and the complete
non-AI feature inventory remain part of the active goal. Actual desktop inputs,
file panels, VoiceOver and macOS 14 runtime are unavailable; no desktop automation
was retried and offscreen/model evidence is not desktop acceptance.

### Catalog Import # and Image # numbering

Engine generation 42 / schema 30 adds catalog starting numbers and the corresponding
Copy naming tokens. [Adobe's filename editor documentation](https://helpx.adobe.com/lightroom-classic/desktop/import-photos/filename-template-editor-text-template.html)
defines Import # per import operation and Image # per imported photo; its catalog
settings reference permits setting starting values. Failed, cancelled, partial,
duplicate-only and exhausted counter behavior is not established by those sources.
The rules below are explicit LumaRAW contracts, not claimed Lightroom edge parity.

Mac Settings and File Renaming share an editor for revision-bound starts. Conflicts
keep drafts; explicit Reload displays current values alongside the retained draft.
Import # is distinct from batch-local Sequence. Add, direct and folder-sync imports
allocate only successful new originals inside their insertion transaction. Direct
imports retain one import number across their bounded commit batches. Virtual
copies inherit provenance without advancing counters; backups and XMP consume no
extra photo numbers. Historical photos keep NULL provenance on migration; new
catalog starts initialize at 1, with explicit adjustment available.

Previews and saved templates/configurations consume nothing and store no live
global starts. A numbered Copy requires the reviewed sequence revision, captures
tentative values, then preflights all targets. Counter revision validation,
reservation of the whole selected range and transition to copying share one
transaction before writes. A concurrent change returns the plan to ready with
refreshed names, requiring explicit review/application. Frozen ranges survive
crashes, partial cancellation and catalog-commit failure; gaps are intentional.
Schema-29 interrupted copies receive provenance on explicit resume without
changing retained destination paths. Existing files are never overwritten by a
counter reset or exhausted range.

The complete required-Metal/real-NEF suite passed **893 tests in 95.99 s**, no
skips. The focused import/folder/previous-import group passed **173 tests in
16.10 s**. Coverage includes genuine schema-29 migration rollback/idempotency,
unpublished and already-published old Copy journal recovery, missing/stale sequence
revisions, concurrent direct import during Copy preflight, plain-name Copy adopting
current provenance, Add SQL rollback, no-op/virtual/XMP/backup exclusions, direct
import crossing the 100-item commit boundary, full-range retention after partial
cancel, explicit resume and numeric exhaustion/reset. A recovered Add initially
retained an unnecessary tentative row; limiting tentative capture to Copy fixed
that duplicate-insert regression before the final full run.

Five packaged-engine native suites passed **124 assertions**: counters 26, naming
30, Add/Copy 29, saved configurations 23 and responsiveness 16. Counter draft
conflicts, explicit reload, revision-bound Copy apply, refreshed filenames and
original byte preservation use real Backend IPC. Inspected offscreen renders cover
the counter editor, Settings Import section and existing naming window; the new
controls/readouts are readable. These are model/IPC and offscreen layout checks,
not actual pointer, keyboard, sheet-dismissal or VoiceOver acceptance.

The catalog-counter naming probe used 10,000 and 100,000 generated SQLite staged
rows on Apple M3 Max / 128 GiB / macOS 26.6.2. Each page returns 60 names and has
one first request plus five warm requests. The new connection's OS cache is warm
from seeding; the first 10,000-row request also includes lazy Python setup. Timings
exclude seeding, IPC, file I/O, pixels and desktop rendering. No GPU or image worker
is involved, so image dimensions/backend are not applicable. Tests/builds had ended.

| Staged rows / offset | First | Warm median / max | Reply bytes |
| --- | --- | --- | --- |
| 10,000 / 0 | 27.172 ms | 3.685 / 3.748 ms | 7,529 |
| 10,000 / 5,000 | 4.218 ms | 4.080 / 4.133 ms | 7,660 |
| 10,000 / 9,940 | 4.685 ms | 4.539 / 4.645 ms | 7,532 |
| 100,000 / 0 | 4.022 ms | 3.688 / 3.960 ms | 7,590 |
| 100,000 / 50,000 | 9.935 ms | 9.134 / 9.214 ms | 7,782 |
| 100,000 / 99,940 | 15.015 ms | 14.305 / 14.710 ms | 7,594 |

One-time rank freeze took 12.754 / 187.615 ms; process RSS sampled every 5 ms peaked
at 36.50 / 45.125 MiB. Final-page VM work was about 115,000 / 1,105,000 steps, with
disjoint rank ranges retained. This establishes bounded counter preview work,
not desktop frame rate or cold-storage import throughput.

The Mac 14 deployment-target app builds and passes deep/strict local ad-hoc signing.
Packaged initialization, **137 full MCP schemas**, engine identity and bundled guide
match source. Build identities:

- Source digest: `363abde1bc8c3aa26256f65b68a9931f3aacebd006c1500947db336d491b3f72`
- Engine SHA-256: `53480525f4296e835baf23fe55fa6a0ac4e3e685488b2754b0f8755d3e48dabf`
- Native SHA-256: `b4e8baf2531cc28ed56b5f8e0641d8259704d6288d5a84385135b11313603bec`

Official MCP SDK execution was not run. macOS 14, actual desktop input/VoiceOver
and a Lightroom reference interaction comparison remain unavailable. No desktop
automation was retried. Full import parity still needs Move/DNG, further date
formats/destination grouping, preview policies, shared/Adobe preset exchange,
camera/card workflows and reference acceptance; the overall non-AI goal is open.

### Copy capture-date folder formats

Engine generation 43 / schema 31 adds a separate Date Format choice for Copy's
By Capture Date organization: `YYYY/YYYY-MM-DD` (existing default), `YYYY/MM/DD`
and a single `YYYY-MM-DD` directory. The format is captured in the plan, displayed
in saved configuration summaries and restored through explicit preset use/rescan.
Older plans and presets missing this field keep the original layout. Explicit
preparation options override a preset; recovery continues using journaled targets.

[Adobe's hard-drive import documentation](https://helpx.adobe.com/lightroom-classic/desktop/import-photos/import-photos-video-catalog.html)
describes the Date Format control. The [Adobe Press 2024 sample chapter, page 59](https://www.adobepress.com/content/images/9780138318147/samplepages/9780138318147_Sample.pdf)
explains nested year/month/day directories and distinguishes folder separators
from characters in a single date name. These sources do not enumerate the entire
current menu or establish localization behavior, so three numeric choices are
partial coverage, not a complete reproduction of every Lightroom date preset.

The portable formatter validates captured civil year/month/day and emits only
numeric components with fixed separators. It does not use UTC-normalized dates,
host locale or filesystem timestamps. Missing/invalid capture dates use Unknown
Date. Old snapshots containing only the historical civil-date string remain
supported. Naming and associated XMP stems are independent of the date folder;
second copies retain their separate original-state backup naming. Destination
calculation decodes a stored clock once instead of twice for date organization.

The focused group passed **132 tests in 12.76 s**; the complete required-Metal /
real-NEF suite passed **905 tests in 96.25 s**, no skips. Coverage includes civil
dates across UTC offsets, unknown dates, preset defaults/overrides, primary/XMP
paths, collision preflight, schema-30 migration rollback/idempotency and immutable
old journal recovery. Four packaged-engine native suites passed **139 assertions**:
date folders 71, configurations 23, Import 29 and responsiveness 16. The date suite
copies fifteen 160 x 100 EXIF-tagged PNG originals across all three layouts, checks
preview/preset restore and verifies original bytes. Its camera date is September
28 with +14:00 offset while UTC is September 27. Inspected offscreen date pickers
are readable; this is not real desktop input, sheet dismissal or VoiceOver testing.

The generated SQL naming probe combined catalog counters with `year_month_day`
on Apple M3 Max / 128 GiB / macOS 26.6.2. Each page has 60 names, one first request
and five warm requests. Connections are new, OS cache warm from seeding; the first
10,000-row request includes lazy Python setup. Tests/builds had ended. Timings
exclude seeding, IPC, image processing and desktop rendering; there are no image
dimensions, GPU dispatches or pixel workers in this probe.

| Staged rows / offset | First | Warm median / max | Reply bytes |
| --- | --- | --- | --- |
| 10,000 / 0 | 28.617 ms | 4.021 / 4.109 ms | 8,189 |
| 10,000 / 5,000 | 4.560 ms | 4.443 / 4.493 ms | 8,320 |
| 10,000 / 9,940 | 5.002 ms | 4.920 / 5.004 ms | 8,192 |
| 100,000 / 0 | 4.195 ms | 3.922 / 3.966 ms | 8,250 |
| 100,000 / 50,000 | 9.427 ms | 9.088 / 9.222 ms | 8,442 |
| 100,000 / 99,940 | 15.035 ms | 14.985 / 15.641 ms | 8,254 |

One-time rank freeze took 14.412 / 196.156 ms; process RSS sampled every 5 ms
peaked at 36.094 / 41.547 MiB. Last-page VM work remained about 115,000 / 1,105,000
steps. These measurements cover bounded path preview work, not cold-storage import
throughput or frame rate.

The Mac 14 deployment-target app builds and passes deep/strict local ad-hoc signing.
Packaged initialization, all **137 MCP schemas**, engine identity and bundled guide
match source. Build identities:

- Source digest: `4b6f2fa08a9335eb982bfa0e98ad7a3960a8d21e9fd49e4e17e2b0c2865c77c0`
- Engine SHA-256: `7a2940ad199d95d61c3552e9e749308542093aef8abd355262c4109f4622e87f`
- Native SHA-256: `aecbc391bfb2291d732a2e15f27166e92ea2717588de1c2db0a9b72829775640`

The official MCP SDK was not run. macOS 14, actual desktop interaction/VoiceOver,
localized date menus and Lightroom reference comparison remain unverified. No
desktop automation was retried. Further date formats, destination grouping and
the wider non-AI import/product scope remain open.

### Copy destination-folder count preview

Engine generation 44 / schema 32 adds `get_import_destinations` and the native
Destination Folders sheet on a ready Copy review. It lists captured primary
folders with checked, eligible original counts, plus a separate backup destination
and count. Empty relative paths denote the destination root. It preserves Unicode
source folder names and supports all captured flat/source/date layouts. Sidecars
are transfers, not additional photos. Reading the preview never creates folders.

[Adobe's hard-drive import documentation](https://helpx.adobe.com/lightroom-classic/desktop/import-photos/import-photos-video-catalog.html)
describes grouping previews by target folder and showing destination counts. The
current implementation covers a paged folder/count list; grouped thumbnails,
collapsible trees, italic new-folder indicators and exact Adobe selection/count
edge behavior still need implementation or reference acceptance.

The directory rule is shared with Copy target construction and captured during
bounded scan batches. Transactional triggers maintain separate selected new and
duplicate counts; two partial indexes serve the corresponding duplicate policies.
Pages seek after the last binary directory key and return at most 60 groups, with
no whole-review GROUP BY, per-file clock parsing or naming-rank work. Each read
requires the captured review revision. The native model reads on opening, explicit
reload and paging, not on the import progress polling interval. A conflict keeps
the old page visible with an error until an explicit reload.

The same change removes a catalog-sized recount after an individual checkbox
change. Selection validates all requested IDs first, computes count/byte deltas
for rows whose checked state actually changes, and updates the plan totals in the
same transaction. Bulk checking still performs work proportional to the affected
rows; no-op checks preserve totals and keep existing revision semantics.

Migration from schema 31 backfills retained Copy rows in bounded batches. It does
not change plan revisions, global sequence allocation or retained transfer paths.
Interrupted/active copies continue to use transfer details for recovery evidence;
the new folder preview is available only for ready reviews.

The focused import group passed **167 tests in 18.96 s**. Its migration fault test
seeds a genuine schema-31 review with 125 rows, injects failure at row 61 after
confirming 60 rows were updated, and verifies complete rollback of schema/data.
Successful/idempotent retry preserves frozen journal paths, reservations, global
counter values and plan revisions, including old `capture_date`-only clocks.
Selection cases verify exact byte totals and repeated no-op behavior.

The directory scale probe ran after the targeted tests ended and before the full
tests/build. It used 10,000 and 100,000 generated SQLite originals, one per folder,
on Apple M3 Max / 128 GiB / macOS 26.6.2. Pages contain 60 folders with one first
request and five warm reads. Connections are new but OS caches warm from seeding.
The probe times domain SQL/path construction, excluding seeding, JSON encoding, IPC, image/file
I/O and desktop frames; no image dimensions, GPU dispatch or pixel workers apply.

| Original/folder count / cursor position | First | Warm median / max |
| --- | --- | --- |
| 10,000 / first | 0.297 ms | 0.202 / 0.211 ms |
| 10,000 / middle | 0.238 ms | 0.203 / 0.209 ms |
| 10,000 / last | 0.220 ms | 0.200 / 0.202 ms |
| 100,000 / first | 0.314 ms | 0.211 / 0.218 ms |
| 100,000 / middle | 0.245 ms | 0.195 / 0.214 ms |
| 100,000 / last | 0.225 ms | 0.193 / 0.213 ms |

Pages used approximately 500–600 SQLite VM instructions at both sizes; JSON
responses were 5,555–5,563 bytes. With 99% of folders containing only excluded
duplicates, first/warm-median/max were 0.241/0.203/0.270 ms at 10,000 folders and
0.314/0.191/0.217 ms at 100,000, with the same VM bound. Including duplicates at
the last page remained 0.193 ms warm median at either size.

Six single-item uncheck/recheck operations took 1.043–1.318 ms at 10,000 rows and
1.016–1.359 ms at 100,000, including the ordinary bounded review reply. Both sizes
used approximately 1,500–1,900 VM instructions. Process RSS sampled every 5 ms
peaked at 32.938 / 37.094 MiB across the read, selection and duplicate-policy probe
phases. This establishes size-independent indexed reads and individual selection
work in the generated fixture, not camera throughput or real desktop frame rate.

The complete required-Metal / real-NEF suite passed **921 tests in 101.53 s**,
without skips. The app builds for the Mac 14 deployment target and passes local
deep/strict ad-hoc signature verification. A Mac 14 runtime remains unavailable.

Four packaged-engine native suites passed **141 assertions**: destination folders
25, date formats 71, Add/Copy 29 and responsiveness 16. The destination suite uses
65 generated source folders to exercise both cursor pages, previous navigation,
empty cursors, stale-page retention, explicit reload, zero selections and separate
backup counts. It verifies unchanged originals and no destination creation.
Inspected offscreen snapshots show readable Unicode/long directory paths, counts,
backup information and navigation, plus the ready Import window with long preset
summaries wrapping below its action buttons. These are model/IPC and offscreen
layout checks, not desktop pointer/keyboard, sheet-dismissal or VoiceOver tests.

Packaged initialization, all **138 MCP schemas**, engine identity and the bundled
guide match source. Build identities:

- Source digest: `99ff0747ffd1f15177e4a927dd24c32a0df50bec1e126dfd2229ac2b03971fc3`
- Engine SHA-256: `43ba45e6ba91c28a611b10828756904dd0ca7abb4704bf74d009aa0145164153`
- Native SHA-256: `4a508a3563a1343c1402520252b8b8c23562902bf5a937c23d55f3ba87ddaec0`

The official MCP SDK, macOS 14, actual desktop interaction/VoiceOver and Lightroom
reference acceptance were not run. No desktop automation was retried. Grouped
thumbnails, destination trees/new-folder styling and the broader non-AI scope
remain unfinished.

### Import Loupe 100% viewport and completed-preview reuse

Engine generation 45 / schema 32 retains the existing import thumbnail and
1600-pixel Fit requests and adds a complete physical-pixel viewport with explicit
`detail=true`. The native Import Loupe offers Fit and 100%, keeps its viewport
separate from Library, and displays a rendered pixel as one physical display pixel.
Pan requests derive from the actual clamped ROI rather than a requested center
outside the image. Dragging moves the current frame locally; release requests a
new bounded region. Changed focus, plan, revision or pane geometry cannot apply
an old drag or frame to a new photograph.

The existing renderer supplies full-resolution regions no larger than 2048 x 1536,
using captured import Develop settings. RAW decoding still loads the full source
inside the bounded disposable worker; only the requested region is rendered for
display. This is on-demand Import review and does not implement the separate
Build Previews policies or persistent full-image 1:1 assets.

Import Loupe previously bypassed broker-side completed-preview lookup and started
new image work for repeated Fit requests. Both Fit and exact ROI requests now
reuse the existing validated preview receipts before worker admission. Cache keys
retain source, recipe/assets, engine/backend and complete render options. Cached
and newly rendered paths recheck source identity, plan/item revision and client
generation before returning; unchanged images do not justify accepting stale
review state. Source thumbnails also receive the final generation check.

Focused import/cache regression passed **118 tests**. The complete suite passed
**945 tests in 108.65 s**, requiring actual Metal dispatch and the real NEF fixture,
with no skips. Five packaged-engine native suites passed **106 assertions**:
Loupe 14, Add/Copy 29, import processing 22, destination folders 25 and
responsiveness 16. Coverage includes Retina physical dimensions, exact ROI edges,
immediate reverse movement from an edge, delayed focus/resize replies, rejection
of a drag captured before resize, changed source identity and unchanged originals.
One pre-existing destination test depended on the length of the work-directory
name; it now checks the generated relative path's UTF-8 length and exact joined
path. That suite passed after correction. No engine or app change was required.

The inspected offscreen 100% pane shows the generated labeled 100-pixel grid at
the expected physical scale, readable zoom controls and clipped panning. Resize
invalidates the current frame immediately and coalesces requests after 160 ms of
stable geometry. These are native model/IPC and offscreen checks, not desktop
pointer/keyboard or VoiceOver acceptance.

Real-RAW measurement used the same read-only Nikon D3S NEF, **4284 x 2844**,
**10,656,312 bytes**, on an Apple M3 Max / 128 GiB / macOS 26.6.2. Tests and builds
were stopped before the packaged relay probe. Each backend starts a fresh catalog;
first Fit has cold application caches, first ROI populates the full-resolution
linear base, and storage/OS caches remain warm. Each mode has one first request
and five exact repeats. Fit outputs 1600 x 1062; ROI outputs 800 x 600.

| Backend / request | First request | Repeated median / max |
| --- | ---: | ---: |
| CPU / prior Fit | 1071.616 ms | 832.269 / 837.490 ms |
| Metal / prior Fit | 899.151 ms | 640.606 / 643.178 ms |
| CPU / cached Fit | 1071.999 ms | 7.214 / 7.660 ms |
| Metal / cached Fit | 864.859 ms | 7.219 / 7.701 ms |
| CPU / center ROI | 970.143 ms | 6.031 / 7.112 ms |
| Metal / center ROI | 911.172 ms | 6.288 / 7.129 ms |
| CPU / new panned ROI | 406.088 ms | 6.213 / 6.946 ms |
| Metal / new panned ROI | 358.130 ms | 5.972 / 6.587 ms |

The center ROI is `[1742,1122,800,600]`; the panned ROI is
`[3113,1890,800,600]`. First Fit dispatched nine grading tiles and first ROI five,
on the requested backend. Every candidate repeat reused its completed receipt,
spawned no image worker and reported zero CPU/Metal grading tiles. Repeated PNG
pixels were exact; CPU/Metal maximum 8-bit code differences were Fit 1, center 1,
pan 0. Embedded ICC data remained present. The original hash was unchanged and
no catalog photos were created.

Broker RSS sampled every 5 ms peaked at **55.594 MiB CPU / 53.406 MiB Metal**.
Separately reported worker RSS peaked at **331.8 MiB** for either backend; panned
ROI workers reused the linear base and peaked at 100.4 / 106.3 MiB. These are
separate process peaks, not whole-app memory. Timings include relay IPC and cache
validation, exclude native image preparation and desktop drawing, and do not
establish camera color accuracy or Adobe pixel identity. The previous engine
SHA-256 was `43ba45e6ba91c28a611b10828756904dd0ca7abb4704bf74d009aa0145164153`.

The Mac 14-target app builds without Swift warnings and passes deep/strict local
ad-hoc signature verification. Packaged initialization, all **138 MCP schemas**,
engine identity and the bundled guide match source. Build identities:

- Source digest: `1b96fbc60d7eafebda7375b2f074f55b32a05d1ae169ed67f0564ad1b86d310f`
- Engine SHA-256: `10b19d34d30669c9785556e6a5ca39a30cf30af9d179c0504eb7b1c913808719`
- Native SHA-256: `46e22bf8cb5ea95b27d928e937c0c54ab8d4e73a9dcbd055829222e2c8a49ab6`

The official MCP SDK, macOS 14 runtime, actual desktop interaction/VoiceOver and
Lightroom reference acceptance were not run. Desktop automation was not retried.
Import preview policies, offline assets and the wider non-AI parity inventory
remain incomplete.

### Full-stack member ordinals in Library badges

Engine generation 46 / schema 32 adds `stack_ordinal` to Library page rows.
Expanded Grid and Filmstrip badges display the photograph's one-based position
within its entire source-scoped stack; collapsed covers retain the total count.
Help and accessibility text distinguish the visibility action from Photo X of Y.
Filtering or paging does not renumber members. Folder and regular/Quick collection
stacks remain independent; flat/unsupported scopes return a null ordinal.

The existing sparse ordering labels can be negative after moving a photo to the
top, or have gaps after removal. They remain unchanged. Only the current page's
at-most-60 rows are grouped in memory. Each stack uses one indexed prefix and
disjoint intervening ranges to calculate true ranks, instead of independently
recounting the prefix for every visible photo. Collapsed covers use their known
ordinal 1. Deep pages still scan the needed prefix once per stack; arbitrary-size
stack navigation is not claimed to be constant-time.

Reference: Adobe's [stacking documentation](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/grouping-photos-stacks.html)
distinguishes collapsed total-count badges from expanded sequential member
numbers. Pixel styling, actual desktop clicks/keyboard and VoiceOver still need
reference acceptance. Cross-page cover-focus behavior is a separate remaining gap.

Focused stack/virtual-copy regression passed **44 tests**. The complete suite
passed **953 tests in 126.90 s**, with required Metal and the real NEF fixture and
no skips. New cases cover negative top positions, up/down, removal holes, split,
virtual-copy insertion, auto-stack, independent collection ordering, tied labels,
null flat/smart/unstacked rows, 130 members across three pages and sparse filters.
A 100,000-member case guards SQL VM work against repeatedly counting each row's
entire prefix. Query plans confirm covering `stack_order` searches for prefix,
equal-position and intervening-position ranges. Scope ownership is checked once
per returned stack. Inner and outer page order use photo ID as the final tie-break.

Synthetic scale evidence on Apple M3 Max / 128 GiB / macOS 26.6.2 uses one expanded
stack with intentionally negative and sparse labels. Each case has one first
request and five repeats after opening a new SQL connection; storage/OS caches
remain warm from seeding. No photographs, pixels, IPC or native frames are timed.
Full-page results exclude total-count queries; isolated ordinal timing uses the
already-fetched page of at most 60 rows.

| Members / page | Full page first / warm median | Ordinals warm median / max |
| --- | ---: | ---: |
| 10,000 / first | 4.225 / 3.988 ms | 0.168 / 0.177 ms |
| 10,000 / middle | 4.720 / 4.551 ms | 0.266 / 0.313 ms |
| 10,000 / last | 5.330 / 5.261 ms | 0.346 / 0.367 ms |
| 100,000 / first | 42.875 / 40.957 ms | 0.180 / 0.234 ms |
| 100,000 / middle | 49.461 / 48.556 ms | 1.125 / 1.154 ms |
| 100,000 / last | 58.856 / 59.064 ms | 1.995 / 2.096 ms |

Ordinal-only VM work was about 4,100 instructions on the first page at either
size, 19,200 / 154,200 in the middle and 34,000 / 304,000 on the last page. This is
consistent with one prefix scan, not sixty overlapping scans. Full-page VM work
reached about 439,700 / 4,309,700 on the last page; the pre-existing stack sorting
and offset cost remains significant. Full-page warm maxima were 5.322 / 59.675 ms.

With only every hundredth member matching a rating filter, first/last-page warm
medians were 0.667 / 0.741 ms at 10,000 members and 1.770 / 3.765 ms at 100,000.
Corresponding isolated ordinal medians were 0.301 / 0.367 and 0.328 / 2.063 ms.
Reply payloads stayed between 28,704 and 29,520 bytes. Process RSS sampled every
5 ms after seeding peaked at **33.359 / 47.609 MiB**. A collapsed cover's ordinal
annotation took 0.003 ms at both sizes; its existing complete page query took
2.843 / 35.420 ms. These measurements do not establish desktop frame rate or
constant-time queries for arbitrary stack sizes.

Five packaged-engine native suites passed **94 assertions**: stacks 27,
auto-stack 19, virtual copies 19, Library 13 and responsiveness 16. Native evidence
covers collapsed total count, expanded member ordinals, moving the cover,
splitting and a filtered page retaining ordinal 2 for its sole displayed member.
Inspected offscreen badge renders show collapsed count 3 and expanded ordinal 2.
These are layout/model/IPC checks, not actual desktop input or VoiceOver testing.

The app builds for the macOS 14 deployment target without Swift warnings and
passes deep/strict local ad-hoc signature verification. Packaged initialization,
all **138 MCP schemas**, identity negotiation and the bundled guide match source.
Build identities:

- Source digest: `cfc51d8e3cc31d523e537689fba98d930a06e29c208ecb1e51952d7c288d01bc`
- Engine SHA-256: `16d66ae247c3e2dc1c14de70ea9d71bc7953f612d3815e6401668a4015d2ef2f`
- Native SHA-256: `3b583d2ba969996a1ef974179d6155fbd93281661a20690b5351e79ffe076d4a`

macOS 14 runtime, the official MCP SDK, desktop interaction/VoiceOver and Adobe
reference acceptance remain unverified; no desktop automation was retried.
Cross-page cover focus, large-stack page sorting cost and the remaining parity
inventory are still open.

### Collection color labels and bounded tree refresh

Engine generation 47 / schema 33 adds standard labels to regular collections,
smart collections and collection sets. Single-row context actions and a dedicated
native batch sheet support five colors and None. Batches capture up to sixty
collection revisions across pages, validate every target before writes and keep
all rows unchanged after a stale target or SQL failure. Quick is excluded. Changed
nodes and ancestor sets advance once per affected node; assigning the same label
to every target is a validated no-op. Labels do not propagate to photos or child
nodes. Subtree copies preserve labels as a local policy; Adobe's documentation
confirms collection labeling/copying but does not specify label inheritance.

Flat color filtering spans the entire hierarchy, retains normal tree expansions
and page offsets, and uses indexed counts plus at most sixty payload rows. A
bounded parent-name lookup supplies immediate-parent context for matching names.
Tree mutations advance an independent counter, preserving Quick/target conflict
semantics. The Mac shell refreshes loaded pages after that counter changes,
including when the photo result is empty, rejects older page/state replies and
preserves captured editor/batch selections. Filtered rows reuse the existing
subtree deletion confirmation and context actions. Batch conflicts explicitly
require reloading and reselecting changed targets; no mutation is retried.

Focused collection, identity, target-Painter and stack regression passed
**44 tests in 5.53 s**. New Python coverage includes a genuine schema-32 upgrade,
DDL failure rollback, custom schema objects, hierarchy/Quick target/membership/
stacks preservation, standard label assignment/clear/no-op, atomic parent-child
batches, injected mid-write failure, label-preserving copies/moves, bounded global
paging and unchanged originals, photo metadata, recipes and history. The older
v4 identity fixture now seeds its published schema directly and checks preserved
old columns separately from the new default label.

An isolated SQL probe used 10,000 and 100,000 synthetic top-level collections,
10% labeled red, on Apple M3 Max / 128 GiB / macOS 26.6.2. Each page used a fresh
SQL connection, one first request and five repeats. Count and page costs are
included; connection startup is separately recorded. OS caches remain warm from
seeding and the genuine schema-32-to-33 upgrade. VM instrumentation ran in a
separate request after timing. There were no photos, image dimensions, pixels,
workers, GPU work, IPC or native frames in this measurement.

| Collections / filter | First page first / warm median | Last page first / warm median |
| --- | ---: | ---: |
| 10,000 / any | 0.384 / 0.252 ms | 0.516 / 0.385 ms |
| 10,000 / labeled | 0.184 / 0.130 ms | 0.145 / 0.106 ms |
| 10,000 / no label | 0.424 / 0.323 ms | 0.597 / 0.522 ms |
| 10,000 / red | 0.178 / 0.142 ms | 0.186 / 0.132 ms |
| 100,000 / any | 2.323 / 1.908 ms | 3.649 / 3.654 ms |
| 100,000 / labeled | 0.354 / 0.255 ms | 0.417 / 0.374 ms |
| 100,000 / no label | 2.666 / 2.673 ms | 5.013 / 5.156 ms |
| 100,000 / red | 0.477 / 0.362 ms | 0.634 / 0.554 ms |

Last pages contain forty rows where the matched total is not divisible by sixty;
no-label last pages contain sixty. Warm maxima at 100,000 were 3.758 ms for any,
0.380 ms for labeled, 5.180 ms for no label and 0.562 ms for red. Payloads ranged
from 6,800 to 10,344 bytes. Queries used the intended indexes without a temporary
sort; deep no-label work reached about 721,000 VM instructions, so counts/deep
OFFSET remain proportional to matching index entries. This is not constant-time
paging. Connection-open measurements ranged from 0.868 to 1.106 ms.

Compact Quick/target/tree polling used 372–373 bytes and fewer than 1,000 VM
instructions. First/warm medians were 0.041/0.013 ms at 10,000 collections and
0.033/0.012 ms at 100,000. Process RSS sampled every 5 ms after seeding peaked at
37.797/42.516 MiB; these are SQL-probe process measurements, not whole-app memory.

The complete Python suite passed **962 tests in 129.11 s**, with required actual
Metal and the real 4284 x 2844 Nikon D3S NEF fixture, with no skips. This covers
existing image/export behavior as well as the collection increment; it does not
establish Adobe color equivalence.

Five native suites against the packaged engine passed **116 assertions**:
collections 42, Library 13, Target Collection Painter 18, stacks 27 and
responsiveness 16. Collection checks cover across-page captured batches, the
sixty-target cap, stale rejection/reselection, global filters, preserved tree
state, active collection readback, empty-filter external changes and quiet polls.
The first native run stopped on a test that expected yellow while still selecting
red. The test now explicitly selects yellow before the captured-conflict scenario;
all five suites passed in a fresh run without changing application code. Both
receipts remain local. Inspected batch-picker and filtered-row PNGs match the
successful run byte-for-byte and show the parent context and color indicators.
They are offscreen layout evidence, not desktop interaction or VoiceOver testing.

The Mac app builds for the macOS 14 deployment target without Swift diagnostics
and passes deep/strict local ad-hoc signature verification. Packaged MCP
initialization, all **139 tool schemas**, broker/client/source identity equality
and bundled-guide bytes match. Build identities:

- Source digest: `1533fa43bb5efc6339d6dc20db79fbfafe3fda2c912ac71aead7e947ae90d90f`
- Engine SHA-256: `33ec0cacc85146643ab322e83d44790a0e6ab17c7b3053547a93737436dba182`
- Native SHA-256: `c40ac23ee361ddc9a032b2df6e779087b5f06fde92a4ab4d449d2c70ed090247`

The independent batch sheet differs from Adobe's sidebar multi-selection gesture.
Custom label names/sets, full ancestor-path disambiguation for repeated parent
names, collection-node drag/drop, remaining smart criteria/exchange and Adobe desktop
reference acceptance remain open. Photo drops into regular collections are added
in the later increment below. The macOS 14 runtime, current desktop input,
VoiceOver and official MCP SDK were not tested; desktop automation was not retried.
This module does not complete the overall Lightroom parity inventory.

### Captured export presets

Adobe's documented workflow saves the current Export dialog settings as a named
preset and loads them before an explicit export. Its multi-preset workflow can
retain each preset's destination or choose replacement locations. This increment
implements single-preset configuration reuse for the existing JPEG/16-bit TIFF
pipeline. It does not implement multi-preset batch submission, Adobe preset
exchange or built-in export presets. Export with Previous follows in the next
increment below.

Engine generation 48 / schema 34 adds shared-default and optional catalog-local
export preset libraries. Names have stable UUID identities and normalized unique
names. Thirty-row pages omit settings payloads; a captured token is required to
read settings, create/update, rename/delete or switch storage. Tokens include the
catalog and shared-store roots, storage mode and both library revisions. Switching
storage neither moves records nor changes a previously loaded configuration.

Saved settings contain the format, all eight existing output options, and an
optional literal absolute destination. The destination is included only by an
explicit save choice; preset IO does not inspect it or create folders. A preset
without a destination clears the previous draft folder, requiring a new choice
before queue submission. Photo IDs, recipes, queue state and request keys are
excluded. Loaded values and already-submitted job snapshots remain independent of
subsequent preset edits/deletion.

The Export sheet now opens a searchable, paged preset browser with save, update,
rename and delete workflows; Settings controls the storage scope. Custom long-edge
size, numeric output sharpening and queue priority expose existing engine options.
Sharpening preserves fractional values but does not implement Adobe's distinct
screen/matte/glossy output classes. Every editor keeps its original token. A
rename may update a loaded name but cannot advance an older settings token; closing
the browser invalidates in-flight loads, and later pages/searches reject stale
responses. Choosing a preset neither changes photo selection nor submits jobs.

Focused export, metadata-preset, collection-migration and service regression passed
**57 tests in 9.81 s**. The initial run passed 56 and failed an over-specific query
plan assertion: SQLite selected its unique normalized-name index instead of the
explicit composite index. Both satisfy the stable ordering without a temporary
sort. The test now checks indexed access/no temporary sort alongside actual page
contents; application queries were unchanged. Coverage includes genuine schema-33
upgrade rollback, custom schema objects and existing photo/job/collection data,
product backup/restore, cross-catalog/shared-root revision isolation, storage
switches without copying, stale/missing-target mutations, literal-path no-IO
guards and independent frozen jobs. Generated 240 x 160 PNG input produced
120 x 80 JPEG and 16-bit TIFF with exact Display P3 ICC bytes; JPEG quality and
collision behavior were checked and original bytes remained unchanged.

The isolated scale probe ran on Apple M3 Max / 128 GiB / macOS 26.6.2 with 10,000
and 100,000 synthetic shared presets. Each measurement includes in-process Service
validation, shared/catalog connections and transactions, token reads and count/page
queries. Seeding, IPC, native rendering, photos and pixels are excluded. Each case
has one first call and five repeats; OS caches are warm after seeding, not cold disk.

| Presets / request | First call | Warm median | Warm maximum | Reply |
| --- | ---: | ---: | ---: | ---: |
| 10,000 / first page | 1.978 ms | 1.694 ms | 1.913 ms | 1,508 B |
| 10,000 / last page | 1.996 ms | 1.770 ms | 1.803 ms | 611 B |
| 10,000 / sparse search | 2.294 ms | 2.334 ms | 2.453 ms | 199 B |
| 100,000 / first page | 2.477 ms | 2.162 ms | 3.293 ms | 1,509 B |
| 100,000 / last page | 3.436 ms | 3.446 ms | 3.644 ms | 613 B |
| 100,000 / sparse search | 8.274 ms | 8.704 ms | 8.720 ms | 199 B |

First pages return thirty names, last pages ten and exact-name substring searches
one. Separate SQL VM samples use 100-instruction granularity: first-page selection
uses about 200 instructions, while deep OFFSET uses about 30,000/300,000 and
sparse substring count plus selection uses about 90,000/900,000. All plans use
the normalized-name unique index without a temporary sort. Bounded replies do not
make deep paging or substring scans constant-time. After-seed process RSS sampled
every 5 ms peaks at 37.55/43.81 MiB; the larger-case baseline may include memory
retained from the smaller case. These measurements do not establish desktop latency.

The complete Python suite passed **984 tests in 133.44 s** with required Metal
and the real 4284 x 2844 Nikon D3S NEF fixture, with no skips. The first Mac build
then caught two Swift `catch` variable-shadowing errors in preset failure display;
both assignments now explicitly target the model's error property. This native-only
repair leaves the validated Python engine unchanged; the failed build log remains
local with the successful evidence.

Five native suites passed **115 assertions** against the packaged engine: export
presets 38, export metadata 16, metadata presets 32, Library 13 and responsiveness
16. Preset coverage includes eight-option round trips, explicit successful updates,
captured conflicts for every mutation, rename without stale-token rebasing, late
read rejection, destination clearing, bounded browsing, storage separation and
unchanged loaded drafts/job settings after deletion. The probe cancels its own
paused jobs before exit. Existing unchanged polls still publish no Store updates.

Four offscreen renders cover the main Export sheet, preset browser, save editor
and storage setting. Inspection found a wrapped duplicate label beside the numeric
sharpening input. The final UI hides redundant numeric-field labels while retaining
explicit accessibility names; a fresh Mac build and all 38 export-preset native
assertions then passed, and the updated render was inspected. Other native source,
engine and tests were unchanged by this layout repair. Offscreen renders establish
limited layout evidence, not desktop interaction, folder-panel behavior or VoiceOver.

The final macOS 14-target app builds without Swift diagnostics and passes deep/
strict local ad-hoc signature verification. Packaged MCP initialization and all
**143 tool schemas**, broker/client/source identities and bundled-guide bytes match:

- Source digest: `eda55470631ea7489bf7fea1abdc1bc4eda15bab218315aa41b74130dd4d6050`
- Engine SHA-256: `1dc0d8b94a2fb2db8558b9f99c5f1a9feaee153c5243702af3b7b8b2d6a9211e`
- Native SHA-256: `9ad6cba7d423a122c7010dd66f512022f9a1d7a5e1979f930277bd691dc73259`

Remaining export work includes multi-preset batch submission,
Adobe exchange/built-ins, groups and more destination policies, complete metadata,
watermarking, additional formats, plugins/postprocessing and publish services.
The separate browser differs from Adobe's Export dialog sidebar. macOS 14 runtime,
current desktop input, VoiceOver, official MCP SDK and Lightroom reference acceptance
were not tested; desktop automation was not retried. This remains partial export
coverage within the full Lightroom parity goal.

### Export with Previous

Adobe documents this action as reusing the latest manually configured export
session, including modified presets while excluding unchanged presets. Its Mac
shortcut is Command-Option-Shift-E. LumaRAW now follows that distinction for its
existing JPEG/16-bit TIFF options. Catalog-local persistence, queue acceptance as
the session boundary and destination-only changes counting as modifications are
explicit LumaRAW policies; the cited documentation does not establish all of these
details as Adobe behavior.

Engine generation 49 / schema 35 introduces one catalog-local configuration with
canonical output values, a destination and a revision. New and upgraded catalogs
start empty without inferring manual intent from old export jobs. An optional
`remember_previous` flag on ordinary submission defaults to false and saves the
configuration atomically with accepted jobs and the request receipt. Identical
canonical settings retain their token; later cancellation or worker failure does
not erase the session. Catalog backups include this configuration.

The new Previous command reads the captured configuration and all current target
photos inside one write transaction. It freezes fresh recipes, metadata and
orientation into new jobs without changing Previous. Receipt lookup precedes the
revision check, allowing an explicit identical replay to recover accepted jobs
after the configuration changes. Existing ordinary-export digests retain their
historical bytes; Previous digests include their command identity, so cross-command
request-key reuse fails. No uncertain request is retried automatically.

The Mac File menu captures selected photo IDs before awaiting pending edits and
then performs a fresh configuration read and one revision-checked submission.
Export drafts keep a copied preset baseline; unmodified presets preserve Previous,
and any changed output value makes a submitted draft manual. Queue polling carries
only the configuration's availability and revision, with no additional recurring
command or full-settings payload. Repeated equal state stays quiet in the shell.

Focused Previous, preset, metadata-export and service regression passed **63 tests
in 8.99 s**. Coverage includes a genuine schema-34 catalog with an old raw-argument
request digest, exact receipt replay after upgrade, no inference from historical
jobs and product backup/restore. Denying the schema-version update after creating
the new table proves transactional DDL rollback. Failures at the second photo,
configuration update and request-receipt insert leave no partial jobs or settings;
Previous receipt failure also rolls back already-created jobs.

Equal canonical manual settings keep their revision, while current photo edits
and metadata are captured afresh on reuse. A deliberately corrupt settings payload
still permits compact queue polling but fails explicit settings retrieval. Worker
failure/cancellation retain Previous. A generated 64 x 48 PNG produces a 32 x 24
ICC-tagged JPEG through the actual worker and preserves the original bytes. This
small raster check does not establish camera accuracy or Adobe pixel equivalence.

The full Python suite passed **993 tests in 136.17 s**, with required actual Metal
and the real 4284 x 2844 Nikon D3S NEF fixture, with no skips. Existing RAW and
export processing remains covered alongside the new configuration workflow.

Four native suites passed **94 assertions** against the packaged engine: Previous
24, export presets 38, export metadata 16 and responsiveness 16. The new suite
changes selection while submission is awaiting edits and invokes both submission
paths again; only the originally captured photo is added once. It verifies manual,
unchanged/updated/modified preset distinctions, captured save baselines, deletion
without losing draft values, stale rejection and immutable submitted snapshots.
Repeated equal queue polls and a revision-only Previous response cause no Store
publication. The general responsiveness suite also reports zero unchanged-poll
publications. These state checks are not desktop frame-rate measurements.

The Export sheet's offscreen image was inspected: configuration-retention guidance
and submission controls remain visible. The additional preset suite renders cover
the existing preset browser/editor/settings layouts. They are limited layout
evidence, not desktop shortcut dispatch, native folder panels or VoiceOver.

The macOS 14-target application builds without Swift diagnostics and passes deep/
strict local ad-hoc signature verification. Packaged MCP initialization and all
**145 tool schemas**, broker/client/source identities and bundled-guide bytes match:

- Source digest: `14df64b2e86a52feb9b99fad1d0f8a9eafaa31098c22719a55e80117c5e4367a`
- Engine SHA-256: `fca9bcde890834c1a63b2f4b6fe3e8e7e9764478d8240f04f08457d8a19788af`
- Native SHA-256: `4287cd895b2d4d9260eaeb0191c979b6e74e612e9a1ab8f30c3f1e71cde90f13`

Multi-preset batch export follows in the next increment below. Adobe preset
exchange/built-ins, complete output metadata,
watermarking, additional formats, plugins/postprocessing and publish services remain
open. The macOS 14 runtime, current desktop input, VoiceOver, official MCP SDK and
Lightroom reference acceptance were not tested; desktop automation was not retried.
This increment does not complete the full Lightroom parity inventory.

### Multiple-preset export batches

Adobe's documented batch workflow selects preset checkboxes, fixes their output
settings during batch setup and exports one variant per photo/preset combination.
It supports individual destinations or one parent with child folders, and appends
the preset name when filenames conflict. LumaRAW adds those paths for its existing
JPEG/16-bit TIFF settings through a separate batch sheet, rather than Adobe's
checkbox sidebar. Custom-text/start-number overrides from Adobe's broader filename
template system remain outside the existing export options.

Engine generation 50 / schema 36 adds a shared-contract multi-preset read, atomic
batch submission and durable batch list/detail commands. Thirty distinct presets
and a product of at most one thousand jobs bound each submission. Library tokens
include both storage revisions and mode; concurrent preset changes require an
explicit refresh and reselection. The final transaction captures current recipes,
metadata, orientation, destinations and output values. Later edits or deletion of
presets do not alter accepted jobs. Batch export preserves Previous as an explicit
LumaRAW policy; Adobe's referenced documentation does not specify this interaction.

Individual mode retains saved destinations unless explicitly overridden. Parent
mode replaces them with validated child components. All target/configuration checks
precede directory creation; batch/job/request receipts commit together. Directory
creation is outside SQLite rollback, so a failed submission can leave empty folders
while accepting no partial batch. Exact request replay precedes revision validation
and returns the original batch identity after later preset changes; cross-command
or changed-argument request-key reuse fails.

Batch job names first try the ordinary template output. A collision adds the exact
captured preset suffix, then a number. Suffixes have a 120-byte UTF-8 limit; the base
stem is shortened on character boundaries when necessary to keep the complete
filename within 255 bytes. Existing files remain protected by atomic hard links.
Invalid suffixes require an explicit override; user suffixes are never silently
rewritten. Parent child components preserve accepted spelling and reject normalized,
case-folded duplicates.

The native workflow keeps output settings read-only during batch setup, captures
the selection and overrides before pending-edit waits, and shares the ordinary
submission guard. A batch browser pages through thirty summaries and sixty jobs at
a time; scoped cancellation/retry leaves unrelated work alone. Pause/resume remains
global. Processing retains the same bounded, one-photo-at-a-time worker.

An isolated submission probe used 100 generated 8×8 PNG sources, each with 100
direct keyword assignments, on Apple M3 Max / 128 GiB / macOS 26.6.2. Each case
accepted six new batches (distinct request keys); the table separates the first
call from the median of five repeated calls. Destinations were pre-created and
SQLite/OS caches were already warm after fixture seeding. The queue stayed paused;
no CPU/Metal image worker ran. RSS was sampled every 5 ms in the service process.

| Jobs per batch | First submit | Warm median | Catalog transaction median | Peak RSS / rise |
| --- | ---: | ---: | ---: | ---: |
| 100 (1 preset) | 120.9 ms | 123.0 ms | 113.3 ms | 47.6 / 9.1 MiB |
| 500 (5 presets) | 513.0 ms | 510.9 ms | 495.9 ms | 53.3 / 2.9 MiB |
| 1,000 (10 presets) | 1,005.0 ms | 1,018.1 ms | 996.0 ms | 64.5 / 6.5 MiB |

Preset capture medians were 1.8–2.1 ms with replies of 363–2,811 bytes; submission
receipts were 99–101 bytes. These are in-process service/SQLite measurements,
including validation, path checks and frozen metadata creation. They exclude IPC,
desktop rendering, cold storage, source decoding and export throughput. RSS rises
use each series' starting process size; memory can remain allocated between cases.
The largest batch still holds the catalog transaction for about one second;
repeated metadata preparation across equivalent preset policies remains an
optimization opportunity, not a demonstrated responsiveness improvement.

Validation on the same Mac:

- Focused export/previous/preset/metadata/service tests: **75 passed**. Full Python
  suite with required actual Metal dispatch and the retained real NEF fixture:
  **1,005 passed in 143.16 s**, no skips.
- Five packaged-engine native suites passed **140 assertions**: Batch 46,
  Previous 24, Export Presets 38, Export Metadata 16 and Responsiveness 16.
  After increasing the captured-preset card height, a fresh app build and all
  **46 Batch assertions** passed again. Native compilation targeted macOS 14.
- Checks include shared/catalog token conflicts, genuine schema-35 migration and
  rollback, transactional fault injection, all-target path preflight, late edits,
  backup/restore, exact replay, scoped active-worker cancellation and Unicode
  collision output. Generated raster workers preserve originals and existing
  destinations; these outputs do not establish Adobe camera/pixel equivalence.
- Offscreen picker/history/receipt images were inspected. The receipt's clipped
  setting cards were corrected. AppKit List rows were absent in the offscreen
  images, so list-row desktop rendering remains unverified; no desktop automation
  was retried. State/paging checks are separate from rendered acceptance.
- Packaged/source/broker identities, all **149 MCP schemas**, bundled guide bytes
  and deep strict ad-hoc signature verification matched. This is local packaging
  evidence, not notarization or an official MCP SDK interoperability test.

macOS 14 runtime, real desktop interactions, folder panels, VoiceOver and Lightroom
reference acceptance remain unavailable or unverified. Full filename templates,
custom-text/start-number batch overrides, additional formats, complete metadata,
watermarks and publish workflows remain open. This increment does not complete
the full Lightroom parity inventory.

### Reusing metadata during batch submission

The generation-50 probe above measured about one second inside the catalog write
transaction for 100 photos exported with ten metadata-equivalent presets. Every
photo/preset job independently queried the same keyword hierarchy, validated its
XMP and serialized its frozen snapshot. This work blocks other catalog commands
while the batch is accepted, even though pixel work is outside that transaction.

Engine generation 51 reuses the exact serialized metadata snapshot and compact
receipt for repeated photo/policy pairs inside that single write transaction.
Catalog, copyright-only and no-metadata modes remain distinct; hierarchy settings
matter only for catalog metadata. Image format, destination and processing options
remain job-specific, as do recipes and orientation. Preset-first job ordering and
ordinary export's independent preparation path are unchanged. The cache is local
to one submission, retains at most 16 MiB of UTF-8 payloads and 1,000 entries, and
evicts least-recently used entries. Oversized entries still export but are not
retained. The cache never survives a submission; later batches read current values.
Exact request replay returns its existing receipt without new snapshot preparation.
Schema 36 and all 149 command contracts remain unchanged.

The identical isolated scale probe (100 generated 8×8 PNGs, 100 direct keywords
per photo, paused queue, no pixel workers) produced these results on the same
Apple M3 Max / 128 GiB / macOS 26.6.2 host. Each row is one first submission plus
five further submissions with fresh request keys, warm OS/SQLite state and
pre-created destination folders; no tests or builds ran concurrently.

| Jobs | Before warm median | New first / warm median | New transaction median | New peak RSS / rise |
| --- | ---: | ---: | ---: | ---: |
| 100 (1 preset) | 123.0 ms | 121.1 / 124.4 ms | 115.0 ms | 45.2 / 7.8 MiB |
| 500 (5 presets) | 510.9 ms | 143.8 / 147.9 ms | 128.1 ms | 48.2 / 2.5 MiB |
| 1,000 (10 presets) | 1,018.1 ms | 170.3 / 178.6 ms | 142.3 ms | 48.7 / 0.1 MiB |

At 1,000 jobs, warm submission was about **5.7× faster** and the measured catalog
transaction fell from 996.0 to 142.3 ms. A single preset has no reuse opportunity
and stayed approximately unchanged. RSS is sampled process memory, not a heap
proof or a guarantee; the last case starts after earlier cases have already
allocated memory. The transaction measurement excludes the shared preset-store
transaction. These measurements do not include IPC, desktop drawing, image
processing or cold storage, and do not establish desktop frame rate or export
throughput improvements.

Validation: **81 focused Python tests passed**; the full suite with required
actual Metal dispatch and the retained real NEF fixture passed **1,011 tests in
141.68 s**, without skips. The new regression checks compare canonical snapshot
and receipt bytes across formats and output options, four effective metadata
policies, ordinary export, exact replay, job order/orientation, Unicode byte
budgets, LRU eviction, oversized entries and later metadata/keyword/rating changes.
The packaged engine passed **78 native assertions** (Batch 46, Export Metadata 16,
Responsiveness 16). All 149 MCP schemas, source/client/broker identity, bundled
guide bytes and deep strict ad-hoc signature verification matched.

The app was built for the macOS 14 deployment target and run on macOS 26.6.2.
macOS 14 runtime and current desktop/VoiceOver/Lightroom reference acceptance
remain unverified; desktop automation was not retried. This optimization changes
submission preparation, not image algorithms, processing throughput or product
parity status.

### Suspected duplicates in folder synchronization review

Engine generation 52 / schema 37 adds a separate suspected-duplicate classification
to new Folder Sync reviews. Matching uses original filename, byte size and known
capture time, including clock provenance and fractions beyond microseconds. It
checks catalog originals and earlier candidates in the same plan through indexes;
an earlier unchecked item still participates in identity matching. Unknown capture
time is never inferred from modification time. Both change pages and duplicate
pages stay bounded to sixty summaries; large metadata remains a separate read.

The Mac review sheet shows duplicate counts, possible matching paths, a dedicated
filter and item/folder selection. Duplicate inclusion starts off. Turning it off
preserves individual checks; disabling new-photo import excludes both new and
duplicate files. An explicit inclusion request initializes capture/XMP metadata,
Import/Image numbering, folder counts and Previous Import with the same eligibility
as ordinary new imports. Original files stay in place and are not written.

New candidates are checked for newly cataloged duplicates inside the final write
transaction, before number allocation, removal or metadata mutations. A conflict
requires a fresh scan. Additive migration keeps saved pre-feature plans on their
original rules through resume; they are not silently reclassified. A fresh plan
is required to adopt duplicate review.

Adobe's [folder synchronization documentation](https://helpx.adobe.com/lightroom-classic/desktop/manage-catalogs-and-files/create-folders.html)
distinguishes direct synchronization from its optional Import dialog, where
suspected-duplicate exclusion is available. LumaRAW places this policy in its
existing mandatory review sheet. The complete Adobe Import dialog and direct
workflow equivalence remain gaps; this increment does not complete Library or
product parity.

Validation: **86 focused Python tests passed**. The full Python suite with
required actual Metal dispatch and the retained real NEF fixture passed
**1,018 tests in 145.38 s**, without skips. New cases cover original-name matching,
nanosecond fractions, unknown clocks, within-plan predecessors independent of
selection, explicit inclusion and backup/restore, metadata/counter/Previous Import
provenance, and a late catalog conflict before removal or number allocation.
Genuine schema-36 fixtures exercise rollback and a saved pending plan's scan and
application after upgrade; the matching candidate retains its legacy classification.
Query-plan checks verify indexed change pages, duplicate pages and identity lookups.
These are correctness and access-path checks, not a new latency benchmark.

The packaged engine passed **102 native assertions**: Folder Sync 41, Import
Sequence 26, Previous Import 19 and Responsiveness 16. The sync fixture waits for
the library's preceding preview work before beginning another apply; a busy-image
refusal remains visible and is not automatically retried. Its inspected offscreen
sheet shows the default-off inclusion control, retained item check, duplicate
filter and matching path. This is layout evidence, not desktop interaction.
All **149 MCP schemas**, source/client/broker identity, bundled guide bytes and
deep strict ad-hoc signature verification matched. The app targets macOS 14 and
was checked on macOS 26.6.2; macOS 14 runtime, desktop input, VoiceOver and Lightroom
reference acceptance remain unverified. Desktop automation was not retried.

### Reducing folder-sync transaction work

The generation-52 apply path paged every staged file, queried its current master
individually and decoded its fingerprint JSON inside the catalog write transaction.
That included unchanged originals and missing originals already removed earlier
in the same transaction. An isolated direct-domain probe measured about one second
for 100,000 unchanged originals; a separate missing/import probe measured a
2,996.2 ms transaction and a 3,005.4 ms concurrent browse wait.

Generation 53 retains complete source-snapshot and filesystem identity checks,
then reads at most sixty indexed change candidates joined to surviving masters.
It uses the scan's stored byte size and mtime instead of decoding per-file identity
JSON again. Deselected existing changes still refresh stat/availability fields;
metadata and new/duplicate imports retain their explicit selection gates. Indexing
can change a master's missing flag without advancing its source revision, so a
separate keyset query repairs those unchanged masters and their virtual-copy
families. SQLite still inspects that unchanged range, and the full conflict checks
and staging cleanup still scale with plan size; this is not constant-time apply.
Schema 37 and all 149 service contracts remain unchanged.

An isolated before/after run on Apple M3 Max / 128 GiB / macOS 26.6.2 used
actual SQLite originals, source families, folder membership and staged rows,
with absent synthetic original paths and no image dimensions or pixel backend.
Each case used a fresh plan, one first apply and five subsequent warm applies;
OS caches were not flushed. These CPU/SQLite timings include the atomic apply,
conflict checks and staging cleanup, but exclude prepare, filesystem validation,
IPC, image decoding and desktop rendering:

| Originals | Changed stat rows | First apply, before → after | Warm median, before → after |
| --- | --- | --- | --- |
| 10,000 | 0 | 95.8 → 57.7 ms | 95.0 → 47.4 ms |
| 10,000 | 10 | 99.2 → 49.1 ms | 93.9 → 48.5 ms |
| 100,000 | 0 | 1,042.0 → 677.2 ms | 1,018.3 → 575.1 ms |
| 100,000 | 10 | 1,036.1 → 573.4 ms | 1,032.1 → 572.5 ms |

The process-wide RSS high-water mark was 80.9 → 85.2 MiB, including seed work
and previous cases; it is not an apply-only memory measurement. All catalog,
source revision, folder count and original-absence assertions passed.

The broader warm service/stat probe used 100,000 catalog originals, 99,999 missing
originals and 10,000 new empty PNG placeholders. Its single before/after run
measured atomic commit 2,996.2 → 2,816.5 ms, complete apply 9,111.9 → 9,057.1 ms,
and maximum concurrent browse wait 3,005.4 → 2,812.0 ms. Browse p95 remained
8.6 ms; process peak RSS was 86.7 → 85.0 MiB. This workload remains dominated
by actual catalog mutations and complete filesystem validation. It does not
establish desktop smoothness or a repeatable end-to-end speedup, and the remaining
multi-second write hold is an explicit performance gap.

Validation: **91 focused Python tests passed**. The full suite with required actual
Metal dispatch and the retained real NEF fixture passed **1,023 tests in 149.62 s**,
without skips. New regressions cover deselected stat refresh, selected XMP scope,
missing-flag recovery across original/virtual-copy families, late source-version
and file conflicts without partial import, and a real 10,000-master catalog whose
single changed row uses the production partial index with bounded result pages.
The apply-only probe also asserts exact final counts, stats and source revisions.

The packaged application passed **102 native assertions**: Folder Sync 41, Import
Sequence 26, Previous Import 19 and Responsiveness 16. All **149 MCP schemas**,
source/client/broker identity, bundled guide bytes and deep strict ad-hoc signature
verification matched. The app targets macOS 14 and was checked on macOS 26.6.2.
macOS 14 runtime, desktop input, VoiceOver and Lightroom reference acceptance
remain unverified; desktop automation was not retried. This change reduces
catalog work and does not change image processing or complete Lightroom parity.

### Photo drops into regular collections

The Mac Grid and filmstrip now share a session-scoped photo drag value with the
existing Reference/Active targets. In Grid, dragging a selected photo captures
the valid visible selection, bounded to sixty IDs. An unselected anchor or a
photo outside Grid carries only that anchor. Regular collection rows accept
the captured IDs with their displayed collection revision; existing memberships,
photo edits and original files are preserved. Menu membership actions also capture
their existing selection scope before scheduling asynchronous work.

A collection drop rejects foreign sessions, malformed ID lists and photos no
longer on the visible page. A later selection-only change does not substitute
different photos. Stale collection revisions fail visibly without refreshing a
token and replaying the mutation. Reference/Active targets continue to consume
only the anchor, including legacy single-photo values. No new engine API, catalog
migration or image work is introduced; generation 53 / schema 37 / 149 contracts
remain unchanged.

Adobe documents [adding photos by dragging them into a collection](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/photo-collections.html)
as a membership copy; moving between collections requires a separate removal.
This increment covers regular-collection photo addition. Quick Collection drops
are added below; collection-node reparenting by drag, manual photo ordering and complete desktop
gesture/reference acceptance remain open. Smart collections and sets are not
manual photo-drop targets. Existing menu actions remain available.

The unchanged collection, identity, label, stack and Reference service contracts
passed **41 focused Python tests in 7.16 s**. The portable engine source identity
is unchanged from the preceding 1,023-test actual-Metal/real-NEF checkpoint;
that full result is retained as prior evidence, not reported as a new full run.

The rebuilt Mac application passed **125 native assertions**: Collection Drop 15,
Collections 42, Reference 52 and Responsiveness 16. Drop checks use the packaged
service to verify exact membership and preserved photographic state/original
bytes. They exercise sixty-ID capture, legacy JSON decoding, current-page
invalidation, selection changes before a scheduled Task runs, regular-only
admission and stale target rejection without retry. The inspected offscreen
regular-collection row retains its readable name, parent context and color mark;
this is layout evidence, not mouse drag or hover acceptance.

All **149 MCP schemas**, source/client/broker identity, bundled guide bytes and
deep strict ad-hoc signature verification matched. The build targets macOS 14 and
was checked on macOS 26.6.2. macOS 14 runtime, desktop gestures, VoiceOver and
Lightroom reference acceptance remain unverified; desktop automation was not
retried. No new desktop latency or processing-performance claim is made.

### Direct Quick Collection photo drops

The native Quick Collection row now accepts the same bounded, session-scoped
photo payload as regular collections, with an Add Selected Photos menu alternative.
The row's Quick identity and revision are captured before asynchronous work;
changing the configurable Target Collection does not redirect a Quick drop.
The direct membership service checks the captured Quick revision and only adds
relationships. A repeated add with a newly read revision preserves membership
and follows the existing service behavior of advancing the collection revision.
A stale Quick value fails without retry or partial membership changes.

The [Adobe collection reference](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/photo-collections.html)
describes Grid-to-collection dragging and separate Quick menu, B-key and thumbnail
circle actions. It does not explicitly establish Quick-row dragging. This native
operation is therefore recorded as LumaRAW behavior; matching the Adobe desktop
gesture remains unverified. Smart collections and sets still reject manual photo
drops. Engine generation 53, schema 37 and all 149 service contracts are unchanged.

The relevant collection, identity, label and stack Python regressions passed
**35 tests in 4.36 s**. The portable engine digest remains identical to the prior
full actual-Metal/real-NEF checkpoint; that result is not a new full-suite run.

The packaged application passed **77 native assertions**: Collection Drop 19,
Collections 42 and Responsiveness 16. The Quick-specific cases verify a Target
switch after capture, repeated additions with a current revision, rejection of
stale Quick revisions and preservation of photo state and original bytes.
The nineteen Drop assertions passed again after a fixture-only layout change.
The native List produced only a background in an offscreen snapshot, so it is
not accepted as visual evidence. A standalone stack of the actual sidebar
controls was inspected instead: Quick and the separate targeted regular row
remain readable and distinct. This establishes isolated control layout only.

All **149 MCP schemas**, source/client/broker identity, bundled guide bytes and
deep strict ad-hoc signature verification matched. The app targets macOS 14 and
was checked on macOS 26.6.2. macOS 14 runtime, native List/desktop drag and hover,
VoiceOver and Adobe gesture equivalence remain unverified. Desktop automation
was not retried; no processing-speed claim is made for this UI increment.

## Quiet thumbnail refresh after catalog actions (October 2, 2026)

A warm collection-membership or metadata change refreshed the bounded photo page
and correctly reused its image objects, but the thumbnail renderer published the
same image/error dictionaries twice. The Store callback then assigned both
published fields twice, creating four avoidable workspace notifications. The
renderer now compares immutable image identities and errors before publishing.
It retains the previous bounded image set to avoid confusing a reused object
address with an unchanged image. Forced cache/source validation, cancellation,
miss fallback, image replacement/removal and error clearing remain active.

An isolated native measurement used the same generation-53 packaged engine before
and after the native change, on Apple M3 Max, 128 GiB, macOS 26.6.2. Separate
disposable catalogs contain five or sixty generated 160 by 100 PNGs. Each page is
warmed before one collection-membership addition and one metadata-title edit;
periodic Store polling is not started. All four before/after pairs retain the
same visible photo IDs and NSImage objects, execute one cancellation and one
bulk cache validation, make no direct thumbnail requests and report no cache
worker spawn. Original bytes remain unchanged.

| Observable updates per action, at both page sizes | Before | After |
| --- | --- | --- |
| Thumbnail renderer callback, either action | 2 | 0 |
| Store notifications, collection membership addition | 17 | 13 |
| Store notifications, metadata title edit | 16 | 12 |

These counts establish removal of redundant publication. Necessary library,
selection and metadata updates still occur. Single-sample action times were
27.87 to 28.42 ms and 33.75 to 32.76 ms for five photos, and 35.13 to 33.46 ms
and 38.38 to 39.07 ms for sixty photos (membership, then metadata). They do not
establish an elapsed-time improvement. The separate 100-ms stable-state barrier
is not included in those action times; action return is not displayed completion.
Native process RSS high-water marks were 32.38 to 32.22 MiB and 35.66 to 35.67
MiB, including warm-up and prior operations, not per-action or whole-app peaks.
No new pixel processing or RAW throughput is measured.

The relevant Python thumbnail and cache regressions pass **11 tests in 4.28 s**.
The final packaged engine passes **45 native state/IPC assertions**: Thumbnail
Publication 15, Thumbnails 14 and Responsiveness 16. Gated replies verify
same-target force validation, cache failure fallback, error clearing, same-path
image replacement and obsolete responses; live-engine checks also cover source
relinking and cache eviction. Unchanged background polls still emit zero Store
notifications. The Mac app builds for macOS 14, passes deep strict ad-hoc signature
verification, and matches source/client/broker identity, all 149 MCP schemas and
the bundled guide. These checks run on macOS 26.6.2, without desktop automation.
Engine generation 53, schema 37 and the 149 command contracts are unchanged.
Desktop scrolling/input/frame rate, VoiceOver and macOS 14 runtime acceptance
remain unverified; this measured publication defect does not explain every
possible cause of the reported interface lag. Full non-AI parity remains open.

## Photo-list reads during catalog writes (October 2, 2026)

`list_photos` previously waited for the service-wide catalog lock, including the
entire atomic application of a large folder synchronization. It now uses a short
read-only SQLite snapshot without constructing the writable Catalog or running
migrations. Exact count, clamped page, stack/family rows and all returned state
revisions share that snapshot. A write committed between query statements cannot
produce a mixed response; the next request sees the new committed data. Shared
Library query code preserves the existing source/filter/sort/stack behavior.
Writes retain their original lock, transaction and conflict barriers.

The connection uses a read-only URI and query_only, registers the existing SQL
functions, checks the exact schema in its transaction and closes before returning
the response. It cannot create a missing catalog or silently migrate a mismatched
one. Normal Service startup still upgrades old catalogs. This engine release is
generation **54**, with schema **37** and **149** public commands unchanged.

An isolated before/after run on Apple M3 Max, 128 GiB, macOS 26.6.2, Python 3.12.0
and SQLite 3.42.0 used 100,000 synthetic catalog originals: 99,999 missing paths,
one empty existing placeholder and 10,000 new empty PNG placeholders. It exercises
real service/SQL/stat work with warm catalog and directory caches, without file
hashing, valid photographic pixels, IPC or native display. Each side runs once;
the concurrent reader samples throughout planning/scanning/application.

| Measurement | Before | After |
| --- | --- | --- |
| Concurrent list requests | 660 | 879 |
| List median / p95 | 6.359 / 8.609 ms | 6.120 / 7.699 ms |
| Longest list request | 2,788.433 ms | 82.988 ms |
| Atomic apply | 2,779.576 ms | 2,916.068 ms |
| Complete apply, including verification | 8,895.306 ms | 9,096.350 ms |
| Process peak RSS, including setup and earlier phases | 86.70 MiB | 83.20 MiB |

The observation is reduced photo-list lock waiting, not faster synchronization.
The write transaction and complete apply did not improve in this pair. Both runs
retain correct final photo/folder counts, clear staging, restore maintenance and
start no image workers. One run per side does not establish repeatable maximum
latency or a desktop responsiveness budget.

The targeted suite passes **52 tests in 6.22 s**, including snapshot consistency
when another connection commits, service-level import between count and page,
reads while a writer holds the service lock, real schema-32 startup migration,
URI-sensitive Unicode catalog paths, and physical read-only enforcement even
after query_only is disabled. Missing or mismatched schemas do not trigger writes.

The full Python suite passes **1,031 tests in 153.23 s**, with actual Metal required
and the read-only Nikon D3S NEF fixture enabled; no tests are skipped. The Mac app
builds for macOS 14 and passes deep strict ad-hoc signature verification. Its
generation-54 source, packaged client and broker identities match, together with
all 149 MCP schemas and the bundled guide. Execution is on macOS 26.6.2.
The packaged engine passes **163 native state/IPC assertions**: Library 13,
Stacks 27, Collections 42, Folder Sync 41, Thumbnails 14, Responsiveness 16 and
Connection 10. These are generated-fixture integration checks, not desktop input
or scrolling/frame-rate acceptance.

This first read path covers only `list_photos`. Store refresh still awaits
collection/orientation state and sometimes folders/keywords; summary polling and
thumbnail queries also retain their previous locking. Saturated broker admission
and expensive filters may delay readers independently of the service lock.
Those waits, desktop interaction/frame rate, VoiceOver and macOS 14 runtime remain
open acceptance work. This does not complete the interface-lag investigation or
the full non-AI Lightroom Classic inventory.

## Compact refresh-state reads during catalog writes (October 2, 2026)

`library_state`, `photo_summaries`, `collection_state` and `orientation_state`
now use one independent read-only snapshot per response, following the photo-list
path. Revision envelopes, bounded photo summaries, Quick/target membership and
orientation undo state remain internally coherent when another connection commits
between statements. The shared summary query retains its 1–60 ID bound, ascending
ID order and SQL-IN duplicate handling; existing Catalog callers reuse it.
Separate commands can observe different commits, so native generation/revision
guards remain necessary. Engine generation is **55**, schema **37** and the
**149** command contracts are unchanged.

The new isolated refresh-chain probe runs `list_photos`, `collection_state`,
`orientation_state`, `photo_summaries` and `library_state` sequentially during
the same synthetic 100,000-original Folder Sync workload described above. It uses
Apple M3 Max, 128 GiB, macOS 26.6.2, Python 3.12.0 and SQLite 3.42.0, with warm
catalog/directory caches, 99,999 missing paths and 10,000 new empty PNG placeholders.
One run per engine generation records 526 before and 690 after chains, with no
omitted samples. Per-command revisions are recorded independently, not required
to match across requests.

| Measurement | Generation 54 | Generation 55 |
| --- | --- | --- |
| Refresh chains during apply | 143 | 226 |
| Apply-phase chain median / p95 | 21.810 / 25.383 ms | 15.461 / 19.808 ms |
| Longest apply-phase chain | 2,982.828 ms | 159.052 ms |
| Longest collection-state request during apply | 2,969.797 ms | 7.778 ms |
| Scan-phase chain median / maximum | 22.137 / 767.808 ms | 15.453 / 55.910 ms |
| Atomic apply | 2,968.904 ms | 3,197.269 ms |
| Complete apply, including verification | 10,130.687 ms | 10,116.407 ms |
| Process peak RSS, including setup and retained samples | 95.95 MiB | 109.12 MiB |

The pair establishes reduced waits in these read commands, not faster catalog
mutation or a repeatable maximum-latency guarantee. More completed samples and
their retained revision records also contribute to process memory; RSS is not a
per-command allocation measurement. Both runs retain correct photo/folder counts,
clear staging, restore maintenance and start no image workers. This measures
in-process SQL/stat/control work with empty synthetic files, not valid-image/RAW
processing, IPC, broker admission, actual Store.refresh completion or UI frames.

Targeted regression passes **68 tests in 8.38 s**, including all four commands
reading the old state while a writer holds Service.lock, followed by the new
committed state. Real import, rating, membership and orientation commits inserted
between response components preserve whole-response snapshots. Response keys,
summary ordering/limits and collection membership sets remain compatible.
The full Python suite passes **1,038 tests in 155.77 s**, with actual Metal required
and the read-only Nikon D3S NEF fixture enabled; no tests are skipped.
The final packaged engine passes **199 native state/IPC assertions**: Library 13,
Collections 42, Orientation 51, Snapshot Filter 25, Reference 52 and Responsiveness
16. The Mac app builds for macOS 14 and passes deep strict ad-hoc signature
verification; source/client/broker identities, all 149 MCP schemas and the bundled
guide match. These generated-fixture checks run on macOS 26.6.2 and do not dispatch
desktop input or establish rendered interaction acceptance.

Conditional folder/keyword pages, selected-photo details and thumbnail work still
use their previous paths. Saturated broker admission and expensive queries can
also delay reads. Desktop input/scrolling, VoiceOver and macOS 14 runtime acceptance
remain open, together with the broader non-AI Lightroom Classic inventory.

## Collection nodes dragged into sets (October 2, 2026)

The Mac sidebar accepts regular collections, smart collections and collection
sets dragged onto a set. Adobe documents this node-to-set workflow in its
[collection guide](https://helpx.adobe.com/lightroom-classic/desktop/organize-photos-in-lightroom-classic/photo-collections.html).
LumaRAW uses a distinct exported transfer type with session, source ID and
captured revision; no names, rule edits, photo IDs or paths are trusted from the
payload. Admission requires fresh loaded source/target pages. The authoritative
source is fetched and checked before the existing revision-bound save command
changes its parent. Same-parent drops do not write. Quick is excluded. Root
moves remain available through Edit / Move and Use Root; root-area drag behavior
was not established from the inspected reference and is not implemented here.

Moves retain the node's name, kind, smart rules, match policy, color label,
memberships and subtree. The service's existing cycle/depth and stale-revision
failures remain visible without retry. After saving and reloading bounded sidebar
pages, the currently active Library set refreshes its aggregate photos, including
when the user entered that destination before the write completed. No source is
opened automatically. Navigation guards reject a stale refresh before advancing
its page token and after asynchronous work. Photo collection drops and Reference
drags keep their separate payload and behavior.

An acknowledged move records a pending photo-page invalidation before reloading
the tree. Develop/Reference and in-flight view changes defer that refresh, keeping
the active photo and recipe in place. Returning to Library refreshes the current
set before Compare/Survey initializes. Failed reads retain pending work; a late
older page cannot consume a newer invalidation or overwrite its state. New node
drops are not admitted while Develop is active.

The collection/domain suite passes **17 tests in 2.05 s**. The new native suite
passes **19 state/IPC assertions** against the verified generation-55 engine,
including two gated real-save/navigation races, open source/destination set counts,
same-parent revision stability, stale/cycle/depth failures and unchanged authored
photo state/original bytes. Depth fixtures expand one ancestor at a time, avoiding
an unrelated command-admission burst. A generated standalone sidebar snapshot
shows readable regular/smart/set rows and disclosure controls; it is offscreen
layout evidence, not native pointer, hover, drop or accessibility acceptance.

A separate native regression first reproduced the selected Develop photo being
replaced after a gated move completed. After the fix, the new transition suite
passes **21 assertions**, alongside **19** node-move and **20** Compare/Survey
assertions. The tests gate actual saves and bounded page replies to cover locked
Reference identity, active recipes, failed reads, newer moves overtaking older
replies, Develop entry during a pending page and fresh view initialization on
return. Generated originals remain byte-identical.

The final packaged engine passes **214 native state/IPC assertions** across node
moves 19, Develop/node races 21, photo drops 19, collections 42, Library 13,
selection 12, Compare/Survey 20, Reference 52 and responsiveness 16. The Mac app
builds with a macOS 14 target, exports both transfer types and passes deep strict
ad-hoc signature verification. Source/client/broker identities, all 149 command
schemas and the bundled guide match. These checks run on macOS 26.6.2 with
generated fixtures; the offscreen sidebar was inspected separately.

No engine command, schema or generation change is required: generation **55**,
schema **37**, and **149** contracts remain unchanged. Desktop drag/drop,
VoiceOver, macOS 14 runtime and Lightroom interaction acceptance remain open.
This is one collection workflow increment, not complete non-AI parity.

## Captured culling shortcuts (October 2, 2026)

The focused Mac Library surfaces map ratings 0–5, flags P/X/U and labels
6/7/8/9 (red/yellow/green/blue). Adobe's
[keyboard reference](https://helpx.adobe.com/lightroom-classic/desktop/introduction-to-lightroom-classic/keyboard-shortcuts.html)
documents the corresponding Shift forms for applying a value and advancing.
LumaRAW advances after an acknowledged write for one Grid target or the active
Loupe photo. Grid batches retain captured targets; Compare/Survey change only the
active photo without advancing. Ordinary rating/flag keys retain their existing
Develop behavior; the new Shift and label-key paths are scoped to Library.

Affected modes, filters, sort orders and smart/set membership requery the bounded
page. Rows, clamped offset and focus reconcile together before asynchronous detail
loads. The next photo comes from the captured visible order, intersected with the
new page. A batch retains surviving selection and its active photo, or a captured
surviving selected row; an empty selection clears instead of selecting an unrelated
first row. No successor wraps around or guesses a photo on an unloaded page.
Pending collection-node invalidations are consumed only by a successful current
aggregate refresh. Later navigation, selection, view changes or culling actions
prevent an older action from retargeting focus.

The initial native preflight passes **151 state/IPC assertions**: culling 97,
Library 13, Compare/Survey 20 and collection-node/Develop transitions 21. Five
generated originals plus catalog-only virtual copies cover batches, membership,
61-to-60 page clamping and gated real mutation/page replies. A reversed rating-sort
tie assumption in the fixture was corrected before this passing run.

A subsequent regression reproduced an older accepted rating being absent from
native state after a newer attempt failed: the catalog held 2 while the displayed
value remained 0. Rating/flag adoption now tracks the most recent acknowledged
attempt for each photo/field until its in-flight requests drain. A pending or
failed attempt cannot suppress an accepted value, while a later accepted attempt
blocks older replies. Metadata adopts the entire canonical patch at a non-stale
revision; status and focus ownership remain independent. No mutation is replayed.
The shared organization, keyword and metadata-preset service tests pass **26 tests
in 3.15 s**.

The final packaged engine passes **323 native state/IPC assertions**: culling 121,
Library 13, selection 12, Compare/Survey 20, Reference 52, collection-node/Develop
transitions 21, metadata presets 32, Painter 36 and responsiveness 16. The new
failure cases use distinct starting values and both reply orders, and retain a
third successful write against an older late response. Generated originals remain
byte-identical. The Mac app builds for a macOS 14 deployment target and passes
deep strict ad-hoc signature verification; source/client/broker identities, all
149 command schemas and bundled guide bytes match on macOS 26.6.2. Engine
generation **55** and catalog schema **37** remain unchanged because this increment
changes native presentation and reuses existing commands.

Auto Advance preferences, Caps Lock, Shift+B, cross-page advance, purple/no-label
keys and exact Adobe sorted/filter-removal selection behavior remain open. The
state suite does not dispatch physical keyboard events or verify international
keyboard layouts, text-focus routing, VoiceOver or macOS 14 runtime behavior.
Desktop automation remains unavailable, and full Lightroom parity is not claimed.

## Folder Sync original-name insertion (October 2, 2026)

New synchronized originals now insert both `name` and `original_name` from the
validated source path. Schema 19's fallback trigger no longer has to update each
new row just to fill its original name. Staged name caches remain irrelevant to
this identity, including an empty migrated schema-36 name or an incorrect cache.
The duplicate/synchronization suites pass **41 tests in 8.46 s**, including a
genuine legacy ready plan, decomposed Unicode basename, actual apply through the
runner, virtual-copy inheritance and unchanged original bytes.

The domain-only mutation probe uses absent synthetic originals, 100,000 existing
catalog rows and 10,000 new rows where applicable. Each case has one first sample
and three later samples from fresh SQLite backups/connections. On Apple M3 Max,
128 GiB, macOS 26.6.2, Python 3.12.0 and SQLite 3.42.0, the sequential old/new runs
record the following complete-apply times; OS caches were not flushed:

| Case | Old first / warm median | New first / warm median |
| --- | ---: | ---: |
| 10,000 new only | 421.476 / 1,275.015 ms | 355.826 / 373.015 ms |
| 100,000 unchanged + 10,000 new | 1,129.456 / 1,112.181 ms | 1,015.420 / 1,061.650 ms |
| Remove 100,000 missing catalog entries | 2,168.805 / 2,210.110 ms | 2,178.035 / 2,202.485 ms |
| Remove 99,999 + add 10,000 | 2,622.251 / 2,659.222 ms | 2,700.817 / 2,786.028 ms |

Transaction-finalization outliers make these unsuitable for a general speedup
claim; the mixed median increased. Process peak RSS is 111.55 / 116.50 MiB and
includes seeding, database copies and prior samples, not just one application.

A second probe alternates only the old/new INSERT SQL in the same process, with
five pairs per case and reversed order on alternate pairs. Every application
checks counts, original names, folder state, numbering, Previous Import and staging
cleanup. The 10,000-photo INSERT plus its triggers makes exactly **60,000 versus
50,000 SQLite row changes** in both cases: one fewer update per new photo. Its
warm INSERT medians are **388.892 / 387.895 ms** for new-only and **297.664 /
224.212 ms** with 100,000 existing rows. Large timing outliers persist in both
variants; peak process RSS is 117.28 MiB. The retained improvement is fewer writes
with preserved semantics, not a guaranteed elapsed-time reduction.

Both reproducible probes are public under `tests`. They exclude discovery,
filesystem revalidation, IPC, image workers, pixel processing and desktop input.
No camera-throughput, frame-rate or Lightroom performance equivalence is implied.
Engine generation advances to **56**; catalog schema **37** and the **149** command
contracts remain unchanged. The complete Python suite passes **1,039 tests in
176.08 s**, with required actual Metal execution and the public Nikon D3S NEF
fixture; no tests are skipped. The Mac app builds for a macOS 14 deployment target
and passes deep strict ad-hoc signature verification. Source/client/broker
identities, all command schemas and bundled guide bytes match on macOS 26.6.2.
The final packaged engine passes **89 native state/IPC assertions**: Folder Sync
41, Library 13, Previous Import 19 and responsiveness 16. These generated-fixture
checks are not desktop-input or Lightroom acceptance; macOS 14 runtime remains
unavailable. A fresh fetch finds no unmerged local or remote branches.

## Source-bound raster White Balance Selector (October 2, 2026)

Adobe's [tone and color reference](https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/image-tone-color.html)
describes selecting a neutral area with W, paired Temp/Tint adjustment, a loupe
and optional automatic dismissal. LumaRAW's increment is a one-shot raster
selector in the active After image, available from the Color inspector or W.
Fit and full-resolution detail expand the click into normalized full-output
coordinates; Reference/Before pixels and margins cannot submit a sample.

The shared read-only `sample_white_balance` command binds the displayed source's
24-hex stat fingerprint and photo revision to a dedicated cancellation generation.
The worker samples at most 25 full-resolution source-linear pixels through the
existing geometry, excluding grading and display effects. It reverses current
relative gains, rejects predominantly invalid/dark/clipped or out-of-range points,
and returns a candidate. One guarded `edit_photo` stores both fields in one
history step when values change; unchanged values retain revision and history.
Originals are read-only; no hover request or screen sampling occurs.

The Python selector, service, reference-preview and completed-cache tests pass
**84 tests in 32.99 s**. They cover all eight catalog orientations, rotation,
crop/perspective/lens transforms, one-pixel output, actual source-worker delivery,
source/revision races, actual child cancellation, NaN input non-interference and
stale proxy-cache dimensions. Generated rasters establish this relative model's
math and data flow; they do not establish Adobe processing equivalence.

The complete Python suite passes **1,086 tests in 194.44 s**, with actual Metal
required and the read-only public Nikon D3S NEF fixture; no tests are skipped.
Native review also exposed and corrected no-op reply handling, cancelled edit
waits and stale sample failures clearing a newer edit's busy state. An uncertain
save now retains concurrent slider drafts behind an explicit captured recovery
decision instead of leaving an unexplained navigation block or retrying the write.

This adapter explicitly rejects RAW before decoding. RAW camera-gain selection,
absolute Kelvin calibration, sample loupe/scale, hover Navigator preview and
Auto Dismiss preference remain open. Source identity uses file stat information,
not a content hash or filesystem lock. Engine generation **57** raises the command
inventory to **150**; catalog schema **37** is unchanged. The final Mac package
builds for a macOS 14 deployment target, passes deep strict ad-hoc signature
verification, and matches source/client/broker identity, all command schemas and
bundled guide bytes on macOS 26.6.2.

The reproducible packaged-relay probe uses a generated **4,000 × 3,000 RGB PNG**,
CPU processing, a fresh catalog and five identical read-only center samples. Fit
preview setup is separately **949.710 ms**. The first full-source sample takes
**1,512.855 ms**, including decoding and linear-cache publication, with sampled
worker peak **970.8 MiB**. Four warm linear-cache samples take **300.198–310.775
ms**, median **306.902 ms**, with peak **65.9 MiB** and no source decode. Candidate
values repeat and the catalog/original bytes remain unchanged. OS caches were
not flushed; these are command/worker measurements, not camera accuracy,
desktop latency or Lightroom performance equivalence.

The packaged white-balance suite passes **39 state/IPC assertions**. Its original
ImageRenderer inspector capture was blank; the replacement NSHostingView capture
is checked for nonuniform pixels and manually inspected. Temperature, Tint and
Cancel Point Selection are readable in the 390 × 1,700-point inspector. The other
capture contains the selector instruction overlay only, not a displayed photo.
Both remain offscreen layout evidence; desktop input, VoiceOver and macOS 14
runtime are unavailable. The complete packaged native run passes **245
state/IPC assertions**: white balance 39, Before/After 19, Reference 52, curve
targeting 33, mixer targeting 48, responsiveness 16, general state 15 and history
23. A fresh fetch finds no unmerged local or remote branches.

## Bounded raster color conversion (October 2, 2026)

The raster selector probe exposed high cold-worker memory use. The supported
8-bit raster path previously converted the full image to float32 and evaluated
both sRGB transfer branches over that frame. It now uses a read-only 256-entry
transfer table computed by the same float32 formula, then applies the existing
ProPhoto matrix and relative gains in 128-row strips. EXIF orientation, preview
resizing and ICC conversion retain their order. Pillow's decoded pixels and the
random-access linear output remain full-frame allocations; RAW decoding is
unchanged, and existing memory admission/watchdog limits remain in force.

The new decoded-array regressions require bitwise equality with the former
expression across transfer values, mixed channels and strip boundaries. Full
and preview paths cover all eight EXIF orientations, ICC/no-ICC, actual resizing,
grayscale/alpha conversion, metadata and original-byte preservation. The targeted
decode/core/white-balance suites pass **104 tests in 10.99 s**, with actual Metal
required and the public Nikon D3S NEF supplied. Engine generation advances to
**58**; schema **37** and **150** command contracts remain unchanged.

The full Python suite passes **1,122 tests in 186.55 s**, with required actual
Metal execution and the read-only public Nikon D3S fixture; no tests are skipped.
The Mac app builds for macOS 14 and passes deep strict ad-hoc signature checks.
Source/client/broker identity, all commands and bundled guide bytes match on
macOS 26.6.2. The packaged engine passes **55 native state/IPC assertions**:
white balance 39 and responsiveness 16. macOS 14 runtime, desktop interaction
and Lightroom acceptance remain unavailable.

Five alternating old/new pairs use a generated **4,000 × 3,000 RGB PNG**, CPU
processing and independent fresh catalogs/preset roots through each packaged
native relay. All ten trials preserve original/catalog state, reproduce the same
fixture bytes and return identical white-balance candidates. Each trial primes
Fit separately, then samples once with a cold full-linear cache and four times
with that cache warm. OS caches are not flushed; fixture hashing and Fit setup
make file pages likely warm before the full decode.

Median first-full-source worker peak is **971.0 → 561.6 MiB**, approximately
**42% lower**, while command-wall medians are **2,002.556 → 1,921.118 ms**.
The new cold sample is slower in two of the five pairs; the retained evidence
is reduced sampled worker memory with bitwise-preserved source pixels, not a guaranteed
latency improvement. Pillow decode, ICC transforms and the full linear result
still allocate full frames. These generated-raster measurements do not establish
RAW throughput, whole-app memory, desktop interaction speed or Lightroom parity.
