# Phase 0/1 report — CoPylot-GPU

Date: 2026-10-14. This report records the completed local preparation phase. The headless CPU baseline is built and validated. Optical CUDA simulation is not implemented; remote toolchain/device validation is a separate continuation task.

## 1. Repositories and branch choice

| Repository | Upstream ref | Upstream SHA | Patched SHA |
|---|---|---|---|
| SolarPILOT | develop | `c74618a70fd8e85708957b1ee57b157ba75a5045` | `53640fdfd671f06255a6b35db2e139ea0d6d1b24` |
| ssc | solarpilot-develop | `e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec` | `9ce2c8c6424bbc8e91718734404266c8137170ae` |
| SolTrace | v3.4.0 | `79b2ca3dfec496506d24ae56055c0d7e240ba368` | `699263f12b2de1c6f12e211e3e8906a80054cc1b` |

Inner checkouts use feature/copilot-gpu. SolarPILOT/develop supplies the current Python API. Current official SSC lacks CoPilot_API; use the mjwagner2/ssc fork recommended by the upstream README. Published SolTrace v3.4.0 retains the compatible legacy core. The current SolTrace branch was inspected but not integrated. Details and historical copilot comparison: [dependencies.md](dependencies.md).

## 2. Clean build

```bash
python3 scripts/bootstrap.py
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
scripts/build_cpu.sh
```

Output: build/cpu/lib/solarpilot.so. Requirements: CMake >=3.24 and <4, Ninja, GCC/G++, Python 3.12. No GUI/wxWidgets/LK/WEX. The bootstrap reconstructs the tracked local commit series and exact patched SHAs without overwriting existing mismatched repositories. Clone → patches → clean configure/build was independently exercised in /tmp/copilot-repro. See [build.md](build.md).

## 3. Tests and evidence

```bash
scripts/test_cpu.sh
```

* Python smoke: 1425 generated heliostats, successful simulate, finite/positive 25×25 flux, finite results and context release.
* Regression: exactly 1000/5000/10000 assigned heliostats, metrics, every flux cell and every heliostat result column. rtol=1e-9, atol=1e-10. Original references precede dispatch/profiling; no tolerance was relaxed.
* Seven unittest methods cover all baselines, drift rejection, DNI/sun restoration, CPU dispatch/rejected CUDA, probe/device errors, null contexts, and legacy dataframe/dictionary/matrix forms plus array release on conversion failure.
* Native CTest covers generated layout and three simulations with finite results, including 13! without integer overflow.
* Release, profiling ON/OFF and independent clean reconstruction passed. Native ASan/UBSan/LeakSanitizer passed without errors/leaks. Python ASan/UBSan checked the six initial tests plus the additional export test. LeakSanitizer required thread inspection outside the desktop sandbox.
* Two localized legacy fixes removed factorial_d integer overflow and uninitialized optical tree state; original CPU regressions still pass.
* The three exercised Python array exports now release C++ buffers in try/finally without changing public result forms or values.

## 4. Benchmarks and profiling

```bash
.venv/bin/python benchmarks/run_cpu.py --repeats 10
.venv/bin/python benchmarks/export_overhead.py
scripts/profile_cpu.sh
.venv/bin/python scripts/summarize_profile.py
```

Raw data: benchmarks/results, with source SHAs/hashes and weather/layout hashes for final measurements. Hermite, double precision, one thread, cylindrical receiver, simple aiming, 25×25 map, DNI 950, azimuth 180°, elevation 55°. Generation/filtering is timed separately from deterministic assigned-field simulations.

## 5. Local CPU timings

Dynabook host: 12th Gen Intel Core i5-1240P, Release/O3. Medians of ten calls; generation/assignment are single measurements. Frequency/affinity are not locked. Differences from earlier captures are not acceleration claims.

| Case | generate_layout ms | assign_layout ms | simulate ms | get_fluxmap ms | detail_results ms |
|---|---:|---:|---:|---:|---:|
| small (1000) | 83.984 | 54.544 | 64.476 | 0.065 | 1.881 |
| medium (5000) | 174.923 | 124.425 | 322.782 | 0.072 | 9.391 |
| large (10000) | 226.737 | 204.324 | 659.102 | 0.067 | 19.858 |

Generated fields contain 1421/6291/13704 heliostats; measured simulations use exactly 1000/5000/10000. Original data and inclusive/exclusive function tables: [cpu-profile.md](cpu-profile.md).

## 6. Measured hot spots

| Function/loop | small % | medium % | large % |
|---|---:|---:|---:|
| Flux::fluxDensity | 85.92 | 84.91 | 84.30 |
| Flux::imagePlaneIntercept | 9.36 | 9.43 | 9.28 |
| ShadingBlockingNeighbors | 2.04 | 3.09 | 3.87 |
| calcHeliostatShadows | 0.24 | 0.25 | 0.25 |

AnalyticalFluxSimulation contains nearly all fluxDensity time: do not add parent/child times. CalcDimensionalFluxProfiles contributes ~0.03–0.04%. The actual neighbor shading/blocking loop was measured separately from calcHeliostatShadows preparation.

At 10000 heliostats, median C detail export takes ~1.113 ms versus ~21.905 ms for the complete Python dictionary; flux takes ~0.008 ms C versus ~0.061 ms Python. Cache/reconstruction opportunities are code-derived inferences. Multiprocessing, optimization/deep-copy overhead and other geometries/elevations were not measured.

## 7. CPU/GPU architecture

CopilotObject owns ComputeBackendState: CPU default, requested device, unique_ptr<GpuContext>, and an error string. sp_simulate dispatches once and retains the previous CPU body. CUDA selection is rejected explicitly while preserving previous state. C/Python extensions expose availability/count, backend/device selection and errors. CPU-only reports false/0.

SOLARPILOT_ENABLE_CUDA=ON detects the CUDA language/Toolkit and links a trivial probe that writes 42, with explicit errors and RAII. OFF needs no CUDA dependency. ON without nvcc fails clearly. Availability does not establish optical backend support.

Persistent VRAM/SoA/epochs/evaluate_batch are designed, not implemented. Sun/DNI changes do not require static position uploads, but sun/tracking affect optical state and neighbors. See [backend.md](backend.md) and [gpu-data-model.md](gpu-data-model.md).

## 8. Files and commits

* Workspace: CMakeLists, lock/requirements, README/docs, build/test/bootstrap/patch/profile scripts, benchmarks/raw data, tests and readable JSON baselines.
* SSC: additive backend/probe/profiling files and CoPilot_API/CMake changes; compile-time profiling scopes in Flux/SolarField/interop; valid HELIO_INTERCEPT constant; localized Toolbox/OpticalMesh sanitizer fixes.
* SolarPILOT: only deploy/api/copylot.py (additive wrappers and array ownership); no GUI source changed.
* SolTrace: only coretrace/treemesh.cpp (`<limits>` inclusion).
* Inner commits are preserved in patches/*.patch. Workspace history originally used .workspace-git; the continuation exposes it via a root .git pointer and integration branch main. No pushes or history rewriting.

## 9. Limits at Phase 0/1 completion

* Local NVIDIA/driver/nvcc were unavailable; CudaProbe compilation/runtime awaited remote validation. No GPU timings/speedup were claimed.
* CoPylot uses the recommended SSC fork, not current SAM SSC. Dependency updates require regression rather than an unreviewed pull.
* Initial cases cover cylindrical/simple-aim fields; multiple receivers/cavities/particles/canting/extreme elevations require additional coverage before general GPU claims.
* Selected single-thread timers are not a full call graph. perf sampling was restricted.
* Unexercised legacy APIs retain their original preconditions and may need ownership/error auditing.
* Current SolTrace/OptiX is not validated with CoPylot. Its legacy adapter loses hit attributes and has build/error-propagation gaps; relinking does not select OptiX or prove numerical equivalence. See [soltrace.md](soltrace.md).

## 10. Next gate

Validate the existing remote CUDA probe and the same-host CPU baseline first. Only after user review, extract a pure CPU fluxDensity contribution and establish CPU-old/CPU-new equivalence before any optical CUDA kernel. The 84–86% cost supports that candidate for these cases; imagePlaneIntercept follows with all moment/sigma/hcoef side effects.

The Phase 2–9 [roadmap](roadmap.md) remains a design. No optical CUDA, batch/evaluate_batch or OptiX integration has been implemented.
