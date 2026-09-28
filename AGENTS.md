# LumaRAW engineering instructions

## Product and priorities

Build a native Mac photography application with Adobe Lightroom Classic for Mac
as the functional reference. Exclude AI features. Prioritize complete photographic
workflows, originals safety, color correctness, responsiveness, and processing
throughput before cosmetic matching. Track the full scope in `PARITY.md`; do not
call a subset or a similar-looking control a completed 1:1 reproduction.

macOS 14 is the current minimum. Test macOS 14 and the current macOS separately;
record unavailable systems. Windows is a future port, not a supported product.
Keep SwiftUI/AppKit as the Mac shell and replaceable adapters around the portable
engine. Follow `ARCHITECTURE.md` and `DEVELOPMENT.md` instead of rewriting the UI
or processing stack speculatively.

## Read intent before implementation

Read each file's opening comment before analyzing or changing it. It is a mini
README: purpose, responsibilities, data/event inputs, outputs and side effects,
constraints, non-goals, and deliberate design decisions. Honor those boundaries.
When absent, state assumptions and add a concise structured opening comment when
editing the file. Update stale comments with the implementation. Framework
mechanics do not replace the documented intent.

## Working tree and source boundaries

Inspect status, local/remote branches and worktrees before work. Fetch before
claiming all branches are integrated. Preserve user changes and branch history;
do not discard branches or force push. Use `codex/` branches for development.
Merge requested branches before implementation, resolve conflicts deliberately,
and verify the combined result. Record when no unmerged branches exist.

Project-owned source, UI, documentation and error text use English. Preserve
Unicode filenames and user content. Never commit catalogs, photographs, exports,
credentials, local paths, generated binaries or private verification receipts.
Keep the explicit publication allowlist current when adding public documentation.

## Invariants

- Originals are read-only. Metadata and recipes belong to the catalog. Import
  copying, sidecars and filesystem changes require explicit product workflows.
- Native views do not own SQL, pixel algorithms or business validation. App, CLI
  and MCP use the same versioned command/service contracts.
- Revision conflicts fail visibly. Never retry a stale mutation by overwriting a
  newer revision. Validate all targets before transactional batch mutations.
- Freeze export recipes/options/metadata at submission. Preserve collision-safe output,
  idempotent requests, cancellation and explicit crash-recovery decisions.
- Use bounded queries, pages, worker concurrency, caches and memory. Never load
  a whole catalog to filter or sort it. Keep CPU reference/fallback behavior and
  report actual Metal dispatch, not just library availability.
- Negotiate engine identity before broker commands. Never retire a broker with
  active commands or image work, and never retry an uncertain mutation response.
  Increment `runtime.ENGINE_GENERATION` for a new engine release; build digests
  distinguish development builds. Keep `CATALOG_VERSION` aligned with migrations.
- Keep schema migrations additive where possible, idempotent and tested against
  an old catalog. No silent data loss or silent precision reduction.

## Evidence and completion

For each vertical feature, implement catalog/domain + service contract + native
workflow + meaningful regression evidence. Run relevant Python and native checks;
build the Mac app for visible changes and inspect its rendered interaction.
Synthetic images establish algorithms, not camera accuracy or Lightroom pixel
equivalence. Record fixture, cold/warm cache, dimensions, backend, elapsed time
and peak memory for performance claims. See `TESTING.md`.

Keep a current `PARITY.md` entry with implementation, evidence and remaining gaps.
Report skipped checks and absent RAW fixtures, devices or OS runtimes explicitly.
Do not label compilation, offscreen snapshots, or old receipts as desktop testing.

For an explicitly budget-limited goal, check account usage at milestones and
before costly work. Honor the user's stop threshold without consuming reset
credits. Do not mark unfinished scope complete merely because work stops.

## Future iOS shells

If iOS is introduced, explicitly target the minimum supported OS, pre-iOS-26,
and iOS 26+. Preserve native navigation/back accessibility and interactive pop.
Centralize legacy appearances/tint/minimal back-item presentation before bars
are created; gate legacy overrides to preserve iOS 26 Liquid Glass. Verify pushed
views, sheets, scrolling states, back taps and edge swipes on both OS families,
including supported languages. Never use per-screen replacement navigation bars
to conceal a compatibility problem.
