---
name: lumaraw
description: Develop and organize local RAW photographs with LumaRAW through MCP or its packaged CLI. Use for Nikon NEF editing, preview inspection, reversible recipe changes, catalog organization and bounded batch exports.
---

# LumaRAW local darkroom

Use the LumaRAW MCP tools when connected. The native app's **Agent Connection** page shows the exact command and catalog path. App, CLI and MCP use the same service. No login, API key or network service is needed.

If MCP is unavailable, call the packaged engine at `<LumaRAW.app>/Contents/Resources/Engine/LumaRAWEngine`. Pass `--catalog <catalog-path> <method>` and a JSON object on stdin. `status` and `recipe_schema` need no input. Source checkout fallback: `uv run --frozen lumaraw --catalog <path> <method>` from the project directory. The CLI wraps results in `{ok,result}` or `{ok,error,type}`; stdout of `--mcp` is JSON-RPC only.

## Service compatibility

All commands negotiate with the catalog's running engine before execution.
`service_connection` with `action: status` reports client compatibility and the
broker identity. Newer generations can take over only when no command or image
operation is active. A same-generation build switch requires `action: activate`
when switching is part of the user's request; it does not interrupt active work.
Clean handoff preserves pending jobs and pause state. Do not retry uncertain
mutation replies; keep export request keys for their existing idempotency contract.
Older generations and schemas cannot downgrade a newer catalog.

A legacy broker without this handshake must finish its work and exit naturally.
Report the instruction to close older app/agent clients and reconnect after the
three-minute idle period; never kill a user broker as a workaround. If an engine
was replaced while running, a worker refuses mismatched code before opening images;
the affected export is interrupted and the remaining queue is paused. Reconnect,
inspect jobs and retry only under the user's export authorization.

## Editing workflow

1. `lumaraw_status` identifies the active catalog; do not assume an unrelated catalog is the user's library.
2. `lumaraw_import_photos` takes explicit local file or directory paths. Imports reference originals; moving originals makes them offline. `lumaraw_list_photos` paginates in 60-photo pages and returns summaries. `lumaraw_get_photo` returns a full recipe and revision.
3. Read `lumaraw_recipe_schema` for defaults, numeric limits and presets. Send a **partial** `patch` to `lumaraw_edit_photo` with `photo_id` and `expected_revision`. Preserve crop, masks, LUT and calibration unless the task asks to change them. On `ConflictError`, re-read and reconcile; do not blindly overwrite the newer edit.
4. Inspect `lumaraw_preview_photo`'s local `preview` and `before` image paths. Add `detail: {cx: 0.5, cy: 0.5, width: 1024, height: 768}` for a true full-resolution viewport. The normal preview is reduced resolution. Do not claim Nikon color accuracy from appearance alone.
   Use `include_before: false` when no baseline is needed. `max_edge` (128–1680)
   requests a fitted preview; do not combine it with `detail`. `photo_summaries`
   reads at most 60 existing IDs without recipe/EXIF payloads. A preview client may
   pass its own `client_id` and monotonically increasing `generation`;
   `cancel_preview` with a newer generation invalidates only that client's older
   preview/thumbnail work, leaving other clients and exports intact.
5. Save named versions before exploratory changes if useful. Undo affects the last recipe edit; ratings and flags are separate.

Example edit arguments:

```json
{"photo_id": 12, "expected_revision": 3, "patch": {"exposure": 0.35, "highlights": -20, "shadows": 12}}
```

## Library organization

`rate_photos` applies an explicit rating and/or flag atomically to at most 60 IDs.
Every target is validated before writes. It preserves recipe and descriptive
metadata revisions. Use `rate_photo` for the existing single-photo contract.

`list_photos` accepts `filters`, `collection_id`, `sort` and `descending`, and
returns a clamped offset plus at most 60 summaries. `list_collections` paginates
regular/smart collections and sets, excluding the single Quick Collection. Omit
`parent_id` for the flat list; use null for root children or a set ID for its
children. `get_collection` also returns its ancestor path. Use `save_collection`
with `collection_id` and
`expected_revision` for updates; `collection_membership` applies only to regular
or Quick collections and also requires their revision. `parent_id` moves a
collection; new regular collections can take `photo_ids` to add initial members.
Sets aggregate nested collections without owning photos directly. Ancestor revisions
change when descendants change. Deleting a set removes the entire subtree and
memberships; `duplicate_collection` copies it, preserving rules/memberships.
Deleting a collection never removes
photos or originals. Smart rules evaluate current metadata when the library is queried.

`collection_state` returns the Quick/target collections and independent state
revision; optional `photo_ids` returns target membership for that page. Target
changes require `set_target_collection` with the state revision; null resets to
Quick. `target_membership` requires the captured target ID, its collection revision
and the state revision, and an explicit add/remove action. Never refresh and retry
a target conflict blindly. `quick_collection` saves or clears Quick using its
collection revision; save can atomically clear afterward. The Quick Collection
cannot be renamed, moved or deleted. Limits: 32 nesting levels, 128 smart descendants
in an aggregate view, and 1,000 collection nodes per subtree duplication.

`edit_metadata` takes at most 60 `{photo_id,expected_metadata_revision}` targets and
a shared `patch` containing title/caption/copyright/color_label/keywords/copy_name. Read each
target before editing; keywords replace the current set. The response contains a
single normalized patch and per-photo metadata revisions, not newer recipe state.
Conflicts leave the whole batch unchanged. Metadata stays in the catalog; EXIF and
sidecars are not rewritten. `cached_thumbnails` returns existing paths for a bounded
page without starting workers; use `thumbnail` for missing entries. Both commands
accept `kind: "developed"` for a 320-pixel recipe-aware image, or `kind: "source"`
(the default) for the original/source preview. Developed replies include the
captured recipe revision: reject stale results instead of labeling them as newer
edits. A thumbnail client can use its own `client_id`/`generation` and
`cancel_preview` to discard obsolete work. Metadata edits preserve the pixel cache;
recipe, source or LUT changes invalidate it. The Mac shell uses developed images.

## Hierarchical keywords

`list_keywords` returns at most 60 roots, children of `parent_id`, or flat name/
synonym search matches. Pass a bounded `photo_ids` selection for direct assignment
counts. Each page carries `keyword_revision`. `save_keyword` creates/renames/moves
a tag with this `expected_revision`, a name, optional parent (null/omitted means
root) and synonyms. Optional photo `targets` atomically assign a newly created tag;
each target needs its current `expected_metadata_revision`.

Large list rows carry `details_deferred:true`, null `path`/`synonyms`, and an
abbreviated `path_preview`. These are unknown values, not empty defaults. Read
`get_keyword(keyword_id,expected_revision)` before editing: it returns the full
path, authoritative parent path, all synonyms and export flags. A changed or
removed keyword fails visibly; reread the list instead of retrying a stale edit.
Small rows retain their inline values for compatibility.

`keyword_membership` adds/removes one ID for up to 60 revision-checked targets and
preserves other tags. `delete_keyword` removes a complete subtree and assignments,
with the captured global revision. Both preserve original files and pixel recipes.
Read before editing, and never resubmit a stale mutation automatically. A failed
batch leaves every target unchanged.

`get_photo` always includes complete `keyword_ids` and `keyword_count`. Small
assignments also include `keyword_tags` IDs/qualified paths and compatible
`keywords` strings. With `keywords_deferred:true`, those display arrays are omitted
as empty arrays; this does **not** mean the photo is untagged. Use
`get_photo_keywords(photo_id,expected_metadata_revision,offset)` for twenty full
paths per page. A stale revision requires rereading the photo.

`keyword_choices` searches names/synonyms or filters up to 100 supplied
`keyword_ids`, returning twenty complete paths. An explicit empty ID list returns
no rows. For large assignment edits, `edit_metadata.patch.keyword_ids` replaces
the entire set by identity; optional `keyword_additions` resolves new typed paths
in that same transaction. Empty IDs explicitly clear assignments. Never combine
these fields with the alternative `keywords` text-replacement field. Omit all
keyword fields when only changing a title or caption.

A replacement string list accepts `parent | child`, `parent > child` or
`child < parent`; ambiguous bare leaf names fail. `filters.keyword_id` selects a
stable tag plus descendants; name and synonym filters can match multiple branches.
Tag IDs are never reused after deletion. Synonyms are searchable catalog terms.
Keyword forms accept optional `include_export`, `export_containing` and
`export_synonyms` booleans. Omitted flags preserve existing values; new tags default
to true. Parents can stop further ancestor traversal. Excluded names/synonyms are
also omitted from hierarchy paths. Limits are 32
levels, 30 synonyms per tag and 100 direct tags per photo.

`is_person` is a manual keyword classification, accepted by save_keyword and
returned by list/get. Omission preserves an existing value; new tags default false.
It does not invoke recognition.

`import_keywords(path,expected_revision)` reads a UTF-8 tab-indented .txt or keyword
options .csv dictionary, validates the whole input, then adds new tags atomically.
Tabs define hierarchy, square brackets mark excluded text keywords, and nested
braces identify synonyms. Existing tags keep their IDs, synonyms and flags; imports
do not rename/delete tags or alter photo assignments. An invalid file or stale
revision commits nothing. Limits: 64 MiB, one million tags, 32 levels, 30 synonyms.

`export_keywords(path,format,expected_revision)` writes a new .txt (`text`) or .csv
(`csv`) file. CSV retains all four keyword flags; text retains hierarchy, synonyms
and Include on Export, reporting `omitted_options` for tags with other nondefault
flags. Existing files/symlinks are never replaced. Unrepresentable legacy names
fail without publishing a partial file. Receipts remain compact; the dictionaries
travel as explicit files, not oversized broker responses. Do not automatically
retry a mutation after an uncertain response.

## Keyword sets

`list_keyword_sets` returns thirty names, the selected nine text slots, storage
mode and an opaque `revision`. `offset` pages names; it does not select a preset.
`save_keyword_set(name,slots,expected_revision)` creates a set; include `set_id`
to update or rename that identity. Supply exactly nine strings, using empty strings
for unused slots. Saving does not create or assign catalog keywords.

`keyword_set_action` accepts `select` or `delete` with `set_id`, or `storage` with
`store_with_catalog`. Every mutation needs the captured token. The reserved
`recent` set cannot be edited/deleted, but its slots can seed a new preset.
Shared storage is the default. Switching to catalog storage preserves shared sets
in place; it does not copy them. Catalog backups contain local presets and recent
IDs; shared presets use a separate user repository. Set `LUMARAW_PRESETS_ROOT`
before launching an isolated broker to override platform storage defaults.

`apply_keyword_set(slot,targets,expected_revision)` adds slot 1–9 to up to sixty
revision-checked photos, preserving unrelated tags and recipes. Optional
`draft_slots` applies a transient nine-slot edit to a custom set without saving it.
Recent slots resolve by stable catalog identity. Empty slots, ambiguous text,
stale state, missing targets or capacity errors commit nothing. Never retry an
uncertain mutation response or silently replace the captured token. Adobe built-in
preset contents and `.lrtemplate` exchange are not implemented.

`get_keyword_set(set_id,expected_revision,offset)` previews a set without selecting
it. It returns the same thirty-name/nine-slot shape as `list_keyword_sets`, plus
parallel `selected.keyword_ids` (IDs for Recent Keywords, nulls for custom text)
and `keyword_revision`. Capture choices locally across sets. Browsing is read-only;
use `set_keyword_shortcut` once to confirm chosen IDs and explicit text additions.
Preserve the original shortcut revision and never split a recent display label.
Custom slot text is frozen at selection; edits to that preset do not retarget it.

## Keyword shortcuts and Library Painter

`get_keyword_shortcut` returns complete `keyword_ids`, twenty full paths and a
captured `revision`. Use `offset` and `expected_revision` for consistent additional
pages. `set_keyword_shortcut(keyword_ids,expected_revision,keyword_additions)`
replaces the shortcut, resolving explicit additional text paths in one transaction.
Empty IDs and no additions clear it; at most one hundred keywords are allowed.
The shortcut preserves IDs through rename and prunes deleted tags. Setting it does
not assign photos. Never reparse existing labels containing literal separators.

`paint_library` applies `kind: keywords|rating|flag|label` to up to sixty `targets`
with `photo_id` and `expected_metadata_revision`. Keywords require
`expected_shortcut_revision`; optional `erase:true` removes only the loaded
shortcut IDs. Other modes take `value` (0–5 rating, -1/0/1 flag, or a supported
color label); use 0/`none` to clear, not keyword erasure. Omit shortcut revision and
erase for these modes. All targets and keyword capacity validate before commit.
Recipes, originals and frozen jobs are preserved. Native gestures submit on
mouse-up without selecting painted photos; agents use explicit target lists.
An uncertain or stale stroke must never be automatically replayed.

Native Target Collection Painter uses `target_membership`, not `paint_library`.
Read `collection_state`, then capture `target.id`, `target.revision` and the state
`revision`. Submit those as `collection_id`, `expected_revision` and
`expected_state_revision`, with up to sixty `photo_ids` and `action:add|remove`.
Adding an existing member never toggles it off. Preserve captured revisions across
a drag; never reread and redirect the same pending stroke to a changed target.
Membership changes do not alter photo metadata/recipe revisions. The native Option
stroke removes only touched target members and refreshes the displayed source.

## Folder sources

`list_folders` pages visible roots or a `parent_id` at 60 items. Optional `search`,
`favorites` and `color_label` produce a flat folder list, independent of photo
filters. `get_folder` takes exactly one `folder_id` or `photo_id`; its ancestors,
tree `page_offset` and direct-folder `photo_offset` support explicit navigation.
The photo offset assumes unfiltered, unstacked import order descending.

Pass `folder_id` and optional `include_subfolders` (default true) to `list_photos`.
A collection and folder source are mutually exclusive. Keep source selection
separate from the existing `filters.folder` metadata criterion, which remains
recursive for compatibility. `library_state` returns structural folder/stack/keyword
revisions for empty-page polling. A folder's counts include virtual copies and
ignore photo filters; unavailable directories remain catalog entries.

`edit_folder` changes only `favorite`/`color_label` with the row's revision.
`set_folder_visibility` checks the global folder revision and uses `show_parent`
or `hide_parent`; a parent with direct photos cannot be hidden. These commands do
not create, rename, move or delete physical folders. Do not infer that a displayed
empty/unavailable folder authorizes deleting originals or removing catalog photos.

For an explicitly chosen replacement of a missing folder, call
`prepare_folder_relocation` with `folder_id`, `destination` and the global
`expected_revision` from `library_state.folder_revision`. Read the returned plan
and run `scan_folder_relocation(plan_id,expected_revision)` using each new plan
revision while its state is `planning` or `interrupted`. Each scan reads at most
60 physical originals outside the catalog lock. `get_folder_relocation` returns
the latest or specified plan and 60 issue rows (`issues_only:false` includes all
rows). Review verified/unverified/missing/conflict counts and folder merges before
`apply_folder_relocation`; conflicts prevent applying. An unindexed file is matched
by relative path, not a content hash. Application reconnects the entire subtree,
including virtual copies, without moving originals. Existing destination photo
collisions and overlapping trees are rejected. Recipes, metadata, stacks and
export snapshots survive. Active image/export work returns the plan to `ready`
with an explanation; retry only explicitly, using the new revision.
`cancel_folder_relocation(plan_id)` discards an unfinished plan. Always inspect
its returned state: a commit that already finished stays `applied`. Restarted scans
require explicit resumption. Do not retry an uncertain apply response; read the
plan's receipt. One active plan and 32 terminal receipts are retained per catalog.

For an explicitly chosen available folder, `prepare_folder_sync` takes `folder_id`,
the global folder `expected_revision`, and required `scan_metadata`. Continue
`scan_folder_sync(plan_id,expected_revision)` while `planning` or `interrupted`,
adopting each returned revision. `get_folder_sync` pages 60 files with `kind`
`changes`, `all`, `new`, `missing`, `updated`, `error` or `unchanged`. Review counts,
metadata values, notes and errors before applying. Items with `metadata_deferred`
keep large scanned values out of the list response. Read them with
`get_folder_sync_metadata(plan_id,item_id,expected_revision,offset)` using the
captured plan revision. It returns complete fields and 20 keyword paths per page;
continue until `offset + page_size >= total`. A changed plan requires refreshing
the review. Never treat a deferred empty patch as absent metadata.
`select_folder_sync_items`
uses a revision, `selected`, and a `kind` of `new`, `missing` or `updated`; choose
at most 60 `item_ids`, a `folder` subtree, or omit both to select the whole kind.

`apply_folder_sync` defaults to `import_new:true`, `remove_missing:false`,
`read_metadata:true`. Set `read_metadata:false` when metadata was not scanned.
Removing missing originals requires the user's explicit workflow choice: all
their copies, edits, snapshots and memberships are removed from the catalog.
Originals and export receipts stay untouched. New files are referenced in place;
supported XMP updates affect masters' descriptive metadata, not independent copy
metadata or Develop recipes. This is not complete IPTC/ACR/Adobe Develop import.
Scan errors block application. Read the receipt after an uncertain reply; never
repeat a mutation automatically. Busy image/export work returns a ready plan for
explicit retry. `cancel_folder_sync(plan_id)` discards an unfinished plan, but
cannot undo a committed result. Closing/restarting preserves review selections.

## Photo stacks

`list_photos` defaults to source-scoped stacks and includes `stack_revision` plus
stack ID/count/cover/visibility on each visible row. Folder stacks are separate
from regular/Quick collection stacks; smart/set views are flat. Collapsed members
are hidden from filtering and selection. Use `stacked: false` to inspect all
matching photos without changing saved visibility. Never assume selecting a cover
authorizes editing or exporting its hidden members.

`stack_photos` takes `photo_ids` (1–60 distinct IDs), `expected_revision` captured
from the page, an optional `collection_id`, and an action: group, unstack, remove,
expand, collapse, toggle, split, top, up or down. For a new group, order IDs as displayed
and provide its selected `active_id` to choose the cover. Grouping requires at
least two photos; folder groups require the same exact folder. Grouping two
collapsed covers moves only the selected photo from the other stack. Remove and
unstack leave photos, originals and recipes intact. A stale revision is a conflict,
not permission to refresh and retry the mutation automatically.
Split requires a proper subset from one expanded stack, beyond only its cover.
It retains selected internal order in a new expanded stack; singletons are unstacked.

`set_stack_visibility` expands/collapses every stack in a captured source, without
depending on photo selection or metadata filters. Pass `collapsed`, the current
stack revision and either `collection_id` or `folder` (including descendants unless
`include_subfolders` is false).
Omitting the source affects all folder stacks. `stack_state` reads the revision
without photo payloads. New virtual copies automatically join an expanded folder
stack, even when created in a collection; no collection stack is invented.

`preview_auto_stack` takes `seconds` (0–3600) and exactly one `folder` or
`collection_id`. A folder includes only its immediate catalog photos. Selection,
filters and visibility do not narrow this operation. Adjacent gaps strictly below
the threshold form groups. The response reports counts, unknown dates, existing
stacks and a `token`; applying replaces stack organization in that source. Call
`apply_auto_stack` only with the reviewed source, duration and token. A conflict
requires a new preview and review; never automatically retry a stale replacement.

`refresh_capture_times` reads up to 60 physical originals per call; pass its returned
`after_source_id` until `done`, allowing cancellation between calls. This reads
bounded TIFF-family/JPEG/PNG EXIF headers, without hashing or pixels, and updates
shared source-family clocks. Unknown/unsupported dates are explicit. Offsets become
UTC; dates without offsets retain camera clock provenance. Fractional precision is
preserved. Migration keeps old integer timestamps but does not invent precise
clocks, so older catalogs may need this explicit refresh. Originals are read-only.

## Virtual copies and snapshots

`create_virtual_copies` takes up to 60 `{photo_id, expected_revision,
expected_metadata_revision}` targets. It duplicates catalog edit/metadata state,
never original files or prior undo history. Optional `collection_id` and
`expected_collection_revision` add copies to a captured regular/Quick collection.
`get_photo` and summaries expose `source_id`, `master_id`, `is_virtual`, `copy_name`
and `source_revision`. Filter by `is_virtual`, `source_id` or literal `copy_name`.
Use `edit_metadata` to rename a copy. `save_version`/`list_versions` are named
snapshots shared by every variant of the same source; restore changes only the
chosen photo's recipe and preserves undo.

`set_copy_as_master` takes a target plus `expected_source_revision`; it swaps roles
without changing IDs or recipes. `remove_virtual_copies` takes targets with that
same source revision and removes only virtual copies, private history and
memberships. This removal cannot be undone; the native app shows a confirmation.
Original files, shared snapshots and submitted export jobs survive. Never silently
retry stale removal/promotion by adopting newer revisions. Relinking a missing
original applies to its family, including eligible jobs from removed copies.

## Batch and output

- `lumaraw_sync_photos` copies only named groups and requires every target's current revision; `Composition`, `Local Masks`, `Camera Profile` and `LUT` are separate explicit choices.
- `lumaraw_enqueue_exports` requires a new `request_key` per logical submission. Persist and reuse that same key for an uncertain submission retry. The same key with changed arguments is rejected. Queue parameters are immutable snapshots; later edits do not change pending exports.
- `preview_export_metadata` reads one photo's resolved metadata with `kind:keywords`
  or `hierarchy`, a 60-item `offset` page and optional export policies. Export
  options accept `metadata:catalog` (default), `copyright` or `none`, and
  `keyword_hierarchy` (default false). These cover supported catalog descriptions,
  ratings/labels and keywords; they do not claim full EXIF/IPTC/GPS copying. Respect
  the user's intended metadata scope. Metadata and resolved keywords are frozen
  with recipes at submission. Public jobs return `export_metadata` counts/policy/
  digest, while full snapshots stay in the catalog. Legacy jobs retain empty
  snapshots. Original metadata files are never rewritten by export.
- Supply `photo_ids`, `destination`, `format` (`tiff16` or `jpeg`) and optional `options` (`space`: `srgb`, `p3`, `adobe`, `prophoto`; `max_edge`; `quality`; `name`). Inspect `lumaraw_list_jobs` until all requested IDs complete. It lists the most recent 60; use `lumaraw_get_job` for an individual durable receipt beyond that page.
- Report actual output paths, failures and cancellations. A job queued is not a job completed. Recovered tasks remain interrupted; retry only when consistent with the user's requested work. After an interrupted publication, inspect the destination before retrying. Existing files are never overwritten.
- Pause takes effect after the current image. Cancel stops an active worker and pending jobs. A file published just before cancellation can remain. `retry` covers failed/interrupted jobs; `retry_cancelled` is a separate explicit action.

## Color and safety boundaries

Originals remain read-only. “Non-destructive” does not mean reversible demosaicing or mathematically lossless color conversion. TIFF is 16-bit; JPEG is lossy. HE/HE* NEF compatibility depends on LibRaw. Temperature/tint are **relative** to as-shot white balance, not absolute Kelvin.

Camera calibration needs the actual RAW chart and a reference image, matching 6 × 4 chart orientation, normalized source/reference rectangles, camera identity and lighting. Synthetic chart tests or LibRaw matrix parity do not establish NX Studio/Picture Control equivalence. Lens correction uses manual coefficients, not an automatic lens database.

Memory estimates and sampled RSS guard risk; they are not a hard OS allocation cap. The engine processes one image at a time, uses disposable workers, and keeps pixels on disk. Never bypass a budget failure by unbounded parallel export.


## Metal and performance (0.4+)

`lumaraw_settings` accepts `compute_backend`: `auto` (default, Metal with CPU fallback), `cpu`, or `metal` (report GPU initialization/dispatch failures). This is catalog processing policy; it does not alter saved recipes. `auto` uses CPU for tiny or over-budget tiles. GPU support is checked inside the worker, so a present library alone is not proof of acceleration.

Preview replies and completed `lumaraw_get_job` receipts include `processing`: actual backend/device, `metal_grade_tiles`, `metal_output_tiles`, `cpu_tiles`, shared-buffer peak, fallback reasons, GPU/dispatch/initialization durations, worker duration and named stage timings. `status`/`settings` expose the latest worker report. Use these receipts before claiming Metal ran. Masks/LUTs can retain CPU grading and use GPU output conversion; geometry and neighborhood filters remain CPU.

NEF decompression, metadata parsing, white balance and AHD demosaicing still use LibRaw CPU; Metal accelerates subsequent pixel grading/output conversion. Compare identical source/recipe/output and distinguish empty application cache from warm cache. Include initialization, transfers and encoding in end-to-end timings; a kernel-only speedup is not whole-photo throughput. FP32 GPU results have small numerical differences from the CPU reference. Keep memory preflight and the dynamic 70% cap enabled.
