# Metal Compute Backend

The optional backend plugs into `lumaraw.accelerators.grade_output`. A small Objective-C++ dynamic library exposes a C ABI, loaded by Python through ctypes. SwiftUI, CLI, and MCP continue to use the same service and recipes. Windows retains the CPU path; Direct3D/Vulkan adapters are not implemented.

## CPU/GPU split

| Stage | Implementation |
| --- | --- |
| NEF metadata, decompression, white balance, AHD demosaicing, camera matrix | LibRaw on CPU |
| Crop/rotation/perspective/distortion sampling; denoise/sharpen/defringe | CPU with overlapping strips |
| Exposure, tone, contrast, saturation/vibrance, curves, eight-band HSL/B&W mixer, camera profile matrix, monochrome | Fused Metal grading kernel, or CPU reference |
| Masks, LUT and very steep point curves | Complete CPU grading followed by Metal output conversion; reported as hybrid |
| Output matrix, sRGB/P3/Adobe/ProPhoto encoding, gamut flags | Metal, or CPU fallback |
| Optional Develop SDR RGB/Lab D50 readouts | Fused with Metal grade/output, or unchanged CPU reference |
| ICC soft proof, histogram, PNG/JPEG/TIFF encoding | CPU; exported files retain ICC profiles |
| Native display | sRGB-tagged NSImage; no custom MTKView canvas |

Metal accelerates decoded pixels. It does not parse or decompress NEF on the GPU. Original files, recipe semantics, cache space, and ICC definitions remain unchanged. FP32 CPU/GPU results are not guaranteed to be bit-identical.

The eight mixer bands use 32 floats in the existing parameter buffer; ordinary
HSL and B&W recipes remain fully fused. A compensated cube-root residual improves
the Oklab input transform. Neutral protection, band weights and slider units match
the CPU path. Masks/LUTs retain their documented hybrid boundary.

RGB master and three channel curves share the CPU's normalized PCHIP coefficients.
Ordinary curves stay in the fused kernel. A curve whose exact maximum segment
derivative exceeds 32 uses CPU grading and Metal output, reported as hybrid with
`steep_point_curve_uses_cpu_grade`; no curve points are changed to hide precision
differences. Identity curves bypass encoding/clipping on both backends.

The v3 C entry point (`lr_metal_run_v3`) takes an explicit parameter count and an
optional six-channel float32 readout output. The v2 entry point retains ordinary
RGB/gamut compatibility. An absent/mismatched readout buffer fails before dispatch
or destination writes, and simultaneous linear-work/readout captures are rejected.
The adapter requires 640 floats (2560 bytes) and checks `lr_metal_parameter_count`
before allocating. Both Python and C reject mismatched sizes before reading the
buffer. Libraries lacking v3 are rejected with rebuild guidance; auto mode retains CPU
fallback. The payload stays below Metal's 4 KiB inline-byte limit.

Four parametric regions use sixteen previously unused floats in that same buffer;
the 640-float capacity remains unchanged. The shader composes the same
smooth monotone warps as the CPU, then applies a shared RGB gain before point
curves. Ordinary parametric/point/HSL combinations remain fused. Zero amounts and
unchanged tones bypass unnecessary encoding round trips.

Synthetic regressions keep the encoded absolute/relative limits of 1e-4/2e-5,
except Adobe RGB channels below 0.02 on both backends: its pure-gamma derivative
diverges at zero, magnifying FP32 cancellation. Those channels must satisfy both
a 16/65535 encoded bound and a 1e-6 linear-light bound. All output spaces also
require at most 1e-5 absolute decoded-linear error and mean encoded error below
2e-6. This is an explicit numerical allowance, not bit identity. The real-RAW
packaged probe independently retains its stricter maximum of eight 16-bit codes
and one 8-bit preview code.

Binary gamut markers retain their -1e-5 / 1.00001 linear thresholds. CPU/Metal
roundoff can put a pixel on different sides of those thresholds, especially after
curves place many channels at the same endpoint. Regression requires every marker
disagreement to lie within **1e-6 linear units** of a reference threshold; markers
away from this boundary must agree. This replaces the arbitrary maximum of one
disagreeing pixel with a bound on the actual classification uncertainty. Encoded
and decoded color-error limits above are unchanged.

## Memory, lifetime, and fallback

Each disposable worker owns its Metal device, queue, pipeline, and reusable shared tile buffers. No extra persistent image process is introduced.

RGB input and output each use 12 bytes per pixel; gamut flags use one byte. Shared buffers are bounded by the minimum of 100 MiB, 15% of the worker budget, and four million pixels. Growth releases old buffers first. Output is copied back only after a successful command.

Optional readouts add 24 bytes per pixel, making 49 rather than 25 bytes in the
shared-buffer admission check. Switching buffer layouts releases the previous
buffers first, including a larger ordinary tile when a smaller readout tile is
requested. Reuse stays within the same layout and bounded capacity. Allocation
failure releases partial buffers; command failure publishes no partial output.

Readouts convert the final graded linear work to clipped SDR ProPhoto D50 RGB
percentages and CIELAB D50 before display/proofing. The fused shader uses the same
matrix, white point, transfer curves and Lab branch as the CPU reference. FP32
matrix rounding and subtractive Lab chroma calculations retain the existing
0.002 absolute readout allowance (percentage points or Lab units); this does not
change the stored six-float format or claim Adobe numerical equivalence. The
CPU equations remain unchanged, including higher precision Lab intermediates.
CPU conversion covers only the visible tile region, excluding filter halos.

Auto mode uses the CPU for tiles below 16,384 pixels or above the buffer allowance. Initialization or command failure triggers CPU fallback for the remainder of that request and records the reason. Explicit Metal mode reports GPU initialization/command failures; small-tile and memory limits still apply.

RAW admission estimates, the dynamic 70% memory cap, RSS sampling, cancellation, broker monitoring, and atomic output publication remain active. Shared-buffer accounting does not include all driver allocations, and RSS is not a machine-wide hard quota.

`MTLStorageModeShared` and `waitUntilCompleted` establish CPU/GPU ordering. Fast math is disabled. Shaders compile on first use; the OS shader cache may help later processes. No separate Metal command-line tool download is required.

## Public contract

`settings.compute_backend` accepts `auto`, `cpu`, or `metal` and defaults to `auto`. It is catalog processing policy, not a recipe change.

Preview and completed-job receipts include `processing`: actual backend/device, Metal grading/output tile counts, CPU tile counts, GPU and dispatch time, initialization time, shared-buffer peak, fallback reasons, worker time, and named stage timings. Status/settings expose the latest worker receipt. A present library alone does not prove GPU execution.

`metal_readout_tiles` counts successful fused conversions; `cpu_readout_tiles`
counts CPU reference/fallback conversions. Ordinary fused readouts no longer
require the legacy `cpu_readout_output_tiles` path. Their GPU conversion time is
part of `grade_and_output`, not an additional `color_readouts` CPU stage. These
stage counters overlap and must not be summed as independent work durations.

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
