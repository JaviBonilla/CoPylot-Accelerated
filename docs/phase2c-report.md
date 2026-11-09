# Phase 2C: CUDA performance characterization

Phase 2C is complete with **the unchanged CUDA v1 production default, 256 threads
per cell**. No tested alternative produces a material, consistent kernel and
end-to-end improvement. No SSC/SolarPILOT/SolTrace code or dependency pin changed.
The final profile identifies CPU `Flux::imagePlaneIntercept` as the next hotspot.
Phase 2D is not implemented.

## Reproducible evidence

* Initial repository state: all four working trees clean; Phase 2B and SPT committed.
* [Immutable instrumented CUDA v1 baseline](../benchmarks/results/phase2c-baseline.json), captured before any kernel modification (none was subsequently made).
* [36-case instrumented block sweep](../benchmarks/results/phase2c-block-sweep.json) and [compact CSV](../benchmarks/results/phase2c-block-sweep.csv).
* [Primary event/file-output-free end-to-end control](../benchmarks/results/phase2c-end-to-end.json).
* [Fresh final production-default profile](../benchmarks/results/phase2c-final.json).
* [Kernel resources](../benchmarks/results/phase2c-kernel-resources.json), [derived metrics and paired intervals](../benchmarks/results/phase2c-summary.json).
* [Unchanged Phase 2B suite rerun](../benchmarks/results/phase2c-correctness.json). The public archive carries this summary.
* [Detailed protocol](phase2c-methodology.md); analysis is reproducible with `benchmarks/summarize_phase2c.py`.

The baseline, sweep, plain control and final profile have identical shared-library
SHA-256 `419b3f615643168e047f73463ec736f26ed0d5a1aec8e74069f18f69124e6e52`.
Raw metadata records the exact integration/dependency SHAs for each run. SSC
remains `5343ddbef451549ac573ccd020f692c26ee0e222`, SolarPILOT remains
`0b56acb4e80a5206ec8196d21eac38af5c93e405`, and SolTrace remains
`699263f12b2de1c6f12e211e3e8906a80054cc1b`. Their working trees are unchanged.

## Environment and method

Canonical same-machine CPU/GPU server: Intel Xeon w5-3423 (12 cores/24 threads),
RTX 6000 Ada Generation (142 SMs, sm_89, 49140 MiB), driver 580.159.03. Existing
pinned CUDA container: CUDA 13.0, nvcc 13.0.88, GCC 13.3.0, CMake 3.30.5, Release
`-O3 -DNDEBUG`, double precision, normal FMA, no fast math. Core profiling and
flux diagnostics are enabled identically for every backend. No host toolkit,
driver, clock, power-limit, governor or service change was made. Nsight Compute
is unavailable and was not installed.

The simulation thread uses CPU 0; telemetry uses CPU 23. The existing CPU governor
is `powersave`, left unchanged, with automatic hardware frequency behavior.
No builds/tests/other benchmark jobs ran concurrently on the server during any
performance window. Legacy and Flat use one thread in the same CUDA-enabled
library, not CPU timings from another computer.

Two CPU warmups; three CUDA warmups, all excluded. CPU has ten repeats except
H>=5000/grid>=50 (five, bounding long legacy runs; same rule for both CPU paths).
CUDA has ten repeats. The sweep/plain control rotate block order over ten rounds
within each case. Every sample and median/min/max/mean/stdev/CV are retained;
there is no best-run selection. The largest observed plain CUDA CV is
5.17%.
Small sub-percent block differences are not interpreted as optimization gains.

GPU windows began at 2 MiB, 0% utilization and no compute processes. Only the
benchmark's initialized process is subsequently allowed. Before/after case
checks and two-second telemetry reject external compute processes, >1024 MiB
memory, thermal slowdown or >=85 C. Across all valid windows, observed memory
peaked at 442 MiB (the benchmark process), temperature at 50 C, and no thermal
slowdown or unexpected process was observed. Automatic clocks varied with load;
no fixed clocks are claimed. Polling cannot exclude very short external work
between samples. Metadata uses a generic machine identifier and omits private
paths, usernames, IP addresses and private project data.

The nine synthetic inputs, weather hash and layout generator are unchanged from
Phase 2B. Raw metadata `parameters` contains base defaults; each case's grid
overrides x/y resolution and `configure` sets q_des=H/10. The derived summary
explicitly records these effective parameters and layout hashes.

## Primary same-machine steady-state end-to-end results

Milliseconds, medians. Events and per-call profile/timing file output are disabled
for this table; compiled core scope probes remain identical for every backend.
Generation, extraction and correctness work are outside timed calls.


| H | Grid | Legacy ms | Flat ms | CUDA 256 ms | Flat/CUDA simulate |
|---:|---:|---:|---:|---:|---:|
| 1000 | 25² | 72.472 | 33.174 | 10.054 | 3.30× |
| 1000 | 50² | 254.480 | 103.792 | 10.945 | 9.48× |
| 1000 | 100² | 1026.329 | 388.433 | 14.337 | 27.09× |
| 5000 | 25² | 355.296 | 169.643 | 54.680 | 3.10× |
| 5000 | 50² | 1277.523 | 525.378 | 57.868 | 9.08× |
| 5000 | 100² | 5125.728 | 1932.984 | 70.125 | 27.56× |
| 10000 | 25² | 714.498 | 345.918 | 113.964 | 3.04× |
| 10000 | 50² | 2530.282 | 1046.145 | 120.862 | 8.66× |
| 10000 | 100² | 10203.234 | 3850.140 | 143.466 | 26.84× |


The following ratios stay separate. The kernel-only ratio compares the full Flat
density scope (including its adapter) with device kernel time; it is not an
end-to-end speedup. Density/hybrid timings come from instrumented runs; simulate
ratios come from the plain control above.

| H | Grid | Legacy/Flat simulate | Flat density/kernel | Flat density/hybrid | Legacy/CUDA simulate |
|---:|---:|---:|---:|---:|---:|
| 1000 | 25² | 2.18× | 79.95× | 44.52× | 7.21× |
| 1000 | 50² | 2.45× | 92.61× | 78.78× | 23.25× |
| 1000 | 100² | 2.64× | 88.15× | 82.27× | 71.58× |
| 5000 | 25² | 2.09× | 95.65× | 68.73× | 6.50× |
| 5000 | 50² | 2.43× | 108.71× | 96.89× | 22.08× |
| 5000 | 100² | 2.65× | 111.71× | 107.49× | 73.09× |
| 10000 | 25² | 2.07× | 105.20× | 70.69× | 6.27× |
| 10000 | 50² | 2.42× | 118.18× | 103.14× | 20.94× |
| 10000 | 100² | 2.65× | 120.12× | 115.08× | 71.12× |


Legacy-to-CUDA includes the CPU refactor benefit and is secondary. It is never
presented as the improvement caused solely by GPU.

## First call versus steady state

Single observed first simulation per fresh CoPylot/GpuContext; these are not
startup distributions. Public backend selection already probes CUDA, so this
is not cold-process startup. The baseline process-runtime probe cost 302.158 ms
and is separate; other windows observed 181.812–317.277 ms. No startup speedup
is inferred. Fresh flux-buffer allocation remains inside first simulate.

The following baseline table is instrumented and must not be mixed silently
with the primary plain end-to-end table.

| H | Grid | First call ms | Steady median ms | Min ms | Max ms |
|---:|---:|---:|---:|---:|---:|
| 1000 | 25² | 10.692 | 9.832 | 9.798 | 10.401 |
| 1000 | 50² | 11.061 | 10.703 | 10.677 | 11.228 |
| 1000 | 100² | 14.675 | 14.182 | 14.146 | 14.206 |
| 5000 | 25² | 56.241 | 52.821 | 52.762 | 54.891 |
| 5000 | 50² | 61.432 | 56.407 | 55.824 | 58.968 |
| 5000 | 100² | 71.155 | 69.019 | 68.887 | 72.024 |
| 10000 | 25² | 115.570 | 113.376 | 112.937 | 117.805 |
| 10000 | 50² | 122.760 | 122.200 | 118.819 | 124.189 |
| 10000 | 100² | 147.686 | 144.154 | 142.206 | 147.633 |


The untimed capacity experiment observes cumulative flux-buffer allocations
3,3,5,5,7,7,7,7 for grids 25,25,50,50,100,100,50,25 in one context: three on first
use, zero on second/successive unchanged calls, two per cell/output growth, none
when shrinking. H capacity stays 1000. Probe allocations, events, driver context
and allocator granularity are not counted as flux-buffer allocations.

## Block sweep and resource characterization

Kernel medians, milliseconds. All four use exactly the same compiled kernel;
only the launch block dimension changes. Hybrid, instrumented simulate and
plain simulate distributions for all 36 combinations are in the CSV/JSON.

| H | Grid | 64 | 128 | 256 | 512 |
|---:|---:|---:|---:|---:|---:|
| 1000 | 25² | 0.297 | 0.300 | 0.292 | 0.294 |
| 1000 | 50² | 1.112 | 1.102 | 1.101 | 1.120 |
| 1000 | 100² | 4.320 | 4.272 | 4.287 | 4.372 |
| 5000 | 25² | 1.233 | 1.238 | 1.221 | 1.213 |
| 5000 | 50² | 4.385 | 4.342 | 4.321 | 4.344 |
| 5000 | 100² | 17.074 | 16.873 | 16.877 | 17.058 |
| 10000 | 25² | 2.243 | 2.253 | 2.236 | 2.227 |
| 10000 | 50² | 7.944 | 7.959 | 7.932 | 7.969 |
| 10000 | 100² | 31.459 | 31.033 | 31.051 | 31.328 |


Geometric-mean plain simulate speedups relative to 256 are 0.99915× (64),
0.99579× (128), 1.00000× (256), and 0.99944× (512). Paired bootstrap intervals
(5000 fixed-seed resamples of ten rotating rounds) are supplied per case; these
are descriptive small-sample intervals, not evidence of universal performance.
No alternative provides a consistent material kernel or end-to-end gain.
**Decision: retain 256; no production code change.**

Runtime Driver API queries on the actual baseline cubin report 94 32-bit
registers/thread, zero static shared bytes, 40 local bytes/thread and a 640-thread
kernel limit. An independent compilation of the unchanged source with the same
nvcc/O3/sm_89 settings reports a 40-byte stack frame and **zero spill stores and
loads**. Local stack storage is not reported as register spilling.

| Block | Dynamic shared bytes | Resident blocks/SM | Active warps/SM | Theoretical occupancy |
|---:|---:|---:|---:|---:|
| 64 | 512 | 10 | 20 | 41.67% |
| 128 | 1024 | 5 | 20 | 41.67% |
| 256 | 2048 | 2 | 16 | 33.33% |
| 512 | 4096 | 1 | 16 | 33.33% |


Occupancy uses NVIDIA's [Driver occupancy API](https://docs.nvidia.com/cuda/cuda-driver-api/group__CUDA__OCCUPANCY.html).
It is a resource upper bound, not achieved occupancy. A 625-cell grid also limits
how many blocks can occupy 142 SMs. Higher theoretical occupancy alone did not
accelerate this kernel. Registers remain 94 for every runtime block size; no
`--maxrregcount` experiment was justified. Nsight counters are unavailable, so no
claim of measured memory/compute bound behavior or achieved occupancy is made.

Only block size was experimentally varied. Alternative reduction/layout changes,
register caps, residency, pinned memory, streams, graphs and batching were not
implemented. The measured block alternatives were rejected; untested alternatives
are deferred, not falsely described as failed experiments. The unchanged fixed
double reduction, SoA heliostats/AoS cells, normal FMA and O(H+C) device storage
remain intact; no global atomics or H×C matrix exists.

## Fresh final profile and transfer decomposition

Ten profiled repeats after three excluded warmups, using the actual production
default without a block override. A second ten-repeat plain confirmation is
stored separately. The baseline library hash and source are unchanged.

Milliseconds, medians. Optical prep is the inclusive `PerformanceSimulationPrep`
scope: it contains intercept and neighbor shading/blocking and must not be added
to those child times again. Packing is POD+SoA host preparation. Hybrid includes
packing/growth/transfers/kernel/scatter; normalization/dimensional postprocessing
is separate. CPU shadows and residual API/analytical costs are in the exclusive
profiles below. The sum of independently reported medians need not equal the
median total. Pageable-copy event intervals include staging/scheduling effects.

| H | Grid | Optical prep | Pack | H2D H | H2D cells | Kernel | D2H | Post | Hybrid density | Simulate |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1000 | 25² | 9.393 | 0.111 | 0.050 | 0.019 | 0.298 | 0.015 | 0.015 | 0.535 | 10.399 |
| 1000 | 50² | 9.062 | 0.083 | 0.031 | 0.018 | 1.008 | 0.013 | 0.020 | 1.185 | 10.695 |
| 1000 | 100² | 8.983 | 0.133 | 0.029 | 0.055 | 4.282 | 0.027 | 0.057 | 4.588 | 14.105 |
| 5000 | 25² | 49.880 | 0.307 | 0.113 | 0.013 | 1.218 | 0.010 | 0.061 | 1.695 | 53.317 |
| 5000 | 50² | 49.275 | 0.334 | 0.113 | 0.020 | 4.321 | 0.014 | 0.071 | 4.848 | 55.859 |
| 5000 | 100² | 49.853 | 0.393 | 0.113 | 0.060 | 16.874 | 0.023 | 0.113 | 17.536 | 69.338 |
| 10000 | 25² | 107.555 | 0.845 | 0.185 | 0.011 | 2.236 | 0.012 | 0.134 | 3.328 | 114.667 |
| 10000 | 50² | 106.006 | 0.888 | 0.184 | 0.022 | 7.929 | 0.014 | 0.145 | 9.086 | 118.828 |
| 10000 | 100² | 107.142 | 0.994 | 0.189 | 0.069 | 31.056 | 0.025 | 0.252 | 32.417 | 143.601 |


| H | Grid | H2D H bytes | H2D cells bytes | Total H2D bytes | D2H bytes | Transfer % simulate |
|---:|---:|---:|---:|---:|---:|---:|
| 1000 | 25² | 200000 | 30000 | 230000 | 5000 | 0.814% |
| 1000 | 50² | 200000 | 120000 | 320000 | 20000 | 0.584% |
| 1000 | 100² | 200000 | 480000 | 680000 | 80000 | 0.791% |
| 5000 | 25² | 1000000 | 30000 | 1030000 | 5000 | 0.256% |
| 5000 | 50² | 1000000 | 120000 | 1120000 | 20000 | 0.264% |
| 5000 | 100² | 1000000 | 480000 | 1480000 | 80000 | 0.283% |
| 10000 | 25² | 2000000 | 30000 | 2030000 | 5000 | 0.182% |
| 10000 | 50² | 2000000 | 120000 | 2120000 | 20000 | 0.185% |
| 10000 | 100² | 2000000 | 480000 | 2480000 | 80000 | 0.196% |


Transfers preserve 200H+48C H2D and 8C D2H bytes per call. For 10k/100²,
packing is about 0.994 ms, transfers 0.282 ms and postprocessing 0.252 ms versus
143.601 ms instrumented simulate. These measurements do not justify implementing
residency, pinned memory or overlap in this phase.

## New hotspot, scaling and Amdahl

Approximate shares of median internal API time, using exclusive scopes. Density
contains kernel/packing/transfers; intercept is not counted again inside its
parent preparation. Remaining CPU/API work includes normalization, dimensional
conversion, neighbor updates and unscoped work. Median ratios are approximate.

| H | Grid | Intercept | Neighbor shading/blocking | Density | Other |
|---:|---:|---:|---:|---:|---:|
| 1000 | 25² | 63.9% | 13.4% | 5.2% | 17.5% |
| 1000 | 50² | 59.3% | 12.9% | 11.1% | 16.7% |
| 1000 | 100² | 44.3% | 9.6% | 32.6% | 13.4% |
| 5000 | 25² | 61.5% | 19.6% | 3.2% | 15.7% |
| 5000 | 50² | 57.7% | 18.4% | 8.7% | 15.2% |
| 5000 | 100² | 47.4% | 14.9% | 25.3% | 12.4% |
| 10000 | 25² | 58.8% | 23.2% | 2.9% | 15.0% |
| 10000 | 50² | 55.9% | 21.9% | 7.7% | 14.6% |
| 10000 | 100² | 46.8% | 18.4% | 22.6% | 12.2% |


Classification **A: imagePlaneIntercept dominates** in every measured configuration.
For 10k/100² its exclusive time is approximately 67.1 ms (46.8%), compared with
26.4 ms neighbor shading/blocking and 31.1 ms GPU kernel. For 10k/25² the density
scope is only about 2.9% of API time, while intercept is about 58.8%.

The freshly measured Flat density share is 68.0% at 10k/25² and 97.1% at
10k/100². Eliminating it entirely gives approximate Flat Amdahl limits of 3.12×
and 34.41×; the observed primary Flat/CUDA speedups are 3.04× and 26.84×.
The density/kernel ratio must not be substituted for those end-to-end gains.

Kernel work grows approximately with H×C, while the optical preparation remains
primarily H-dependent. More receiver cells amortize the unchanged CPU optical
cost, explaining the roughly 3×, 9× and 27× end-to-end groups at 25², 50² and 100².
H-dependent neighbor/optical costs and real geometry prevent exact linear scaling.
Transfers and host packing are small in this supported range.

At 10k/100², eliminating the remaining kernel entirely could improve the current
end-to-end time by only about 1.28×. Eliminating intercept alone has an idealized
additional limit near 1.88× (2.43× at 10k/25²), before considering transfer and
integration overhead of a future implementation. These are optimistic Amdahl
bounds, not predictions of attainable GPU performance.

**Recommended Phase 2D:** investigate a separately scoped imagePlaneIntercept
acceleration/design, retaining Legacy/Flat as references and validating its
contribution/coefficients and full maps. No such implementation, new receiver
physics, private-case adaptation, CPU multithreading, annual work, SolTrace or
OptiX work is included here. Further density micro-optimization stops because
all block alternatives are marginal and another component clearly dominates.

## Correctness, preservation and limits

All 36 block/case combinations pass complete dimensional maps and same-state raw
maps/peak-cell diagnostics at rtol=1e-9, atol=1e-10. Repeated CUDA maps are bitwise
equal at every tested block size. Legacy/Flat remain bitwise equal. Maximum
errors across the sweep are:


* Dimensional max absolute: 1.11413100967e-11 kW/m².

* Max relative: 8.94403141018e-15 (nonzero-reference cells).

* RMS maximum: 1.55775093144e-12 kW/m².

* Peak difference maximum: 3.18323145621e-12 kW/m².

* Integrated incident flux difference maximum: 3.49245965481e-10 kW.


Receiver power differences are zero at the existing summary API's reported
precision. The final-default maximum relative error is 8.86709e-15 and its maximum peak
difference is 2.95586e-12 kW/m². The fresh final-default profile and unchanged
nine-case Phase 2B suite rerun also pass. Original Phase 2B artifacts and historical baselines were
not replaced or regenerated. SPT regressions remain included.

CPU-only Release build: CTest 2/2, Python 15 passed/5 expected CUDA-or-diagnostic
skips. CUDA Release build: CTest 3/3, Python 20/20 passed, including the functional
CUDA-event test after verifying the free GPU. The standalone CUDA matrix is 9/9.
No dependencies changed, so existing pins/patches remain correct; bootstrap
verification confirms all three clean pinned trees. Only integration commits
were needed. No artificial dependency commits, push or history rewrites occurred.

Limitations: one GPU/server/compiler combination and one supported physical
configuration family; CPU powersave and automatic GPU clocks remain in effect;
compiled core-profile probes remain in plain controls; ten/five repetitions are
finite; first call is a single fresh-context observation, not cold-process
latency statistics; telemetry polls cannot prove absence of sub-second external
work; no Nsight achieved-occupancy/stall counters. Small block differences are
noise-scale and are not claimed as wins. No private project was benchmarked,
modified or copied into versioned results. SolTrace and all numerical/CUDA source
are unchanged. Phase 2D remains unstarted.

