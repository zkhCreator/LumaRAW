# LumaRAW

A native macOS RAW darkroom with non-destructive editing, Metal-accelerated color processing, and a shared CLI/MCP interface for agents.

LumaRAW references your originals without changing them. The SwiftUI app and your agent work through the same local catalog service, with revision checks to prevent conflicting edits. No account, API key, or cloud service is required.

**Status:** source release, version 0.4.1. The packaged build targets Apple Silicon and macOS 14 or later; current validation was performed on macOS 26. Windows support is an architectural target, not a shipped application.

## Features

| Area | Capabilities |
| --- | --- |
| Import | Resumable Add review, thumbnail/Loupe inspection, checked selections, subfolder choice, suspected duplicates, and embedded/sidecar descriptions |
| RAW development | Nikon NEF/NRW and other LibRaw formats, as-shot white balance, exposure, highlights/shadows, relative temperature/tint, monochrome, and presets |
| Color | Custom tone curves, color mixer, camera-bound chart calibration, `.cube` LUTs, ICC soft proofing, and gamut warnings |
| Detail and composition | Full-resolution 1:1 viewports, noise reduction, sharpening, defringing, rotation, crop, straighten, and perspective |
| Local adjustments | Radial, gradient, luminance-range, and brush masks; manual lens distortion, vignette, and chromatic-aberration correction |
| Library | Folder tree/search/favorites/labels, ratings, flags, catalog metadata/keywords, regular/live smart collections, nested sets, Quick/target collections, SQL filters/sorting, manual/capture-time stacks, duplicate/missing indexing, virtual copies/shared snapshots, selective sync, and backup/restore |
| Culling | Grid/Loupe/Compare/Survey, anchored page selections, active-photo review actions, linked or independent full-resolution comparison viewports |
| Export | JPEG and 16-bit TIFF with embedded sRGB, Display P3, Adobe RGB, or ProPhoto RGB ICC profiles; frozen catalog XMP/keyword policies, persistent queue, pause/cancel/retry, and collision-safe filenames |
| Agents | 109 MCP tools, equivalent JSON CLI commands, and a bundled skill; app and agent edits share conflict detection |

## Build and run

Requirements: an Apple Silicon Mac, Xcode Command Line Tools, and [uv](https://docs.astral.sh/uv/). The Python requirement is 3.12 or 3.13; dependencies are pinned in `uv.lock`.

```sh
git clone https://github.com/zkhCreator/LumaRAW.git
cd LumaRAW
uv sync --frozen
uv run --frozen python scripts/build_macos.py --build-root /absolute/new-build-directory
open /absolute/new-build-directory/LumaRAW.app
```

Replace `/absolute/new-build-directory` with a new directory that does not already exist. The build compiles the Metal backend and SwiftUI shell, packages the Python engine, and applies a local ad-hoc signature. The resulting app does not require a separate Python installation. Developer ID signing, notarization, and public binary distribution are separate release steps.

Open `Package.swift` for Swift development. A standalone Swift executable needs `LUMARAW_ENGINE` set to the engine executable; use the build script for a self-contained app.

The default catalog is `~/Library/Application Support/LumaRAW Native`. Use `--catalog /absolute/catalog` or `LUMARAW_CATALOG` for a separate library. Imports reference original file locations; they do not copy photos. Back up a catalog before migration, and do not open the same SQLite catalog simultaneously with an older Qt application.

If another build already owns the catalog service, use **Settings → Background
Service → Connect with This Version** when image processing is idle. Newer engine
releases switch automatically when idle; a clean handoff preserves pending exports
and pause state. A genuinely older, pre-handshake service must finish its work and
exit first: close its app/agent clients and reconnect after three minutes. Failed
or uncertain exports still require explicit review/retry.

## Editing workflow

1. Press **⌘I** to choose photos or folders, then **Scan Photos**. Review Grid/Loupe previews, check the desired photos and choose **Import Checked**. Drag-and-drop and Finder file-open events open the same review. **File → Review Pending Import** reopens an unfinished review.
2. Double-click a photo to open Library Loupe. Press **D** or choose **Develop** to edit light, color, detail, composition, lens, and local adjustments.
3. Use **Tools** to draw a crop or mask, or enable the split before/after view. In Develop, press **\\** to toggle the original preview; in Library it opens filters.
4. Choose **1:1 Detail** to inspect a full-resolution viewport. Inspector sliders move the viewport horizontally and vertically.
5. Press **1–5** to rate, **0** to clear the rating, **P** to pick, **X** to reject, or **U** to clear the flag. With the gallery focused, arrow keys select photos and Return opens Loupe.
6. Command-click to toggle selection; Shift-click selects a contiguous range on the current page. **⌘A** in the focused grid selects the visible page. Grid rating/flag/metadata actions apply to the selection; Loupe, Compare, Survey and Develop actions apply to the active photo. **Photo → Sync Selected Photos** copies selected adjustment groups; composition, masks, and camera profiles are excluded by default.
7. Press **⇧⌘E** to export. Choose a format, color space, long-edge size, and filename template. Existing files are preserved.

Press **G / E / C / N** with a photo view focused to open Grid / Loupe / Compare / Survey.
Compare keeps a Select photo beside a changing Candidate: use arrows to navigate,
Swap to exchange roles, or Make Select to promote the candidate. Linked zoom/pan
can be unlocked and synchronized. Survey fits the selected page photos together;
its remove button only deselects a photo. Click a selected photo to make it active
without losing the group. Full-resolution comparison and fitted Survey use separate
preview requests; unchanged comparison frames are retained.

Import uses **Add**: originals stay in their current locations. Scanning and
previewing do not add photos to the library. Suspected duplicates share an original
filename, file size and known capture time; an unknown date never uses modification
time as a substitute. Turning duplicate exclusion off makes those candidates
selectable. Already cataloged paths remain unavailable. Check/Uncheck All affects
the current category across its pages; clicking a preview only changes focus.
Closing preserves the review, while Cancel Import Review discards its staging.
Interrupted scans resume explicitly. Changed sources/sidecars or catalog conflicts
reject application without a partial import. Copy, Move, Copy as DNG and import-time
presets are not implemented yet.

Adjustments save automatically. Each photo supports up to 50 undo steps, named snapshots shared by a source’s master and virtual copies, and portable recipe bundles. The full recipe editor supports precise curve points and brush paths. Submitted exports retain their original recipe snapshot even if you continue editing.

Use **Photo → Stacking** to group, unstack, remove members, choose a cover or
reorder photos. **⌘G / ⇧⌘G** group/unstack; with a photo surface focused, **S**
expands/collapses, **⇧S** moves to the top, and **⇧[ / ⇧]** move up/down. The count
badge also expands/collapses. Folder stacks require the same physical folder;
regular and Quick collections have independent stacks. Smart collections and
collection sets show individual photos. A collapsed stack selects only its cover,
so ratings, edits and collection additions do not silently include hidden members.
Expand all stacks in a source from the menu, or turn off **Library → Show Photo
Stacks** to search every photo without changing saved stack visibility. New
virtual copies join an expanded folder stack, including copies created inside a
collection. To split an expanded stack, select a proper subset beyond just its
cover and choose **Split Stack**; a single selected member becomes unstacked.

**Auto-Stack by Capture Time…** previews all catalog photos in one explicit folder
(excluding subfolders) or regular/Quick collection, regardless of the current
selection and filters. Gaps equal to or longer than the selected duration start a
new stack. Applying replaces that source's existing stack organization and rejects
a stale preview. **Refresh Capture Times** reads metadata in batches with progress
and a Stop button; it does not hash or decode photos. Unknown dates stay unstacked.
Classic TIFF-family, JPEG and PNG EXIF are supported; other containers and malformed
metadata remain unknown. Dates without offsets use the camera clock, so mixed
timezone sources need review. Older catalogs need a refresh to populate precise
clocks; original files remain unchanged.

The **Folders** sidebar follows imported photo locations with bounded child pages,
direct/descendant photo counts, text search, favorites and color labels. Selecting
a folder changes the browsing source while preserving metadata filters.
**Include Photos from Subfolders** changes the source scope and displayed counts.
Root-folder menus expose **Show Parent Folder** and **Hide This Parent**; parents
with directly contained photos cannot be hidden. These actions change catalog
presentation only. An unavailable directory keeps its catalog counts and is marked
in the sidebar. **Go to Folder in Library**, available from a photo's menu or
inspector, clears filters and shows individual photos in import order, locating the
target even beyond the first page. Folder rename/move, multi-folder
selection and empty-directory import remain unfinished.
Use **Folder Options → Refresh Folders** after a volume goes offline or returns;
directory availability is checked when folder pages are read.

For a folder moved outside the app, choose **Find Missing Folder…** from its
sidebar menu. Select its new directory, review the bounded scan and click
**Reconnect**. Known hashes are verified; files without an indexed hash are
identified by relative path and are clearly counted. Missing files retain their
new paths and missing status. Conflicts block the complete operation. Edits,
copies, keywords, stacks and pending export settings are preserved atomically.
Existing destination folders combine memberships and favorites while retaining
their own color labels. **Folder Options → Resume Folder Relocation…** reopens a
saved plan; cancellation discards staging without moving any originals. Active
image work defers application until an explicit retry. Overlapping old/new folder
trees and colliding catalog photo paths are not supported.

Choose **Synchronize Folder…** from an available folder's menu to scan its full
subtree. Review new files, missing originals and changed metadata in bounded
pages; select individual files, all items of one kind, or a folder subtree.
Large metadata opens **Review Complete Metadata…**, preserving every scanned
description and paging full keyword paths without enlarging the file list.
**Synchronize** imports selected new files in place. **Remove missing photos from
catalog** is off by default: enabling it also removes their virtual copies, edits,
snapshots and memberships, while preserving export receipts and files on disk.
Scan/read metadata options are independent. Supported XMP fields include title,
caption, copyright, integer rating, standard color labels and keyword paths;
capture-time headers are refreshed without decoding pixels. Sidecar properties
override standard embedded TIFF/JPEG/PNG XMP; virtual copies retain independent
descriptive metadata and Develop recipes are preserved. Review unsupported-field
notes and errors before applying. **Folder Options → Resume Folder Synchronization…**
restores a saved scan or review. This is not yet the complete Lightroom Import
Dialog, duplicate policy, full IPTC/XMP/ACR support or missing-empty-folder removal.

The **Keyword List** supports nested keywords, synonyms, search and 60-item pages.
Its checkboxes add/remove tags on the Grid selection, or just the active photo in
Loupe, Compare, Survey and Develop. A minus indicates a mixed selection. Create a
keyword from the **+** menu, optionally assigning it to the captured selection in
the same transaction. Context menus create children, edit names/synonyms/parents,
show matching photos or delete a subtree and its assignments. Photo files and
recipes remain unchanged. List counts describe direct assignments; **Show Photos**
also includes nested keywords and clears other source/filter restrictions.
Large vocabulary rows show an abbreviated path; **Edit Keyword…** reads the full
path, synonyms and options before opening. Parent selection also resolves complete
paths. A changed keyword list requires reopening the editor with fresh values.
**Metadata → Import Keywords…** adds a UTF-8 tab-indented text or keyword-options
CSV dictionary. It preserves existing keywords and their attributes, synonyms and
photo assignments. The entire file must validate before any new tags are added.
**Export Keywords** writes a new file: CSV includes export options and the manual
**Person Keyword** classification; text retains hierarchy, synonyms and Include on
Export. Files may contain up to 64 MiB and one million unique tags. Existing output
files are never replaced. The same commands are available in the Keyword List menu.
The metadata editor accepts qualified paths such as `Places | Coast` (also `>` or
reversed `<`). Equal leaf names under different parents retain separate IDs;
ambiguous unqualified names require a path. Keyword changes remain in the catalog.
Long assignment lists open **Review Keywords…** in the inspector. Full paths are
paged without shortening names. **Choose Existing Keywords…** in the metadata
form builds a replacement selection; additional typed paths can create new tags.
Picker changes stay local until the metadata form is saved. Unchanged single-photo
assignments are preserved while editing other fields, and batch replacement uses
complete tag identities rather than resending large display paths.
Keyword forms include **Include on Export**, **Export Containing Keywords** and
**Export Synonyms**. Each parent can stop traversal to higher ancestors; excluded
names and their synonyms are omitted from flat keywords and hierarchy paths.
**Will Export…** in the inspector previews resolved words and hierarchy pages.
Keyword sets, Painter and vocabulary file exchange are described below;
unused-tag purge and metadata undo remain pending.

The export sheet offers **None**, **Copyright Only**, or **Catalog Descriptions
and Keywords**, plus optional Lightroom hierarchy paths. The catalog option
includes title, caption, copyright, rating/rejection and standard color labels.
Exported JPEG/TIFF files contain XMP; large JPEG keyword packets use Extended XMP.
Recipes, local asset paths and source filenames are not embedded as descriptions.
ICC profiles remain embedded regardless of metadata policy. Camera EXIF, GPS,
complete IPTC and Adobe Develop metadata copying remain incomplete.
Recipes, metadata and resolved keyword policies are frozen together at submission;
later edits, renames, removals and policy changes do not alter pending jobs.
Legacy queued jobs retain their original empty descriptive-metadata snapshot.

Use **Collections → New Collection** to create a regular collection or a smart
collection with live rules. Add/remove selected photos from a regular collection
through its contextual menu or **Organize**. Collection sets lazily expand and
show the union of their nested regular and smart collections. **Edit / Move**
changes a collection's parent; **Duplicate** copies its rules and memberships.
Creating a regular collection can include the selected photographs atomically.
Collection removal preserves catalog
photos and originals. **Filter** combines rating, flag, color, keyword, text,
camera and folder criteria; sorting is stable across 60-photo pages. Camera and
capture-time filters require the library index to have read that metadata.

The **Quick Collection** is persistent and unique per catalog. Its contextual menu
can save it as a regular collection, optionally clearing it in the same operation.
Set any regular collection as the target; a **+** identifies it. Press **B** with a
photo view focused, or click a thumbnail circle, to add/remove target members.
A fully included selection is removed; otherwise selected photos are added.
Target actions reject stale target/membership versions from another client. Delete
in a focused photo view removes membership when a regular/Quick collection is open.
Deleting a set also removes its nested collections, after confirmation, while
preserving catalog photos and originals.

**Organize → Edit Metadata** edits title, caption, copyright, keywords and labels.
For a batch, check only the fields to apply; keywords replace the selected photos'
current keyword assignments. These changes are catalog-only, with separate metadata
revision checks; they do not write EXIF/XMP into originals. Warm grid pages reuse
completed thumbnail paths in one service call without starting image workers.
Mac grid and filmstrip thumbnails show the saved edits, including crop, rotation,
color and masks, through the shared renderer. Recipe changes invalidate only the
affected image; metadata edits reuse its thumbnail. External edits to any visible
photo are detected by bounded summary polling. Refresh Library rechecks source
files and retries missing or failed thumbnails. Legacy CLI thumbnail requests
default to source previews; pass `kind: "developed"` for the edited result.

The **Keyword Set** sidebar provides nine slots and **Recent Keywords**. Click a
slot or use its Option-number menu shortcut to add that keyword: Grid applies to
the selection; Loupe, Compare, Survey and Develop apply to the active photo.
Create a blank set or save the current slots as a preset. **Edit Set → Change**
keeps a temporary draft; **Update Preset** saves edits and a changed name. Choosing
another set discards the draft. **Discard Draft** returns to the saved version.
Deletion removes the preset and preserves assigned photo keywords. Recent entries
retain catalog identities, including renamed or legacy literal keywords.

Sets are shared across catalogs by default. **Settings → Keyword Sets → Store
Keyword Sets with This Catalog** switches storage without moving existing sets;
switch back to access them. Catalog backups include local sets and recent entries,
but shared presets remain in the separate user preset store. Platform directory
selection is isolated behind an adapter; `LUMARAW_PRESETS_ROOT` explicitly overrides
it for isolated tests or deployments. Built-in Adobe presets, `.lrtemplate` exchange,
suggestions remain pending. Native shortcut dispatch and rendered
interaction still require desktop acceptance.

**Metadata → Set Keyword Shortcut** configures one or more keywords independently
of the nine-slot presets. Choose existing tags by identity, or type comma-separated
new paths. **Use This as Keyword Shortcut** is also available on a Keyword List
row; a plus marks shortcut members. **Add Keyword Shortcut** and Shift-K in a
focused photo view use the current selection/active-photo scope, even with Painter
put away. Setting the shortcut does not tag photographs.

In Grid view, enable **Painter** (Command-Option-K), choose Keywords, Rating, Flag,
Color Label, Target Collection, Rotation, Develop Preset or Metadata Preset, then click/drag across thumbnails. Touched thumbnails highlight;
mouse-up applies one transaction without selecting the touched photos. Hold Option
before a keyword stroke to remove only the shortcut's keywords. Choose None or
Unflagged to clear the other attributes. Esc puts the tool away and discards an
unsubmitted stroke. Changing the page/source cancels that stroke; a stale target
rejects the whole batch. Strokes are bounded to the current sixty-photo page.
Use **Choose from Sets…**, its Metadata menu action, or Shift with the Painter
focused to open a multi-set chooser. Select individual slots or all slots in a set,
switch sets to add more, and review/remove choices before **Load Painter**. This
replaces the loaded shortcut; Cancel leaves it unchanged. Browsing does not change
the sidebar's active preset. Recent choices retain IDs, including legacy literal
names; custom choices retain the text shown when selected. The draft is bounded
to one hundred choices. Scrolling between pages and rendered
pointer/keyboard acceptance remain pending. Keyword, rating, flag, label and
collection strokes preserve Develop recipes; originals remain unchanged in every mode.

**Metadata Presets…** in the Metadata menu or inspector manages named, selective
metadata templates. Create a blank preset or start from the current photo, then
check individual fields or use Check All / None / Filled. A checked empty scalar
clears that field; unchecked fields survive. Preset keywords append to existing
assignments. Search thirty names per page, edit, duplicate, rename or delete, then
apply to the Grid selection or active photo in other views. Load a preset into
Painter to apply it to touched thumbnails. Stale preset, vocabulary or photo
state rejects the entire action, including rating changes made outside this form.
Shared storage is the default; Store Metadata Presets with This Catalog switches
repositories without moving or deleting entries, independently of other presets.

The ordinary metadata editor and presets support thirty descriptive IPTC fields,
including creators/contact information, caption accessibility text, location,
credit/instructions and rights. Lists use one value per line, preserving commas
inside names. Date Created is descriptive and never changes source capture time.
Supported fields survive virtual copies and catalog backups, participate in
frozen export metadata, and can be read through folder synchronization. Copyright
export policy includes rights fields without creator/contact/location information.
Adobe `.lrtemplate` exchange, IPTC Extension structures, custom textual labels,
metadata Undo and full reference acceptance remain open.

**Target Collection** paints into the current regular collection or Quick
Collection. Use **Set as Target Collection** on a collection to choose it. The
Painter shows the captured destination; Option removes touched photos from it.
Repeated painting adds membership and never toggles existing members off. A target
switch, rename, deletion or membership change during a stroke rejects that stroke;
it is never redirected to a new destination. Removing visible members refreshes
the source, including its empty state. No photo metadata or recipe revisions change.

**Photo → Rotate Left / Rotate Right** (Command-[ / Command-]) and **Flip Horizontal /
Flip Vertical** change catalog orientation. Grid actions use all selected photos;
Loupe, Compare, Survey and Develop use the active photo. Painter **Rotation** applies
its captured rotate/flip action once to each touched thumbnail. A stale visual
revision rejects the entire stroke. Orientation survives Reset All Adjustments
and recipe imports; **Undo Last Rotation or Flip** restores the latest orientation
batch while preserving later Develop edits. This separate, fifty-batch history has
no Redo or unified Command-Z integration yet. A missing target blocks that batch's
undo. New virtual copies inherit orientation and can then change independently.

Previews, before/detail views, both thumbnail types and exports include orientation.
Export jobs freeze it when queued. Existing masks and crops rotate with the image;
drawing and inspector crop/mask coordinates follow the displayed direction.
Drawing is available on a matching fitted preview, not a 1:1 viewport. Advanced
recipe JSON retains canonical coordinates and the legacy Develop `rotation` field.
Calibration rectangles refer to full EXIF-oriented sources before catalog/Develop
edits. Rendered desktop interaction and Lightroom Mac reference acceptance remain
unverified.

**Photo → Develop Presets…** (also in the Develop inspector) opens the preset
library. Create a preset from the current photo, enter a name/group and select
individual settings; Check All/None controls that selection. Applying preserves
unchecked settings. Browse/search thirty presets at a time, filter favorites or
groups, show/hide groups, and duplicate, rename, move, update or delete custom
presets. The five LumaRAW built-ins can be favorited and duplicated. Existing-name
conflicts require an explicit Keep Both or Replace Existing choice.

**Apply to Photos** uses all selected photos in Grid and the active photo in other
views. Each changed photo receives ordinary Develop undo history; applying equal
settings adds no history. Catalog rotation, descriptive metadata, originals and
queued exports are preserved. In Grid, **Load Painter** captures the chosen preset;
mouse-up applies it once per touched photo. Later preset or photo changes reject
the whole stroke, and refreshing the browser does not silently update that capture.

Develop presets are shared across catalogs by default. **Store Develop Presets
with This Catalog**, in the library or Settings, switches to catalog-local presets
without moving existing ones. LUT assets are retained with their preset and copied
into a target catalog on application; local presets and assets are backed up with
the catalog. Hover previews, Amount, ISO-adaptive presets, Adobe XMP/`.lrtemplate`
exchange and import-time application remain pending.

Virtual copies share the original file while keeping independent adjustments,
ratings and catalog metadata. Use **Photo → Create Virtual Copies**, rename with
**Edit Metadata → Copy name**, and use **Set Copy as Master** to switch roles
without replacing either edit. **Show Master and Copies** opens a bounded family
view; filters can show only masters or virtual copies. In a regular or Quick
collection, creation adds the new copies to that collection. Removing a virtual
copy requires confirmation and removes its private history/memberships; shared
snapshots and submitted export jobs survive. Folder-stack presentation and the
copy-name export template token remain pending.

## Metal acceleration

Choose **Settings → Acceleration** to select **Auto**, **CPU**, or **Metal**. Auto prefers Metal where supported and records any fallback. Settings show the actual device and recent processing time.

Metal accelerates grading and output color conversion. **NEF parsing, decompression, white balance, and AHD demosaicing remain on the CPU through LibRaw.** Geometry, neighborhood filters, and some mask/LUT operations also use the CPU. The app, CLI, and MCP share this backend policy.

On a limited Apple M4 / Nikon D4 sample, full-size TIFF export improved from 2.70 to 1.10 seconds for a default recipe, and from 4.87 to 1.14 seconds for a curve/color-mixer recipe. These include process startup and encoding; they are not universal speedup claims. See [Metal design](METAL.md) and [validation scope](VERIFICATION.md).

## MCP and agent skill

The **Agent Connection** page provides the exact MCP configuration for your installed app. A portable example is in [examples/mcp.json](examples/mcp.json):

```json
{
  "mcpServers": {
    "lumaraw": {
      "command": "/Applications/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine",
      "args": ["--mcp"]
    }
  }
}
```

Update `command` if the app is installed elsewhere. Add `"--catalog", "/absolute/catalog"` to use a separate catalog. Without that option, MCP and the app share the default catalog. Configure your client explicitly; LumaRAW does not change other applications or global agent settings.

The [LumaRAW skill](skills/lumaraw/SKILL.md) is also bundled in `LumaRAW.app/Contents/Resources/skills/lumaraw/`. Copy the whole `lumaraw` skill folder into your agent's skill directory or reference it directly. It covers revision conflicts, selective sync, immutable exports, memory limits, and result verification.

### CLI

```sh
ENGINE='/Applications/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine'
"$ENGINE" status
"$ENGINE" recipe_schema
"$ENGINE" list_photos --params '{"offset":0}'
"$ENGINE" get_photo --params '{"photo_id":1}'
"$ENGINE" edit_photo --params '{"photo_id":1,"expected_revision":0,"patch":{"exposure":0.35,"highlights":-20}}'
"$ENGINE" preview_photo --params '{"photo_id":1,"detail":{"width":1024,"height":768}}'
"$ENGINE" enqueue_exports --params '{"photo_ids":[1],"destination":"/absolute/exports","format":"tiff16","options":{"space":"prophoto"},"request_key":"export-001"}'
"$ENGINE" list_jobs
```

Use the current revision from `get_photo` when editing. Long JSON can be passed on stdin. CLI responses use `{ok,result}` or `{ok,error,type}`; MCP stdio uses JSON-RPC. Run from source with `uv run --frozen lumaraw <method>`.

`recipe_schema` is the authority for supported parameters, presets, and sync groups. Group names are now English: `White Balance`, `Light`, `Color`, `Tone Curve`, `Detail`, `Lens`, `Composition`, `Local Masks`, `Camera Profile`, and `LUT`. Clients using the earlier local build's translated group names must refresh the schema. Existing recipe fields, originals, and user-entered names are unchanged.

## Architecture

Development priorities, contributor instructions and the Lightroom Classic parity
ledger are in [AGENTS.md](AGENTS.md), [DEVELOPMENT.md](DEVELOPMENT.md) and
[PARITY.md](PARITY.md). Full non-AI Lightroom Classic parity is work in progress.

```text
SwiftUI app ── JSON CLI ──┐
                         ├── Local catalog broker ── SQLite + persistent queue
Agent ─────── MCP stdio ──┘             │
                              Disposable image worker
                                       │
                         LibRaw decode → CPU / Metal → new output file
```

The portable Python core owns recipes, color, storage, and jobs. SwiftUI owns presentation and native interaction. Metal sits behind a narrow C ABI with a CPU reference/fallback. Windows can reuse the core and command contracts with a separate native shell. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Validation and limits

```sh
uv sync --frozen
uv run --frozen python scripts/build_metal.py
LUMARAW_TEST_NEF=/absolute/photo.NEF LUMARAW_REQUIRE_METAL=1 uv run --frozen pytest -q
```

Without a real NEF fixture, RAW integration tests explicitly skip. Metal tests can skip when the optional backend is absent unless `LUMARAW_REQUIRE_METAL=1` is set. See [TESTING.md](TESTING.md) for native, packaged-engine, recovery, and official MCP-client probes.

- Non-destructive editing leaves original files unchanged. It does not make demosaicing or color transforms mathematically reversible; JPEG is lossy and 16-bit TIFF is not reversible sensor RAW.
- Nikon NX Studio, Picture Control, and Active D-Lighting matching are not guaranteed. HE/HE* support depends on LibRaw. Camera-specific accuracy needs real captures and reference measurements; synthetic chart tests verify algorithms only.
- Lens correction uses manual coefficients, without an automatic lens database. High-bit-depth ordinary TIFF/PNG import is rejected rather than silently reduced; 16-bit TIFF export is supported.
- RAW decoding still allocates a full frame. Postprocessing uses strips and one image worker per catalog. The effective budget is capped at 70% of available memory, with estimates and 50 ms RSS sampling; this is not an OS hard limit or a machine-wide quota.
- Complete EXIF/GPS/MakerNotes copying, DCP, spot removal, cloud sync, and a comprehensive camera compatibility matrix are not implemented.
- Windows, Intel, older macOS, VoiceOver, full keyboard traversal, and end-to-end monitor color management are not fully validated. Native controls alone do not establish accessibility acceptance.

## License and source publication

Original code is licensed under [MIT](LICENSE). Dependencies and ICC assets retain their own terms and attribution; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Project documentation, UI labels, built-in names, errors, examples, and agent instructions use English. User filenames and catalog content retain their original text and Unicode support.

Run `python3 scripts/check_public.py --strict` on a clean source snapshot. To package a development checkout while excluding generated local data:

```sh
python3 scripts/package_public.py /absolute/new-source.zip
```

See [PUBLIC_RELEASE.md](PUBLIC_RELEASE.md) for the publication boundary. Private catalogs, RAW fixtures, logs, credentials, and old binary deliveries do not belong in the source repository.
