# First hybrid CUDA Hermite flux-density backend (Phase 2B)

Legacy CPU, flat CPU and CUDA are distinct implementations. CPU defaults to flat; diagnostic CPU builds retain `SOLARPILOT_FLUX_PATH=legacy|flat|verify` for scientific comparison. Public `set_compute_backend(context, 'cuda')` now selects a real hybrid optical backend when build/device initialization succeeds. A requested CUDA operation never silently falls back to CPU. Flat CPU is the primary future GPU speedup baseline; original-to-flat improvements remain a separate comparison.

## Supported boundary

Hermite analytical, one enabled external cylindrical receiver, simple aiming with aimpoint updates enabled, specified sun position, one CPU preparation thread, double precision. Rectangular grids are also supported. Other receiver types, multiple receivers, other aiming/time modes, SolTrace, nthreads!=1 and update_aimpoints=False return a clear C error (`simulate` returns False; `get_last_backend_error` gives the reason), retaining the selected backend. Missing/nonfinite optical coefficients, nonpositive sigmas and degenerate directions are explicit errors on CUDA. CPU behavior/geometry coverage remains unchanged.

Pipeline: existing CPU performance preparation/tracking/optics/shading → host POD packing → SoA transpose → synchronous H2D inputs → block/cell evaluation/reduction → synchronous D2H dimensionless map → unchanged CPU normalization, dimensional conversion and summary processing. imagePlaneIntercept and coefficient generation are still CPU operations. Dispatch is scoped to sp_simulate's Flux object; the GPU context itself persists in CopilotObject across calls and CPU/CUDA switches. Same-context concurrent mutation is unsupported.

## Shared arithmetic and layout

FluxDensityNumerics.h contains the single contribution formula. A compiler-conditional host/device annotation is active only under nvcc; ordinary CPU builds include no CUDA headers and need no toolkit. Normal FMA contraction is retained. No float or mixed-precision optical calculations, fast-math, approximate transcendental or changed physics was added. CUDA's event API requires a float millisecond destination; this is timing metadata, not optical precision.

Device heliostats use SoA `[25][active_H]`: direction xyz, aim xyz, sigma xy, normalization, 16 coefficients. Adjacent lanes process adjacent heliostats, so each field/term load is contiguous. Cells use the tested 48-byte AoS; every block reads one six-double point/normal. Parameters (tower height, pi) are kernel arguments. This mixed layout is a provisional clarity/coalescing choice, not the outcome of an AoS/SoA campaign. The host packs the actual C++ geometry, including original serialization precision and offset/division order.

One CUDA block maps to one x-major cell, `cell=x*NY+y`. Default block size is 256; lane t handles h=t,t+B,t+2B,… and accumulates a double partial. All lanes write one shared double, synchronize, then reduce at offsets B/2,B/4,…,1 with a barrier at every step. Lane zero writes the cell result. No global atomics, Thrust/CUB, H×C contribution array, multiple blocks/cell or batched launch was introduced. Internal diagnostic configuration accepts 64/128/256/512, but only 256 was used in Phase 2B: no block-size sweep was performed.

## Resource ownership and transfers

Concrete GpuContext owns three typed device buffers plus optional two reusable events. Capacity grows only when insufficient; repeated and smaller inputs reuse existing allocations. H capacity and C/output capacities are separate. Input values are uploaded every simulation for now; cells and optics are independent buffers/transfers so later geometry residency can be added without redesigning the kernel. Full invalidation epochs, pinned memory, async copies, custom streams and graphs are deferred.

Each buffer/event remembers its device. Calls select the owning device and restore the caller's previous device. Allocation/transfer/launch/execution/event/release failures are checked and converted to the per-context backend error. Normal data_free/device replacement explicitly closes resources with checked errors; destructors provide best-effort cleanup on exceptional unwinding and never throw. Growth keeps the old buffer until a replacement allocation succeeds. Native tests cover capacity reuse and explicit invalid block/device errors; destructive allocation exhaustion or hardware faults were not injected.

Active transfers: H2D heliostats **200H** bytes; H2D cells **48C**; D2H result **8C**. Three buffer payloads total **200H+56C**, excluding runtime context overhead/events/allocator granularity and kernel argument storage. No output initialization transfer is needed: every block writes its cell. The adapter adds the initial raw host cell value before existing post-processing (ordinary analytical maps are cleared first).

| H | Grid | H input B | Cell input B | Output B | Total buffer B |
|---:|---:|---:|---:|---:|---:|
| 1000 | 25² | 200,000 | 30,000 | 5,000 | 235,000 |
| 1000 | 50² | 200,000 | 120,000 | 20,000 | 340,000 |
| 1000 | 100² | 200,000 | 480,000 | 80,000 | 760,000 |
| 5000 | 25² | 1,000,000 | 30,000 | 5,000 | 1,035,000 |
| 5000 | 50² | 1,000,000 | 120,000 | 20,000 | 1,140,000 |
| 5000 | 100² | 1,000,000 | 480,000 | 80,000 | 1,560,000 |
| 10000 | 25² | 2,000,000 | 30,000 | 5,000 | 2,035,000 |
| 10000 | 50² | 2,000,000 | 120,000 | 20,000 | 2,140,000 |
| 10000 | 100² | 2,000,000 | 480,000 | 80,000 | 2,560,000 |

Each correctness case owns a separate context, so observed capacities equal these active dimensions; the second call still has only three buffer allocations. A long-lived context retains its maximum capacities after smaller calls. This is allocation residency, not yet a static-data cache.

## Two-level numerical validation

Direct native fixtures compare flat host/device contributions before accumulation. Whole simulations use optional `verify_cuda`: run flat on the same prepared state, restore the initial raw map, then run CUDA and compare every unnormalized cell at atol=1e-10+rtol=1e-9×abs(reference). Separate CPU legacy/flat checks still require bitwise equality. Exported dimensional cells, peak, incident integral and absorbed power are also checked.

For a meaningful real-data contribution test, the diagnostic selects the raw peak cell and evaluates each of its H pairs on the device in bounded 256-pair tiles. It compares these device terms to flat terms, then sums the device terms sequentially on the CPU and compares that sum with the block result. This residual isolates accumulation/reduction from the separately evaluated terms; it can include normal compiler fusion in the inlined accumulator as well as changed sum order. It does not claim to attribute all residual error solely to the shared tree. No optimization or FMA change was needed to pass.

The fixed tree is reproducible for identical inputs/GPU/block size/executable, although it does not reproduce CPU sequential rounding. Relative error is reported separately from the combined tolerance; zero-reference cases use absolute tolerance. Raw max-error coordinates are grid[x][y]; dimensional error coordinates are exported [row,column]. Peak-cell arithmetic diagnostics do not exhaust every H×C pair, but every complete raw/dimensional map cell is checked.

## Opt-in instrumentation

`SOLARPILOT_CUDA_TIMING_FILE` enables CSV timing; default is OFF. It is incompatible with verify_cuda so reference work cannot be confused with GPU performance. Columns:

```text
H,C,preparation_s,H2D_heliostat_ms,H2D_cell_ms,kernel_ms,D2H_ms,CPU_postprocessing_s,hybrid_density_s,simulate_s
```

Host steady clock measures adapter+SoA preparation, complete hybrid density (including capacity growth/scatter), normalization+CalcDimensionalFluxProfiles, and full simulate. CUDA events in the default stream bracket each synchronous transfer and kernel; end events synchronize before elapsed-time reads. Pageable synchronous copies may include staging/scheduling effects; event intervals are not a raw PCIe bandwidth benchmark. Definitions follow the [CUDA event API](https://docs.nvidia.com/cuda/cuda-runtime-api/cuda_runtime_api/group__CUDART__EVENT.html).

The functional timing test requires `COPILOT_GPU_TIMING_ALLOWED=1`, set only after verifying an idle GPU. It checks units/finite positive stages without printing their values. The correctness matrix explicitly removes timing output and publishes no GPU times or speedups. Future performance measurements need an excluded initialization/warmup, repeated samples, workload/VRAM checks, fixed build/inputs, and separate transfer/kernel/end-to-end reporting against flat CPU. Initial calls may include context initialization, allocations and cold caches.

## Build and reproduction

CPU-only OFF remains independent of nvcc/headers/toolkit. CUDA ON adds CudaProbe.cu and FluxDensityKernels.cu; `CMAKE_CUDA_ARCHITECTURES` remains configurable, with 89 used in this environment. No sm_89 assumption appears in the numerical core. Host native CPU builds use optional ccache; CUDA uses the existing pinned image/toolkit and no CUDA launcher.

```bash
BUILD_DIR="$PWD/build/cuda" scripts/test_cpu.sh \
  -DSOLARPILOT_ENABLE_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89 \
  -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON
COPILOT_LIB_DIR="$PWD/build/cuda/lib" .venv/bin/python benchmarks/cuda_flux_correctness.py \
  --output artifacts/cuda-correctness.json
```

A live CUDA device is required for the matrix. CTest's CUDA numerical target explicitly skips with code 77 when none is visible, while CPU tests remain runnable. Metadata records integration/dependency SHAs, host/CPU/GPU/compiler/toolkit/CMake/build settings, block size, inputs and precision. Environment-specific transport/image launchers remain separate from this generic core.
