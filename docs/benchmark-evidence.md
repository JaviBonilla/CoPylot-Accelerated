# Archived benchmark evidence

The files below contain measured results and validation records. They are inputs
to offline analysis. Fresh builds and campaigns produce separate outputs with
their own hardware, compiler and binary identities.

| Evidence | Files and interpretation |
| --- | --- |
| Single-state execution modes | [Original baseline](../benchmarks/results/original-baseline-single-state.json) and [CPU/GPU comparison](../benchmarks/results/phase4s-cpu-gpu-summary.json) record the Legacy and refactored CPU controls, multicore CPU and CUDA comparisons. The [Original validation](../benchmarks/results/original-baseline-validation.json) records compatibility checks. |
| CPU temporal allocation | [CPU campaign summary](../benchmarks/results/phase5a-campaign-summary.json) records workers across independent states, threads per state, scheduling policy, repetitions and accepted timing windows. Allocations with the same 24-logical-CPU budget can use it differently. |
| GPU temporal and annual selection | [CUDA campaign summary](../benchmarks/results/phase5b-annual-summary.json) records the evaluated groups, payload coverage and the selected rolling-context configuration. |
| Complete annual comparison | The [CSV](../benchmarks/results/annual-benchmark-matrix.csv) and [JSON](../benchmarks/results/annual-benchmark-matrix.json) contain eight complete measurements across two cases and four approaches. [Annual validation](../benchmarks/results/annual-benchmark-validation.json) records coverage and cross-mode checks. |
| Hardware and compiler | [Measured toolchain](../benchmarks/results/measured-toolchain.json) records the reference Xeon w5-3423, RTX 6000 Ada and GCC 13.3 configuration. [CUDA details](phase2dc-report.md) record the toolkit and driver. Per-result hashes and revisions identify the actual measured library and sources. |
| Integrity and provenance | The [dataset manifest](dataset-manifest.json) lists file hashes. The [reviewed evidence manifest](../benchmarks/results/public-evidence-manifest.json) records hashes and provenance for the sanitized projections. The [dependency pins](../repos.lock.json) describe what a fresh checkout builds. |

The complete commercial annual workload contains 4,403 daylight states on a
222 × 87 receiver grid. The selected CPU strategy uses 24 independent states with
one thread each. The selected GPU strategy uses 24 independent rolling contexts.
The Original and Refactored CPU controls use a single state and one thread.
The JSON distinguishes six newly executed campaigns at the time of the study
from two earlier accepted commercial campaigns. CESA-I appears only as approved
aggregate evidence because its input data and per-state records are private.

## Timing boundaries

Evaluation throughput divides the completed state count by evaluation wall time.
That window includes state updates, simulation, complete output materialization,
NPZ writes and worker metadata flushes. Total elapsed time adds worker and
context setup and teardown. Total-wall throughput uses that longer denominator.
Validation runs outside both benchmark windows. Both rates include the first
call under the annual protocol. Compare like-for-like timing boundaries and
workloads, and use the unrounded total times for total-wall speedups.

## Numerical checks

The annual validation checks expected states and metadata, complete persisted
arrays, finite values, runtime output signatures and byte accounting. Zero-DNI
daylight states are retained and checked for zero flux. The annual CPU controls
use bitwise checks against CPU references. CUDA uses the recorded
`rtol=1e-9`, `atol=1e-10` criterion. Fresh representative CPU probes also check
all 215 optical values per heliostat. These checks establish computational
compatibility for the evaluated cases.

Use the [reproducibility guide](public-reproducibility.md) to render tables from the
archive, rerun functional checks, or plan a fresh benchmark.
