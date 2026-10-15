# Phase 2C measurement protocol

First capture the unchanged Phase 2B kernel at block size 256 before any SSC
source change. The existing diagnostic block-size selector already permits
64/128/256/512; the baseline requires no kernel modification.

The canonical GPU server and pinned CUDA 13.0 container run every backend with
the same Release library, inputs, compiler settings and core profiling enabled.
The main thread is pinned to the first allowed CPU; the independent GPU telemetry
thread uses the last allowed CPU. Neither clocks, power limits, governor nor
services are changed. Legacy and flat use one simulation thread.

`benchmarks/cuda_flux_performance.py` refuses an initially occupied GPU. After
the public API probe initializes the sole benchmark process, only that compute
PID may appear. Telemetry polls every two seconds and at case boundaries,
rejecting unexpected compute PIDs, memory over 1024 MiB, thermal slowdown or
85 C temperature. Initial memory must be <=128 MiB and utilization <=2%.
Process IDs and private filesystem paths are excluded from published metadata.
Polling cannot exclude a very short external workload between observations.
No builds, tests or other benchmark processes run concurrently on this server.
Only an entirely validated window is published. Invalid and partial observations
remain under ignored `artifacts/phase2c/`; existing results are never overwritten.

Each baseline case/backend has a fresh CoPylot context. First simulation is
recorded separately, followed by two excluded CPU warmups or three CUDA warmups.
CUDA always has ten measured repeats. CPU has ten except the four combinations
with H>=5000 and grid>=50, which have five to bound the long legacy/flat runs.
Every repetition is retained; median/min/max/mean/stdev/CV use all samples.
Backend-selection/probe overhead is recorded separately. The first simulate
includes fresh flux buffers and first use of the density kernel, but the public
CUDA selection probe has already initialized the process runtime. It is not a
cold-process startup measurement.

The sweep uses all nine cases and all four blocks, three excluded warmups per
block, then ten rounds rotating block execution order within one warmed context.
Correctness checks run outside timed intervals. They include complete dimensional
maps and the existing same-state raw map/peak-cell contribution diagnostic, plus
repeat determinism at each block size. Tolerances remain rtol=1e-9, atol=1e-10.

Wall simulate time surrounds the public Python call and includes instrumentation
CSV writes. CPU density time is the core-profile inclusive Flux::fluxDensity
scope (including flat adapter packing). CUDA events time the two synchronous
pageable H2D copies, kernel and D2H copy separately. Host clocks measure POD/SoA
preparation, complete hybrid density (including allocation/growth/scatter),
normalization plus dimensional postprocessing, and internal simulate. Hybrid
density excludes the common normalization/dimensional postprocessing, matching
the CPU density-scope boundary. Event copies include scheduling/staging effects;
they are not a pure PCIe bandwidth measurement. First-call allocation overhead
belongs to the host/hybrid interval, not the event transfer intervals.

All eleven existing profile scopes retain inclusive and exclusive time per
repetition. Nested times must not be added twice. Final profiling uses exclusive
scopes to identify intercept, neighbor/shading, other optical work and residual
API/analytical work; CUDA density is further decomposed using its stage timers.
Packing, event/synchronization overhead and any unassigned residual are reported
instead of forcing the sum of medians to equal the median total.

The allocation experiment runs untimed raw diagnostics in one context through
25,25,50,50,100,100,50,25 grids. Expected cumulative allocations are
3,3,5,5,7,7,7,7: only the cell and output buffers grow; shrink/repeat reuses them.

Report Legacy/Flat simulate separately from Flat/CUDA simulate. Flat density /
CUDA kernel is a kernel-only ratio with unequal host-work boundaries, not an
end-to-end speedup. The comparable hybrid ratio uses CPU density / CUDA hybrid
density. No private project or extension of the Phase 2B physics is involved.

A separate `plain` control repeats Legacy/Flat and all four CUDA blocks with
runtime event timing and profile/timing-file output disabled. Compiled core
scope probes remain identical across backends. It uses two CPU warmups and the
same 5/10 CPU repeat schedule; CUDA uses three warmups per block and ten rotating
rounds. These wall times are the primary end-to-end speedup data. Instrumented
runs supply stage decomposition; the two datasets are not silently mixed.
