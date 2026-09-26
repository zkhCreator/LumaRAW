# Metal Compute Backend

The optional backend plugs into `lumaraw.accelerators.grade_output`. A small Objective-C++ dynamic library exposes a C ABI, loaded by Python through ctypes. SwiftUI, CLI, and MCP continue to use the same service and recipes. Windows retains the CPU path; Direct3D/Vulkan adapters are not implemented.

## CPU/GPU split

| Stage | Implementation |
| --- | --- |
| NEF metadata, decompression, white balance, AHD demosaicing, camera matrix | LibRaw on CPU |
| Crop/rotation/perspective/distortion sampling; denoise/sharpen/defringe | CPU with overlapping strips |
| Exposure, tone, contrast, saturation/vibrance, curves, OKLab mixer, camera profile matrix, monochrome | Fused Metal grading kernel, or CPU reference |
| Masks and LUT | Complete CPU grading followed by Metal output conversion; reported as hybrid |
| Output matrix, sRGB/P3/Adobe/ProPhoto encoding, gamut flags | Metal, or CPU fallback |
| ICC soft proof, histogram, PNG/JPEG/TIFF encoding | CPU; exported files retain ICC profiles |
| Native display | sRGB-tagged NSImage; no custom MTKView canvas |

Metal accelerates decoded pixels. It does not parse or decompress NEF on the GPU. Original files, recipe semantics, cache space, and ICC definitions remain unchanged. FP32 CPU/GPU results are not guaranteed to be bit-identical.

## Memory, lifetime, and fallback

Each disposable worker owns its Metal device, queue, pipeline, and reusable shared tile buffers. No extra persistent image process is introduced.

RGB input and output each use 12 bytes per pixel; gamut flags use one byte. Shared buffers are bounded by the minimum of 100 MiB, 15% of the worker budget, and four million pixels. Growth releases old buffers first. Output is copied back only after a successful command.

Auto mode uses the CPU for tiles below 16,384 pixels or above the buffer allowance. Initialization or command failure triggers CPU fallback for the remainder of that request and records the reason. Explicit Metal mode reports GPU initialization/command failures; small-tile and memory limits still apply.

RAW admission estimates, the dynamic 70% memory cap, RSS sampling, cancellation, broker monitoring, and atomic output publication remain active. Shared-buffer accounting does not include all driver allocations, and RSS is not a machine-wide hard quota.

`MTLStorageModeShared` and `waitUntilCompleted` establish CPU/GPU ordering. Fast math is disabled. Shaders compile on first use; the OS shader cache may help later processes. No separate Metal command-line tool download is required.

## Public contract

`settings.compute_backend` accepts `auto`, `cpu`, or `metal` and defaults to `auto`. It is catalog processing policy, not a recipe change.

Preview and completed-job receipts include `processing`: actual backend/device, Metal grading/output tile counts, CPU tile counts, GPU and dispatch time, initialization time, shared-buffer peak, fallback reasons, worker time, and named stage timings. Status/settings expose the latest worker receipt. A present library alone does not prove GPU execution.

`source_decode` includes its detailed RAW sub-stages, so stage durations overlap. Worker time excludes Python startup; the benchmark's wall time includes startup and encoding. GPU time covers Metal commands only.

## Build and validate

```sh
uv sync --frozen
uv run --frozen python scripts/build_metal.py
LUMARAW_REQUIRE_METAL=1 LUMARAW_TEST_NEF=/absolute/photo.NEF uv run --frozen pytest -q
uv run --frozen python scripts/build_macos.py --build-root /absolute/new-build
uv run --frozen python tests/acceleration_probe.py \
  --engine /absolute/LumaRAW.app/Contents/Resources/Engine/LumaRAWEngine \
  --fixture /absolute/nikon-d4.NEF --work /absolute/new-probe
```

The build uses a portable `@rpath` install name and compiler source-path mappings. Generated libraries are excluded from the source archive.

Compare the same NEF, recipe, dimensions, and ICC space on CPU and Metal. Measure cold/warm application caches, full-size export, 1:1 viewports, and pixel differences. An empty application cache does not mean an empty OS file cache or Metal shader cache. See [VERIFICATION.md](VERIFICATION.md) for measured scope.

Implementation references: [Apple shared storage](https://developer.apple.com/documentation/metal/mtlstoragemode/shared), [Metal command structure](https://developer.apple.com/documentation/metal/setting-up-a-command-structure), and [LibRaw documentation](https://www.libraw.org/docs).
