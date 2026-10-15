# Phase 2D-A — image-plane intercept CPU extraction

Phase 2D-A is complete with a preserved Legacy oracle, a fixed numerical CPU
core, complete optical-state comparisons and same-server CPU characterization.
**Phase 2D-B has not started.** The CPU benefit is small; there is no demonstrated
consistent end-to-end acceleration. The useful result is an explicit numerical
boundary suitable for a later, separately validated GPU investigation.

## Provenance and preserved boundaries

Initial clean repositories:

| Repository | Branch | Initial HEAD |
|---|---|---|
| Root | main | e902edceb258e28766eb21cca77e7c00e4f9bc95 |
| SSC | feature/copilot-gpu | 5343ddbef451549ac573ccd020f692c26ee0e222 |
| SolarPILOT | feature/copilot-gpu | 0b56acb4e80a5206ec8196d21eac38af5c93e405 |
| SolTrace | feature/copilot-gpu | 699263f12b2de1c6f12e211e3e8906a80054cc1b |

The detailed analysis was committed in root 4c7d3bb before extraction. SSC
a400a6c5b adds profiling and an internal diagnostic bridge, preserving the
arithmetic. The server baseline at that revision was captured before Flat code
was written. SSC bb247d4f8 extracts the core and preserves the oracle; a0d23d62e
only removes trailing whitespace. The canonical library before and after that
formatting-only commit is identical:

`f7df4a6b041bb5ad99453963164f687764673e3f7db0aab58865e4474d6e018f`.

Raw JSON records the actual root/inner SHAs used for each measurement, rather
than attributing earlier measurements to the later documentation commit. Root
7385a47 preserves the original baseline; ce8f05d integrates numerical tests and
pipelines; cc24088 adds complete-output statistics tests and clean mailboxes;
fb55aa2 makes the old profile reader accept additive scopes. That compatibility
fix retains all eleven originally required scopes and the density call-count
check; it does not rerun Phase 2C or change its published results.

`check_phase2da_boundaries.py` verifies protected Phase 2C result/document bytes,
both density CUDA source files and the original optical oracle plus callees.
The oracle is equal after removing only profiling macros and whitespace. No
SolarPILOT or SolTrace commits, upstream updates, push, reset, clean, CUDA kernel,
GPU buffer/residency, shading/blocking or private-case changes are included.
The receiver remains the validated single continuous cylinder, with simple aim,
specified sun, double precision and one CPU thread. Other paths keep Legacy.

## Call flow, state and implementation

See `image-plane-intercept-analysis.md` for the pre-extraction analysis, exact
input/output ownership, normalization, helper formulas and edge preconditions.
The measured public performance simulate calls intercept exactly H times:
1000/5000/10000. Layout initialization has separate representative/zoning calls.
Disabled or rejected heliostats return in the caller; an invisible aperture
returns zero without changing prior optical state. No other H output is read,
no field reduction occurs, and tables are read-only during evaluation.

The implemented chain is:

```
SolarPILOT objects -> prepareImagePlane -> image_plane::Input
                  -> image_plane::evaluate(Input, Tables, Output)
                  -> writeImagePlane -> existing H state -> existing density
```

The core contains sun/error/projected mirror moments, facet translations,
convolution, cylinder aperture quadrature, sigmas and packed Hermite coefficients.
The adapter retains compatibility/visibility checks, object access, panel/mirror
packing and writeback. Tables refresh when `initHermiteCoefs` runs, with lazy
initialization for a copied Flux. The initial state is not consumed by the core.

The original `imagePlaneInterceptLegacy`, `hermiteIntEval`, `hermiteIntegralSetup`
and `hermiteIntegral` remain executable. Diagnostics builds accept
`SOLARPILOT_INTERCEPT_PATH=legacy|flat|verify`; verify executes both on the same H,
checks all 215 values, existing tolerances and exact bit representations. Production
uses Flat within its guarded scope. The public API is unchanged. The native
benchmark's C++ field bridge exists only in diagnostics builds and has no public
API header entry. The independent native numerical tests use a private friend.

Flat supports no cant, on-axis slant and user-radius canting and at most 64
facets. Unsupported cant/receiver/order/path/capacity falls back to Legacy.
It does not add off-axis, planar, annual, batching or private-case support.

## Correctness

* **60 direct native fixtures**, independent of `simulate`: four sun models,
  three cant methods, unfaceted/16/64 facets, symmetry, long/short ranges, distinct
  focal distances, aim offsets, 1e-8 to 0.008 error scales, point sun, zenith sun,
  direct disabled-H semantics, and invisible-state preservation. Each compares
  four complete 7x7 matrices, 16 coefficients, two sigmas and intercept.
* **48,000 H evaluations / 10,320,000 values** across 1k/5k/10k and
  25x25/50x50/100x100 are bitwise equal against the pre-extraction snapshots and
  the preserved oracle. Every output family has max abs = max rel = RMS = 0.
  The recorded argmax is index zero by convention when all differences are zero.
* Resolution changes preserve every family hash bitwise. The code reads no cell,
  grid or surface values; this evidence justifies the representative 25x25 direct
  benchmark instead of a redundant nine-way timing sweep.
* In all nine downstream cases, Legacy intercept + Flat density, Flat intercept
  + Flat density, and the full Legacy pipeline have bitwise equal maps and all
  detail columns. Peak, integrated incident flux, receiver power and numeric
  summaries agree exactly. Summary formatting is inherited; correctness also
  checks the complete arrays, not just rounded summaries.
* The existing Phase 2B correctness harness passes all nine cases with Flat
  intercept as the default input to CUDA density, at block 256. Raw contribution
  checks, complete maps, power/peak/integral, stable repeated allocations and
  bitwise repeat CUDA maps pass. Worst dimensional CPU/CUDA map max abs is
  **1.1141310096718371e-11**, within unchanged **rtol 1e-9 / atol 1e-10**.
  CPU/CUDA maps are not claimed bitwise equal: the existing CUDA reduction rounds
  differently. No GPU performance data is collected in this phase.

Machine-readable sources are `phase2da-direct-tests.json`,
`phase2da-cpu-performance.json` (all intermediate families and grid hashes),
`phase2da-correctness.json`, `phase2da-cuda-correctness.json`, and
`phase2da-summary.json` under `benchmarks/results/`.
Full numerical snapshots remain reproducible ignored benchmark artifacts; the
versioned results retain hashes, full-coverage metrics and failure-checked results.

## CPU measurements and internal profiles

Canonical Xeon w5-3423, affinity CPU 0, one thread, existing pinned CUDA-toolchain
container, GCC 13.3.0, Release `-O3 -DNDEBUG`, no fast-math or manual SIMD. The
library's **CPU backend** is selected for all CPU measurements; CUDA compilation
does not mean those samples execute GPU density. Governor remains `powersave`;
no clock, power or service settings changed. No server build/test/other benchmark
runs concurrently with the valid measurement sequence. GPU-idle checks also pass.
Each primary series keeps two warmups and all seven repetitions. Extraction,
comparison, CSV parsing and file output are outside the direct timed loop.
Detailed optical scopes are off for the primary samples and on for separate
profiles. Existing coarse intercept clocks remain enabled equally in both paths.

| H | Pre-extraction Legacy median ms | Same-final-binary Legacy median ms [min,max] | Flat median ms [min,max] | Legacy/Flat |
|---:|---:|---:|---:|---:|
| 1000 | 6.372 | 6.339 [6.310,6.799] | 6.198 [6.196,6.209] | 1.023x |
| 5000 | 32.629 | 32.083 [31.952,32.853] | 31.985 [31.149,33.617] | 1.003x |
| 10000 | 67.153 | 66.560 [66.032,69.099] | 64.578 [63.856,66.744] | 1.031x |

Primary speedups use the same final binary for both paths, not different builds.
The original baseline is retained as a chronological control. These are descriptive
medians with overlapping ranges; they do not establish a robust global gain.

10k detailed stage exclusive medians (ms):

| Stage | Pre-extraction Legacy | Final Legacy | Final Flat |
|---|---:|---:|---:|
| Visibility | 1.136 | 1.147 | included in preparation |
| Sun moments | 1.424 | 1.391 | 0.328 |
| Error transforms/moments | 4.855 | 4.897 | 4.208 |
| Mirror projection | 8.767 | 8.388 | 6.479 |
| Facets/canting | 17.013 | 17.098 | 17.101 |
| Moment convolution | 4.295 | 4.346 | 3.076 |
| Coefficients, excluding aperture | 3.449 | 3.444 | 1.993 |
| Aperture setup, excluding quadrature | 0.872 | 0.869 | 0.837 |
| Quadrature | 24.904 | 25.060 | 24.106 |

The final Flat breakdown is **preparation 7.009 ms, numerical core 60.554 ms,
writeback 0.692 ms, total 69.992 ms** (inclusive profile medians; wrapper and
instrumentation overhead also exists). Its largest exclusive numerical stages
remain quadrature and facets. Flattening reduces several table/container stages,
but guarded packing introduces meaningful adapter cost. No isolated allocation
percentage was measured. The detailed total must not be subtracted from the
64.578 ms primary median to invent exact overhead-adjusted stage times.

Whole public `simulate`, CPU Flat density in both paths:

| H/grid | Legacy intercept ms | Flat intercept ms | Legacy/Flat |
|---|---:|---:|---:|
| 1000/25x25 | 32.753 | 33.147 | 0.988x |
| 5000/25x25 | 168.897 | 167.903 | 1.006x |
| 10000/25x25 | 347.501 | 343.152 | 1.013x |
| 10000/100x100 | 3832.214 | 3841.354 | 0.998x |

There is no consistent end-to-end improvement. No end-to-end CUDA timing was
needed or collected. All individual samples are retained, including slower ones.

## Memory, compiler and future GPU investigation

Input/output/tables occupy **1640/1728/3256 bytes**. The two fixed facet power
workspaces reserve 7168 bytes; the separate uninstrumented host analysis object
reports an 8128-byte `evaluate` stack frame. It imports libm and stack protection,
with no allocation or object-method symbols. GCC vectorizes two loops using
16-byte vectors and some recurrence blocks with SLP; most nested/control-flow
loops remain scalar. No fast-math, AVX intrinsics or altered arithmetic is used.
The full compiler remarks, stack record and symbol evidence are versioned.

| H | Input bytes | Output bytes | Both arrays + tables, bytes |
|---:|---:|---:|---:|
| 1000 | 1640000 | 1728000 | 3371256 |
| 5000 | 8200000 | 8640000 | 16843256 |
| 10000 | 16400000 | 17280000 | 33683256 |

These are possible full-field storage budgets. The current CPU adapter streams
one input/output on its stack; it does **not** allocate these arrays or any GPU
buffers. Normalized mirror/panel geometry and errors can remain stable with a
template; global tables follow sunshape/order initialization. Tracking/solar
vectors, aim and ranges follow position/aim changes. Receiver/layout changes
update the relevant subsets. No residency or annual/batch policy is implemented.

A later CUDA investigation can start from one H per work item and independent
writeback, with **no cross-H reduction**. Fixed tables are read-only candidates.
The large per-H moment/facet arrays, recurrence dependencies, variable facet/cant
paths, covariance/clipping/cutoff branches and transcendentals make register use,
local-memory spills and divergence real concerns. The 8128-byte host frame is
not evidence of a CUDA register count. Do not choose a block size or promise a
speedup from this analysis. A later implementation must retain this CPU oracle,
full intermediate verification and end-to-end accounting including preparation
and writeback; it would target the numerical fraction rather than all intercept
wall time. This report recommends investigating that boundary in a separately
authorized Phase 2D-B; no implementation has begun.

## Validation, limitations and reproduction

CPU-only production CTest: **3/3 pass**. Python: **23 tests, 18 pass, 5 expected
CUDA/diagnostic skips**. The diagnostics/sanitizer build has **19 pass, 4 CUDA
skips**. Native ASan/UBSan/LeakSanitizer CTest: **3/3 pass**, with leak detection
on. Python ASan/UBSan runs preload ASan and libstdc++, with runtime leak detection
off to avoid CPython leak noise. Native leak coverage remains enabled.

CUDA CTest: **4/4 pass**. Python after the additive-profile compatibility test:
**23 tests, 22 pass, 1 expected timing-test skip**. The nine-case correctness
matrix passes. Automatic approval review rejected enabling the GPU timing test;
this was resolved by the safer correctness-only run, explicitly leaving timing
semantics untested in this phase. No GPU speedup claim depends on that omission.

An initial sanitizer run inside the sandbox failed because LeakSanitizer cannot
operate under ptrace; the subsequent run outside that tracing boundary passed.
Inherited source warnings remain (macro redefinitions, conversions and misleading
indentation); the pure core compiles without warnings. The adapter repeats the inherited
`SP_USE_SOLTRACE`/`SP_USE_THREADS` header macro-redefinition warnings; no new
warning category is introduced. Initial mailbox
trailing-whitespace warnings in the extracted source were fixed in a dedicated
formatting commit with an identical resulting library. No mathematical fixes or
silently relaxed tolerances are included.

Legacy preconditions remain: initialized order-six tables, positive heights and
sigmas, valid normalized vectors, nonzero focal/cant distances and normalization,
matching positive facet dimensions, and valid aim geometry. Singular A/E/rho
expressions, invalid vectors, empty facets and zero sigmas are not newly defined.
The direct fixture suite checks valid near-zero inputs, not arbitrary undefined
states. Unsupported paths retain their historical behavior and exceptions.

A fresh ignored workspace was cloned from local object stores, checked out at
each original upstream base, and reconstructed by applying the exported mailbox
with deterministic committer identity/dates. All three final inner HEADs exactly
match `repos.lock.json`; bootstrap verifies them. That workspace builds CPU-only
and passes CTest/Python regression. This uses no upstream refresh or reset.

Typical reproduction from a prepared workspace:

```sh
scripts/bootstrap.py
BUILD_DIR="$PWD/build/phase2da" scripts/test_cpu.sh \
  -DSOLARPILOT_ENABLE_CORE_PROFILE=ON -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON
cmake --build build/phase2da --target image_plane_benchmark
build/phase2da/image_plane_numerics
# Capture baseline at the recorded pre-extraction root/SSC revisions first.
taskset -c 0 .venv/bin/python benchmarks/image_plane.py --stage baseline
# After applying the Flat revisions and verifying the native fixtures:
COPILOT_LIB_DIR="$PWD/build/phase2da/lib" taskset -c 0 .venv/bin/python \
  benchmarks/image_plane_pipeline.py --output artifacts/phase2da/pipeline.json
taskset -c 0 .venv/bin/python benchmarks/image_plane.py --stage final
COPILOT_LIB_DIR="$PWD/build/phase2da/lib" taskset -c 0 .venv/bin/python \
  benchmarks/image_plane_pipeline.py --performance --output artifacts/phase2da/end-to-end.json
.venv/bin/python scripts/check_phase2da_boundaries.py
.venv/bin/python benchmarks/summarize_image_plane.py
```

Use the pinned existing toolchain container for a same-server comparison; the
commands above do not install packages or start/stop services. Public results
contain no usernames, IP addresses, private paths or private-case data.
