# Development contract

## Delivery unit

Deliver a user-visible workflow with persistent state, explicit failures and
repeatable evidence. Start with Library and Develop, then export and secondary
modules. `PARITY.md` is the inventory, not a promise that every existing control
matches Adobe's proprietary processing. AI generation, semantic selection,
AI denoising, assisted culling and inferred depth are excluded.

Before changing a feature, read its opening comments, trace the native action
through `api.py` and `service.py` to catalog/renderer ownership, and identify the
observable acceptance condition. New code should be normally formatted with
named helpers and bounded responsibilities; do not extend dense one-line code
when a clear function is more maintainable. Avoid unrelated formatting churn.

## Contracts and persistence

- Add JSON Schema inputs before wiring native controls. Reject unsupported keys,
  invalid ranges and overlarge arrays at the service boundary. Keep existing
  commands compatible; use explicit revisions for editable persisted objects.
- Keep descriptive library metadata separate from decoder-derived EXIF and pixel
  recipes. Metadata edits must not invalidate pixel caches or adopt edit revisions.
- Virtual copies share a stable source-family ID, never a fabricated file path.
  Keep edits/metadata/history independent; share snapshots, indexing and relinking.
  Deleting a virtual copy must preserve original files and frozen export jobs.
- Store collection membership relationally. Compile supported filters to bound
  SQL parameters; whitelist sort columns. Smart collections evaluate stored rules
  at query time. Count and page queries must use identical predicates.
- Persist identities that cannot be reused by a later object. Migration must
  preserve live references and roll back failures; a stale native editor must
  never modify a newly created collection with an old identifier.
- Keep capture-time provenance and fractional precision. Unknown metadata is not
  file modification time. Read bounded headers separately from hashing/pixels;
  source-wide replacements require a preview bound to the data being replaced.
- Add indexes for common query paths. Use a deterministic ID tie-breaker for
  pagination and never decode image pixels merely to search the library.
  Bound serialized response bytes as well as row counts: a 60-row page containing
  full nested metadata can still exceed the broker's 1 MiB frame. Keep summaries
  compact and provide explicit paged detail access instead of silent truncation.
- Test migration with existing photos, edits and jobs. Backups include all new
  catalog state; export jobs keep their original recipe and destination snapshots.
  Construct legacy fixtures with the actual earlier migration chain; changing only
  `user_version` on a newer schema does not prove upgrade compatibility.
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

If profiling justifies moving a hot algorithm to C++ or Rust, extract only that
algorithm behind a narrow buffer/recipe contract, retain the CPU reference and
reuse golden fixtures. Do not rewrite catalog/business logic to obtain GPU speed.
Windows adapter code remains unverified until run on Windows. iOS is not part of
the current deliverable; its navigation policy is recorded in `AGENTS.md`.

## Verification and performance

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
