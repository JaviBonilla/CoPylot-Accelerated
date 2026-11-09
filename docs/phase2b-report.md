# Phase 2B completion report

The first real hybrid CUDA flux-density backend is implemented and validated. Legacy CPU is preserved, flat CPU remains the primary single-thread performance reference, and explicitly selected CUDA performs real optical density evaluation. This phase stops before Phase 2C tuning. No scientific GPU speedup or timing campaign is reported.

## Architecture and scope

The [backend contract](cuda-flux-density.md) documents shared arithmetic, SoA/AoS choices, RAII, capacities, supported inputs, error handling and stage semantics. CPU preparation, tracking, imagePlaneIntercept/coefficient production, shading/blocking, normalization, dimensional conversion and receiver-power summaries remain CPU operations. Only the double contribution and cell reduction execute on CUDA.

One block maps to each receiver cell; 256 threads accumulate strided heliostats, followed by a fixed synchronized shared-memory double tree. No HC matrix or global atomics exist. The generic implementation accepts 64/128/256/512 for later tests, but only 256 was exercised here. FMA remains enabled normally and there is no fast-math/mixed precision. The same contribution header is compiled for CPU and device; CPU-only builds require no CUDA headers/toolkit.

Supported: Hermite analytical, one enabled cylindrical receiver, current simple aiming, specified sun position, one CPU preparation thread, double. Other models/geometries/multiple receivers/aiming or time modes, disabled receiver, nthreads!=1, disabled aimpoint updates and invalid optical packing return explicit errors; selected CUDA is never silently relabeled CPU. CPU legacy/flat retain existing coverage.

## Numerical results

All cases use the Phase 2A deterministic fields/weather, DNI950, azimuth180°, elevation55°, simple aim and one CPU thread. Each case checks legacy/flat bitwise equality, raw flat/CUDA on the same prepared state, every exported dimensional cell, peak/integral/power and two bitwise identical CUDA repetitions. Tolerances remain rtol=1e-9, atol=1e-10.

Direct fixtures (24) have contribution max abs=0 and max rel=0. Synthetic whole-cell checks have max abs=1.1546319456101628e-14, max rel=1.929180516391698e-15. They cover H=0,1,255,256,257,513; one cell, six cells, invisible/zero-cosine cells, negative Hermite clamp, deterministic repeats and capacity reuse. An additional 20×30 full simulation checks rectangular indexing.

The following errors are for **dimensional exported maps** (kW/m²); raw errors and locations are retained in JSON. Coordinates here are exported [row,column], zero-based.

| H | Grid | Map max abs | Map max rel | Map RMS | Max-abs cell | Raw max abs |
|---:|---:|---:|---:|---:|---:|---:|
| 1000 | 25² | 7.389644e-13 | 2.873364e-15 | 9.430437e-14 | (13, 6) | 6.821210e-13 |
| 1000 | 50² | 8.526513e-13 | 3.260468e-15 | 1.042977e-13 | (22, 19) | 9.094947e-13 |
| 1000 | 100² | 7.958079e-13 | 3.465690e-15 | 8.876640e-14 | (51, 43) | 7.958079e-13 |
| 5000 | 25² | 3.524292e-12 | 4.424699e-15 | 7.033118e-13 | (12, 14) | 3.637979e-12 |
| 5000 | 50² | 4.206413e-12 | 5.033862e-15 | 6.535269e-13 | (23, 21) | 4.661160e-12 |
| 5000 | 100² | 5.002221e-12 | 6.295133e-15 | 6.871603e-13 | (42, 62) | 5.570655e-12 |
| 10000 | 25² | 7.503331e-12 | 6.564210e-15 | 1.557751e-12 | (12, 13) | 7.503331e-12 |
| 10000 | 50² | 9.094947e-12 | 8.578969e-15 | 1.433959e-12 | (23, 27) | 8.867573e-12 |
| 10000 | 100² | 1.114131e-11 | 8.867089e-15 | 1.543581e-12 | (51, 54) | 1.000444e-11 |

Real-data contribution diagnostics evaluate all H heliostats at each case's raw peak cell in bounded tiles. The reduction residual compares the GPU block result to a **CPU sequential sum of device-evaluated terms**, separating contribution evaluation from accumulation. Normal compiler fusion in accumulation can also contribute to this residual; it is not attributed exclusively to the shared tree or addition-order change.

| H | Grid | Contribution max abs | Contribution max rel | Reduction residual abs | Reduction residual rel |
|---:|---:|---:|---:|---:|---:|
| 1000 | 25² | 1.776357e-15 | 4.996651e-14 | 3.979039e-13 | 8.873127e-16 |
| 1000 | 50² | 2.442491e-15 | 2.166229e-14 | 1.136868e-13 | 2.540111e-16 |
| 1000 | 100² | 3.108624e-15 | 4.816801e-14 | 5.115908e-13 | 1.139303e-15 |
| 5000 | 25² | 1.776357e-15 | 1.309976e-13 | 4.547474e-13 | 4.274141e-16 |
| 5000 | 50² | 1.776357e-15 | 4.372344e-14 | 1.136868e-12 | 1.070994e-15 |
| 5000 | 100² | 1.776357e-15 | 8.346475e-14 | 2.273737e-13 | 2.137172e-16 |
| 10000 | 25² | 1.776357e-15 | 1.309976e-13 | 1.591616e-12 | 1.213244e-15 |
| 10000 | 50² | 1.776357e-15 | 4.372344e-14 | 2.728484e-12 | 2.084193e-15 |
| 10000 | 100² | 1.776357e-15 | 8.346475e-14 | 2.273737e-12 | 1.733394e-15 |

No FMA disabling experiment or tolerance change was required. All raw/dimensional relative errors are finite in these cases; zero-reference mismatch counts are zero. Independent peak-cell sampling does not exhaust all HC individual terms, whereas all map cells are checked.

| H | Grid | Flat peak kW/m² | CUDA peak kW/m² | Incident integral difference kW (CUDA−flat) | Absorbed power kW (both) |
|---:|---:|---:|---:|---:|---:|
| 1000 | 25² | 426.011709827102 | 426.011709827102 | -1.455192e-11 | 89947 |
| 1000 | 50² | 425.194027936339 | 425.194027936339 | -2.910383e-11 | 89947 |
| 1000 | 100² | 426.592408022878 | 426.592408022879 | 0.000000e+00 | 89947 |
| 5000 | 25² | 1036.088078498208 | 1036.088078498208 | 0.000000e+00 | 358035 |
| 5000 | 50² | 1033.785204336356 | 1033.785204336358 | 5.820766e-11 | 358035 |
| 5000 | 100² | 1036.132283576782 | 1036.132283576781 | -2.910383e-10 | 358035 |
| 10000 | 25² | 1369.842313876623 | 1369.842313876624 | -3.492460e-10 | 573347 |
| 10000 | 50² | 1367.145759582848 | 1367.145759582851 | 1.164153e-10 | 573347 |
| 10000 | 100² | 1369.892699454814 | 1369.892699454816 | -1.164153e-10 | 573347 |

Maximum dimensional-cell error is 1.1141310096718371e-11 kW/m²; maximum peak difference is approximately 2.96e-12 kW/m²; maximum incident-integral difference is 3.4924596548080444e-10 kW. Absorbed power summaries are identical (rounded upstream); normalization power and optical preparation are unchanged CPU calculations. Every comparison passes the original combined tolerance.

## Buffers, transfers and reuse

Per h: 25 doubles in SoA =200 bytes. Per cell: six-double AoS =48 bytes. Output: one double/cell =8 bytes. Upload/download byte counts and observed capacities are in each JSON case. Three buffer allocations were observed on the first call and still three on the second. Capacity growth retains device ownership and is checked; shrinking/repeating dimensions reuse capacity. Context persists across simulations and explicit CPU switches until device replacement/data_free.

The [contract's nine-row memory table](cuda-flux-density.md#resource-ownership-and-transfers) gives all active sizes: smallest total 235,000 B; largest 2,560,000 B (~2.44 MiB). These exclude CUDA context/event/runtime overhead and kernel argument marshalling. No contributions[H][C], pinned memory, async copies, custom stream or comprehensive static-geometry cache is implemented. Cells/optics have independent buffers and transfers; later time-series epochs can skip unchanged geometry uploads. verify_cuda overwrites these buffers for bounded diagnostics, so future residency must invalidate cached values or use separate diagnostic scratch.

## Validation and environment

Native CPU: Servidor GPU, GCC13.3/CMake3.28.3/Ninja1.11.1/Python3.12.3, optional ccache. CUDA: existing pinned image, CUDA13.0/nvcc13.0.88, sm_89, RTX6000Ada. No host CUDA installation, driver/container-toolkit changes or new image pull. Source remains architecture-configurable via CMake; numerical code contains no server paths, IP, user/container names or sm_89 assumption.

| Validation | Result |
|---|---|
| Native CPU diagnostic build | CTest2/2; 8 Python tests PASS, 3 CUDA-only skips |
| CUDA ON with CPU backend | Original full regression/smoke PASS |
| CUDA native CTest | 3/3 PASS, including original/flat and new CUDA fixtures |
| CUDA full Python suite on idle GPU | 11/11 PASS, including capability/rectangular/event tests |
| Nine-case scientific correctness matrix | 9/9 PASS; legacy/flat bitwise; repeated CUDA bitwise; strict map/scalar checks |
| Local CPU production OFF (no profile/diagnostic requirement) | CTest2/2, smoke and 7 Python tests PASS; 4 explicit GPU/diagnostic-only skips |
| Local Debug ASan/UBSan/LeakSanitizer | Native CTest2/2 PASS with leak checks; Python8 PASS/3 GPU-only skips (Python leak tracking disabled) |
| CUDA-enabled hidden-device behavior | Clear no-device error, previous CPU selection retained |
| CUDA runtime resources | Direct repeat/growth/shrink and checked normal release exercised |

GPU Compute Sanitizer was not installed in the existing image, so no device sanitizer claim is made; no package was installed to change that environment. CUDA runtime/launch errors are checked, but destructive OOM/device-loss faults were not injected. Sanitizers listed above are host CPU checks.

vLLM initially held ~43GiB. Early direct correctness tests did not collect CUDA event timings. Automatic approval review blocked the combined matrix/timing request while that workload was active; tests were separated and an idle-only gate added. The human user then stopped vLLM, and read-only checks confirmed 2MiB VRAM usage, utilization0% and no vLLM container. Final matrix and timing-plumbing validation ran after that verification. The agent did not stop/restart/alter services and told the user the GPU could be returned to vLLM afterward.

The timing test checks preparation, H2D h/cell, kernel, D2H, CPU map post-processing, hybrid density and full simulate semantics. Its one functional sample is not printed/published and is not a speedup benchmark. Correctness JSON contains no GPU timings; no paper performance claim is derived from test runtimes, even with the GPU idle. Future measurements require warmup/repeats/fair flat-CPU baseline and explicit workload conditions.

## Reproducibility, commits and remaining work

Canonical [machine-readable result](../benchmarks/results/phase2b-cuda-correctness.json) records integration SHA e0d312fe1406b41bdeaf8ba27b0bbd0a4b8e3f3a, SSC a553d244d8bc9ed68a81d7c62467cc20ee97855e, SolarPILOT5209ccaf5ed4449f39c2405f166db161adb8c6ae and unchanged SolTrace699263f. It includes hostname/CPU/GPU/compiler/CUDA/CMake/build settings, block, H/grid, precision/thread count, configuration, errors/scalars/transfers/capacities and native fixtures. Later integration commits add only documentation/evidence. The public archive carries the machine-readable result and the test summaries above.

SSC commits: ca23d10fa (shared formula/device buffers/kernel), a553d244d (hybrid adapter/dispatch/capability errors/post-processing instrumentation). SolarPILOT5209cca updates only the existing backend selector docstring; there is no new public Python API. Integration: ce98da3 (build/native tests/pins), c4a786a (matrix/capability tests), e0d312f (idle-only event gate), 6fc8419 (backend contract/scientific roadmap), 7bf682a (machine-readable validation evidence). The final report commit is recorded in integration history. No push, reset, clean, rebase or history rewrite was performed. Final working trees are clean.

Main new files: SSC FluxDensityKernels.cu and FluxDensityCuda.cpp; tests/cuda_flux_numerics.cpp, tests/test_cuda_flux.py and benchmarks/cuda_flux_correctness.py. Modified: shared numerical header, ComputeBackend interface/stubs, Flux hook, CoPilot_API dispatch/release, relevant SolarField post-processing timers, CMake/test script and existing backend test. Existing CudaProbe.cu, numerical legacy body, baselines, SolTrace, NLopt and GUI are unchanged. Documentation/model/roadmap and exported dependency patches/pins reflect the implementation.

Limits: supported single-cylinder/simple-aim path only; same-context concurrent mutation unsupported; no persistent-value cache/invalidation epochs; GPU results are tolerance-equivalent rather than CPU bitwise; peak-cell contribution samples are not exhaustive HC coverage; no GPU sanitizer/device-fault injection; portable architecture compilation is configurable but only sm_89 was validated here.

Future annual/time-series execution can preserve these allocations and independently update optics/cells. Future batching may add explicit candidate/field strides and independent result tiles; nothing stores host pointer graphs on device. A separate public-release phase must still address installation/CI/examples/packaging/license review; no release/publication cleanup is attempted here. Scientific roadmap explicitly retains high-throughput Hermite (legacy/flat/parallel/CUDA, including annual and possible CESA-I) and independent high-fidelity SolTrace/OptiX work.

**Stop before Phase 2C.** After review: perform controlled flat-CPU versus CUDA measurements with warmups/repeats, stage decomposition and correct provenance; test 64/128/256/512 and inspect register/local-memory/shared-memory/occupancy; only then decide whether layout/tile/residency changes are justified. Do not combine original→flat improvement with flat→CUDA speedup or expand to intercept/shading/batching/annual/SolTrace during that first tuning exercise.
