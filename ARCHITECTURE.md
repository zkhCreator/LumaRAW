# Architecture

LumaRAW separates native macOS interaction from RAW processing, storage, queues, and agent contracts. This preserves a path to a Windows shell without coupling the portable domain layer to SwiftUI or Metal.

The current product priority is Lightroom Classic for Mac functional workflows,
excluding AI. See [PARITY.md](PARITY.md) for gaps and [DEVELOPMENT.md](DEVELOPMENT.md)
for replacement boundaries, migration gates and performance evidence requirements.

## Layers

| Layer | Implementation | Responsibility and boundary |
| --- | --- | --- |
| Native presentation | `native/*.swift` | System navigation, menus, inspector, file panels, and accessibility labels; no SQL, pixel processing, or MCP logic |
| Command contracts | `lumaraw/api.py` | Shared JSON schemas for app, CLI, and MCP; `api_version=1` |
| Service | `lumaraw/service.py` | Validation, optimistic revisions, atomic batch edits, idempotent submission, and a shared queue |
| Catalog | `lumaraw/catalog.py` | SQLite WAL; photos, recipes, history, versions, and jobs; v1 recipes migrate to v2 |
| Scheduling | `Service.run_worker` / `queue_loop` | One image subprocess per catalog; JSON and file paths cross the process boundary |
| Image core | `imaging.py`, `render.py`, `color.py`, `calibration.py` | Portable decoding and image algorithms, independent of SwiftUI, AppKit, and Qt |
| Compute adapter | `lumaraw/accelerators`, `metal/Bridge.mm` | CPU reference with an optional macOS Metal C ABI |
| Transport | `bridge.py`, `mcp.py` | Local IPC and newline JSON-RPC over stdio; no HTTP listener |

The Swift `Backend` launches an explicit executable through `Process`, without a shell. Short CLI calls connect to a single persistent broker for the selected catalog. App exit does not cancel submitted exports. An idle broker with no unfinished jobs exits after about three minutes; a paused unfinished queue keeps it alive.

On macOS/Linux, IPC uses a Unix socket in a user-only temporary directory (0700). Bounded JSON crosses `send_bytes`/`recv_bytes`; no pickle deserialization is used. A startup lock prevents competing brokers. Windows has AF_PIPE and msvcrt locking branches, but these have not been validated on Windows.

## Broker compatibility

`runtime.py` identifies an engine by broker protocol, ordered generation, source/
dependency digest and supported catalog version. Source runs hash the engine and
Metal sources plus dependency declarations; packaged builds read an embedded
manifest. Each process retains its identity for its lifetime. Every command uses a
read-only transport handshake before mutation, and the broker checks the admitted
identity again. A second broker must acquire a nonblocking lifetime owner lock
before migration or endpoint replacement. Startup and lifetime locks are separate.

Newer generations automatically request an idle handoff. Different builds within
one generation require `service_connection(action: activate)` / the Mac Settings
connection action. A newer generation or schema cannot be downgraded. Active
commands (including response delivery), reserved exports and image workers defer
handoff without cancellation. Once idle, admission closes, queue acquisition stops,
and a durable target reservation and exact-target clean receipt are written. The
next matching broker consumes the receipt once, preserving pending jobs and the
queue's pause setting. Other restarts keep ordinary interrupted-job recovery.
Lost handoff replies cannot strand the retiring service. Uncertain domain-command
responses are never automatically resubmitted.

Legacy brokers without negotiation are detected before the requested domain
command is sent. Their work is left running; the error explains finishing exports,
closing older app/agent clients, and reconnecting after the idle exit. Legacy
clients also cannot mutate a newly negotiated broker. Windows branches retain
named pipes/locking but still need Windows runtime acceptance.

Image workers verify the broker's expected build before opening pixels or outputs.
If files were replaced in place, the affected export becomes interrupted and the
queue pauses, preserving remaining pending jobs for explicit reconnection/retry.
This check detects changed builds, not malicious modifications that also falsify
the manifest; binaries remain subject to release signing/notarization controls.

## Consistency and recovery

- `get_photo` returns a revision. Edits, undo, version restore, recipe import, and sync require the expected revision. Stale writes fail; the caller must read again and reconcile.
- Service database access is serialized. Sync validates every target before one transaction writes all changes. Ratings and flags are separate explicit operations.
- Export submission freezes the recipe, source, destination, and output options. The request key, normalized argument digest, and job IDs are stored atomically. The same key and arguments return the original result; different arguments with that key fail.
- Originals are never written. Output is written to a temporary `.part`, flushed, then hard-linked to a new collision-safe name. A late cancellation preserves an output already published.
- Running and pending jobs become interrupted after abnormal service restart. A sealed idle handoff has the narrowly scoped pending-job exception described above. They are never silently replayed. A forced exit can leave an uncertain publication outcome; inspect the destination before retrying.
- Image workers monitor the broker and exit when it disappears. This is not an operating-system transaction over the entire process tree.
- The UI polls jobs and selected-photo revisions every two seconds. A local editing barrier protects pending edits; the service revision check remains authoritative.

The native store clears photo-specific state when selection changes and intersects selected IDs with the visible page. Recipe mutations hold the editing barrier until a reply arrives. Rating replies update only rating/flag, preserving the revision used for recipe conflict detection. Asset imports verify their captured photo target before applying.

## Memory and performance

Library pages contain at most 60 summaries; full recipes are fetched on demand. Preview and export share strip processing, with overlap for neighborhood filters. Full-resolution viewports are limited to 2048 × 1536. LibRaw still decodes a complete RAW frame; linear pixel caches live on disk.

Library organization lives in `organization.py`: catalog-only descriptive fields,
normalized keyword relations and descriptive revisions. `collections.py` owns
regular/Quick membership, live smart predicates, parent links and durable target
state. Schema version 2 added these without changing existing photo/collection IDs.
Ancestor revisions cover descendant changes, protecting subtree deletion/copy.
Quick save/clear is one transaction; target membership checks both state and
collection revisions. Set views combine relational descendants and live smart
predicates. Children page at 60; collapsed branches release native cached pages.
Nesting is limited to 32 levels, aggregate views to 128 smart descendants, and
subtree duplication to 1,000 collection nodes. These resource bounds are explicit.
Metadata
and collections have independent revisions. Grid filtering/counting/sorting runs in
SQLite with a deterministic ID tie-breaker; summaries never select recipe or EXIF
JSON. Collections also paginate at 60 and do not eagerly count every smart collection.

`virtual_copies.py` owns schema version 3 and catalog variants. A source-family ID
is independent of photo identity; one partial unique index permits exactly one
master for a path and another permits at most one master per family. Creation and
promotion maintain that invariant transactionally. The migration rebuilds the
photos table to remove path uniqueness for copies, preserves existing columns,
indexes, triggers and IDs, and makes photo IDs non-reusable. It rolls back on
unsupported schemas rather than guessing at constraints. A source import trigger
allocates the family once; repeated import still deduplicates the master path.

Each variant owns its recipe, undo history, descriptive metadata and collections.
Named snapshots are keyed to the family and retain their creator ID as provenance.
Creation checks recipe/metadata revisions; promotion/removal also check a separate
family revision. Removal is catalog-only and preserves shared snapshots and export
jobs. Jobs capture the family ID so explicit missing-source relinking can update
eligible jobs even after their originating virtual copy is gone. Relinking and
hash/EXIF indexing affect the whole family; indexing reads each physical original
once. Duplicate detection counts distinct families, not copies of the same source.
Native batch target capture is one bounded summary request. Identical recipes
share source-keyed caches; different variants still carry distinct photo/revision
identities in asynchronous native requests. This schema upgrade is not a supported
downgrade path to older application builds.

`stacks.py` owns schema version 4. Stack membership is unique per photo and source:
one folder stack, plus an independent stack in each regular/Quick collection.
Folder groups validate exact parent directories. Smart/set sources are flat.
Summaries project stack count/cover/visibility with SQL joins, anchor group sorting
to the cover and keep internal order independent of ascending/descending sorting.
Filtering applies to visible members; `stacked: false` returns a flat query. Pages
remain capped at 60 even when a stack spans pages. Queries sort narrow IDs/keys
before reading the page's summaries and family fields. Unfiltered All Photos
counts use maintained stack sizes; empty stack sources retain the indexed flat
query path. No pixel worker or recipe JSON participates.

A catalog-wide stack revision is intentionally conservative: every stack mutation
requires the captured revision and rejects concurrent changes atomically. Collection
stack edits also advance collection/ancestor revisions. Cleanup triggers remove
membership on photo/collection removal, promote the first remaining member and
dissolve singleton stacks. Cross-folder relinking detaches folder membership;
collection organization remains intact. Collection duplication and Quick saving
copy scoped stacks inside their enclosing transaction. New virtual copies join
the origin's expanded folder stack; migration leaves existing variants unchanged.
Native stack metadata is separate from recipe revisions, and lightweight polling
refreshes structural changes, including previously empty pages.

`source_identity.py` provides stat-based cache identities without importing pixel
libraries. The broker returns a page of completed thumbnail paths in one command;
misses still use bounded image workers. Workers publish JPEG cache entries atomically.
Warm cache lookup does not claim image processing ran. Source thumbnail requests
remain the default API behavior; the Mac app requests `kind: developed`. These
320-pixel thumbnails use the shared geometry/color renderer and ICC output. Cache
identity covers source stat, full recipe, pipeline version and LUT stat; metadata
revisions do not invalidate pixels. Undo can reuse an earlier recipe image.
Native page requests retain matching images, reject mismatched or late revisions,
and cancel obsolete thumbnail generations through their own client ID. All visible
photo summaries are polled; active inspector recipes keep their separate edit
barrier. Refresh rechecks source state, and per-photo errors remain visible.
Offline-source cache lookup is not yet supported.

Library Compare retains at most two revision-keyed frames and Survey at most 60
512-pixel fitted frames. Compare detail requests use physical display scale and
the existing 2048 × 1536 viewport bound. Review previews omit unused before-image
work; the default Develop contract still returns it. Review has a separate client
generation, drops stale replies and cancels its own workers on exit. Lightweight
summary polling detects external edit revisions without loading all recipes.

Each image worker exits after one operation, releasing native allocations. The parent samples RSS every 50 ms and stops work above the effective budget or after five minutes. The effective budget is the lower of the configured limit and 70% of available memory; this is not a system hard limit. When available memory falls below 384 MB, the queue pauses job acquisition. Independent catalogs can start separate brokers, so budgets are not a global quota.

Superseded UI previews are skipped or cancelled by client generation. Cancelling a UI preview does not cancel an unrelated agent preview or export. Large imports and indexing still hold the catalog service lock and may delay other commands; persistent metadata jobs remain future work.

Status and settings expose `budget_mb`, `available_mb`, `effective_budget_mb`, and `limited_by_available_memory`. Failed workers retain observed RSS peaks. Metal reports bounded shared buffers and actual dispatch/fallback information; see [METAL.md](METAL.md).

## Color

The working space is linear LibRaw ProPhoto D65, not ICC ProPhoto D50. Output conversion uses the exact working-space matrix and the matching fixed ICC asset. ICC regression tests verify conversion after removing the Qt runtime dependency. The native preview uses an sRGB-tagged NSImage; soft proofing simulates an explicit ICC profile.

This does not establish monitor calibration, Nikon Picture Control equivalence, or per-camera color accuracy. Camera profiles are bound to a specific model. A synthetic chart fit is algorithm evidence, not independent camera acceptance.

## Language and contracts

First-party text uses English. Sync group and preset names are English in `recipe_schema`; UI, CLI, MCP schemas, and skill documentation agree. Clients of earlier local builds must refresh these names. Recipe field keys and stored user text are unchanged. Unicode filenames and user-defined names remain supported.

## Windows migration

1. Validate dependency wheels, AF_PIPE access control, msvcrt locks, Unicode/long paths, atomic hard links, and crash recovery on Windows. Where hard links are unavailable, introduce an explicit non-overwriting publication adapter.
2. Reuse the Python service, recipes, SQLite schema, MCP, and pixel tests. Build a Windows-native shell against the same JSON contract; SwiftUI is not the cross-platform UI layer.
3. Validate real IPC, display ICC behavior, Narrator, installation, upgrade, uninstall, and signing separately.
4. Compare the same RAW/recipe/output fixtures across platforms. Existing adapter code is not a compatibility claim.

## Design references

The native shell uses standard navigation sidebars, a hideable inspector, command menus, system typography, and file panels following Apple's [macOS design guidance](https://developer.apple.com/design/human-interface-guidelines/designing-for-macos). Implementation choices do not replace desktop and accessibility testing.

MCP negotiates the [2025-11-25 stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) and [tool contract](https://modelcontextprotocol.io/specification/2025-11-25/server/tools), with the earlier handshake versions listed in the implementation. HTTP, remote authentication, task extensions, resource subscriptions, cancellation notifications, and later protocol versions are not claimed.
