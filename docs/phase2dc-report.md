# Phase 2D-C: measured CUDA image-plane integration

Phase 2D-C is complete. The selected implementation uses 64 image-plane threads
per block and a simulation-scoped device handoff into the unchanged 256-thread
density kernel. Complete canonical C++ optical state is eagerly materialized
before successful public return and completion callbacks. All scientific
comparisons retain rtol=1e-9 and atol=1e-10. Double precision and FMA remain enabled;
fast math is disabled.

The principal acceleration is Flat CPU 1T to final CUDA, 5.42–43.95x across the
nine cases. The incremental exact Phase 2D-B v1 to Phase 2D-C speedup is
1.057–1.137x. These are distinct claims. There is no fixed performance target.

## Provenance and environment

Initial clean repositories:

| Repository | Initial SHA | Selected implementation SHA |
|---|---|---|
| Root | ddffe62bfaee007b5aaf9cbd1a1bb813b08cfca8 | f1f6241ca77fde61060d75b3fdce4c63626dbe16 (primary performance) |
| SSC | 012b1a2ce195f5060867828773a2a339edf67b96 | cb3c0371884a2cf69aded43c20dd5081a56cf96d |
| SolarPILOT | 0b56acb4e80a5206ec8196d21eac38af5c93e405 | unchanged |
| SolTrace | 699263f12b2de1c6f12e211e3e8906a80054cc1b | unchanged |

V1 benchmark root is 86a3e7d56d48d9e1a0d45f93695c5f4e74d281dd with unchanged
SSC 012b1a2. Sweep root is 2876e27 with SSC 5554361. Final independent reprofiling
and committed correctness use root 6ca3c1804b034c227401ba043043d4eb3ad81f0e
and the same final SSC and binary. Later reporting commits do not change the
measured library. Every campaign retains its actual executed SHA; no metadata
has been rewritten to claim execution at a later documentation commit.

Hardware: NVIDIA RTX 6000 Ada Generation, 142 SMs, compute capability 8.9,
49140 MiB; Intel Xeon w5-3423, 12 cores / 24 threads. Existing canonical Docker
image sha256:8e6e3752946ff2dde451b313cbaec2ea8e7b52221b21bfbcf53fb68dd4f4c42e,
CUDA 13.0, nvcc 13.0.88, driver 580.159.03, GCC 13.3.0, CMake 3.30.5,
Release -O3 -DNDEBUG, sm_89. CPU governor remained powersave. No installation,
service operation, clock, power or governor change was performed.

## Protocol and validity

All formal campaigns passed three consecutive idle preflight readings and exact
owned-process monitoring. GPU telemetry is retained at boundaries and every two
seconds. No external GPU process or concurrent server build/test was permitted;
post-context memory was bounded to 4096 MiB, temperature below 80 C, with no
thermal slowdown. Telemetry and all individual samples are published.

Optical work uses CPU affinity 0 and one CPU thread; telemetry uses CPU 23.
CPU cases use two warmups and ten repetitions (five for H >= 5000 and grids >=
50). CUDA uses three warmups and ten repetitions. Sweep order rotates 64/128/256
across ten rounds. Means, medians, minima, maxima, sample standard deviation and
CV are retained; zero means have null CV. Ratios below use medians.

Primary timings exclude comparison CSVs, timing CSVs, CUDA events and fine
optical scopes. The common diagnostic/profile build retains its compiled coarse
scope probes. Production profile-OFF/diagnostics-OFF correctness was checked
separately; no speedup is attributed to an unmeasured production-only binary.

Fresh CoPylot-context first calls are separate from steady state, but execute in
an initialized process whose earlier modes may prime modules. They are not
cold-process comparisons. Direct image cases each use an independent process.
The runtime probe took 299.038 ms for v1 and 329.797 ms for final; these are
initialization observations, not steady-state speedups.

Early harness attempts with zero-CV and subprocess-environment errors were
rejected before publication. A completed trial with fine Flat CPU scopes enabled
was retained only as an audit artifact and rerun with those scopes disabled.
The first final raw instrumented group lacked independent event warmup; the
published final profile therefore uses a separate same-binary calibration with
three instrumented warmups and ten samples, plus paired plain runs. Original
instrumented samples remain available, without being substituted for primary
plain measurements.

## Unchanged exact v1 baseline and direct image-plane measurements

The original library was not rebuilt: SHA-256
16eb71bbd142c2589c7cb4c9589ed1745db0a9cdd9fc5903feeda8660d736df7 before and
after baseline capture. Only its standalone measurement harness was rebuilt.
All following component numbers are milliseconds, measured independently;
component medians need not sum to the wall-time median.

| H | CPU prep | Input H2D | Tables H2D | Kernel | Full D2H | CPU validation/writeback | Hybrid total | First use |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1000 | 0.6919 | 0.1730 | 0.0084 | 0.9723 | 0.2091 | 0.5581 | 2.7533 | 255.250 |
| 5000 | 3.9502 | 0.9000 | 0.0092 | 0.9795 | 0.6622 | 3.1407 | 10.5476 | 242.889 |
| 10000 | 7.8056 | 1.8707 | 0.0099 | 1.0455 | 1.2653 | 6.4791 | 20.3117 | 271.039 |

The retained raw direct samples use their explicit `_ms` and `_s` keys. The
historical harness normalizes **all `cuda_statistics` distributions to seconds**,
even inherited keys ending `_ms`; metadata explicitly records this convention.

Final direct hybrid totals, including eager full materialization, are 2.1558,
8.7331 and 17.4654 ms for 1k/5k/10k. First uses are 258.549, 243.328 and
262.251 ms, respectively. These synthetic direct tests are not full-simulate
speedups or cold application startup measurements.

## Resources, bounded sweep and stopping decision

| Block | Registers/thread | Runtime local B/thread | Active blocks/SM | Theoretical occupancy | Result |
|---:|---:|---:|---:|---:|---|
| 64 | 156 | 7648 | 6 | 25.00% | measured; selected |
| 128 | 156 | 7648 | 3 | 25.00% | measured; exact v1 launch geometry |
| 256 | 156 | 7648 | 1 | 16.67% | measured |
| 512 | 156 | 7648 | 0 | 0% | unavailable; not launched |

Runtime maxThreadsPerBlock is 384 for this kernel. The launch is ceil(H/64)
blocks, one heliostat per thread, bounds checked, no dynamic shared memory.
The ptxas stack frame/cumulative stack is **7648 bytes**, with **zero spill
stores and loads**. Zero spills does not mean zero local storage. cuobjdump
reports STACK:7648 and additional LOCAL:0; runtime localSizeBytes is 7648.
Static shared memory is zero. Runtime constantSizeBytes=0 does not mean absent
compiler constant banks: cuobjdump reports 384 B in bank 0 and 616 B in bank 2.
Shared optical tables remain ordinary read-only device data, 3256 B/call.
These numerical-kernel resources are unchanged from v1.

The two source FacetPowers arrays declare 7168 B. PTX declares a 7600 B local
depot, with 118 static ld.local and 46 st.local instruction sites. This proves
private local-state use, not dynamic memory traffic or stalls. Nsight Compute
and Compute Sanitizer are absent in the existing environment; cuobjdump is
available. Nothing was installed. No register cap, private-array rewrite,
occupancy target, fast math or precision experiment was accepted or attempted.

Direct kernel medians for 64/128/256 are 0.6465/0.9680/1.7570 ms at 1k,
0.6712/0.9790/1.7587 at 5k and 1.0394/1.0476/1.7961 at 10k. End-to-end evidence:

| H / grid | 64 simulate ms | 128 simulate ms | 256 simulate ms |
|---|---:|---:|---:|
| 1000 / 25² | 5.9846 | 6.3265 | 7.1283 |
| 1000 / 50² | 7.0043 | 7.5031 | 8.3448 |
| 1000 / 100² | 10.4832 | 10.9221 | 11.6605 |
| 5000 / 25² | 32.4044 | 32.0709 | 33.7934 |
| 5000 / 50² | 34.7711 | 35.7473 | 36.1999 |
| 5000 / 100² | 48.2364 | 47.9739 | 48.8844 |
| 10000 / 25² | 70.0898 | 69.9483 | 70.8234 |
| 10000 / 50² | 75.9896 | 75.9903 | 77.3727 |
| 10000 / 100² | 99.6195 | 100.1110 | 100.3891 |

64 helps the small cases and avoids the clear 256 penalty; larger-case 64/128
differences are within ordinary sample variation. It is an evidence-based
conservative default, not a universal optimum. The final numerical kernel takes
only 1.21% of 10k/100² public wall time. Further private-state tuning has a small
end-to-end bound and was deliberately stopped.

## Accepted handoff and public semantics

See [the exact dependency map](cuda-imageplane-fluxdensity-handoff.md).
Output comprises sun/errors/mirror/flux moments (49 each), coefficients (16),
sigmas (2) and intercept (1): exactly 215 doubles, plus update flag/padding.
Density needs 18 optical doubles and seven current CPU-derived doubles.
C/Python directly exposes intercept and derived results; public C++ getters
expose all families. None are discarded.

The original image numerical kernel produces the same complete device output.
A separate health kernel checks all 215 outputs and update status, then returns
16 B/H of intercept/update/valid status. Original CPU efficiency, intercept clamp,
geometry, shading and normalization remain in place. CPU uploads 56 B/H of current
direction/aim/normalization. A separate packing kernel joins this with the resident
18 optical doubles in the unchanged density SoA. The density numerical kernel
remains separate, with unchanged arithmetic and block size 256.

Finally, full 1728 B/H output is downloaded and written before completion callbacks
and successful public return. The pending state is simulation scoped, with exact
pointer-order/count checks and context-owned buffers. No lazy returned state,
cross-state cache, stream, pinned-memory/overlap or kernel fusion was introduced.
Unexpected ordering/filtering or an unupdated image takes complete GPU output
materialization and the existing density adapter; there is no CPU optical fallback.

Diagnostic `SOLARPILOT_IMAGE_PIPELINE=v1` selects complete output; combine it with
`SOLARPILOT_IMAGE_BLOCK_SIZE=128` to reproduce v1 launch geometry. `verify_cuda`
always compares complete 215-double CPU/GPU output. CUDA image plus Flat density
also retains full materialization. Public production has resident64 by default,
without new Python arguments. Diagnostics-OFF ignores diagnostic selection knobs.

### Bytes and host overhead

For H heliostats and C cells, per nonempty simulation:

| Transfer | Original v1 bytes | Selected final bytes |
|---|---:|---:|
| H2D total | 1840H + 3256 + 48C | 1696H + 3256 + 48C |
| D2H total | 1728H + 8C | 1744H + 8C |
| Density heliostat H2D | 200H | 56H |

H2D saves 144H (1.44 MB at 10k), a 72% reduction in the density H record and
6.20–7.81% of total H2D in the nine cases. **Total D2H increases** by 16H,
about 0.9%, because eager complete C++ compatibility remains mandatory.
Optics avoid the GPU→CPU→GPU path *between kernels*, not all eventual downloads.
Reusable owned device storage grows by 72H (required-status and metadata records).
All optical inputs and shared tables are still repacked/uploaded each call.

CPU input preparation and physical validation were retained. Density preparation
avoids 18 optical reads/host finite checks and host SoA repacking. Full output
finiteness validation moves to a GPU pass rather than being removed. Historical
matrix object writeback remains eager. In the same-campaign 10k/100² control,
full host finite scan is 3.0145 ms and matrix writeback 3.0948 ms; resident finite
scan on CPU is zero, GPU health pass 0.03562 ms and matrix writeback 3.0534 ms.
Image hybrid time falls 19.6942→16.7207 ms and density preparation
1.1619→0.4259 ms. Small input-preparation timing differences are not claimed as
an optimization because that packing code is unchanged. These are raw primary
instrumented observations; final profile fractions use independently warmed
calibration below.

## Formal nine-case full simulate results

Plain medians in milliseconds. Legacy, Flat, density-only, v1 compatibility and
final are in the final campaign; exact historical v1 is separately measured with
its preserved original binary. Density-only is a same-server reconstruction of
the historical Phase 2C path, not a republished old-machine timing.

| H / grid | Legacy | Flat 1T | Density-only GPU | Exact v1 | Final CUDA | Flat/final |
|---|---:|---:|---:|---:|---:|---:|
| 1000 / 25² | 66.403 | 33.243 | 9.837 | 6.185 | 5.438 | 6.113x |
| 1000 / 50² | 238.180 | 102.845 | 11.048 | 6.878 | 6.257 | 16.437x |
| 1000 / 100² | 969.697 | 386.257 | 14.499 | 10.381 | 9.722 | 39.732x |
| 5000 / 25² | 342.101 | 168.402 | 52.846 | 30.757 | 27.826 | 6.052x |
| 5000 / 50² | 1198.123 | 523.340 | 55.719 | 33.815 | 31.077 | 16.840x |
| 5000 / 100² | 4830.210 | 1921.292 | 69.074 | 46.221 | 43.720 | 43.946x |
| 10000 / 25² | 683.778 | 343.174 | 112.790 | 68.290 | 63.324 | 5.419x |
| 10000 / 50² | 2396.874 | 1038.288 | 118.707 | 74.473 | 68.614 | 15.132x |
| 10000 / 100² | 9655.765 | 3835.590 | 142.012 | 98.354 | 92.927 | 41.275x |

Separated staged ratios (exact-v1 comparisons span valid campaigns on the same
hardware; the same-campaign full-output control independently isolates the final
handoff/launch change):

| H / grid | Legacy/Flat | Density-only/exact v1 | Exact v1/final | Same-campaign v1/final | Flat/final | Legacy/final |
|---|---:|---:|---:|---:|---:|---:|
| 1000 / 25² | 1.998x | 1.580x | 1.137x | 1.122x | 6.113x | 12.210x |
| 1000 / 50² | 2.316x | 1.621x | 1.099x | 1.095x | 16.437x | 38.066x |
| 1000 / 100² | 2.510x | 1.364x | 1.068x | 1.067x | 39.732x | 99.747x |
| 5000 / 25² | 2.031x | 1.736x | 1.105x | 1.101x | 6.052x | 12.294x |
| 5000 / 50² | 2.289x | 1.643x | 1.088x | 1.085x | 16.840x | 38.554x |
| 5000 / 100² | 2.514x | 1.491x | 1.057x | 1.068x | 43.946x | 110.481x |
| 10000 / 25² | 1.993x | 1.659x | 1.078x | 1.076x | 5.419x | 10.798x |
| 10000 / 50² | 2.308x | 1.594x | 1.085x | 1.068x | 15.132x | 34.933x |
| 10000 / 100² | 2.517x | 1.448x | 1.058x | 1.050x | 41.275x | 103.907x |

No speedup is inferred from correctness runtimes, first calls or instrumentation.
Ratios are measured CPU 1T comparisons, not best-practical-multicore claims.

## Final disjoint profile and Amdahl interpretation

Per-sample functional budgets sum exactly to instrumented public wall time.
Image initial work is subtracted from preparation, then combined with late
materialization once. Shading and neighbors are subtracted from their preparation
parent. Normalization and dimensional postprocessing are sequential scopes;
API exclusive time and residual driver/timing work close the budget. Nested
scopes remain in raw calibration data but are not added to their parents.
Individual component medians/fractions need not sum exactly.

| H / grid | Image % | Density % | Shading % | Other prep/tracking % | Measured host prep/integration lower bound % | Observer ratio |
|---|---:|---:|---:|---:|---:|---:|
| 1000 / 25² | 32.92 | 7.29 | 23.43 | 27.94 | 49.53 | 1.0148 |
| 1000 / 50² | 28.66 | 18.55 | 20.42 | 24.53 | 43.96 | 1.0268 |
| 1000 / 100² | 19.07 | 44.86 | 13.31 | 16.46 | 30.62 | 1.0182 |
| 5000 / 25² | 25.82 | 4.88 | 34.88 | 26.97 | 53.09 | 1.0057 |
| 5000 / 50² | 23.36 | 14.71 | 31.15 | 24.09 | 47.13 | 1.0204 |
| 5000 / 100² | 16.92 | 37.20 | 22.77 | 17.76 | 35.38 | 1.0042 |
| 10000 / 25² | 25.79 | 4.26 | 39.19 | 23.82 | 50.50 | 0.9910 |
| 10000 / 50² | 23.39 | 12.25 | 35.86 | 21.79 | 46.23 | 1.0098 |
| 10000 / 100² | 17.52 | 34.25 | 26.75 | 16.29 | 34.85 | 0.9997 |

The host figure overlaps functional image/density totals: it is a separately
computed lower bound from disjoint timed host subsets, excluding shading and
unassigned driver/wait time. Do not sum that column with functional fractions.
Observer ratios compare independently warmed instrumented and paired plain
medians; near/below-one ratios reflect ordinary run variation, not negative
instrumentation cost.

| H / grid | Eliminate image ideally | Eliminate density ideally | Eliminate shading ideally | Eliminate image numerical kernel ideally |
|---|---:|---:|---:|---:|
| 1000 / 25² | 1.491x | 1.079x | 1.306x | 1.136x |
| 1000 / 100² | 1.236x | 1.814x | 1.154x | 1.073x |
| 10000 / 25² | 1.347x | 1.045x | 1.645x | 1.018x |
| 10000 / 100² | 1.212x | 1.521x | 1.365x | 1.012x |

These are ideal 1/(1-f) additional-speedup upper bounds conditional on the
instrumented workload, not predictions. At 1k/25² image integration and other
preparation dominate together; at 10k/25² shading is the largest individual
component. At 1k/100² density accounts for 44.86%; at 10k/100² density is 34.25%
and shading 26.75%. A future phase should first compare CPU preparation/shading
costs for small grids and density costs for large grids, retaining these separate
workloads. No such implementation has started.

The raw calibration includes CPU image preparation/input validation, image H2D,
health and numerical kernels, early/full D2H, object writeback, density preparation,
metadata/cell H2D, conversion kernel, density kernel, map D2H and postprocessing.
Tracking is grouped with other preparation because there is no independent
tracking-only timer; no unsupported finer attribution is invented.

## Scientific correctness and observable state

The shared 60-fixture oracle is unchanged. Both full and resident paths pass all
215 outputs. Fixture max abs is 4.092726157978177e-12, RMS
6.404148640631048e-14, worst fixture 6/coefficient 12 (global index 208).
Maximum finite relative error is 57.29797 near a zero reference; exact-zero
relative errors are null with counts, not concealed by a fabricated denominator.
Acceptance remains abs <= atol + rtol*abs(reference).

Canonical post-return C++ tests cover 1k/5k/10k, three captures each (645000,
3225000 and 6450000 values). Max abs is 4.547473508864641e-12, worst H34,
coefficient 0/global index196. RMS values are 4.400909e-14, 2.081149e-14 and
1.484839e-14; maximum finite relative errors are 20.08505, 20.08505 and
242.20490 near zero. Full/resident host state is bitwise equal and switching
back to CPU reproduces original CPU bytes. Repeated GPU output/maps are
bitwise deterministic on this GPU/build; CPU/GPU are tolerance-equal, not
universally bitwise equal.

All nine cases pass CUDA image + Flat density and full CUDA, checking complete
maps, detail columns, peaks, integrated incident flux and receiver power.
Image-only map max abs is 1.1368683772161603e-12 kW/m². Full CUDA max abs remains
1.1141310096718371e-11 kW/m², consistent with historical density rounding.
Resident/full CUDA maps are bitwise equal in every case. Per-case relative/RMS,
peak/integral/power differences and worst indices are in the correctness JSON.

Growth/shrink/repetition, block edges, 0/1 input, invisible/update-false behavior,
invalid cant/device and recovery, nonfinite device output, allocation reuse,
Sun/DNI mutation and enable/disable changes are checked. Synthetic device packing
is bitwise identical to the original host-packed density inputs/maps. Complete
Legacy/Flat regression compares 10320000 doubles with bitwise identity and zero
errors. Historical nine-case density regression passes independently.

## Validation, reconstruction and boundaries

| Configuration | Native | Python |
|---|---|---|
| CPU production, diagnostics/profile OFF | 3/3 | 32 methods: 22 pass, 10 expected skips |
| CPU diagnostic | 3/3 | 32 methods: 23 pass, 9 expected skips |
| CPU ASan/UBSan, native LeakSanitizer | 3/3 | 32 methods: 23 pass, 9 expected skips |
| CUDA diagnostic | 6/6 | 32 methods: 31 pass, 1 gated timing skip |
| CUDA production, diagnostics/profile OFF | 5/5 | 32 methods: 28 pass, 4 expected skips |
| CUDA events, separate idle functional window | — | 1/1 |

Native sanitizer tests run with leak detection. CPython tests preload sanitizer
runtimes and disable CPython leak detection; no Python leak-clean claim is made.
Compute Sanitizer is unavailable, so no CUDA sanitizer claim is made. Production
test assumptions about diagnostic-only knobs/CSV were corrected and the complete
production suite rerun; no physical implementation was changed for those tests.

SSC changes were committed in three small commits (5554361, 02e4756, cb3c037),
then exported to the full mailbox and pinned in repos.lock.json with original
upstream bases unchanged. Fresh launch and resident trees replayed the mailbox
from the original upstream commits, reproducing exact pinned SHAs. Fresh CPU
build/native/Python tests pass in both reconstructed trees. The final resident
reconstruction uses cb3c037. Current root reporting changes are fast-forwarded
without rewriting any dependency or tested numerical source.

Boundary checks prove 65 historical files unchanged; the complete image and
density numerical headers, original image numerical kernel body, density
load/numerical/contribution bodies, SolarField.cpp, Flux.cpp, host image adapter
and public physical dispatch are unchanged. SolarPILOT/SolTrace pins are
unchanged. Existing historical snapshots remain frozen and clean; active final
and reconstructed repositories are audited clean at closure. No push.

## Results and reproduction

- `phase2dc-v1-baseline.json`: preserved v1 direct/full samples and telemetry.
- `phase2dc-block-sweep.{json,csv}`: resources, bounded sweep and unavailable 512.
- `phase2dc-final-performance.json`: primary plain measurements and controls.
- `phase2dc-profile-calibration.json`: independently warmed detailed profile.
- `phase2dc-final-profile.json`: disjoint budgets, fractions and Amdahl bounds.
- `phase2dc-summary.json`: staged ratios and first calls.
- `phase2dc-handoff-analysis.json`: dependency families and actual transfer bytes.
- `phase2dc-resource-usage.json`: runtime/cubin/PTX/compiler evidence.
- `phase2dc-correctness.json`: fixtures, canonical host state, nine-case checks.
- `phase2dc-{cpu-optics,density}-regression.json`: independent regressions.
- `phase2dc-boundaries.json` and `phase2dc-validation/`: scoped checks/test logs.

Run scripts only in the documented canonical environment, after finishing builds
and checking idle GPU. No package or service change is needed:

```sh
COPILOT_LIB_DIR=build/cuda/lib .venv/bin/python benchmarks/image_plane_cuda_performance.py --stage final --output artifacts/phase2dc/final-performance.json
COPILOT_LIB_DIR=build/cuda/lib .venv/bin/python benchmarks/image_plane_cuda_performance.py --stage profile --skip-direct --output artifacts/phase2dc/final-profile-calibration.json
COPILOT_LIB_DIR=build/cuda/lib .venv/bin/python benchmarks/image_plane_pipeline_correctness.py --output artifacts/phase2dc/resident-downstream-final.json
.venv/bin/python scripts/check_phase2dc_boundaries.py
.venv/bin/python scripts/bootstrap.py
```

`summarize_phase2dc.py` assembles the complete retained campaign inputs, checks
validity/library identity, and publishes JSON with nonfinite/privacy checks. It
does not rerun or overwrite historical 2C/2D-A/2D-B measurements.

## Limitations and stop boundary

One GPU/build, specified synthetic fixtures and one-thread CPU references only;
no best-multicore, other-GPU, cold-start, annual-throughput or universal optimum
claim. No dynamic Nsight stall/traffic analysis. No injected allocation/copy
hardware fault. Eager C++ compatibility limits D2H reductions and leaves matrix
writeback/preparation CPU cost. Small launch gains can be within variability on
large cases. No benchmark ran concurrently with server builds/tests.

No annual, batch, time-series, cross-state cache, multi-GPU, CPU multithreading,
private case work, flat receiver, new aiming, shading/blocking optimization,
SolTrace, Embree or OptiX change was made. Phase 2D-C stops here; the next phase
has not started.
