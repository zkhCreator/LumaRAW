# Validation Scope

The following 0.4.0 results were recorded locally on Apple M4 and macOS 26. Raw receipts containing private catalog, photo, and machine paths are excluded from public source. This summary is not a substitute for independently auditable raw results; reproduce checks with your own fixtures using [TESTING.md](TESTING.md).

## Historical processing and workflow checks

| Check | Observed result and scope |
| --- | --- |
| Python suite before source-publication changes | 89 passed, no skips; real Nikon D3S NEF and required Metal execution |
| Native state | 15 assertions covering selection, empty exports, concurrent edits, and undo |
| MCP | Official Python client exercised 27 tools and Metal preview/export receipts |
| Batch | 12/12 exports from repeated D3S/D4 samples, with GPU dispatch checked for each job; not 12 independent camera samples |
| CPU/GPU parity | One full-size D4 4940×3292 16-bit ProPhoto TIFF comparison, ICC embedded; maximum difference of one 16-bit code value |
| Desktop interaction | Import, development, exposure, empty filters, settings, full-size TIFF export, and CPU/Auto switching were exercised |

## Limited-sample performance

Full-size D4 TIFF, including process startup and encoding:

| Recipe | CPU | Metal | Ratio |
| --- | ---: | ---: | ---: |
| Default | 2.697 s | 1.096 s | 2.46× |
| Curves and color mixer | 4.870 s | 1.142 s | 4.27× |

LibRaw decoding remains on CPU; masks/LUTs can use a hybrid path. These samples do not establish general camera compatibility or universal speedups. Memory budgets combine estimates with periodic RSS sampling; full-frame RAW decoding remains. Large images/recipes can be rejected by the memory budget. Preserve those failures and adjust the budget or output size rather than treating successful samples as universal acceptance.

## Source-publication checks

The source cleanup added 10 publication-gate regressions to the original 89 tests. The 99-test suite passed with a real D3S fixture and required Metal execution. A complete macOS build and ad-hoc signature verification also passed. Source and archive scans excluded local receipts, precompiled libraries, private paths, and image EXIF metadata while preserving third-party notices.

The English source revision changes project-owned text and public sync-group/preset names. Existing recipe field keys and user data remain unchanged. The English revision passed 100 Python tests with no skips (real D3S and required Metal), 15 native state assertions, and the official MCP client probe with 27 tools and actual GPU preview/export dispatch. The packaged app declares English localization and passed ad-hoc signature verification. Gallery/develop, export, and settings were inspected on the desktop; the sidebar label was shortened after observing truncation. This focused language/layout check is not full VoiceOver or keyboard acceptance.

The engine AST is unchanged apart from string constants. A new service regression verifies that the advertised English Light sync group copies exposure while preserving unrelated crop and white-balance settings. Final source and archive checks cover 142 files with no scanner findings; all 127 UTF-8 text files have no remaining CJK text or punctuation. Pattern scanning does not establish every aspect of language quality or absence of unknown secrets. Rerun checks for later changes.

## Unverified boundaries

- Windows hardware, Intel, and older macOS versions; Windows currently has core/IPC adapter code only.
- VoiceOver, complete keyboard traversal, and end-to-end monitor color management.
- Nikon NX Studio/Picture Control equivalence, every camera model, and HE/HE* variants. Camera accuracy requires real captures and same-scene references.
- Developer ID, notarization, and complete dependency obligations for public binary distribution.

Private original receipts are intentionally not included in this repository.
