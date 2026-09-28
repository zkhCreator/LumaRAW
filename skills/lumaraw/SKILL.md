---
name: lumaraw
description: Develop and organize local RAW photographs with LumaRAW through MCP or its packaged CLI. Use for Nikon NEF editing, preview inspection, reversible recipe changes, catalog organization and bounded batch exports.
---

# LumaRAW local darkroom

Use the LumaRAW MCP tools when connected. The native app's **Agent Connection** page shows the exact command and catalog path. App, CLI and MCP use the same service. No login, API key or network service is needed.

If MCP is unavailable, call the packaged engine at `<LumaRAW.app>/Contents/Resources/Engine/LumaRAWEngine`. Pass `--catalog <catalog-path> <method>` and a JSON object on stdin. `status` and `recipe_schema` need no input. Source checkout fallback: `uv run --frozen lumaraw --catalog <path> <method>` from the project directory. The CLI wraps results in `{ok,result}` or `{ok,error,type}`; stdout of `--mcp` is JSON-RPC only.

## Editing workflow

1. `lumaraw_status` identifies the active catalog; do not assume an unrelated catalog is the user's library.
2. `lumaraw_import_photos` takes explicit local file or directory paths. Imports reference originals; moving originals makes them offline. `lumaraw_list_photos` paginates in 60-photo pages and returns summaries. `lumaraw_get_photo` returns a full recipe and revision.
3. Read `lumaraw_recipe_schema` for defaults, numeric limits and presets. Send a **partial** `patch` to `lumaraw_edit_photo` with `photo_id` and `expected_revision`. Preserve crop, masks, LUT and calibration unless the task asks to change them. On `ConflictError`, re-read and reconcile; do not blindly overwrite the newer edit.
4. Inspect `lumaraw_preview_photo`'s local `preview` and `before` image paths. Add `detail: {cx: 0.5, cy: 0.5, width: 1024, height: 768}` for a true full-resolution viewport. The normal preview is reduced resolution. Do not claim Nikon color accuracy from appearance alone.
5. Save named versions before exploratory changes if useful. Undo affects the last recipe edit; ratings and flags are separate.

Example edit arguments:

```json
{"photo_id": 12, "expected_revision": 3, "patch": {"exposure": 0.35, "highlights": -20, "shadows": 12}}
```

## Library organization

`list_photos` accepts `filters`, `collection_id`, `sort` and `descending`, and
returns a clamped offset plus at most 60 summaries. `list_collections` paginates
regular and smart collections. Use `save_collection` with `collection_id` and
`expected_revision` for updates; `collection_membership` applies only to regular
collections and also requires their revision. Deleting a collection never removes
photos or originals. Smart rules evaluate current metadata when the library is queried.

`edit_metadata` takes at most 60 `{photo_id,expected_metadata_revision}` targets and
a shared `patch` containing title/caption/copyright/color_label/keywords. Read each
target before editing; keywords replace the current set. The response contains a
single normalized patch and per-photo metadata revisions, not newer recipe state.
Conflicts leave the whole batch unchanged. Metadata stays in the catalog; EXIF and
sidecars are not rewritten. `cached_thumbnails` returns existing paths for a bounded
page without starting workers; use `thumbnail` for missing entries. Source thumbnails
do not represent developed edits.

## Batch and output

- `lumaraw_sync_photos` copies only named groups and requires every target's current revision; `Composition`, `Local Masks`, `Camera Profile` and `LUT` are separate explicit choices.
- `lumaraw_enqueue_exports` requires a new `request_key` per logical submission. Persist and reuse that same key for an uncertain submission retry. The same key with changed arguments is rejected. Queue parameters are immutable snapshots; later edits do not change pending exports.
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
