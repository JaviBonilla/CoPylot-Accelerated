# Phase 2D-B: first correct CUDA image-plane implementation

The first one-thread-per-heliostat CUDA image-plane kernel passes all 60 shared
fixtures, complete 215-double comparisons for 1k/5k/10k, and all nine downstream
configurations at unchanged rtol=1e-9 and atol=1e-10. Public CUDA now uses both
image-plane and density kernels within the existing physical scope. This phase
does not optimize either kernel and does not start Phase 2D-C.

## Provenance and protected state

Initial repositories were clean: root main 459a178274fcd50f74b8cd9f760c12fb037fb8b6;
SSC feature/copilot-gpu a0d23d62e120a4f2438a3d4a3f04b9231bb2f0e4;
SolarPILOT 0b56acb4e80a5206ec8196d21eac38af5c93e405 and
SolTrace 699263f12b2de1c6f12e211e3e8906a80054cc1b on feature/copilot-gpu.
The initial-state JSON records status, pins and protected hashes.

SSC is now 012b1a2ce195f5060867828773a2a339edf67b96, through commits 57409f22a
(shared numerical core/device executor), 71f2c7b4a (host batch integration and
checked ownership), and 012b1a2ce (validate device before constructing resources). SolarPILOT and SolTrace did not change. Mailbox patches and
the SSC patched pin were updated; all original upstream bases remain unchanged.
Each JSON records its actual tested root SHA rather than a later documentation
commit: d7888da for the final core/downstream build and completed preliminary
timing harness. The final native recovery check reproduced a sticky invalid-device
error during failed-constructor cleanup; validating the index before constructing
RAII resources fixes it, and valid subsequent execution now passes. Numerical
formulas and kernel resources are unchanged by this error-path correction.

Phase 2C and 2D-A published evidence remains byte-identical to the initial hash
inventory. FluxDensityKernels.cu and FluxDensityCuda.cpp remain byte-identical;
density uses 256 threads. The Legacy oracle token hash remains
3b82234992790e91fb214612635e603d35a91222a17440fc718e202cd2dac044.
The boundary checker has an explicit --allow-image-plane-cuda option for this
subsequent phase; its historical default still enforces the original 2D-A limit.
Private local cases stay ignored/untracked and were not used for this phase.

Canonical GPU validation uses the existing pinned container, Xeon w5-3423,
RTX 6000 Ada (142 SM, compute capability 8.9), driver 580.159.03, CUDA 13.0 /
nvcc 13.0.88, GCC 13.3, Release -O3 -DNDEBUG. The kernel explicitly compiles with
--fmad=true and --ptxas-options=-v; no --use_fast_math or approximate math is used.
All optical arithmetic is double. CUDA event APIs themselves require float
milliseconds; that type is not used for optical calculations. CPU-only builds
have no CUDA header/compiler/runtime dependency.

## Architecture and data boundary

The validated Flat body moved mechanically into ImagePlaneInterceptNumerics.h,
shared by CPU and device compilation. Host profiling annotations are removed
only in the device pass. Legacy remains the independent historical oracle;
the same 60 fixtures still verify Legacy/Flat bitwise equality.

One thread computes one independent heliostat, with bounds checking and no
cross-heliostat reduction. A fixed block of 128 is a conventional initial choice,
not an optimized value. There was no sweep, register limit or occupancy tuning.
The [design](image-plane-cuda-design.md) gives field details and ownership.

| Record | Layout | Bytes | Alignment | Explicit padding |
|---|---|---:|---:|---:|
| Input | AoS, fixed numeric arrays and fixed-width metadata | 1640/H | 8 | 2 |
| Output | Four 7x7 matrices, 16 coefficients, 2 sigmas, intercept, updated flag | 1728/H | 8 | 7 |
| Tables | Shared read-only numerical tables in an ordinary device buffer | 3256 | 8 | 0 |

Output retains all 215 doubles plus its update flag. The device layout probe
matches host sizes, alignment and selected offsets. No SolarPILOT object,
pointer graph or host pointer is uploaded. No output subset was eliminated.

GpuContext owns separate RAII image-plane and density executors. The new input,
output and table capacities are independent and reusable. Repeated/smaller calls
do not allocate; growth replaces only insufficient buffers. There is no per-H
malloc/free or H-by-cell allocation. H=0 performs no transfers or kernel launch.

After existing aiming/tracking preparation, a single batch gathers enabled,
accepted heliostats, computes the kernel, downloads everything and writes the
existing CPU optical fields. The existing per-H loop consumes the prepared raw
intercept and retains its original clamp and shading/blocking logic. Scoped
hooks and batch-ready state reset on errors. Device changes and destruction
attempt checked teardown of both executors. Reused capacity does not imply
optical-data residency: all nonempty calls upload every input and table, then
download the entire output before density's existing adapter runs.

| H | Input H2D (B) | Tables H2D (B) | Total H2D (B) | Output D2H (B) |
|---:|---:|---:|---:|---:|
| 1000 | 1,640,000 | 3256 | 1,643,256 | 1,728,000 |
| 5000 | 8,200,000 | 3256 | 8,203,256 | 8,640,000 |
| 10000 | 16,400,000 | 3256 | 16,403,256 | 17,280,000 |

Tables preserve the original sun/binomial/factorial/error and quadrature/Hermite
constants. No constant/texture memory experiment was performed. Private fixed
arrays retain the Flat moment, transform, facet, power and quadrature work.

## Device resources

| Metric | Final sm_89 kernel |
|---|---:|
| Registers/thread | 156 |
| Runtime local bytes/thread | 7648 |
| ptxas stack frame / cumulative stack | 7648 / 7648 B |
| Spill stores / loads | 0 / 0 B |
| Static / dynamic shared memory | 0 / 0 B |
| ptxas cmem[0] / cmem[2] | 384 / 616 B |
| Runtime constSizeBytes | 0 B |
| Active blocks/SM at 128 | 3 |
| Theoretical occupancy | 25% |

The JSON retains ptxas and runtime constant reports separately as reported.
Local memory is backed by device memory, not fast shared memory. Large private
state and the fixed-block occupancy limit are demonstrated resource costs.
Zero spills does not mean zero local-memory use. No profiler counters establish
an actual bottleneck, divergence rate, cache behavior or transcendental share.
The kernel runs correctly through 10k, so no architectural restructuring was
required to complete this correctness phase.

## Numerical verification

The seven families have 49/49/49/49/16/2/1 values per heliostat. Every comparison
records count, max absolute error, max relative error, RMS, worst H/fixture and
family index, nonfinite count, zero-reference differences and bitwise status.
Relative error is undefined/infinite when a CPU zero has a nonzero GPU output:
JSON uses null plus zero_reference_nonzero, and separately max_rel_nonzero.
Passing always uses the original combined absolute/relative tolerance.

The fixture maximum is 4.092726157978177e-12 (fixture 6, coefficient 12), global
RMS 6.404148640631048e-14. The largest finite-reference relative error is
57.297972213466956 among near-zero coefficients. Sun moments are bitwise equal.
The fixture table and full-field table below are generated from the recorded
JSON; all individual worst indices are retained there.

| Family | Fixture max abs | Fixture max rel (nonzero reference) | Fixture RMS | Worst fixture / element |
|---|---:|---:|---:|---|
| sun | 0 | 0 | 0 | 0 / 0 |
| errors | 8.67362e-19 | 2.87022e-15 | 5.62321e-20 | 3 / 14 |
| mirror | 1.26218e-29 | 2.19713e-06 | 8.19259e-31 | 0 / 14 |
| flux_moments | 1.73472e-18 | 2.19713e-06 | 7.41715e-20 | 18 / 14 |
| coefficients | 4.09273e-12 | 57.298 | 2.34758e-13 | 6 / 12 |
| sigmas | 1.38778e-17 | 2.54068e-16 | 3.00176e-18 | 8 / 0 |
| intercept | 5.55112e-16 | 7.04991e-16 | 1.82692e-16 | 59 / 0 |

| H | Compared values | Global max abs | Global max rel (nonzero reference) | Global RMS |
|---:|---:|---:|---:|---:|
| 1000 | 215000 | 4.54747e-12 | 20.0851 | 4.40091e-14 |
| 5000 | 1075000 | 4.54747e-12 | 20.0851 | 2.08115e-14 |
| 10000 | 2150000 | 4.54747e-12 | 242.205 | 1.48484e-14 |

| Family (10k) | Max abs | Max rel (nonzero reference) | RMS | Worst H / element (abs) |
|---|---:|---:|---:|---|
| sun | 0 | 0 | 0 | 0 / 0 |
| errors | 1.11022e-16 | 1.3032e-13 | 5.45288e-18 | 74 / 0 |
| mirror | 1.29247e-26 | 1.19376e-06 | 1.80554e-28 | 157 / 0 |
| flux_moments | 1.11022e-16 | 1.18163e-06 | 3.34211e-18 | 81 / 0 |
| coefficients | 4.54747e-12 | 242.205 | 5.443e-14 | 34 / 0 |
| sigmas | 1.38778e-17 | 5.57912e-16 | 2.78483e-18 | 4718 / 0 |
| intercept | 7.77156e-16 | 8.81007e-16 | 1.65401e-16 | 3188 / 0 |

The full-field global maximum is 4.547473508864641e-12 at H index 34,
coefficient 0. Large relative errors occur near zero; even the global absolute
maximum is below atol=1e-10. No tolerance was relaxed, FMA disabled, formula
simplified or CPU/GPU bitwise identity claimed for the other families.

Native edges cover H=0,1,127,128,129,259,1000,5000,10000, then 1 and 0, including
an invisible input. Public tests cover disabled-H filtering, unsupported 72-facet
input with recovery, mixed pipelines and invalid backend/device behavior. The
focused native test also executes a valid kernel after rejected inputs/device.
Repeated complete output records, including padding, and repeated downstream
maps are bitwise identical on the tested binary/device. Growth/repeat/shrink
retains capacity; the edge sequence ends with capacity 10000. This does not
assert determinism across other compilers, CUDA versions or architectures.

## Downstream and historical error isolation

Internal diagnostic controls cover Legacy+Flat, Flat+Flat, Flat+CUDA,
CUDA+Flat and CUDA+CUDA. Public CUDA defaults to both CUDA stages; explicit
diagnostic Flat intercept retains the historical density-only path. The 2B/2C
harnesses select that historical path themselves. No public signature changes.

All nine 1k/5k/10k by 25/50/100 grid combinations pass full maps, peak flux,
integrated incident flux, receiver power and every detail column. Legacy/Flat
maps remain bitwise equal. The image-plane-only map error is at most
1.1368683772161603e-12 kW/m2. Full CUDA reaches 1.1141310096718371e-11 kW/m2,
also reached by historical CUDA density and density with the same CUDA optics.
The JSON preserves each comparison independently; errors are not assumed to
add arithmetically and are not hidden behind the total map result.

| H | Grid | Intercept-only map max abs | Historical density max abs | Same CUDA optics, density max abs | Full CUDA map max abs |
|---:|---:|---:|---:|---:|---:|
| 1000 | 25 | 1.7053e-13 | 7.38964e-13 | 6.82121e-13 | 7.38964e-13 |
| 1000 | 50 | 2.27374e-13 | 8.52651e-13 | 8.52651e-13 | 8.52651e-13 |
| 1000 | 100 | 3.41061e-13 | 7.95808e-13 | 9.66338e-13 | 9.09495e-13 |
| 5000 | 25 | 4.54747e-13 | 3.52429e-12 | 3.29692e-12 | 3.52429e-12 |
| 5000 | 50 | 5.68434e-13 | 4.20641e-12 | 4.54747e-12 | 4.3201e-12 |
| 5000 | 100 | 6.82121e-13 | 5.00222e-12 | 5.00222e-12 | 5.00222e-12 |
| 10000 | 25 | 1.13687e-12 | 7.50333e-12 | 7.7307e-12 | 7.27596e-12 |
| 10000 | 50 | 9.09495e-13 | 9.09495e-12 | 8.6402e-12 | 9.09495e-12 |
| 10000 | 100 | 9.09495e-13 | 1.11413e-11 | 1.11413e-11 | 1.11413e-11 |

Full-CUDA peak absolute difference is at most 2.9558577807620168e-12 kW/m2;
integrated incident difference at most 3.4924596548080444e-10 kW; receiver power
difference is zero. The integral uses the same relative tolerance on its larger
physical magnitude. Same-state density diagnostics preserve contribution and
reduction errors separately. The additional historical nine-case density-only
campaign passes without changing its original 256-thread kernel.

Unsupported configurations still fail explicitly: no CUDA support/device,
invalid device, non-Hermite, multiple/flat/unsupported cylinder receiver,
unsupported aiming/time/thread mode, unsupported canting, more than 64 facets
or invalid numerical inputs. There is no silent CPU fallback for public CUDA.
The direct numerical fixtures do not expand public physical dispatch.

## Preliminary baseline, not a performance claim

Only after builds/tests had ended, the dedicated server snapshot collected two
warmups and five repetitions for each H at grid 25, one CPU thread pinned to
CPU 0. The unchanged governor was powersave. No clocks, power settings or GPU
services changed. Three consecutive idle readings precede context creation;
the exact owned GPU process set and memory/temperature are checked outside each
sample. Each successful case records 16 checks, no external GPU processes,
maximum temperature 45/45/45 C and GPU memory 1822/1838/1854 MiB respectively.
This telemetry includes CUDA context/stack memory, not just optical buffers.

Earlier incomplete attempts were rejected because the utilization counter
remained nonzero after the previous child exited (2 MiB, no compute process,
32% reported utilization). They are not published as valid timings. The final
harness waits for stable idle instead of weakening any limits.

| H | CPU Flat total | Preparation | Input H2D | Table H2D | Kernel | D2H | Writeback | Hybrid total |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1000 | 6.861777 | 0.673143 | 0.170400 | 0.007712 | 0.967456 | 0.180832 | 0.544971 | 2.701895 |
| 5000 | 32.602356 | 3.841740 | 0.895264 | 0.009216 | 0.993280 | 0.664192 | 3.134253 | 10.432669 |
| 10000 | 64.796392 | 7.848831 | 1.854560 | 0.009504 | 1.130592 | 1.259360 | 6.477592 | 20.400836 |

Times are medians in milliseconds; all individual samples/min/max remain in
JSON. Preparation packs the real adapter inputs. H2D includes the separate table
copy; CUDA events measure transfer/kernel intervals. Writeback includes a full
finite-output scan. Hybrid total also includes validation, driver/event overhead
and the remaining host work, so component medians need not sum to the median
total. CPU Flat total is the private Flat adapter path in the same field harness,
not a newly repeated formal 2D-A campaign. No whole-simulation speedup is claimed.

Phase 2D-C may study register/local state, fixed-block occupancy, math cost,
layout/transfer/writeback costs and other measured candidates. Such work needs
its own formal same-server protocol. None was implemented or swept here.

## Regression, reconstruction and limits

CPU-only production: 3/3 native tests and 26 Python tests (18 pass, 8 expected
GPU/diagnostic skips). Server CPU diagnostics: 3/3 native and 26 Python tests
(19 pass, 7 CUDA skips). CUDA diagnostics: 5/5 native and 26 Python tests
(25 pass, 1 timing-gated skip); that event test then passed separately after
three immediate idle GPU checks. Every Python test is therefore covered by
the combined CUDA runs. Legacy/Flat image-plane bitwise checks remain in both
suites. The separate nine-case CPU optical-state regression compares all
10,320,000 values again: bitwise equality, max abs=0, max rel=0 and RMS=0.

CPU Debug ASan+UBSan+LeakSanitizer: 3/3 native tests pass with leak detection.
Python sanitizer tests: 26 tests, 19 pass and 7 CUDA skips; ASan/UBSan halt on
errors, Python leak detection disabled for interpreter allocation noise. The
native leak suite covers the C++ ownership boundary. Compute Sanitizer is absent
from PATH and the existing toolkit directories; nothing was installed. GPU
memory-check coverage is therefore a stated limit, not a claimed pass.

A fresh ignored reconstruction cloned local object stores at all three original
upstream bases, replayed the complete tracked mailboxes with deterministic
committer dates/identity, and reproduced all patched SHAs exactly. Bootstrap
verifies the pins, and its CPU build/native/Python suite passes. Historical
mailbox whitespace warnings occur in an older intermediate commit, followed by
its existing cleanup commit; final sources pass diff checks. Dedicated remote
2D-B CPU/CUDA snapshots provide additional build evidence; frozen 2D-A snapshots
are preserved. Final states and checks are in the validation JSON/logs.

New implementation files are SSC ImagePlaneInterceptNumerics.h,
ImagePlaneInterceptCuda.{h,cpp}, ImagePlaneInterceptKernels.cu and
ImagePlaneInterceptComparison.h, with minimal Flux/ComputeBackend/CoPilot_API/
SolarField integration. Root adds shared fixtures, CUDA native/public tests,
correctness/preliminary/summary harnesses, build wiring and documentation.
The root integration history contains the tests, guards, evidence and report;
SolarPILOT/SolTrace have no artificial commits.

Results: phase2db-imageplane-correctness.json, phase2db-downstream-correctness.json,
phase2db-resource-usage.json, phase2db-preliminary-timing.json,
phase2db-cpu-optics-regression.json, phase2db-density-regression.json and
phase2db-validation.json under benchmarks/results. Validation logs are sanitized;
raw temporary artifacts and incomplete attempts stay ignored. No private case
data, account name, address or private absolute path is published in results.

Validation covers this device/compiler and the established synthetic physical
scope, not arbitrary fields or other architectures. No block sweep, density
tuning, shading/blocking change, private-case work, CPU multithreading, annual/
time-series batching, streams/pinned memory/overlap, resident optical outputs,
kernel fusion, SolTrace/OptiX work, dependency update or push was performed.
Phase 2D-B ends here; Phase 2D-C has not started.
