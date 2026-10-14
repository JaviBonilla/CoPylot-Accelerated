# Phase 2A completion report

Phase 2A completes numerical CPU preparation for `Flux::fluxDensity` and stops before the first optical CUDA kernel. The original CPU body is preserved exactly, apart from its private method name and moving the existing profiling scope to the dispatcher. No original regression baseline, SolTrace source, public Python API, GUI, NLopt, ray tracing or CUDA source changed. No branch was pushed and no GPU service was stopped.

## Numerical boundary and evidence

[Analysis and close pseudocode](flux-density-analysis.md) cover the receiver/surface caller, h→x→y loop, enabled/facing/aperture branches, projection, rotations, image-normalized coordinates, seven-term recurrence/16 packed coefficients, negative-series clamp, Gaussian and sequential accumulation. `imagePlaneIntercept` still prepares optics; normalization and dimensional power conversion remain downstream. The previous 84–86% measured the entire density routine at 25², not only polynomial arithmetic. The new native final-source legacy measurement is 83.70% at 10k/25² and 98.81% at 10k/100².

The new header exposes trivial numeric records and a pure contribution function, with no host class pointers, dynamic matrix/container, inheritance, CUDA header or annotation. The CPU adapter owns contiguous cells and a double accumulator and packs one 200-byte h record at a time. It preserves h0+h1+… and all polynomial-term operation order. No float, fast-math, manual SIMD, OpenMP, atomic or parallel CPU reduction was introduced. Normalization/DNI scaling is unchanged.

Production uses flat for supported seven-term/16-coefficient state, with the original route retained if coefficient packing is absent. The internal opt-in diagnostic build permits legacy/flat/verify, without a new public API. Verify snapshots the initial raw map, runs legacy on the prepared state, restores the same initial map, runs flat on those same heliostats/coefficients/cells, and asserts all cells before normalization. Diagnostics are single-thread validation controls, compiled out by default.

[Scaling and equivalence](flux-density-scaling.md) includes both paths' complete nine-case median/min/max tables, actual cells/candidate/evaluated counts, all raw samples and resulting physical metrics. Final-source three-repeat performance sweeps follow one excluded warm simulation. An initial native original sweep and intermediate extraction evidence are retained separately. Three differential repetitions per case on the extracted arithmetic, plus one per case after the packing guard, all show **max abs=0, max rel=0, bitwise equality**. Maximum-error coordinates (0,0) are tied zero-error placeholders. Both paths' exported flux maps, peaks, incident integrals and absorbed power also match exactly at each case/grid; full original 25² baselines check all summary and heliostat columns independently at rtol=1e-9/atol=1e-10.

For 10k/25², legacy→flat: density 619.421→248.567 ms (-59.87%); total 740.082→369.534 ms (-50.07%). At 10k/100²: density 9946.069→4047.312 ms (-59.31%); total 10065.859→4170.857 ms (-58.56%). Across nine cases density improves 58.17–61.18%, including packing/scattering/counter overhead. Compiler visibility/inlining through fixed scalar data is the plausible structural cause, not a separately measured instruction-level attribution. No GPU performance claim is made.

Density follows O(HC): legacy cost/pair 97.64–100.82 ns; flat 39.13–40.84 ns. At fixed H, 25²→100² costs 15.971–16.083× legacy and 15.859–16.283× flat, versus ideal 16×. Total time has additional O(H) preparation. Facing tests evaluate approximately half the cylindrical candidate pairs; at 10k/100², 100 million candidates produce 50 million evaluated pairs.

## Minimal future device model

[Flux density data model](gpu-data-model.md#flux-density-data-model) records exact origins, types, dimensions, ownership, sun/aim/layout/receiver dependencies and invalidation. Per h: unit receiver-to-h direction[3], global aim[3], sigma_x/y, cnorm and coefficients[16]. Per cell: global position[3] and normal[3]. Shared: tower height and pi. Output: double accumulator per cell. Enabled packing and identity mapping stay in the host adapter. No moment matrices, duplicate efficiency/area, source pointers or DNI are device contribution inputs.

[CUDA design and all nine memory estimates](flux-density-cuda-design.md) use 72H numeric +128H coefficient +48C cell +16 parameter bytes, plus 8C output. Largest resident input+output: 2,560,016 bytes (~2.44 MiB); unnecessary one-double/pair matrix: 800,000,000 bytes (~763 MiB). Static cell geometry may remain resident until grid/geometry/offset/height changes. H optics require a new epoch for sun/aim/tracking/error/shading changes; layout/enable changes rebuild mapping. Output must be initialized/recomputed each call.

Strategies considered: thread/cell, block/cell, thread/pair with atomics/materialized reduction, two-dimensional tiles, and segmented block/cell×h chunks. Recommend **block per cell**, lanes processing h subsets, fixed double block reduction and one output write for the first functional Phase 2B cylinder port. This supplies C blocks rather than C threads and avoids atomics and HC storage, while keeping the implementation small. Block size, registers, spills, occupancy and tiled alternatives require real controlled GPU measurements. Repeated h loads and HX/HY scratch are likely concerns, not measured GPU bottlenecks.

A fixed GPU tree changes the CPU sum order. FMA contraction and device transcendental differences are additional sources of error; isolate per-pair error from reduction error, retain strict tolerances, and do not claim CPU bitwise identity as a future CUDA requirement. Near-zero cells need absolute tolerance; Hermite cancellation/clamping can amplify relative differences. Other receiver geometries must retain CPU fallback in the initial kernel.

## Validation and environment

CPU development, main suites, profiling and timing used native Servidor GPU at `/workspace/work/copilot-gpu/phase2a-native`, separate from the frozen prior snapshot. Tools verified: Git 2.43.0, GCC/G++13.3, CMake3.28.3, Ninja1.11.1, Python3.12.3, rsync3.2.7, ccache4.9.1. Optional C/CXX launchers were enabled; initial `ccache --zero-stats` succeeded; final 148 cacheable calls, 17 hits (11.49%), 131 misses. This is mainly cold-cache development and not a warm-cache build-speedup experiment. No required cache dependency or CUDA compiler launcher was added.

| Check | Result |
|---|---|
| Initial unchanged local suite | Existing native smoke, Python smoke, 7 Python tests PASS |
| Initial unchanged native remote suite | Existing native smoke, Python smoke, 7 Python tests PASS |
| New direct contribution test | 24 cases: several directions/aim-relative cells/coefficients, backside, zero cosine, >1 cosine, negative-series clamp; PASS |
| Native final-source CTest | New numerical test + existing native smoke: 2/2 PASS |
| Native final-source Python smoke and full suite | 8/8 PASS, including 20×30 raw same-state comparison |
| Local diagnostic same-state full Python suite | 8/8 PASS, plus CTest 2/2 |
| Production CPU, diagnostics/profile OFF, no cache requirement | CTest 2/2 and Python smoke PASS; 7 Python tests PASS, diagnostic-only test explicitly skipped |
| Local Debug ASan/UBSan/LeakSanitizer | CTest 2/2 PASS with leak checking, including same-state native smoke |
| Local Debug Python ASan/UBSan | Full 8/8 PASS in verify mode; Python runtime leak tracking disabled as in prior validation |
| CUDA ON, pinned existing Docker image, sm_89 | Build, CTest 2/2, Python smoke and 8/8 suite PASS |
| CUDA existing probe | Exactly one visible device; successful setter checks readback==42; backend remains CPU; functional PASS, no timings collected |

Evidence is in [validation logs](../benchmarks/results/phase2a-validation). Compiler/build transcripts are retained as full ignored artifacts; versioned logs include test results and selected build tails, not full warning streams. The CUDA snapshot is `/workspace/work/copilot-gpu/phase2a-cuda`, built using unchanged image `sha256:8e6e3752946ff2dde451b313cbaec2ea8e7b52221b21bfbcf53fb68dd4f4c42e`. Existing CudaProbe.cu and GPU context source are unchanged. Native host CUDA was not installed. Driver 580.159.03 and GPU services were untouched; final vLLM remains healthy, GPU usage ~43,160 MiB. No GPU timings are published.

## Scope, commits and limits

SSC commits:

* `5945ac11d63cf9c816bf494dc754b39300cb1c2d`: extract flat numerical core and preserve original oracle.
* `c73d4d5ea40e633b5bfe993ac9ca9761d1bca83d`: guard missing packing, preserve helper's inherited BSD license.

Integration commits before this report:

* `c98fe02`: analyze density and add CPU scaling benchmark.
* `ff01a82`: unit/same-state tests, optional diagnostics and exported SSC integration.
* `5b465b2`: export the final guarded SSC pin/patch series.
* `08a29de`: define the minimal flux density data model and CUDA decomposition.
* `443ce1f`: record native scaling, numerical equivalence and validation evidence.

The final documentation commit completes this report; consult integration history for its exact SHA. Final inner pins: SSC c73d4d5ea, SolarPILOT 53640fd, SolTrace 699263f. Original histories and branches are retained; final trees are clean.

Changed source/build/test files: SSC Flux.cpp, Flux.h, FluxDensityNumerics.h; root CMakeLists.txt; scripts/test_cpu.sh; tests/flux_density_numerics.cpp and test_flux_density.py; new benchmarks/flux_density_scaling.py. Integration pins/patches and benchmark evidence are updated. Documentation: README, build, analysis, scaling, GPU data model, CUDA design and this report. Old benchmarks/baselines remain intact.

Limits: tests exhaust the requested cylinder sizes/grids, not every cavity/snouted/falling-particle geometry. Their existing host predicate remains in the adapter; first CUDA support must be deliberately limited. The original zero-direction projection uses uninitialized point coordinates; equivalence assumes valid nonzero direction/finite optics. Missing coefficient packing falls back to the oracle instead of unsafe eager reads. Same-state profiling is single-thread only. Native timing is descriptive while other host services remain active; register pressure/occupancy/GPU performance is unmeasured. These limits do not justify changing physics or tolerances.

**Stop here.** After human review, Phase 2B should implement only the cylinder contribution and fixed double block/cell reduction, use CPU-prepared optics and unchanged host post-processing, reproduce the direct fixtures and nine-map strict checks, and separately measure packing/transfers/kernel/full simulation under agreed controlled GPU conditions. No optical FluxDensityKernels.cu, optical cudaMalloc/cudaMemcpy, CUDA intercept/shading, batching or OptiX is present in Phase 2A.
