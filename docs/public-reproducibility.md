# Public benchmark reproducibility

Use the [evidence index](benchmark-evidence.md) to choose the workload and
comparison boundary. The workflow separates analysis of archived measurements,
functional validation of a fresh build, and new timings. Run commands from the
repository root and put generated output under ignored `artifacts/`.

## Analyze archived measurements

These commands use only the Python standard library and the checked-in results.

```sh
python3 -m benchmarks.analysis.validate
python3 benchmarks/annual_matrix_report.py --output artifacts/archived-annual-table.md
```

The offline validator checks the reviewed evidence hashes, the eight annual
rows and CSV/JSON agreement, counts and bytes, rate denominators, unrounded
ratios, sample statistics and temporal campaign populations. The report command
renders a Markdown table. Use the [annual CSV](../benchmarks/results/annual-benchmark-matrix.csv)
or the other [indexed datasets](benchmark-evidence.md) as plotting inputs. This
workflow reads existing evidence and requires neither an optical library nor a
simulation run.

## Reconstruct and validate the commercial case

1. Follow the [build guide](build.md) to run `scripts/bootstrap.py`, install the
   pinned Python dependencies and build the CPU library with diagnostics.
2. Run `scripts/test_cpu.sh -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON` for native
   and Python numerical checks. The [example comparisons](build.md#run-the-example)
   provide a short receiver-map check for Original and Multicore against
   Refactored CPU.
3. Reconstruct the commercial field and simulate the public reference state.

```sh
export COPILOT_LIB_DIR="$PWD/build/cpu/lib"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
.venv/bin/python benchmarks/commercial_reference.py --output artifacts/commercial-check.json
```

The [commercial case manifest](../cases/commercial-reference/case_manifest.json)
pins the 8,790-heliostat layout and Daggett TMY2 asset by SHA-256 and records
parameter provenance. Reconstruction checks those assets and evaluates the
reference state with a finite, positive receiver map. The
[case guide](commercial-reference-case.md) explains the physical assumptions.
Compare the fresh output against the archived result for this same reference
state and grid.

```sh
python3 - <<'PY'
import json
import math
from pathlib import Path

fresh = json.loads(Path("artifacts/commercial-check.json").read_text())
archived = json.loads(Path("benchmarks/results/phase3a-commercial-case.json").read_text())
for key in ("case_id", "manifest_sha256", "layout_sha256", "heliostats", "flux_shape"):
    assert fresh[key] == archived[key], key
assert fresh["finite_positive"]
assert math.isclose(fresh["peak_kw_m2"], archived["peak_kw_m2"], rel_tol=1e-9, abs_tol=1e-10)
print("Commercial reference geometry and peak flux agree with the archive.")
PY
```

This is a spot check. The temporal and annual validators below check complete
outputs and state coverage.

## New single-state and repeated-call timings

Keep the CPU library and thread-pool settings from the preceding step. Use an
idle host, run the commands sequentially, and keep timing and profiling
instrumentation disabled.

```sh
SOLARPILOT_INTERCEPT_PATH=legacy SOLARPILOT_FLUX_PATH=legacy \
  .venv/bin/python benchmarks/run_cpu.py --case small --repeats 1 --skip-generation \
  --output artifacts/synthetic-original.json

SOLARPILOT_INTERCEPT_PATH=flat SOLARPILOT_FLUX_PATH=flat \
  .venv/bin/python benchmarks/run_cpu.py --case small --repeats 3 --skip-generation \
  --output artifacts/synthetic-flat-repeats.json
```

These runs use the same synthetic field and solar position with one simulation
thread. The first sample includes the initial simulation call. Additional
samples repeat that state in the same context. The report separates layout
assignment, simulation and result getters. Treat these as new synthetic
measurements, with a different protocol from the scientific single-state
controls and from the multi-state throughput results in the evidence index.

## New CPU temporal measurements

The published CPU allocation protocol requires exactly 12 complete SMT pairs
visible to the process (24 logical CPUs), Linux affinity and process counters,
and a diagnostics build. This constraint applies to the serial controls in
the temporal harness too. On other topologies, the repeated-call commands above
remain available.

Use a clean workspace with the CPU library and numerical pool settings from
above. Build the two adapters and declare the actual local library hash.
Correctness regenerates a public commercial plan, computes fresh serial
references and checks reused contexts. Campaigns consume those local outputs.

```sh
cmake --build build/cpu --target cpu_optical_state_bridge temporal_sun_bridge
export COPILOT_EXPECTED_LIBRARY_SHA256=$(sha256sum "$COPILOT_LIB_DIR/solarpilot.so" | cut -d ' ' -f 1)
.venv/bin/python benchmarks/temporal_campaign.py correctness --case commercial
.venv/bin/python benchmarks/temporal_campaign.py campaign --case commercial \
  --series seasonal --workers 1 --threads 1 --id local-seasonal-serial
.venv/bin/python benchmarks/temporal_campaign.py campaign --case commercial \
  --series seasonal --workers 24 --threads 1 --id local-seasonal-parallel
.venv/bin/python benchmarks/verify_temporal_outputs.py --id local-seasonal-serial
.venv/bin/python benchmarks/verify_temporal_outputs.py --id local-seasonal-parallel
```

Use unique campaign IDs. Inspect each `result.json` under
`artifacts/phase5a/campaigns/` for affinity, coverage, timing window
qualification and both throughput denominators. The storage check reads
persisted NPZ payloads and matches their signatures to the runtime outputs.
Compare the seasonal campaigns with the corresponding commercial series and
allocation in the [archived CPU summary](../benchmarks/results/phase5a-campaign-summary.json).
Use qualified whole campaigns for timing comparisons.

## Optional complete commercial year

Preparation regenerates all 8,760 midpoint-hour requests from the pinned
Daggett TMY2 data and the existing solar-position calculation. The plan has
4,403 daylight states, including zero-DNI states, and 4,357 nighttime omissions.
Preparation alone runs no annual simulation.

Use the CPU build, adapters, numerical pools and library hash set above.
Select a new output directory for a new plan and set of reference probes.

```sh
export COPILOT_ANNUAL_OUTPUT="$PWD/artifacts/annual-matrix"
.venv/bin/python benchmarks/annual_matrix.py prepare
```

The following commands are full campaigns. Allow substantial runtime and disk
space (about 8.5 GB of standard outputs per archived commercial campaign).
The CPU timing protocol requires the same 24-logical-CPU topology described
above. Seed the local full-output and optical-state reference probes first.

```sh
.venv/bin/python benchmarks/annual_matrix.py seed
.venv/bin/python benchmarks/annual_matrix.py run --mode refactored --id local-annual-refactored
.venv/bin/python benchmarks/annual_matrix.py run --mode original --id local-annual-original
.venv/bin/python benchmarks/annual_matrix.py run --mode cpu --workers 24 --threads 1 --id local-annual-cpu

.venv/bin/python benchmarks/verify_annual_matrix.py --mode refactored --id local-annual-refactored \
  --reference "$COPILOT_ANNUAL_OUTPUT/cpu/campaigns/local-annual-original"
.venv/bin/python benchmarks/verify_annual_matrix.py --mode original --id local-annual-original \
  --reference "$COPILOT_ANNUAL_OUTPUT/cpu/campaigns/local-annual-refactored"
.venv/bin/python benchmarks/verify_annual_matrix.py --mode cpu --id local-annual-cpu \
  --reference "$COPILOT_ANNUAL_OUTPUT/cpu/campaigns/local-annual-refactored"
```

For a separately scheduled GPU campaign, use the [CUDA build](build.md#linux-cuda)
on a suitable device and host with at least 24 available logical CPUs for the
archived allocation. Keep the plan and the complete CPU reference generated
above, and declare the CUDA library's own hash. The GPU run uses 24 independent
rolling contexts, bounded FIFO dispatch and static residency disabled.

```sh
export COPILOT_LIB_DIR="$PWD/build/cuda/lib"
export COPILOT_EXPECTED_LIBRARY_SHA256=$(sha256sum "$COPILOT_LIB_DIR/solarpilot.so" | cut -d ' ' -f 1)
.venv/bin/python benchmarks/annual_matrix.py run --mode gpu --workers 24 --id local-annual-gpu
.venv/bin/python benchmarks/verify_annual_matrix.py --mode gpu --id local-annual-gpu \
  --reference "$COPILOT_ANNUAL_OUTPUT/cpu/campaigns/local-annual-refactored"
```

The annual verifier requires an independent complete local CPU reference.
It checks state coverage, weather metadata, stored payloads and cross-mode
agreement. Compare only the matching commercial row in the
[archived annual matrix](../benchmarks/results/annual-benchmark-matrix.json).
Match the fresh campaign's `states_per_s` and `total_states_per_s` to the archive's
`evaluation_states_per_s` and `total_wall_states_per_s`, respectively. A fresh
binary or host has its own provenance, even when all numerical comparisons pass.

The public workflow reconstructs the commercial inputs locally. CESA-I can be
analyzed through the approved aggregate archive. Its private inputs and
per-state outputs are outside the public reproduction workflow.
