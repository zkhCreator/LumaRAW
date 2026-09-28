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
- Export submission freezes the recipe, source, destination, output options and resolved descriptive metadata. The request key, normalized argument digest, and job IDs are stored atomically. The same key and arguments return the original result; different arguments with that key fail.
- Originals are never written. Output is written to a temporary `.part`, flushed, then hard-linked to a new collision-safe name. A late cancellation preserves an output already published.
- Running and pending jobs become interrupted after abnormal service restart. A sealed idle handoff has the narrowly scoped pending-job exception described above. They are never silently replayed. A forced exit can leave an uncertain publication outcome; inspect the destination before retrying.
- Image workers monitor the broker and exit when it disappears. This is not an operating-system transaction over the entire process tree.
- The UI polls jobs and selected-photo revisions every two seconds. A local editing barrier protects pending edits; the service revision check remains authoritative.

The native store clears photo-specific state when selection changes and intersects selected IDs with the visible page. Recipe mutations hold the editing barrier until a reply arrives. Rating replies update only rating/flag, preserving the revision used for recipe conflict detection. Asset imports verify their captured photo target before applying.

## Memory and performance

Library pages contain at most 60 summaries; full recipes are fetched on demand. Preview and export share strip processing, with overlap for neighborhood filters. Full-resolution viewports are limited to 2048 × 1536. LibRaw still decodes a complete RAW frame; linear pixel caches live on disk.

Library organization lives in `organization.py`: catalog-only descriptive fields,
keyword-aware predicates and descriptive revisions. `keywords.py` owns tag identity,
hierarchy and assignments. `collections.py` owns
regular/Quick membership, live smart predicates, parent links and durable target
state. Schema version 2 added these without changing existing photo/collection IDs.
Ancestor revisions cover descendant changes, protecting subtree deletion/copy.
Quick save/clear is one transaction; target membership checks both state and
collection revisions. Set views combine relational descendants and live smart
predicates. Children page at 60; collapsed branches release native cached pages.
Nesting is limited to 32 levels, aggregate views to 128 smart descendants, and
subtree duplication to 1,000 collection nodes. These resource bounds are explicit.
Schema version 5 rebuilds the collection table with AUTOINCREMENT, preserving live
IDs, custom columns, indexes and triggers in one transaction. IDs deleted after
this upgrade are never reused, including after restart; historical IDs deleted
before the upgrade cannot be reconstructed. Stale editors therefore cannot retarget
a replacement collection. Unsupported schemas fail without committing the rebuild.
Metadata and collections have independent revisions. Grid filtering/counting/sorting runs in
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

`capture_time.py` owns schema version 6 and bounded EXIF header reads. It stores
integer microseconds plus an exact decimal residual, including pre-epoch dates.
Explicit offsets normalize to UTC; absent offsets retain a marked camera wall
clock independent of the host timezone. The previous integer `taken` field is
preserved on migration; precise clocks remain unknown until refresh. Import and
indexing populate the new fields. TIFF IFD0/Exif IFD, JPEG APP1 and PNG eXIf are
supported, capped at 1 MiB of reads and 4,096 entries/segments. BigTIFF and other
containers are not inferred from file timestamps. No image decoding is involved.

`auto_stacks.py` streams an explicit folder's immediate photos or a regular/Quick
collection in precise capture order. A strictly shorter adjacent gap joins a
group; zero leaves every photo unstacked. Preview returns counts and at most 20
examples. Its fingerprint includes source, duration, clocks/membership and the
global stack revision. Apply rechecks this in a write transaction before replacing
source stacks; failures roll back, with no automatic retry. Groups are streamed
and their sizes updated once to avoid repeatedly recounting large stacks. Recipes
and originals are untouched. Mixed UTC/camera clocks are identified in the preview;
exact Adobe mixed-timezone behavior remains unverified.

Capture refresh reads at most 60 physical source families per command and updates
their shared clock fields, without hashing or image workers. Native progress can
stop between pages. It captures source/duration, drops late previews and disables
confirmation when the displayed plan no longer matches the current query.

`folders.py` owns schema version 7. A relational folder/photo index is maintained
by insert/delete/relink triggers, including virtual copies. Direct and descendant
counts are updated along the ancestor chain; reads do not recount every photo.
The migration backfills with a streaming SQL insert and rolls back on failure.
Path-parent/name functions are registered on each catalog connection. Direct
external SQLite writers must honor this schema contract; application writes use
the service. Folder IDs are non-reused, while labels/favorites have their own
optimistic revisions. Counts and presentation changes advance a separate global
folder revision, so native polling sees external imports even on an empty page.

Imported directories become visible roots unless an existing root contains them.
Importing into a parent coalesces descendant roots. Show/hide-parent commands only
alter catalog presentation and check the global revision; hiding a parent with
direct photos is rejected. Empty former locations remain represented. Tree pages
and flat name/favorite/color searches return at most 60 folders; hidden ancestors
do not leak into searches. A bounded page checks directory availability, without
recursively scanning disk. Ancestor navigation is limited to 256 levels.

`list_photos` accepts a folder source independently of metadata filters, mutually
exclusive with a collection source. Descendant inclusion defaults to true. An
unfiltered folder count uses maintained totals minus collapsed stack children;
filtered queries retain exact SQL predicates. Native folder pages load lazily and
release collapsed branches. Source navigation flushes pending edits and rejects
superseded requests. Photo-to-folder navigation uses explicit tree and photo-page
offsets, clears filters and switches to a flat direct-folder view; it does not
change saved stack visibility. Physical moves/renames,
multi-source selection and persistent workspace preferences remain future work.

Vocabulary pages retain sixty rows, with an 8 KiB inline budget per row. Larger
path/synonym values are explicitly deferred, with bounded abbreviated labels;
get_keyword returns the complete values and parent path at the captured global
revision. Mac editors resolve complete details before initializing fields. Parent
navigation holds one page and rejects changed revisions and superseded replies.

`keywords.py` owns schema version 8: durable keyword IDs, parent links, synonyms
and many-to-many direct photo assignments. The migration consolidates legacy
normalized names into root tags with a deterministic display spelling and retains
all assignments, including unusual legacy names. `photo_keywords` becomes a
read-only direct-assignment view; production writers use `keyword_photos` through
the domain service. Copies duplicate tag IDs and keep later assignments independent.
Photo deletion cleans up assignments. Backup/restore includes the complete tree.

Names are unique within a parent, not globally. Qualified paths preserve equal
leaf names in different branches. Renaming or moving an ancestor invalidates the
metadata revision of each affected photo once; pixel recipes/caches are unchanged.
The global keyword revision protects forms and assignment commands, and assignment
triggers advance it for copy/removal events. Native polling sees keyword changes
even on empty photo pages. Creating a tag and assigning captured photos is atomic;
both tag and photo revisions are validated before any mutation.

Tree/search pages contain at most 60 tags; hierarchy depth is limited to 32, tag
synonyms to 30, assignments to 100 per photo and batch targets to 60. Native pages
are released when collapsed/replaced, and selection/query generations reject late
replies. Direct counts/selection states use indexed assignments. Keyword ID, name,
synonym and text predicates include descendants via recursive SQL and intersect
other library sources/filters. Smart rules may retain a stable keyword ID; deleted
IDs match nothing and cannot be reused. Subtree edits use SQL rather than loading
the entire dictionary into native or Python arrays. Large edits still hold the
catalog lock; durable background metadata jobs remain pending.

The keyword layer stores export flags but does not encode image metadata.
Keyword suggestions, Painter and metadata undo are separate workflows;
hierarchical catalog storage does not establish those.

`keyword_sets.py` owns schema 13's local presets, selected-set state and bounded
recent-keyword IDs. Shared presets use a separately versioned SQLite repository;
`preset_paths.py` chooses Mac App Support, Windows LOCALAPPDATA or XDG defaults.
The service accepts an injected root, and native regression runs always override
it. The shared repository opens lazily, so ordinary catalog commands do not touch
user preferences. Shared storage is the default; its catalog-storage preference
switches repositories without copying or deleting presets. Catalog backup includes
local sets and recent entries, but not the separate shared database.

All preset commands acquire the shared transaction before the catalog transaction.
Mutations change either preset repository or the catalog, never both (apart from
first-use shared-store initialization). A captured opaque token binds the catalog,
storage mode, both preset revisions, selected identity and keyword revision.
Conflicting writers, deleted sets and stale scope/keyword state fail visibly.
Names page at thirty without slot payloads; only the selected set's nine complete
slots cross IPC. Slots contain text paths for cross-catalog use; recent entries
hold stable IDs and resolve their current complete labels. Explicit additions
record recency in the same metadata transaction; removals, file imports and folder
synchronization do not fabricate recent user actions. Applying a preset preserves
unrelated assignments and recipes, with all targets and the 100-tag bound checked
before commit. Native drafts are separate, retain their revision through external
refresh, and require explicit update/save or discard. No Lua preset is executed.

`get_keyword_set` previews any preset with the captured preset-state revision,
without changing the active selection. It returns thirty names and nine slots,
including parallel stable IDs for Recent Keywords. The native Painter chooser
retains up to one hundred local choices across those pages. It binds its initial
shortcut and preset reads to the same vocabulary revision, invalidates late reads
on dismissal, and confirms one shortcut replacement. Custom slot text is frozen
when selected; a later preset edit never silently changes an existing choice.
The Mac pointer adapter owns Shift and focus; portable code owns preview/shortcut
validation. Browsing and cancelling never create vocabulary or assign photographs.

`library_painter.py` owns schema 14's catalog keyword shortcut and bounded Painter
transactions. Shortcut entries contain stable IDs/positions; deletion prunes only
affected entries, and renaming changes displayed paths without retargeting them.
Read responses keep all one hundred possible IDs and twenty full paths. A token
binds the shortcut revision, vocabulary state and catalog. Setting a shortcut may
create explicitly typed tags but never assigns photos or changes recency.

Painter accepts up to sixty captured targets and one attribute: shortcut keywords,
rating, flag or color label. It checks all metadata revisions and keyword capacity
before writing, changes each photo's metadata revision once, and leaves recipes,
originals and submitted jobs unchanged. Keyword erasure removes only loaded IDs;
other attributes clear through explicit zero/none values. The native Store keeps
stroke state separate from selection and submits once at mouse-up. A replaceable
AppKit pointer adapter reports thumbnail intersections, including coalesced drag
segments; pending state cancels on changed layout/source/page. Deferred teardown
captures a stroke identity to avoid mutating SwiftUI during updates or cancelling
a new stroke. Culling readback updates rating/flag without adopting recipe revisions.

Target Collection Painter reuses `target_membership` instead of the descriptive
metadata command. Mouse-down captures the collection ID, collection revision and
target-state revision. The whole gesture adds/removes only its deduplicated visible
IDs. Existing-member add is not a toggle. Target changes fail at commit rather
than redirecting a stroke; unrelated photo metadata edits do not cause conflicts.
Membership validates at most sixty photo IDs in one indexed query without opening
full photo details or expanding deep keyword paths. Collection/ancestor revisions
and stack cleanup stay in the existing transaction; photo revisions, recipes,
originals and queued jobs are untouched. The shell refreshes membership and the
current source after commit, including removal from a displayed target collection.

`orientation.py` owns schema 15's independent photo orientation, frozen job value
and bounded fifty-batch undo history. The portable D4 representation is a horizontal
mirror followed by zero to three clockwise quarter turns; it is not an EXIF tag.
Rotate/flip composes in displayed coordinates. Up to sixty captured photo visual
revisions validate before one transaction; metadata and Develop history remain
unchanged. Undo validates the global history revision, latest action and every
target's current orientation. It preserves subsequent Develop edits and rejects a
missing target atomically. Existing catalogs/jobs start at identity orientation,
preserving legacy recipe rotation. Virtual copies inherit then own their value.

`OrientedPlan` maps an output strip/ROI to canonical Develop coordinates and applies
an exact array-view transform to the returned pixels and gamut mask. Existing
geometry, neighborhood halos, local-mask coordinates and CPU/Metal processing stay
in their original coordinate system. No extra full-resolution rotated buffer or
resampling pass is introduced. Preview/thumbnail cache identities include catalog
orientation; decoded linear caches remain shared. Preview geometry includes the
effective crop bounds separately from source-family decoder metadata.

The native adapter maps crop bounds, ratios and local-mask coordinates between
display and canonical space. Drawing requires a fitted preview with matching
photo ID, visual revision and orientation. Rotation Painter uses `orient_photos`
with captured visual revisions; it never writes `Recipe.rotation`. Photo menus
follow Grid selection versus active-photo scope. Separate orientation undo avoids
overwriting later Develop edits; unified application Undo/Redo remains future work.

`develop_presets.py` owns schema 16's catalog-local partial recipes, groups and
library revision. An independently versioned shared SQLite repository stores the
default preset library and catalog-storage preference. It uses `preset_paths.py`
and injectable roots; no native or OS path logic enters the domain. Shared-before-
catalog lock ordering matches keyword sets, but their storage preferences and
libraries remain independent. Thirty-row pages omit recipe patches; a captured
revision guards detail reads, management and application across both repositories.
Preset, scope and photo revisions are validated before and after LUT staging.
Content-addressed LUT copies happen outside SQL locks, reject changed bytes and
never overwrite destinations. Catalog restore rebinds local preset asset paths.
Application merges only selected fields, validates all target recipes/camera
profiles and writes one transaction with normal bounded Develop history. Equal
recipes are no-ops. Frozen export jobs, metadata and catalog orientation survive.
The Mac shell owns immutable editor and Painter captures, selection scope and
preview refresh; it does not translate Adobe parameters or process image pixels.

`iptc.py` owns schema 17's additive descriptive JSON field, form descriptors,
validation and named XMP mappings. Thirty supported fields are partial patches:
omission preserves, explicit empty values clear. Each merged photo stays within
64 KiB of UTF-8 JSON. Source EXIF/capture time and Develop recipes remain separate.
Creator contact structures, ordered creators, code bags, language alternatives
(x-default), rights URLs and copyright status round-trip through bounded XMP.
Large descriptive JPEG packets use verified Extended XMP; export policy projection
freezes these values with the existing job snapshot. Folder-sync details reduce
keyword pages to twelve paths when IPTC is present, retaining all values below the
broker frame bound; ordinary summary pages omit large patches.

`metadata_presets.py` owns schema 18's stable preset identities and revision.
Its independent shared/catalog repositories use the existing path adapter and
shared-before-catalog locking. Thirty-name pages omit patches; get/save/action/apply
require a captured token containing both repository revisions, scope and vocabulary
revision. Saved patches contain checked fields only, bounded to 512 KiB of escaped
JSON. Saving keyword text does not create tags. Application resolves additive tags,
validates every captured metadata revision and, when rating is selected, the prior
rating independently. It validates merged IPTC and keyword capacity before atomic
writes. Changed photos increment metadata revision once; equal applications do
nothing. Original files, Develop history, orientation and frozen jobs survive.
Native forms retain their captured revision. Only a successful own application
advances the same loaded Painter token to the acknowledged vocabulary state;
external refresh cannot rebase a pending stroke or draft.

`keyword_exchange.py` owns schema 12's manual person-keyword flag and dictionary
file exchange. Bounded UTF-8 input is copied and fingerprinted outside the catalog
lock, then validated in a temporary SQLite database with a 4 MiB page cache. The
complete stage merges new hierarchy nodes in one transaction, preserving existing
IDs, attributes, synonyms and all assignments. No image metadata is rewritten.
Export walks the hierarchy into a local temporary snapshot under the catalog lock,
then copies and atomically links it into a new destination outside that lock.
It never loads the entire vocabulary into a Python/native array. CSV retains the
manual person and export flags; text retains only Include on Export plus hierarchy
and synonyms. Input limits are 64 MiB, one million tags, 32 levels and thirty
synonyms per tag. These explicit bounds are not proof of complete Adobe file
interoperability; legacy unrepresentable names fail visibly.

`keyword_details.py` bounds photo keyword descriptions without changing assignments.
Photo reads retain every assigned ID and count. A recursive byte-length query
measures escaped names without concatenating all paths; paths above the 32 KiB
inline budget are explicitly deferred. Twenty-path detail pages bind to the photo's
metadata revision, which ancestor edits already invalidate. Assignment pickers
query twenty full paths by IDs or name/synonym search; they do not load the whole
vocabulary. Metadata replacement accepts complete existing IDs plus optional new
text paths in one transaction, validating targets, identities, ambiguity and the
combined 100-assignment bound before commit. Receipts return compact IDs/defer
state. Native pickers keep drafts local and preserve unmodified assignments and
independent recipe revisions.

`keyword_exports.py` owns schema version 11, adding three keyword export flags
and immutable per-job metadata snapshots/receipts. Projection walks explicitly
assigned tags and their ancestors until a containing-keyword flag stops traversal.
Excluded names and their synonyms do not appear in flat lists or hierarchy paths;
synonyms of included nodes expand only when enabled. Equal flat words are deduped
case-insensitively, while distinct hierarchy paths remain separate. Older keyword
edit clients preserve flags they do not supply. Tag changes invalidate affected
photo metadata revisions as before.

New jobs freeze catalog descriptions, resolved tags and options with recipes and
request-key receipts in one transaction. Migrated jobs keep empty metadata; no
later lookup enriches them. Public job queries exclude full snapshots in SQL and
return compact counts/policy/digests. Preview pages expose one captured photo's
fields and at most 60 words/paths. Worker requests use bounded UTF-8 JSON up to
8 MiB to carry one snapshot, rather than one packet per job in queue pages.

`export_metadata.py` validates XML and bounds XMP to 2 MiB before queuing. TIFF
embeds tag 700; JPEG uses standard APP1 or Extended XMP, with a standard descriptive
packet and offset-addressed keyword chunks checked by the specification's MD5
identifier. The reader accepts reordered complete chunks and rejects gaps,
overlaps, mismatched identifiers, checksum failures and oversized data. This format
checksum does not establish cryptographic authenticity. Pixel/ICC encoding is
unchanged; internal recipes, source filenames and local asset paths are no longer
written into TIFF ImageDescription. The None/Copyright/Catalog choices describe
supported catalog fields, not complete source EXIF/IPTC preservation.

`relocations.py` owns schema version 9 and durable missing-folder plans. It snapshots
folder IDs/counts and physical source families into indexed staging tables. Scans
hash at most 60 originals per command without holding the service catalog lock.
Known hashes must match; unknown hashes are reported separately; absent files can
remain missing at their new paths. Before applying, a second bounded stat pass
checks inode/device/size/mtime against the scan and checks the replacement directory
identity and continued absence of the old root. Revisions protect source families,
index metadata and structural folder membership. Metadata/recipe edits may continue.

Application acquires the image slot without waiting and rejects affected running
exports. One SQL transaction remaps photos/copies, folder membership, source
revisions, folder stacks and eligible job source paths. Export recipes/options and
destinations stay frozen. A transaction-scoped maintenance switch suppresses
the per-photo folder-path/count triggers; aggregate folder counts are adjusted by mapped
folder and ancestor instead. Rollback restores the switch and all paths/counts.
Nonmerged folders retain source IDs; merged nodes retain destination IDs, combine
favorites and use destination color labels unless unset. Merged-away IDs retire.
The native initiating source falls back to the result root if its ID was merged.

One active plan per catalog prevents concurrent remaps. Cancellation can interrupt
hash/stat work, but cannot reverse an already committed transaction; its receipt
reports the actual final state. A crash during verification leaves an explicitly
resumable plan. Image/export contention returns a ready plan for explicit retry.
Terminal plans drop their mapping and retain at most 32 small receipts. Backups
include staging. Missing-folder reconnection never moves files, synchronizes new
imports, removes missing catalog photos or deduplicates destination collisions.
Overlapping old/new trees are rejected. Filesystem validation and SQLite commit are
not an OS-wide filesystem transaction; later external file changes remain possible.

`folder_sync.py` owns schema version 10. One durable synchronization plan snapshots
the recursive source families and queues directory/file observations. Directory
iteration visits at most 256 entries per request; file inspection and review pages
contain at most 60 originals. List queries omit metadata patches larger than
4 KiB in SQLite and set metadata_deferred; complete staged values remain intact.
Explicit revision-bound detail reads return full descriptive fields and twenty
complete keyword paths, keeping extreme Unicode metadata below the broker frame
limit. Native review opens a separate read-only detail sheet for deferred patches.
One iterator is retained between requests; after a
restart, replay uses unique staging rows and cannot duplicate discoveries. Hidden
entries and symlinks are excluded from discovery; a catalog path replaced by a
symlink is an error. File/sidecar reads and final fingerprint checks release the
catalog lock. Permission/parser errors cannot be treated as missing originals.

Selections are durable for individual files, a subtree or a whole change kind.
Application rechecks source/index/folder revisions, and edit/metadata revisions
for families being removed or masters receiving metadata. Image work and affected
running exports defer application for explicit retry. One SQL transaction imports
references, optionally removes complete missing families, refreshes source stats
and applies selected descriptive metadata to masters. Copies share capture clocks
but keep independent descriptive metadata and recipes. Export snapshots/receipts
survive removal. SQL trigger guards suppress repeated ancestor counts during the
batch; folder membership remains maintained and aggregated deltas restore counts
before commit. Failed transactions restore guards and all catalog changes.

`xmp_read.py` limits packets to 2 MiB, header reads to 4 MiB and XML depth/node
counts; document types/entities are rejected. Sidecar properties override standard
TIFF/JPEG/PNG XMP. Missing properties leave catalog data unchanged. Titles, captions,
copyright, integer ratings, standard labels and hierarchical/flat keywords are
supported; unknown custom labels and Adobe Develop settings are reported as notes.
BigTIFF/other embedded containers, full IPTC, ACR sidecars and
XMP writing remain incomplete. Source headers are never decoded into pixels here.

Restart requires explicit continuation, preserving file deselections. Cancellation
discards staging unless application already committed; uncertain native replies
are read back without replay. Terminal plans retain 32 small receipts and backups
include active staging. No automatic synchronization or physical file deletion is
performed. Final stat checks are not an OS-wide filesystem transaction.

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
