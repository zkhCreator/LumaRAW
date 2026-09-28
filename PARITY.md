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
- [Keyboard shortcuts](https://helpx.adobe.com/lightroom-classic/desktop/introduction-to-lightroom-classic/keyboard-shortcuts.html)

## Feature inventory

“Partial” means an implementation exists, with important workflow or verification
gaps. Nothing below is full Lightroom parity merely because historical tests pass.

| Area | Baseline | Remaining acceptance / work |
| --- | --- | --- |
| Import and catalogs | Partial: referenced originals, backup/restore | Import preview/selection, copy workflows, metadata/develop presets, catalog switching/merge |
| Library navigation | Partial: bounded grid/filmstrip, flags/stars | Folders, collections/sets, smart/quick collections, stable sorting, metadata/keyword filters |
| Organization | Partial: duplicate/missing detection | Keywords/hierarchy, IPTC, labels, stacks, virtual copies, rename, multi-photo metadata, sidecars |
| Culling | Partial: single-photo view, before/after | Compare/survey, reference view, range selection, auto advance, persistent workspace state |
| Basic development | Partial: light/WB/color | Calibrated absolute WB, eyedropper, texture/clarity/dehaze, complete HSL/B&W and color grading |
| Curves and profiles | Partial: custom composite curve, LUT/ICC | Interactive RGB curves, camera/profile browser, compatible preset import/export |
| Detail and optics | Partial: noise/sharpen, manual lens | Complete manual detail controls, automatic lens profiles, bounded full-resolution acceptance |
| Geometry | Partial: crop/rotate/straighten/perspective | Interactive retained handles/ratios/flip, guided transforms, crop state parity |
| Local editing | Partial: radial/gradient/brush/luma | Mask list/edit/reorder/intersection, range masks, clone/heal, red-eye (non-AI) |
| History and presets | Partial: 50-step undo, named versions | Redo, navigable history, preset management and import-time/batch application |
| Preview/performance | Partial: Metal, proxies, 1:1 viewport | Large-catalog query baselines, edited thumbnails, persistent thumbnail fast path, slider latency |
| Export | Partial: JPEG/16-bit TIFF, ICC, durable jobs | Presets, metadata policies, watermark, additional formats, publish workflows |
| Merge | Missing | Non-AI HDR merge and panorama with bounded resources and reference acceptance |
| Map | Missing | GPS metadata, map navigation, track import, location editing with explicit persistence |
| Book | Missing | Templates, layouts, typography, PDF/JPEG output; external fulfillment is a separate integration |
| Slideshow | Missing | Layout, timing, playback, audio, slideshow export |
| Print | Missing | Contact sheets/packages, physical sizing, native print/ICC workflow |
| Web | Missing | Local gallery templates and export; publishing requires explicit destination |
| Platform/accessibility | Partial: Mac 14 target, Mac 26 historical checks | Current desktop checks, macOS 14, keyboard/VoiceOver, color management; Windows remains future |

## Active increment

Library organization: durable regular/smart collections, catalog-only title/caption/
copyright/keywords/color labels, revision-safe batch changes, SQL filtering/sorting,
native controls, migration and query evidence. Collection sets, keyword hierarchy,
virtual copies and the other rows remain tracked separately.

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

Continue culling and organization: compare/survey, collection sets and quick collection, virtual copies, keyword
hierarchy, source-versus-developed thumbnail behavior. Then close Develop and
export gaps in the inventory. Preserve pending desktop/older-OS acceptance rather
than removing it from the completion criteria.

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
