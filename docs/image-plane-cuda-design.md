# Phase 2D-B image-plane CUDA design

This phase implements the first correctness-oriented device version of the
Phase 2D-A Flat model. It does not tune the kernel or extend physical support.
The initial clean root is 459a178; SSC is a0d23d62e. Full initial states and
protected Phase 2C/2D-A file hashes are recorded in the initial-state JSON.

## Numerical source and initial mapping

The CPU Flat formulas moved mechanically into a shared host/device numerical
header, with the existing CPU entry point retained. The Legacy oracle remains
unchanged. Host profiling annotations disappear only in the device compilation
pass. No formula, threshold, constant, summation order or tolerance is changed.
Normal CUDA FMA remains enabled; no fast-math or approximate replacements.

One CUDA thread evaluates one independent heliostat. Use a fixed **128 threads**
per block, chosen as a conventional first implementation, not an optimum. There
is no cross-heliostat reduction. All 215 output doubles and the updated flag are
retained and downloaded before the existing CPU writeback and density adapter.

Use the existing trivial AoS input/output: 1640/1728 bytes, alignment 8. Explicit
size/offset/alignment assertions and a device layout probe check the host/device
ABI. Fixed-width metadata replaces implementation-sized integer/boolean fields
without changing the byte budget. No host object or pointer crosses the boundary.
The 3256-byte read-only Tables object uses a separate ordinary device allocation;
it is copied on each evaluation, with no constant-memory/residency experiment.

The fixed moment, facet and quadrature arrays remain private per thread. The
8128-byte host frame from 2D-A is a resource risk, not a device resource estimate.
Record ptxas, runtime attributes and readily available occupancy at the fixed
block size before considering any restructuring. High local memory alone is not
a reason to tune a correct, executable first kernel.

## Ownership and integration

GpuContext owns a separate image-plane executor with RAII device input,
output and table buffers, independent capacities and checked normal teardown.
Do not change FluxDensityKernels.cu or FluxDensityCuda.cpp. Device context changes
and destruction release both executors. No allocation per H and no H x cells
storage. Repeated and smaller inputs reuse capacities; larger inputs may grow.

After existing aim/tracking preparation, SolarField gathers exactly the enabled,
accepted heliostats and evaluates one image-plane batch before its existing
per-H efficiency loop. Download/writeback populates the same optical fields;
that loop consumes the prepared intercept and retains its existing clamp and
shading/blocking behavior. Batch-ready state is scoped to this simulation and
cleared on errors. No neighbor, shadow or acceptance algorithm changes.

The validated public CUDA backend uses CUDA intercept plus existing CUDA
density. Diagnostics retain explicit Legacy/Flat intercept with CUDA density,
and CUDA intercept with Flat CPU density. These combinations are internal test
controls, not new public backend variants. Unsupported CUDA image-plane inputs
raise a backend error, never silently run CPU intercept. Historical Phase 2B/2C
harnesses explicitly select Flat CPU intercept to retain their original meaning.

## Validation matrix and measurement policy

1. Reuse the exact 60 Phase 2D-A fixtures, comparing all seven output families.
2. Compare all H/215 values for 1k, 5k, 10k, with counts, max abs, max rel, RMS,
   absolute/relative worst H and family element, zero-reference handling and
   bitwise flags. Repeat device evaluation to test determinism.
3. Check H=0/1/127/128/129/nonmultiple; invisible/disabled layer semantics,
   capacity growth/reuse/shrink, unsupported inputs and device errors.
4. Nine downstream H/grid cases compare CPU/CPU, CUDA/CPU, CPU/CUDA and CUDA/CUDA,
   separating intercept effects from density arithmetic/reduction effects.
5. Run CPU-only, CUDA, Legacy/Flat regression, sanitizers, resource queries and
   fresh original-base-plus-mailbox reconstruction.

Tolerances remain rtol=1e-9 and atol=1e-10 for every family and downstream check.
Near-zero relative errors never replace absolute/RMS reporting. No intermediate
failure may be hidden by a passing map. If differences fail, locate the first
family/element and mathematical stage rather than changing tolerances or FMA.

Correctness may run safely with external GPU load. Preliminary timing is optional
and only valid after immediate GPU/process checks, with no concurrent builds/tests
or other benchmark jobs on the server. Never stop services or change clocks.
Any timing is labeled Phase 2D-B preliminary baseline; no final speedup claims.
No sweeps, register limits, streams, pinned memory, overlap, fusion, residency,
CPU multithreading, new receiver/aiming support or Phase 2D-C work is included.

## Measured implementation

The input ends with three int32 fields, two uint8 flags and two explicit padding
bytes. The output has 215 doubles (1720 bytes), one uint8 updated flag and seven
explicit zeroed padding bytes. The device layout probe agrees with every host
size, alignment and selected field offset. Input vectors include tracking,
tower and sun directions, geometry/error scalars, 49 normalized mirror moments,
and two arrays of 64 facet centers. Tables contain sun moments, binomial/factorial
and error tables, and the original Hermite/quadrature constants.

For sm_89, CUDA 13.0 ptxas reports 156 registers/thread, a 7648-byte stack frame,
zero spill stores/loads, and constant banks of 384/616 bytes. Runtime attributes
report 7648 local bytes/thread, zero static shared bytes and constSizeBytes=0;
both constant reports are retained as reported. Dynamic shared memory is zero.
The fixed-128 occupancy query reports three active blocks/SM and 25% theoretical
occupancy. These are resource limits, not profiler evidence of an actual stall
or bottleneck. The kernel executes correctly at every tested size, so no
resource-driven restructuring or optimization was necessary.

Private temporaries retain the Flat moment arrays, 7x7 transforms, facet-center
work, seven-term powers, sixteen Hermite coefficients and quadrature state.
Local memory is backed by device memory; it is not fast shared memory. Outputs
are written to the complete global output record, not to an additional per-H
host object or H-by-cell allocation.

Repeated calls reuse all three device allocations; growth replaces input/output
buffers independently and shrinking retains capacity. H=0 copies and launches
nothing. All 3256 table bytes are uploaded for each nonempty call. The total
owned optical buffer size at 10k is 33,683,256 bytes, separate from the CUDA
context/stack allocation observed by nvidia-smi. Checked close attempts all
resources; destructors provide best-effort cleanup on exceptions.

All 60 fixtures, all 215 values for 1k/5k/10k and all nine downstream cases pass
the original tolerances. GPU repetitions are bitwise deterministic on the
tested binary/device. CPU/GPU sun moments are bitwise identical; other families
can differ. Exact counts, relative errors, RMS and worst indices are in the
Phase 2D-B JSON files. See [the report](phase2db-report.md) for measured limits.

The preliminary harness requires three consecutive idle readings before context
creation, then checks the exact owned GPU process set and memory/temperature
outside each sample. Utilization counters from a terminated previous child can
remain nonzero with no GPU process; incomplete attempts are discarded. The
completed three-size baseline passed these checks without changing GPU services
or clocks. It is not a formal performance campaign.
