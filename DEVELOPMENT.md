# Development contract

## Delivery unit

Deliver a user-visible workflow with persistent state, explicit failures and
repeatable evidence. Start with Library and Develop, then export and secondary
modules. `PARITY.md` is the inventory, not a promise that every existing control
matches Adobe's proprietary processing. AI generation, semantic selection,
AI denoising, assisted culling and inferred depth are excluded.

Commit each validated module and push it to the authorized development remote.
Verify the remote commit; an unpushed checkpoint is not a remote backup. Preserve
branch history and keep generated fixtures, catalogs, artifacts and receipts local.

Before changing a feature, read its opening comments, trace the native action
through `api.py` and `service.py` to catalog/renderer ownership, and identify the
observable acceptance condition. New code should be normally formatted with
named helpers and bounded responsibilities; do not extend dense one-line code
when a clear function is more maintainable. Avoid unrelated formatting churn.

## Contracts and persistence

- Keep native command encoding/IO/parsing and preview file decoding off the main
  actor. Reuse the bounded native relay while retaining broker identity checks
  for every call. Reserve cancellation/control capacity independently of image
  work, correlate replies by ID, and never replay an uncertain mutation after a
  pipe failure. Recheck frame generations after background image preparation.
  Compare polling state before publishing it; unchanged jobs, collection state,
  orientation state, photo-family/reference summaries and snapshot pages must not
  invalidate the workspace. Track conditional snapshot reads without toggling
  published loading state; explicit reads still show progress.
- Reference and active roles are independent. Keep inspector edits scoped to
  active selection, retain reference identity across source/filter changes, and
  clear an unlocked reference only when leaving the module. The lock is session
  state, not a frozen recipe or persistent catalog preference. Use separate
  cancellation generations; active edits and fitted layout changes must not
  restart unchanged reference processing. Validate ordinary preview revisions
  both before and after workers. Discard stale pane/photo/viewport drags and
  request only bounded physical-pixel ROIs. Cropping requires a captured exit
  confirmation; local drawing and targeting stay attached to the active image.
- Develop readouts sample engine data before proofing/overlays. Keep SDR RGB/Lab
  equations, white point, precision and clipping explicit. Do not derive values
  from screen pixels. Compare full cropped dimensions before pairing roles and
  follow Before state. Load maps off the main actor and isolate hover publications
  from Store. Local pointer movement must not start workers; an off-viewport
  counterpart may use a debounced, cancellable, revision-bound one-pixel request.
- Fuse optional pixel outputs with an existing grading dispatch when their
  equations permit it. Keep CPU reference values, finite SDR clipping and
  proofing boundaries unchanged; document FP32 tolerances and validate real RAW.
  Count every optional GPU buffer in admission and layout changes. Do not expose
  any partial output after failure, repeat grading for readouts, or count a
  skipped CPU stage as the total user-visible speed improvement.
- Completed preview reuse must bind engine/backend, source/assets, both recipes,
  geometry, display and all requested auxiliary maps. Validate bounded artifact
  contents outside SQL locks and repeat revision/source/generation checks before
  returning. A cache hit cannot wait behind image work or claim a new GPU dispatch.
  Serialize corruption repairs with image writers; a normal LRU touch or atomic
  replacement is not evidence that valid maps should be removed. Publish PNGs
  and receipts atomically and preserve ordinary rendering when a cache is absent.
- Snapshot names and recipes are shared by original/virtual-copy families. Keep
  stable non-reused IDs, independent snapshot revisions and a family list token.
  Read summaries through indexed alphabetical pages; never load all recipes for
  listing or polling. Reject stale cursors and stale captured forms. Validate
  photo and snapshot revisions for replacing/restoring settings, and snapshot
  revisions for rename/delete. Capture retained history without selecting it.
  Preserve copied Before settings, live recipes/history, queued exports and
  legacy migration payloads. Snapshot update/delete have no Develop undo; expose
  deliberate native confirmations and accurate command effect annotations.
- Snapshot presence is shared by source family. Maintain indexed counts and the
  compact first/last-change token transactionally, including bulk removals and
  backup restoration. Reuse the same predicate for filters and smart rules; do
  not parse recipes or sum every family's revision while polling. Empty views
  and nested sets must notice external membership changes without stealing
  navigation or interrupting pending edits and captured snapshot forms.
  Keep exact indexed counts separate from bounded page retrieval. Any adaptive
  query shape must preserve source restrictions, all/any logic, stable ordering
  and stack projection; measure dense, sparse and empty cases before changing it.

- Stack display ordinals come from all members of the current source's stack,
  not the filtered page or its sparse sorting labels. Preserve ordering across
  negative labels, holes, ties, virtual copies and splitting. Bound returned rows
  and rank queries; group page members and count disjoint indexed ranges instead
  of repeating whole prefixes. Record deep-page costs for oversized stacks.

- Before snapshots are independent of the Develop timeline. Preserve imported
  presets and inherited virtual-copy settings, and never retarget Before when
  history is cleared or branched. Validate revisions for copy/swap/history
  assignment; swap both recipes atomically and advance the visual revision once.
  Before-only actions preserve redo. Keep complete copied recipes distinct from
  the geometry-aligned preview recipe. Bound and validate the independent cache;
  omit Before work when hidden and reject sources changed during comparison.
- Comparison layouts share one zoom/pan state and one captured pair of images.
  Fit layout/divider changes must not start workers. Convert point dimensions and
  drags using physical display scale, bound requests, and pan from returned ROI
  centers to avoid sticky edges. Reject captures after photo, revision, viewport
  or layout changes. Keep presentation out of recipes and Develop history.

- Keep reviewed imports separate from catalog photos until explicit application.
  Read directory entries, capture headers, XMP and pixels outside catalog locks;
  stage bounded pages and revalidate sources before one atomic Add transaction.
  Duplicate classification uses the original filename, size and known precise
  capture clock; never substitute modification time. Preserve manual check state
  when duplicate eligibility changes. Cancellation must roll back photo inserts,
  metadata, folder counts and maintenance flags, including inside bulk SQL.
  A completed import receipt is immutable; an uncertain response is read back,
  never automatically replayed. Resumption retains captured selection and source
  identity, and must not silently accept changed files. Copy uses the explicit
  destination/collision/recovery contract below; Move remains separate scope.
- Import Loupe 100% must request physical-pixel ROIs, not enlarge a fitted image.
  Keep Import viewport state separate from Library. Pan from the returned clamped
  ROI center; reject stale focus, plan, frame and pane geometry before applying a
  gesture. Reuse completed Fit/ROI receipts with the same source/asset/revision
  and generation checks as new image work; never turn a thumbnail into a 100%
  placeholder or emit a worker request on every drag event.
- Import configurations capture source-neutral options and exact processing/naming
  values, not live preset references. Keep list pages free of payloads and source
  receipts separate from polled summaries. Choosing a configuration pins fresh
  destinations; explicit ready-review rescans replace the old plan atomically,
  resetting checked selections only after all validation succeeds. Recheck both
  captured revisions after unlocked filesystem work. Interrupted transfers cannot
  be retargeted through a preset. Restores rebind nested LUT assets by hash.
- Destination-folder previews count only checked eligible originals. Maintain
  aggregates in the selection/state transaction and use indexed cursor pages;
  never hide an all-row GROUP BY or clock/rank decode behind a page limit. Keep
  separate duplicate-policy indexes, revision-bound pages and explicit native
  reload. Preview performs no destination filesystem work or directory creation.
  Associated XMP and second-copy transfers are not additional photographs.
  Individual checkbox updates must adjust selected totals from the changed IDs;
  do not recount every selected original after a page-scoped change.
- Copy naming captures token values, never a live template reference. Keep original
  names for duplicate identity while displaying verified destination basenames.
  Rename associated XMP to the same stem; validate every target before filesystem
  writes. Sequence order follows checked eligible filenames with a stable ID tie
  break, independently of review sorting. Freeze ordinals before copying, retain
  them across recovery and support cancellation during bulk SQL. Preview ranks
  must seek disjoint index ranges, including same-name IDs; test SQLite VM work
  rather than trusting that an index appearing in EXPLAIN prevents repeated scans.
- Keep catalog Import/Image counters separate from batch Sequence. Preview and
  preset/template storage never consume or freeze global starts. Add, direct and
  folder-sync imports number only successful new originals within their insertion
  transaction; virtual copies inherit provenance without advancing counters. Copy
  reserves its entire checked range after all target preflight and before writes,
  together with the copying phase. Recheck the reviewed counter revision there;
  a race returns to ready with refreshed names and requires explicit application.
  Retain reserved ranges across cancellation, crashes and SQL rollback. Never
  guess historical provenance during migration or reset counters automatically.
- Capture Copy date-folder layouts with the plan and saved configurations. Preserve
  missing-field defaults for older presets and migrations, use original camera
  civil date fields, and never reinterpret published journal paths. Unsupported
  localized formats stay explicit gaps; no mtime or host-timezone fallback.
- Second copies preserve original names, bytes and recognized XMP independently
  of primary naming and presets. Pin both destinations, validate collisions across
  all transfers before writes, and verify both roles before cataloging main copies.
  Inspect destinations outside SQL locks and recheck the captured plan revision.
  Keep backup progress compact, never catalog backup paths, and never redirect or
  skip a required backup during recovery. Cancellation retains published files in
  both locations; restored catalogs cannot clean the original operation's scratch.
- Import-time presets are captured values. Validate preset and plan revisions
  when choosing them; do not reinterpret a saved choice after library edits or
  deletion. Stage LUT assets outside catalog locks, verify before applying and
  rebind them during restore. Freeze keyword hierarchy segments without creating
  vocabulary during selection; a new XMP leaf must not retarget a captured root.
  Apply file metadata first, then selected preset fields and additive keywords
  within the same rollback boundary. Keep large patches off review/list replies.
- Persist last-import membership in the same transaction as newly imported
  sources. Empty imports and failed atomic imports retain the preceding batch;
  legacy incremental import must retain only its committed subsets. Never infer
  missing historical batches on migration or let polling steal native navigation.
- Add JSON Schema inputs before wiring native controls. Reject unsupported keys,
  invalid ranges and overlarge arrays at the service boundary. Keep existing
  commands compatible; use explicit revisions for editable persisted objects.
- Adding recipe fields must preserve old defaults and units. Normalize stored
  JSON before group-based copying, and check full-recipe patches, all-field
  presets and all-group sync against API collection limits. Keep display-unit
  conversion in the native shell and processing equations in the portable core.
  Numerical tolerance changes require a documented error model and independent
  real-image checks; a synthetic threshold alone does not establish color parity.
- Keep descriptive library metadata separate from decoder-derived EXIF and pixel
  recipes. Metadata edits must not invalidate pixel caches or adopt edit revisions.
- Metadata presets preserve unchecked fields and append keyword assignments.
  Explicit empty scalar/list values clear only checked fields; empty preset
  keywords never remove existing tags. Validate merged IPTC byte limits per target
  before writing. Legacy rating commands have independent state, so presets that
  set ratings must capture and check previous ratings as well as metadata revisions.
  Keep form drafts and loaded Painter revisions immutable across external refresh;
  only an acknowledged own mutation may advance that same loaded token.
- Virtual copies share a stable source-family ID, never a fabricated file path.
  Keep edits/metadata/history independent; share snapshots, indexing and relinking.
  Deleting a virtual copy must preserve original files and frozen export jobs.
- Store collection membership relationally. Compile supported filters to bound
  SQL parameters; whitelist sort columns. Smart collections evaluate stored rules
  at query time. Count and page queries must use identical predicates.
- Collection labels belong to collection nodes, not their photos or descendants.
  Validate every captured target before a batch label transaction, including
  no-op targets; preserve ancestor conflicts and original Quick/target semantics.
  Poll a separate tree revision and refresh only loaded pages after changes.
  Color filtering is a bounded flat query across the hierarchy; keep unfiltered
  expansion and page state independent. Never rebase an open label selection or
  editor silently when another client changes a collection.
- Persist identities that cannot be reused by a later object. Migration must
  preserve live references and roll back failures; a stale native editor must
  never modify a newly created collection with an old identifier.
- Keep capture-time provenance and fractional precision. Unknown metadata is not
  file modification time. Read bounded headers separately from hashing/pixels;
  source-wide replacements require a preview bound to the data being replaced.
- Folder-sync duplicate review uses the same original-name/size/precise-clock
  identity as reviewed import. Keep legacy active plans on their captured rules,
  preserve checked selections when inclusion is toggled, and use one eligibility
  predicate for imports, numbering and Previous Import. Recheck catalog conflicts
  inside the final transaction before writes; do not silently reclassify a ready
  review or overwrite another photo's state.
- Avoid a per-photo apply pass over unchanged synchronization rows. Keep complete
  preflight validation and bounded change pages, retain stat refresh for deselected
  existing items, and handle indexing's missing-only changes without relying on a
  source revision bump. The optimization must preserve virtual-copy family state.
- Add indexes for common query paths. Use a deterministic ID tie-breaker for
  pagination and never decode image pixels merely to search the library.
  Bound serialized response bytes as well as row counts: a 60-row page containing
  full nested metadata can still exceed the broker's 1 MiB frame. Keep summaries
  compact and provide explicit paged detail access instead of silent truncation.
- Test migration with existing photos, edits and jobs. Backups include all new
  catalog state; export jobs keep their original recipe and destination snapshots.
  Construct legacy fixtures with the actual earlier migration chain; changing only
  `user_version` on a newer schema does not prove upgrade compatibility.
- Keep catalog orientation independent of Develop recipes/history. Rotate/flip
  composes in displayed coordinates after Develop rendering, preserving attached
  crops/masks and exact tile/ROI behavior. Freeze orientation with each export job;
  never retrofit current orientation into old jobs. Map native crop/mask controls
  through explicit preview geometry, and reject stale drawing/mutation state.
  Batch orientation undo validates all targets and preserves later Develop edits.
- Freeze descriptive metadata and resolved keyword export policies in the same
  transaction as recipes/options and idempotency receipts. Old jobs must not
  acquire present-day metadata during migration or retry. Queue pages return small
  metadata receipts, not full XMP snapshots. Validate XML/packet bounds before
  queuing; encode metadata independently of pixels. Never embed internal recipes,
  local paths or source filenames as image descriptions. ICC remains required
  even when the chosen descriptive-metadata policy is None.
- Keep Library sources separate from metadata filters. Folder counts describe
  catalog membership independently of the filtered/stacked photo page. Imports,
  variants, removal and relinking must maintain these counts transactionally.
- Whole-folder reconnection stages a durable, bounded plan before changing paths.
  Hash/stat I/O must release the catalog lock; cancellation remains available.
  Revalidate source revisions, destination identity and file fingerprints before
  one atomic remap. Deferring for image/export work retains the plan for explicit
  retry; uncertain replies are read back rather than replayed. Preserve recipes,
  metadata, whole stacks and frozen export options across the complete family.
- Folder synchronization stages directory identities, file/sidecar fingerprints,
  source-family revisions and explicit selections before importing or removing
  catalog entries. Missing originals are never inferred from read/permission
  errors. Removal defaults off and includes the complete source family; preserve
  frozen jobs and never delete originals. XMP reads are bounded and preserve
  absent properties, independent copy metadata and Develop recipes. Reject
  malformed/unrepresentable supported values instead of silently truncating them.
  Recheck files outside the catalog lock, then apply catalog changes atomically.
  Measure final transaction contention as well as scan-page latency.
- Keyword assignments reference stable tag IDs. Names are unique only within one
  parent; never merge equal leaf names from different branches. Preserve qualified
  paths and invalidate affected photo metadata revisions on ancestor rename/move.
  Batch tag addition/removal preserves unrelated assignments; replacing a string
  list must reject ambiguous leaf names instead of picking an arbitrary branch.
  Full-photo reads always retain complete assignment IDs. A deferred path array is
  not an empty assignment set; use revision-bound pages for full labels and ID
  replacement for editing. Validate newly typed paths and all existing IDs within
  the same transaction as the other metadata fields. Native keyword pickers hold
  local drafts until the parent form saves, preserving unchecked fields and stale
  revision failures. Metadata receipts must not adopt a newer recipe revision.
  Vocabulary rows also have a byte budget. Explicitly deferred path/synonym fields
  are unknown values, never empty edit defaults. Read complete keyword details at
  the captured list revision before editing or choosing a parent; discard replies
  for superseded forms and dismissed pickers. Use the authoritative parent path
  instead of splitting display strings that may contain legacy literal separators.
  Dictionary imports validate a stable file snapshot in disk-backed staging before
  one additive transaction. Preserve existing tag identities, synonyms and policies;
  file imports do not rename/delete tags or change photo metadata revisions. Parse
  input and publish output outside the catalog lock. Stream hierarchy export into
  a snapshot, preserve UTF-8, report options omitted by text, and never publish a
  partial file or overwrite an existing destination. Reject unrepresentable names
  instead of silently changing them. Person classification is manual metadata.
- Keyword presets store nine text slots; recent entries store stable catalog IDs.
  Saving a preset never creates vocabulary. Applying a slot validates preset scope,
  captured revision, all photo revisions and capacity in one catalog transaction.
  Global preset storage must be injectable; tests must not write user preferences.
  Acquire shared preset storage before the catalog lock consistently. Switching
  global/catalog storage never moves existing sets. Keep temporary native edits
  separate from persisted presets and preserve their captured revision after an
  external refresh; never silently rebase stale drafts onto newer settings.
  Multi-set choosers read revision-bound previews without changing the active
  preset. Keep recent identities separate from custom slot text. Accumulate only
  bounded local choices, freeze selected text, and invalidate reads on dismissal.
  Confirmation replaces the shortcut once; browsing/cancel must not create tags.
- Library Painter gestures capture the initial shortcut/configuration, visible
  photo metadata revisions and source/page. Deduplicate thumbnail hits, include
  intermediate thumbnails crossed by coalesced pointer events, and commit once
  at mouse-up. Publish highlight changes only when a new photo is touched, not on
  every pointer event. Validate every target and assignment capacity before any write.
  Painter never selects touched thumbnails. Metadata/collection modes preserve
  Develop recipes; Develop preset strokes capture preset and visual revisions,
  apply only selected settings atomically and retain per-photo history. Membership
  removal may naturally remove selected photos from the displayed source. Capture
  both target-state and collection revisions for Target Collection strokes; never
  redirect a pending stroke after a target switch. Membership existence checks
  read bounded IDs, not full photo metadata or resolved keyword hierarchies.
  Cancel pending strokes on
  Escape, source/page changes and pointer-layout invalidation. Do not publish
  SwiftUI state during representable updates; defer cancellation with a captured
  stroke identity so an old callback cannot clear a new gesture. Shortcut IDs
  remain complete while labels page at twenty; never split old literal labels.
- Develop presets persist only explicitly selected recipe fields. Saving or
  browsing never edits a photo. Capture both library scope/revision and source or
  target visual revisions; revalidate after asset I/O before any mutation. Shared
  storage always locks before the catalog. Stage checksum-verified, immutable LUT
  assets outside SQL locks; retain them across source-catalog removal and rebind
  catalog-local assets on restore. Never equate application-level recipe fields
  with Adobe preset parameters. Batch application preserves unchecked fields,
  metadata, orientation and frozen jobs, with per-photo history and no-op reapply.
  Native editors and loaded Painter presets retain their original revisions after
  refresh; name conflicts require an explicit duplicate/replacement policy.

- Export presets are configuration values, never photo selections, recipes,
  request keys or queue references. Normalize through the same `ExportOptions`
  validator used by submission. Keep name-only pages bounded and reject duplicate
  normalized names instead of silently replacing a record. Save destination paths
  only through an explicit choice; preserve literal absolute paths without file
  checks or directory creation. Loading a preset without a folder clears the old
  draft folder. Capture form/library revisions, reject late reads and stale writes,
  and never rebase forms or retry uncertain mutations. Shared storage precedes the
  catalog lock; storage switches neither copy records nor alter loaded values.
  Existing numeric output sharpening is not Adobe's screen/matte/glossy behavior.

- Previous export settings record an accepted manual submission, never the newest
  job inferred from queue history. Persist them atomically with jobs and the request
  receipt. Reuse freezes current photo recipes/metadata and never advances Previous.
  Check request replay before revision validation; preserve legacy ordinary-export
  digests and distinguish commands. In native state, compare effective copied
  preset values and capture selection before awaiting pending edits. Unchanged
  availability polls must not republish the workspace. Fail stale or uncertain
  submissions visibly without automatic retry.

- Multi-preset export validates all selected presets, photos, destinations and
  naming components before filesystem writes, then freezes one atomic queue batch.
  Bound the photo/preset product as well as both input lists. Preserve the
  shared-store-before-catalog lock order and receipt-before-revision replay rule.
  Parent-folder mode explicitly replaces stored destinations; do not mix it with
  per-preset destination overrides. Preset context and output settings become
  immutable at submission, and batch export does not replace Previous. Batch
  cancellation/retry must stay within indexed membership; pause/resume is global.
  Keep collision publication atomic and preserve existing files. A failed batch
  may leave created empty directories, never partial jobs or receipts.
  Reuse descriptive metadata only inside that batch's catalog write transaction,
  with bounded retained bytes/entries and policy-aware keys. Never retain a cache
  across commands or use metadata revision alone as a complete change token.
  Preserve serialized snapshot/receipt bytes and preset-first job ordering.

## Engine changes and handoff

`runtime.ENGINE_GENERATION` orders portable-engine releases. Increment it when
shipping changed domain/processing behavior; source and dependency digests also
distinguish builds within a generation. Same-generation switches are explicit;
older generations cannot take over a newer pinned catalog. Mac-only view edits do
not require an engine generation change. The build embeds the digest without
machine paths. Do not change engine sources while building its manifest/bundle.

`CATALOG_VERSION` must equal the latest schema migration. Reject newer catalogs
before writes. Transport admission and a lifetime owner lock protect the catalog;
never bypass them to replace a running service. An idle, sealed handoff stores an
exact-target, one-use receipt before stopping queue acquisition. Only this receipt
can preserve pending jobs. Crashes, wrong targets and running jobs keep explicit
recovery. A worker checks its broker's identity before opening images or outputs;
a replaced engine interrupts that job and pauses the remaining queue.

Test legacy rejection, idle switch, active command/export protection, lost handoff
replies, uncertain mutation replies, ownership, queue snapshots and native retry.
Keep legacy services running until their work finishes; do not terminate an unknown
process merely to make a newer client connect.

## Mac presentation

Use native navigation, menus, focus, file panels and accessibility. Capture the
target photo/selection before asynchronous work; reject stale replies after a
selection or request-generation change. Flush edits before changing contexts.
Show empty filtered results differently from an empty catalog. Offer keyboard
equivalents without consuming text-field input. Long operations run off the main
actor; the UI holds only a bounded page and file-backed images.
Distinguish explicit user-control setters from programmatic navigation restores:
changing a sort or source preference during photo location must not trigger a
second UI callback that resets its computed page offset.

Interactive drafts must not fill history with pointer events. Capture identity
and revision at gesture start, coalesce temporary image requests with bounded
in-flight work, and save one partial mutation on release. Cancellation restores
the saved preview; another photo or a newer revision invalidates the gesture.
Temporary preview contracts must restrict accepted fields and preserve frozen
export jobs. Plot geometry may mirror the engine; pixel processing stays portable.

## Replaceable platform architecture

The first migration choice is **retain the Python domain/service and replace the
platform shell**. SwiftUI/AppKit remains the shipping Mac UI; a future Windows
shell talks to the same JSON contract. Do not introduce a cross-platform UI
runtime until a concrete workflow demonstrates a net benefit.

| Boundary | Mac implementation | Replacement candidate | Required acceptance |
| --- | --- | --- | --- |
| Presentation | SwiftUI/AppKit | WinUI or another native desktop shell | Same command fixtures, keyboard and accessibility workflows |
| IPC/process | Unix socket + Process | Named pipes + platform launcher | Isolation, bounded framing, cancellation, crash recovery |
| Compute | CPU NumPy/SciPy + optional Metal C ABI | CPU first; Vulkan/DirectML adapter only if measured | CPU numerical tolerances, strip seams, actual dispatch and memory receipts |
| Decode | LibRaw/rawpy | Same LibRaw ABI or independently validated decoder | Camera fixtures, white balance, orientation and precision |
| Color | Portable matrices + ICC assets | OS display adapter with same tagged output | Profile correctness and calibrated display tests |
| Files/publication | pathlib + atomic non-overwriting publication | Platform filesystem adapter | Unicode/long paths, offline volumes, no overwritten originals/exports |
| Shared presets | Portable SQLite + App Support path adapter | Same repository with LOCALAPPDATA/XDG path adapter | Cross-catalog revisions, scope isolation, catalog backup, injected test roots |

If profiling justifies moving a hot algorithm to C++ or Rust, extract only that
algorithm behind a narrow buffer/recipe contract, retain the CPU reference and
reuse golden fixtures. Do not rewrite catalog/business logic to obtain GPU speed.
Windows adapter code remains unverified until run on Windows. iOS is not part of
the current deliverable; its navigation policy is recorded in `AGENTS.md`.

## Verification and performance

Copy import filesystem writes belong only to the replaceable copy adapter. Stage
all selected targets before publishing any file. Keep exclusive creation and
publication, source/target identity checks, bounded streaming, checksums and
durable ownership receipts. Never overwrite or delete an existing destination to
make recovery pass. Cancellation retains published files and removes only owned
scratch links; report uncertain scratch ownership. A restored catalog cannot
continue another catalog's transfer. The final catalog transaction must use
destination paths consistently for metadata, presets, folders and Previous Import.

Run targeted regression tests first, then the relevant existing suite and Mac
compile. Use disposable catalogs and generated images by default. Real RAW and
Lightroom references must be explicit read-only inputs. Preserve test failures
and unavailable environments in the work log; never convert skips into passes.
Freeze native sources while compiling, including the per-suite compiles in
`run_native.py`. If a fix changes an input during compilation, retain the failed
receipt and rerun against stable sources; mixed-source runs are not final evidence.

Benchmark visible latency and whole operations: cold/warm import, first grid,
filter/sort page, first/warm preview, slider-to-preview, 1:1 viewport, full-size
JPEG/TIFF and batch throughput. Record sample count, median/p95, image dimensions,
hardware/OS, backend dispatch, caches and RSS. Compare like-for-like inputs and
include startup/encoding. Treat timing thresholds as measured budgets, not flaky
unit-test assertions. Keep numerical/contract assertions separate from benchmarks.

Before publication run `scripts/check_public.py`, build a source archive and
check the extracted clean source with `--strict`. Never expand the allowlist to
include private receipts or photos just to make a gate pass.

Develop history uses one transactional writer for direct edits, presets and sync.
Never restore the old destructive pop or fifty-step truncation. Normalize recipes
before no-op comparison; preserve redo on no-ops, discard only the future branch
on a changed edit, and never reuse step identities. Page summaries without recipe
payloads or whole-history counts. Capture the displayed photo revision for list,
selection, rename and clear, including dialogs opened before an external edit.
Virtual-copy creation must reset history fields instead of inheriting a parent's
cursor. Keep baseline assets in backup/restore and test real legacy migrations.
