---
name: lumaraw
description: Develop and organize local RAW photographs with LumaRAW through MCP or its packaged CLI. Use for Nikon NEF editing, preview inspection, reversible recipe changes, catalog organization and bounded batch exports.
---

# LumaRAW local darkroom

Repeated `preview_photo` calls may return a validated completed preview without
starting image work. `preview_cache_hit=true` and `worker_spawned=false` identify
this path; processing backend `cache` reports lookup time and zero worker/GPU
work. Continue to pass captured revisions and honor stale/cancelled replies.
Reuse includes requested Before, geometry, histogram and targeting/readout maps;
missing, changed or damaged cache data causes normal rendering. This is a local
processing optimization, not evidence of Adobe pixel parity or UI frame rate.

## Develop history

Read `get_photo` and capture its revision before calling `list_history`. Every
history command requires `photo_id` and `expected_revision`. List replies contain
at most sixty summaries, newest first, plus the current cursor and undo/redo
availability. Pass `next_before` as `before_id` for the next older page; do not
interpret missing page entries as deleted states. Step `0` is the initial retained
state, which can include import presets or inherited virtual-copy settings.

`undo_photo`, `redo_photo` and `select_history(step_id)` move through retained
states without deleting future steps. A subsequent real edit replaces the future
branch; a no-op edit preserves it. `rename_history(step_id,name)` changes only its
label, but invalidates captured photo revisions. `clear_history` discards the
timeline and keeps current adjustments as a new baseline; require explicit user
intent for this irreversible deletion. Snapshots, orientation and submitted
exports remain unchanged. Never retry stale or uncertain mutation responses.
These commands cover per-photo Develop history, not global application undo.

## Before / After

Ordinary `preview_photo` calls may supply `expected_revision` captured from
`get_photo` or bounded `photo_summaries`. The service verifies it before and after
processing. If it changes, discard the preview and explicitly refresh the read;
never rebase a pending mutation. Reference photos need `include_before: false`
and a separate `client_id`/generation from the editable active photo. A changed
active photo does not change reference assignment. This UI role/lock is local
session state; it does not create snapshots or edit catalog recipes.

`before_after` requires `photo_id`, `expected_revision` and an `action`:
`after_to_before`, `before_to_after`, `swap`, `snapshot_to_before` with captured
`version_id` and `expected_version_revision`, or `history_to_before` with a
`step_id` (zero selects the retained history baseline). Copying history does not
move its cursor. Before is a separate persistent recipe, initially the imported
or inherited virtual-copy settings. Branching and clearing history leave it
intact. Before-only changes advance the photo revision without truncating redo;
copying to After and swapping create ordinary Develop edits. Develop undo only
changes After. Never retry stale or uncertain mutation replies.

`preview_photo` returns `before_label` and `before_cache_hit` when Before is
requested. Its Before preview uses current After geometry to align both sides,
while copy/swap always transfers the complete stored recipe. Set `include_before:
false` when only After is needed. The service captures the stored Before; clients
cannot inject another baseline into the preview contract.

## Develop RGB / Lab readouts

Set `include_color_readouts: true` on a revision-bound `preview_photo` to request
SDR Develop samples. Receipts describe bounded binary maps: the six ASCII bytes
`LRCOL1` followed by two zero bytes, little-endian uint32 width/height, then six float32
values per pixel in R/G/B/L/a/b order. RGB percentages use ProPhoto D50 primaries
and the sRGB transfer curve; Lab uses D50. Both are computed before display
proofing and overlays, with SDR clipping explicitly declared in the receipt.
Treat this as LumaRAW's documented calculation, not verified Adobe equivalence.

`image_width`/`image_height` describe full-resolution cropped dimensions. Pair
Reference/Active readings only when those dimensions match; otherwise leave the
other role absent. Use `before_color_readouts` for Active Before. Ordinary Fit
maps sample the fitted preview; detail maps use full-resolution pixels. Validate
map metadata/length and capture context before using a file. Local maps support
pointer movement without more commands. A missing counterpart outside its retained
viewport can request a one-pixel detail with a separate cancellable client and
captured `expected_revision`; never create edits or history for a color reading.

## Named snapshots

`list_versions(photo_id)` returns sixty alphabetical summaries without recipes.
Pass `next_after` as `after_id` with `expected_snapshots_revision` for the next
page. A list mutation invalidates that cursor; restart explicitly from the first
page. For polling, `known_revision` returns a compact `unchanged` receipt without
rows. Lists are shared by every variant of the same source.

Use `save_version(photo_id,name,expected_revision)` to capture current settings.
Optional `step_id` saves retained history without selecting it. Keep the returned
snapshot `id` and `revision`; `rename_version` needs those as `version_id` and
`expected_version_revision`, plus `photo_id` and `name`. `update_version` replaces
the stored recipe with current settings and also requires `expected_revision`.
`delete_version` removes the shared snapshot at its captured revision. Update and
delete require explicit intent and have no Develop undo. Current edits, copied
Before values, history and submitted jobs stay unchanged. Never replace a name
collision implicitly; new names are NFC/casefold unique within the family.

`restore_version` takes both photo `expected_revision` and snapshot
`expected_version_revision` and creates an ordinary Develop history edit on the
selected variant. `before_after(action: snapshot_to_before)` copies the complete
recipe to independent Before and preserves history/redo. Never rebase an open
form's tokens or replay a stale/uncertain mutation. Older callers may omit the
new snapshot token on restore and the photo token on current-state creation;
new clients should always capture and send both relevant tokens.

`list_photos(filters: {has_snapshots: true})` selects photos with at least one
shared named snapshot; `false` selects those without. The boolean is also a
`save_collection` smart rule and composes with other all/any criteria and normal
Library source restrictions. Originals and virtual copies share the status;
history, saved Before settings and presets do not count as named snapshots.
`library_state`, `photo_summaries` and `list_photos` expose a compact
`snapshot_filter_revision`. It advances on first/last snapshot transitions,
including bulk removals; additional snapshots, renames and settings updates do
not change this token. Use it to invalidate filtered counts/pages, not to rebase
captured photo or snapshot revisions. Empty views must poll state too.

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

`list_photos` with `mode: previous_import` reads the latest committed import and
its virtual copies with normal paging, filters and sorting. Do not combine this
mode with `folder_id` or `collection_id`. Read the compact `previous_import`
receipt in `library_state`, `photo_summaries` or `list_photos`; it is not an import
history. Failed reviewed imports and no-op imports retain the previous source.
Legacy direct imports can commit partial progress. Older catalogs start with no
batch history until another import. The catalog setting `select_previous_import`
controls post-import navigation in the Mac app; it never alters batch membership.

1. `lumaraw_status` identifies the active catalog; do not assume an unrelated catalog is the user's library.
2. Use the reviewed Add import commands below for source inspection and checked selection. Legacy `lumaraw_import_photos` immediately imports explicit local paths without review. Imports reference originals; moving originals makes them offline. `lumaraw_list_photos` paginates in 60-photo pages and returns summaries. `lumaraw_get_photo` returns a full recipe and revision.
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

Color mixer bands are `red`, `orange`, `yellow`, `green`, `aqua`, `blue`, `purple`
and `magenta`. Each has `_hue` (-30 to 30 degrees), `_sat` and `_lum` (-100 to 100).
The Mac hue slider displays -100 to 100, which is three and one third times the
stored/API degree value. Each band's `_bw` is -100 to 100 and takes effect only
when `monochrome` is true. Switching treatment retains all values; color mixing
still precedes monochrome conversion. `Color` sync copies all HSL controls and
treatment; `Black & White Mix` separately copies the eight `_bw` values. Refresh
`recipe_schema` for authoritative fields/limits. These are LumaRAW parameters,
not interchangeable Adobe XMP values or a claim of calibrated Adobe color parity.

RGB point curves use `curve_rgb_points`, `curve_red_points`, `curve_green_points`
and `curve_blue_points`. Each takes 2–16 `[input, output]` pairs in 0–1; inputs
ascend with a minimum gap of 1/65535. Outputs may invert, and endpoints may move.
Identity is `[[0,0],[1,1]]`. Read `point_curve_presets` from `recipe_schema` for
LumaRAW preset values. Tone Curve sync includes these fields. The older
`curve_points` remains a separate linear luminance curve with its original rules;
do not replace its meaning or copy Adobe parameters without conversion evidence.

For temporary curve inspection, `preview_photo` accepts `curve_patch` containing
only curve fields and requires `expected_revision`. It returns `curve_draft: true`
without changing recipe/history or frozen exports. A normal preview restores the
saved result. Persist an accepted draft with an ordinary revision-checked edit.
Active RGB curves are SDR; identity leaves negative/HDR values untouched. Very
steep curves use CPU grading with Metal output and report the hybrid reason.

Parametric curves have `parametric_shadows`, `parametric_darks`,
`parametric_lights` and `parametric_highlights`, each -100 to 100. The separate
`parametric_splits` array has three ascending normalized boundaries, default
`[0.25,0.5,0.75]`; all four regions must be at least 0.01 wide. Changing splits
preserves amounts. These five fields are included in Tone Curve sync, selected
preset fields and temporary `curve_patch` previews. Reset only these fields when
resetting a parametric curve; preserve legacy/RGB point curves unless requested.
The smooth monotone transform changes encoded luminance before RGB point curves,
preserving channel ratios and out-of-SDR luminance. It is not an Adobe parameter
translation. Old recipes default to neutral amounts without a catalog rewrite.

`preview_photo(include_curve_tones: true)` also returns `curve_tones`: a bounded
file-backed map of encoded luminance immediately before parametric curves. Its
dimensions match the returned preview/ROI after crop and orientation. The binary
format is `LRTONE1\0`, little-endian uint32 width/height, then row-major float32
values in 0–1. It is intended for photo-targeted controls, not RGB eyedropping.
Downstream curve/color/mask/LUT edits reuse it; upstream settings and geometry
invalidate it. Display proofing never changes these inputs. Map requests and
temporary previews do not save recipes. Normal clients can omit the option.

For HSL or Black & White Mix targeting, request `mixer_target: hsl` or `bw` on a
preview. The result's sparse map contains `LRMIX1\0\0`, little-endian uint32
dimensions and 16 bytes per pixel: one uint32 with up to three byte-sized band IDs
and a count in its high byte, then three float32 weights. Band order is supplied
in `bands`. Weight the selected component's control delta by these engine values;
native hue display units still convert to stored degrees by multiplying by 0.3.
HSL samples precede color mixing; B&W samples follow it. Neutral samples have no
bands. `mixer_patch` previews only mixer fields at `expected_revision`, with
`mixer_draft: true`; it cannot accompany `curve_patch`. Persist accepted results
with ordinary revision-checked partial edits. Map/draft reads never save history.

## Reviewed Add / Copy import

`prepare_import(paths, include_subfolders?, skip_duplicates?)` captures explicit
files/folders in one durable review. Both options default to true. Repeatedly call
`scan_import(plan_id, expected_revision)` with each returned revision while the
state is planning or interrupted. A call reads at most 256 directory entries or
60 file headers/sidecars; it never imports photos. Resume after interruption only
when requested. Finish or cancel an existing review before creating another.

`get_import` reads the latest review by default, or a specific `plan_id`. Pages
contain sixty compact items; `kind` is all/new/duplicate/existing/error/selected,
`sort` is name/captured/checked/type, with offset and descending options.
`select_import_items(plan_id, expected_revision, selected, item_ids?, kind?)`
changes check state when ready. Explicit IDs are limited to sixty; omitting IDs
applies to all eligible rows, optionally restricted to new or duplicate. Never
translate an existing/error/checked filtered Check All into an unfiltered mutation.
`set_import_options` takes the captured revision and `skip_duplicates`; changing
eligibility preserves manual checks. Suspected duplicates require equal original
filename, byte size and a known precise capture clock. Existing catalog paths are
always excluded. Unknown capture metadata never falls back to modification time.

`preview_import_item` takes plan/item IDs, captured `expected_revision`, your own
`client_id` and monotonically increasing `generation`. It returns a file-backed
thumbnail or, with `detail: true`, a fitted 1600-pixel preview. For a true 1:1
region, also pass `viewport: {cx, cy, width, height}` with all four fields.
Centers are normalized 0–1; physical pixel dimensions are 1–2048 by 1–1536.
A viewport requires explicit `detail: true`. The reply's `width/height` describe
the output PNG; `full_width/full_height` describe the cropped full-resolution
canvas for ROI replies, and `roi` gives its actual clamped `[x,y,width,height]`.
Compute subsequent pans from that actual region, not the unclamped requested center.
Exact Fit/ROI repeats may return `preview_cache_hit=true` with no worker/GPU work;
they retain source, asset, plan revision and cancellation checks. Previewing does
not create a photo or configure import preview policies. Cancel only your own
preview generations through `cancel_preview`.

`apply_import(plan_id, expected_revision)` verifies selected originals/sidecars
and scanned directories, then imports the checked eligible rows atomically. Read
the returned plan state/error: changed sources or catalog conflicts fail without
partial catalog changes. Use `get_import` to inspect an uncertain response; never
retry application blindly. `cancel_import(plan_id)` interrupts pending work and
discards staging, preserving originals and any completed import. Up to 32 compact
receipts are retained. Review state is included in catalog backup/restore.
Add is the default. For Copy, pass `mode: "copy"`, an existing `destination`,
optional `organization` (`flat`, `source`, `date`) and `subfolder` (one folder name)
to `prepare_import`. Only `apply_import` writes the chosen destination. Source
hierarchy includes the selected root name; dates use the camera's civil date in
the captured `date_format`: `year_date` (default, `YYYY/YYYY-MM-DD`),
`year_month_day` (`YYYY/MM/DD`) or `date` (`YYYY-MM-DD`). Old presets without the
field keep `year_date`. Pass a new explicit value on preparation to override a
preset; interrupted transfers retain their original paths. Unknown capture dates
use `Unknown Date`, never modification time or host timezone. Review pages show
computed destination paths. Originals and recognized XMP are copied byte-for-byte;
existing targets are never overwritten, and all target names are preflighted.

On a ready Copy review, `get_import_destinations(plan_id, expected_revision)`
returns up to sixty target folders and counts of checked eligible originals.
Pass `next_after` as `after` to continue; an empty string is a valid cursor and
only null means the last page. `relative_path` includes the optional subfolder,
and an empty relative path denotes the destination root. XMP and second copies
do not increase photo counts; optional backup totals appear separately. This read
creates no directories and does not inspect whether folders exist. If the review
revision changes, explicitly read it again and restart paging. Do not use this
preview as a recovery journal or infer transfer completion from it.

Copy failures retain a journal and `interrupted` state. When phase is `copying` or
`copy_preparing`, use `resume_import_copy(plan_id, expected_revision)` only on an
explicit recovery request, not `scan_import`. Completed copies are revalidated;
unowned equal-byte files are never adopted. Cancellation keeps completed copies,
cleans owned scratch files and reports any unsafe cleanup. `get_import_copies`
returns sixty transfer receipts per offset, including after cancellation. A
restored catalog can inspect/cancel but cannot resume or clean the original
catalog's transfer. Read the plan after an uncertain reply; never replay blindly.
Move, DNG conversion and extended-attribute copying
remain unsupported. Copy requires a filesystem supporting exclusive hard links.

For an original-state backup, add `second_copy_destination` to a Copy
`prepare_import`, or use `set_import_backup(plan_id, expected_revision,
destination)` on a ready review. Pass null to clear it. The selected folder must
already exist, be separate and nonoverlapping with the main destination, and stay
outside selected source folders and the active catalog. Filesystem checks occur
outside catalog locks, followed by another captured-plan revision check.

Second copies use original filenames and recognized XMP in a captured
`Imported on YYYY-MM-DD` folder; renaming and import-time presets do not alter
them. `get_import` includes `copy.backup` destination/progress and checked-row
`second_destination` previews. `get_import_copies` labels transfers with `role`
`primary` or `second`. Overall copy counters include both roles; backup counters
are separate. A missing backup location or collision interrupts before catalog
application. Both roles are verified; backups never enter the catalog. Resume
retains captured destinations, while cancellation keeps published files in both
locations. Never disable/redirect a required backup to work around interrupted
application. These are one-time copies, not ongoing photo/catalog backup, and
same-filesystem destinations do not establish physical-drive redundancy.

Use `get_import_naming(plan_id)` for the saved Copy configuration, built-in
templates and supported token kinds. `preview_import_naming(plan_id,
expected_revision, settings, offset)` previews sixty checked destinations from an
unsaved draft. `set_import_naming(plan_id, expected_revision, settings)` captures
the complete configuration on a ready Copy plan. Add never renames originals.
Settings contain `enabled`, `template` (1–48 token objects), `custom_text`,
`shoot_name`, `start` (1–9999999999) and `extension` (`preserve`, `lower`, `upper`).
Token kinds are `literal` (required `text`), `filename`, `original_number`,
`folder`, `custom_text`, `shoot_name`, `sequence`, `index`, `total`, `year`,
`month`, `day`, `hour`, `minute`, `second`, `camera`, `import_number`, `image_number`. Number tokens accept optional
`digits` (1–10); other nonliteral tokens accept no additional fields.

`filename` is the source stem; the extension is appended automatically.
`original_number` uses the last ASCII digit run in the source stem. Sequence and
position follow checked eligible filenames (ASCII-NOCASE then stable item ID),
independently of review sorting. Capture tokens use the camera's civil time.
Missing values and invalid/overlong basenames fail visibly, never fall back to
mtime or silently truncate. Full collisions are preflighted before copying.
XMP adopts the new stem and original names remain the duplicate identity.

`list_filename_templates(offset)` pages thirty catalog-local template names and
a numeric revision. Read via `get_filename_template(template_id,
expected_revision)`. Save/create/update/rename via `save_filename_template(name,
template, expected_revision, template_id?)`; delete via
`delete_filename_template(template_id, expected_revision)`. Keep the loaded
template revision with its draft; listing a newer library never authorizes
overwriting it. Saved imports contain values independent of library edits/deletion.
Shared/Adobe template exchange, wider EXIF tokens, Library renaming and export
reuse remain unsupported.

`get_import_sequence` reads `{revision,next_import,next_image}`. Explicit
`set_import_sequence(expected_revision,next_import,next_image)` sets starts from
1 through 9999999999 and rejects stale revisions or an active reserved Copy.
Import # advances per nonempty import; Image # advances per newly cataloged
original. Virtual copies retain original provenance. Migration leaves historical
photo numbers unknown and initializes new counters at 1.

Plan/naming/preview replies contain `sequence` with `revision`, `import_number`,
`image_number` and `frozen`. Previews and saved presets do not consume numbers.
When enabled Copy naming uses either global token, `apply_import` requires
`expected_sequence_revision` from the reviewed plan. Copy captures tentative
values, checks every output, then atomically reserves the range with its copying
phase. If a concurrent import changes that revision before reservation, it returns
to `ready` with an explanation and refreshed names, without destination writes.
Review and explicitly apply again. Frozen reservations survive interruption,
cancellation and recovery; gaps are intentional. Never reset or reclaim them to
repair a failed Copy. Add/direct/folder-sync advance only upon new photo insertion.

For a ready review, `set_import_processing(plan_id, expected_revision, ...)` changes
one or more of `develop_preset`, `metadata_preset` and `keywords`. A preset choice
is `{preset_id, expected_revision}` from its own current preset-library page;
null clears that choice. Omitted settings stay unchanged. `keywords` is an array
of up to 100 additional names/paths; an empty array clears only those additions.
Resolved additional text is limited to 128 KiB of serialized JSON. Capture does
not create tags or photos. Preset settings and exact keyword hierarchy segments
persist with the plan, independently of later preset edits/deletion. `get_import_processing`
returns chosen names/IDs, additional keywords and the plan revision, without large
preset patches. Do not infer an empty metadata preset from omitted payload fields.

File descriptions are imported first. Captured metadata fields then replace only
their selected values; preset and additional keywords append. Merged IPTC/keyword
capacity, camera-profile mismatches and changed LUTs reject the complete import.
Develop settings initialize the new recipe and affect review previews. Backups
retain pending choices and LUT assets. Settings replies can advance only the same
acknowledged editor revision; stale/uncertain writes are never automatically retried.
Create a named metadata preset with the existing `save_metadata_preset` contract
before choosing it for import.

`list_import_presets(offset?)` lists thirty catalog-local configuration names with
an integer library revision. `save_import_preset(name, plan_id,
expected_plan_revision, expected_revision, preset_id?)` captures a ready review;
omit the ID to create or supply it to update. `get_import_preset(preset_id,
expected_revision)` reads options and compact processing summaries. Rename/delete
through `import_preset_action(action, preset_id, expected_revision, name?)`.
These configurations are separate from Develop/metadata preset libraries.

Pass `preset: {preset_id, expected_revision}` to `prepare_import` with newly chosen
`paths`. Explicit options override the saved options; null `second_copy_destination`
turns off backup. An explicit Add method omits inherited Copy destinations, but
passing destination fields explicitly with Add is invalid. Processing and naming
values remain frozen even if their source preset libraries change or are deleted.
Missing/changed LUT assets and stale configuration revisions reject preparation.

`restart_import_with_preset(plan_id, expected_revision, preset)` explicitly replaces
a ready review from its stored source selection. It resets checked rows and requires
new `scan_import` calls before application. Destination/source checks occur before
one atomic replacement; failures preserve the old ready plan. Older reviews without
a source receipt require a new source selection. Interrupted Copy transfers cannot
be replaced. Inspect `get_import` without a plan ID after an uncertain restart;
never replay it. Applying a configuration never copies photos by itself.
Shared/Adobe import-preset exchange and unsupported import options remain open.

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

## Metadata presets and descriptive IPTC

`metadata_schema` returns thirty supported `iptc_fields` and their JSON schema.
`edit_metadata.patch.iptc` merges only submitted fields; omitted fields survive.
Array values use actual string arrays, not comma-separated names. Empty checked
values clear; Date Created never changes source capture time. Merged IPTC is bounded
to 64 KiB of UTF-8 JSON. `get_photo` contains complete IPTC; list summaries omit it.
Supported IPTC participates in export previews/frozen jobs and folder-sync reads.
Catalog export includes all supported values; Copyright includes only rights IPTC.

`list_metadata_presets(offset, search)` returns thirty name/count summaries,
`fields`, storage mode and an opaque `revision`; details require
`get_metadata_preset(preset_id, expected_revision)`. Save a checked-field `patch`
with `save_metadata_preset(name, patch, expected_revision, preset_id?)`. Keywords
are path strings appended on application, never created while saving. New preset
names must be distinct under Unicode normalization/case folding; no implicit replace.
`metadata_preset_action` supports rename/duplicate (preset_id/name), delete
(preset_id), and storage (store_with_catalog), each at the captured revision.
Shared and catalog libraries remain separate; local presets are included in backups.

`apply_metadata_preset` takes a preset ID, captured preset `expected_revision` and
1–60 distinct targets with `photo_id` / `expected_metadata_revision`. When rating
is selected in the preset, every target must also include its `expected_rating`.
Any stale token, metadata/rating conflict, capacity or merged-IPTC error rolls back
the entire batch and any newly resolved vocabulary. Equal reapplication is a no-op.
Returned `revision` acknowledges this application's vocabulary changes; refresh
never authorizes rebasing an unrelated stale draft. Original files, recipes,
orientation and submitted jobs are preserved. Adobe preset exchange is unsupported.

## Develop presets

`list_develop_presets` returns thirty compact names per page, separately paged
groups, `field_groups`, supported `fields`, storage mode and an opaque `revision`.
Use `search`, `group_id`, `favorites`, `include_hidden`, `offset` and `group_offset`
to browse. `get_develop_preset(preset_id, expected_revision)` reads the partial
`patch` at that exact library state. Browsing never applies settings.

`save_develop_preset` takes the captured `photo_id` / `expected_photo_revision`,
selected `fields`, `name`, `group_name` and preset-library `expected_revision`.
Pass `preset_id` to update a custom preset. The default `duplicate_policy: error`
rejects equal names in the same group; `duplicate` explicitly keeps both and
`replace` replaces a single matching custom preset when creating. Do not infer
replacement authorization from an accidental name collision.

`develop_preset_action` requires the captured `expected_revision` and exactly the
fields for its action: `favorite` (preset_id/favorite), `rename` (preset_id/name),
`move` (preset_id/group_name), `duplicate` (preset_id/name/group_name), `delete`
(preset_id), `group_visibility` (group_id/visible), `group_rename` (group_id/name),
or `storage` (store_with_catalog). Built-ins allow favorite/duplicate; their group
can be hidden. Switching storage preserves both libraries without moving entries.
Shared Develop storage uses the injectable `LUMARAW_PRESETS_ROOT` path adapter
independently of keyword-set storage. Catalog backups contain local presets/assets.

`apply_develop_preset` takes `preset_id`, preset-library `expected_revision` and
1–60 distinct `targets` with `photo_id` / photo `expected_revision`. Capture those
revisions before applying. Any stale target, changed preset/scope or incompatible
camera profile rejects the whole batch. Only saved fields change; every changed
photo receives Develop history, and equal recipes do not increment revisions.
Metadata, independent orientation, originals and queued jobs survive. LUTs are
checksum-verified and retained in the target catalog. Neither failed nor uncertain
applications may be retried automatically with fresh revisions. Adobe preset
file exchange, Amount and ISO adaptation are not supported. Reviewed Add imports
can capture a partial Develop preset through `set_import_processing`.

## Photo orientation

`orient_photos` accepts one `action` (`rotate_left`, `rotate_right`,
`flip_horizontal`, `flip_vertical`) and up to sixty distinct `targets` containing
`photo_id` and captured visual `expected_revision`. It increments visual revisions
without changing metadata, Develop recipes/history or originals. Never use the
legacy recipe `rotation` field for this Library action. Grid targets all selected
photos; Loupe/Compare/Survey/Develop target the active photo. Painter captures the
action and photo revisions at mouse-down and commits once at mouse-up.

`orientation_state` returns a global `revision` and optional `latest.id` / `action`.
Pass the captured values to `undo_orientation(action_id, expected_revision)` to
restore the latest batch, preserving later Develop edits. Missing/changed targets
or a changed history head reject the entire undo. Keep stale operations visible;
never refresh and replay them silently. History retains fifty batches; Redo and
unified application Undo are not implemented.

Photo/job `orientation` is a 0–7 internal value: horizontal mirror when >=4, then
`value % 4` clockwise quarter turns. It applies after canonical Develop rendering;
it is not an EXIF orientation number. Export queues freeze it at submission.
Reset/recipe imports leave it intact; virtual copies inherit then edit independently.
Previews return `geometry.orientation` and effective canonical `geometry.crop_box`.
Native drawing maps displayed coordinates through this geometry only for a matched
fitted preview. Recipe JSON stays canonical. Calibration chart bounds continue to
use full EXIF-oriented sources, before catalog orientation and Develop adjustments.

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

Visible stack members include `stack_ordinal`, their one-based position in the
entire scoped stack. Filters and page boundaries do not restart numbering.
Collapsed covers have ordinal 1, while their badge shows `stack_count`.
`stack_position` is an internal sorting label that can be negative or have gaps;
never display it as an ordinal. Unstacked rows and flat `stacked: false` or
unsupported sources return a null ordinal.

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
