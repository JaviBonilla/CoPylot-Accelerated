# CPU profile: measured baseline

Host: 12th Gen Intel(R) Core(TM) i5-1240P. Linux x86_64, GCC 13.3, CMake 3.30.5, Release/O3, double precision, one core simulation thread. Python 3.12, NumPy 1.26.4, pandas 2.2.3. No affinity/frequency locking; wall times depend on host load/thermal state.

Weather: pinned Daggett TMY2; azimuth 180°, elevation 55°, DNI 950 W/m², external cylindrical receiver 17.65 m diameter ×21.6 m height, simple aimpoints, 25×25 flux map. Assigned concentric-ring layouts have exactly 1000/5000/10000 heliostats. Generated fields are a separate measurement (one design point with filtering).

Raw timings/CSV are tracked under benchmarks/results. Original CPU numbers precede dispatch/profiling and use five serial simulations per case. Profile numbers are separate opt-in builds/runs. Warm repeated calls execute the full simulation; the first call is preserved separately in raw data.

## Original CPU end-to-end medians (five calls)

| Case | Generated count | generate_layout ms | assign_layout ms | simulate ms | get_fluxmap ms | detail_results ms |
|---|---:|---:|---:|---:|---:|---:|
| small (1000) | 1421 | 91.471 | 50.540 | 67.812 | 0.076 | 1.902 |
| medium (5000) | 6291 | 171.799 | 122.144 | 328.821 | 0.071 | 9.804 |
| large (10000) | 13704 | 227.590 | 203.773 | 669.905 | 0.064 | 20.450 |

## Core scope measurements

Mean per simulate across five calls. Percentages use instrumented C API wall time. Inclusive rows overlap; never add the parent and child percentages. Exclusive times subtract other instrumented scopes only, not every uninstrumented callee. CSV includes layout phases separately; tables below select phase=simulate. Main timers are compiled out with profiling OFF. Per-thread accounting is validated for nthreads=1, not for worker-thread aggregation.

perf sampling was attempted but software events are blocked by perf_event_paranoid=4. No system settings were changed. Optional internal steady_clock scopes were used instead.

### small

| Function | Calls/simulate | Inclusive ms | Exclusive ms | Inclusive % |
|---|---:|---:|---:|---:|
| API | 1 | 71.428 | 0.257 | 100.00 |
| PerformanceSimulationPrep | 1 | 9.381 | 0.025 | 13.13 |
| calcHeliostatShadows | 1 | 0.177 | 0.177 | 0.25 |
| HermiteFluxSimulation | 1 | 61.612 | 0.001 | 86.26 |
| AnalyticalFluxSimulation | 1 | 61.585 | 0.005 | 86.22 |
| CalcDimensionalFluxProfiles | 1 | 0.026 | 0.026 | 0.04 |
| Flux::fluxDensity | 1 | 61.580 | 61.580 | 86.21 |
| Flux::imagePlaneIntercept | 1000 | 6.532 | 6.532 | 9.15 |
| UpdateNeighborList | 1 | 0.058 | 0.058 | 0.08 |
| SolarField::Simulate | 1 | 9.356 | 1.354 | 13.10 |
| ShadingBlockingNeighbors | 1000 | 1.411 | 1.411 | 1.98 |

Profile/original median wall-time ratio: 1.016. This mixes timer overhead and host variability; it is not a calibrated pure instrumentation overhead estimate.

### medium

| Function | Calls/simulate | Inclusive ms | Exclusive ms | Inclusive % |
|---|---:|---:|---:|---:|
| API | 1 | 348.442 | 0.847 | 100.00 |
| PerformanceSimulationPrep | 1 | 51.284 | 0.135 | 14.72 |
| calcHeliostatShadows | 1 | 0.858 | 0.858 | 0.25 |
| HermiteFluxSimulation | 1 | 295.452 | 0.001 | 84.79 |
| AnalyticalFluxSimulation | 1 | 295.329 | 0.005 | 84.76 |
| CalcDimensionalFluxProfiles | 1 | 0.122 | 0.122 | 0.04 |
| Flux::fluxDensity | 1 | 295.324 | 295.324 | 84.76 |
| Flux::imagePlaneIntercept | 5000 | 33.110 | 33.110 | 9.50 |
| UpdateNeighborList | 1 | 0.312 | 0.312 | 0.09 |
| SolarField::Simulate | 1 | 51.149 | 6.655 | 14.68 |
| ShadingBlockingNeighbors | 5000 | 11.072 | 11.072 | 3.18 |

Profile/original median wall-time ratio: 1.057. This mixes timer overhead and host variability; it is not a calibrated pure instrumentation overhead estimate.

### large

| Function | Calls/simulate | Inclusive ms | Exclusive ms | Inclusive % |
|---|---:|---:|---:|---:|
| API | 1 | 721.898 | 1.813 | 100.00 |
| PerformanceSimulationPrep | 1 | 109.401 | 0.251 | 15.15 |
| calcHeliostatShadows | 1 | 1.794 | 1.794 | 0.25 |
| HermiteFluxSimulation | 1 | 608.890 | 0.001 | 84.35 |
| AnalyticalFluxSimulation | 1 | 608.643 | 0.006 | 84.31 |
| CalcDimensionalFluxProfiles | 1 | 0.246 | 0.246 | 0.03 |
| Flux::fluxDensity | 1 | 608.637 | 608.637 | 84.31 |
| Flux::imagePlaneIntercept | 10000 | 66.672 | 66.672 | 9.24 |
| UpdateNeighborList | 1 | 0.620 | 0.620 | 0.09 |
| SolarField::Simulate | 1 | 109.149 | 13.737 | 15.12 |
| ShadingBlockingNeighbors | 10000 | 28.121 | 28.121 | 3.90 |

Profile/original median wall-time ratio: 1.064. This mixes timer overhead and host variability; it is not a calibrated pure instrumentation overhead estimate.

## Hypotheses and implications

* **A measured:** imagePlaneIntercept is ~9% of these simulate calls, exactly one call per heliostat. It matters, but it is not the dominant cost. The parent preparation scope is ~13–16%, including efficiency/tracking/neighbors.
* **B measured:** fluxDensity is ~84–86%, essentially all AnalyticalFluxSimulation time. CalcDimensionalFluxProfiles is ~0.03–0.04%. These measurements support prioritizing the flux contribution kernel/reduction at this resolution.
* **C measured:** the real shading/blocking neighbor loop is ~2%, 3.2%, 3.9% for small/medium/large. calcHeliostatShadows alone is ~0.25% and does not include those pair calculations. Neighbors grow in relevance with size here, but low elevation/dense layouts need separate profiling; no general bottleneck claim is made.
* **D measured:** at 10000 heliostats, the export-overhead benchmark isolates the raw C allocation/export from full Python dictionary conversion; see table below. Repeated identical simulate calls show no large persistent computation cache benefit in this path. **Code-based inference:** preparation recreates receiver grids/cloud data, updates aim/tracking, rebuilds neighbor validity and recomputes images each call. Resident GPU data and device-side objectives can avoid some packing/returns. Deep layout-thread copies/multiprocessing/optimization overhead have not been timed; no percentage is assigned to them.

## C array export versus Python conversion

Separate Release run, 15 repetitions, 10000 heliostats. Raw C times include allocation/fill and ctypes call, excluding the explicit free; Python times include conversion and free. Their difference approximates conversion/wrapper overhead, not an exact separately sampled attribution.

| Result | Raw C median ms | Complete Python median ms |
|---|---:|---:|
| detail_results | 1.113 | 21.905 |
| get_fluxmap | 0.008 | 0.061 |

No GPU timings or speedup claims. The profiling distribution applies only to these fixed cases; more cells can increase flux cost, and different aiming/geometries/optimization workloads can change the candidate ranking. Full-precision snapshots and strict tolerances remain the gate for any pure CPU extraction or CUDA implementation.
