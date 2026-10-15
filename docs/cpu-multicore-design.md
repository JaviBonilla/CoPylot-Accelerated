# Deterministic Flat Hermite CPU multicore design

## Audit and decision gate

Phase 4 starts at ROOT 477aa0349cb12101a330c9159ad9e0a0120f09ff,
SSC c3ccd7db4d112c5787a5cfdea9df868208810893,
SolarPILOT 84f00a1a9212900aba09806bdf9878a0dd47b505 and
SolTrace 699263f12b2de1c6f12e211e3e8906a80054cc1b.

The Python simulate wrapper passes nthreads to sp_simulate. simulate_cpu calls
SimControl::SetThreadCount only when the argument differs from one. The setter
clamps to [1, hardware_concurrency]. Its saved value can therefore remain stale
after a later nthreads=1 call. PerformanceSimulationPrep, SolarField::Simulate,
HermiteFluxSimulationHandler, HermiteFluxSimulation and the current image/density
loops do not consume SimControl's count. Shadows, result processing and map
normalization are serial. DoManagedLayout and AutoPilot layout workers split
weather/design simulations across copied fields; they do not parallelize this
single-state call. SolTrace consumes its own N worker contexts while the caller
monitors them; that route is outside this phase and will not be executed.

Before editing core threading, archive the exact existing library hash and
measure Legacy and Flat at 1/2/4/8/12/24 for one retained state from each case.
Use separate first calls, two warmups, five Flat samples and three Legacy samples.
Observe runnable simulation threads separately from formal measurements. Only
after that gate may independent Flat numerical work be parallelized.

## Intended implementation if the gate confirms serial Hermite work

Use the existing simulate(data, nthreads=N) API. N is the total participating
execution count including the caller, bounded by hardware concurrency and work
size. N=1 always resets the Flat count on every call. Preserve Legacy arithmetic,
its existing SimControl behavior, and the CUDA numerical configuration.

Use bounded static contiguous ranges, N-1 joined std::threads plus the caller.
No persistent pool is required initially: measure stage-startup overhead before
adding lifecycle complexity. Join every worker before return or exception;
retain worker-local exception slots and rethrow in deterministic range order.
No callbacks, shared profiling state or error logs are invoked from workers.
Affinity belongs exclusively to the benchmark harness.

Image preparation and eligibility checks remain serial. Prepare immutable input
records and shared tables, evaluate the unchanged pure image function per
heliostat, then write back serially. The unsupported Legacy fallback remains
serial. This avoids concurrently touching receiver caches, table initialization,
heliostat objects or GPU context state. The caller's batch-ready flag only spans
the current SolarField performance simulation, like the existing CUDA batch.

Density packs heliostats serially, then each cell range visits all enabled
heliostats in their original order. Keep the existing one-thread implementation
as the 1T oracle; parallel work preserves each cell's arithmetic sequence and
initial accumulator. Unsupported aperture/snout geometry retains the serial
path. Grid writeback, normalization and power reductions remain serial. No CUDA
kernel, block-size, resident-handoff or shading algorithm changes are planned.

## Validation and measurement plan

Require bitwise maps, summary and detailed heliostat outputs across thread
counts, plus full 215-value image anchors. Test repeated calls, 1->12->1,
12->24->4, reload/destruction, error/recovery, zero/small/non-divisible work and
both flat and cylindrical geometry. Run CPU production/diagnostic regressions,
representative CUDA regressions and CPU ASan/UBSan/LSan and TSan where feasible.

Freeze CESA-I at 217x256 and commercial at 222x87, using their exact four retained
states. Measure physical-core-first affinity for 1/2/4/8/12 and both siblings at
24. Retain every sample, first call, frequency/governor, topology, effective
worker observations, binary/source hashes and CPU background-load checks.
Formal Flat uses two warmups/five samples; CUDA uses three/ten in a clean GPU
window. Keep diagnostic profiles separate and distinguish inclusive stage walls
from per-worker CPU-time sums. No governor/service changes, temporal parallelism,
new convergence, SolTrace execution, push or Phase 5 work is authorized here.
