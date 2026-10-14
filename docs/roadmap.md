# Next technical phases

## Phase 2: pure CPU extraction, then first real CUDA kernel

Measured recommendation: fluxDensity contribution evaluation + map reduction, rather than the originally hypothesized imagePlaneIntercept. Its ~84–86% share at 25×25 makes the larger first opportunity. This recommendation is specific to these cylinder/simple-aim cases; reprofile representative optimization geometries and map resolutions before committing to broader coverage.

1. Extract the per-heliostat/per-cell numerical contribution, preserving coordinate conventions and normalization.
2. Replace Heliostat*/Receiver*/matrix_t dependencies with typed numeric views and an explicit 16-coefficient contract.
3. Add CPU-new implementation and compare every map cell, receiver power, efficiency and every heliostat against CPU-old. Retain original reference until equivalence is demonstrated.
4. Implement a double precision CUDA tiled evaluator/reducer; measure thread/block mapping and transfers separately.
5. Compare CPU-new/CUDA using existing tolerances; add boundary/zero/disabled/multiple receiver tests and geometry capability checks.
6. Measure end-to-end Python calls including coefficient packing, uploads, kernel, normalization/reductions and downloads. Kernel-only timing is insufficient.

imagePlaneIntercept follows as a separate extraction with full moment/image/coefficient side effects, using 1 heliostat per thread initially or an equivalent measured strategy. No float conversion or fast-math in the first numerical port.

## Phase 3

Migrate/fuse tracking, cosine, attenuation, intercept and power where profiling justifies it. Keep template/sunshape/error constants reusable. Add geometry/canting regression cases before extending capability.

## Phase 4

Extend the Phase 2 flux map implementation to remaining receiver geometries and efficient normalization/peak/integral reductions. Keep a deterministic reduction mode for regression and compare incident/absorbed power conventions.

## Phase 5

Shading/blocking with validated CSR lists. Measure at low solar elevation and compact/dense fields first; current 55° elevation cases show ~2–4%, so this is not their primary bottleneck.

## Phase 6

Resident geometry/context across simulate. Introduce the documented epochs at all API and optimizer mutation sites, amortize capacity growth and reject stale data. In practice persistent allocation should accompany the first kernel; comprehensive residency/invalidation comes here.

## Phase 7

simulate_batch and evaluate_batch for sun positions/candidates/aimpoints × heliostats. Candidate tiling, constraints/reductions on GPU, compact objective outputs. Define partial failures/cancellation and reproducible result ordering before exposing Python APIs.

## Phase 8

Layout/DoManagedLayout, annual simulations and efficiency maps. Replace deep CPU field copies only after identifying where a batch kernel can share immutable geometry. Leave NLopt on CPU initially; GPU objective evaluation can still accelerate its repeated calls.

## Phase 9

Investigate current SolTrace NativeRunner/EmbreeRunner/OptixRunner/OptixCSP, repair/validate bridge separately and build the receiver/canting geometry test matrix. Compare ray tracing statistically with pinned legacy. Use upstream OptiX work, not a new CUDA ray tracer. Do not equate Hermite CUDA support with SolTrace OptiX support.


## Scientific evaluation roadmap

High-throughput Hermite will compare original legacy CPU, flat single-thread CPU, flat parallel CPU and CUDA, separating original→flat improvement from flat→CUDA acceleration. Flat CPU is the primary GPU performance baseline. Planned regimes include single operating points, H×C scaling, parameter studies/optimization, daily/monthly/yearly time series and annual simulation, with a representative central receiver and possible CESA-I case study. None of parallel CPU, time-series, annual or batching is implemented in Phase 2B.

High-fidelity work will separately compare SolTrace CPU, appropriate CPU parallel implementations and a modern GPU/OptiX path at selected detailed operating points. The current Hermite CUDA backend makes no SolTrace acceleration claim. Future public-repository preparation will address reproducible installation, examples, CI, packaging, license review and public benchmarks as its own phase.

Phase 2B implements only the first block/cell double kernel and correctness boundary. After review, Phase 2C can measure 64/128/256/512 block sizes, layout/register pressure and controlled transfer/kernel/end-to-end behavior. Keep static geometry residency and candidate/time dimensions possible; do not expand optical scope merely to improve a benchmark.
