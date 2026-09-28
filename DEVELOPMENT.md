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
- Add indexes for common query paths. Use a deterministic ID tie-breaker for
  pagination and never decode image pixels merely to search the library.
- Test migration with existing photos, edits and jobs. Backups include all new
  catalog state; export jobs keep their original recipe and destination snapshots.

## Mac presentation

Use native navigation, menus, focus, file panels and accessibility. Capture the
target photo/selection before asynchronous work; reject stale replies after a
selection or request-generation change. Flush edits before changing contexts.
Show empty filtered results differently from an empty catalog. Offer keyboard
equivalents without consuming text-field input. Long operations run off the main
actor; the UI holds only a bounded page and file-backed images.

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

Benchmark visible latency and whole operations: cold/warm import, first grid,
filter/sort page, first/warm preview, slider-to-preview, 1:1 viewport, full-size
JPEG/TIFF and batch throughput. Record sample count, median/p95, image dimensions,
hardware/OS, backend dispatch, caches and RSS. Compare like-for-like inputs and
include startup/encoding. Treat timing thresholds as measured budgets, not flaky
unit-test assertions. Keep numerical/contract assertions separate from benchmarks.

Before publication run `scripts/check_public.py`, build a source archive and
check the extracted clean source with `--strict`. Never expand the allowlist to
include private receipts or photos just to make a gate pass.
