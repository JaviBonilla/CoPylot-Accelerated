# Public computational reproducibility

## Evidence validation

Run `python -m benchmarks.analysis.validate` from the repository root. It needs only the standard library. It validates reviewed result hashes, eight annual modes, calendar counts, complete-output byte accounting, CSV/JSON agreement, rate denominators, unrounded case-specific ratios, Original process statistics, CPU sample statistics, CPU temporal group populations and CUDA campaign output coverage.

These checks validate archived aggregate evidence. They do not claim to recheck unavailable private per-state payloads, repeat the original performance measurements or establish physical validation. Historical source-report hashes identify the reports used for the export, not distributed raw private input files.

## Commercial reconstruction

Run `scripts/bootstrap.py` and the CPU tests as described in README. `commercial_reference.load_manifest()` checks the pinned layout/weather hashes and parameter provenance. `commercial_reference.py` reconstructs the 8790-heliostat public commercial case. Assets are obtained from the pinned upstream repositories; inspect the upstream terms before redistributing input assets or binaries.

## Complete commercial annual campaign

Build the diagnostics bridge and sun adapter, in addition to the numerical library:

```sh
cmake --build build/cpu --target solarpilot cpu_optical_state_bridge temporal_sun_bridge -j 8
export COPILOT_LIB_DIR="$PWD/build/cpu/lib"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export COPILOT_EXPECTED_LIBRARY_SHA256=$(sha256sum "$COPILOT_LIB_DIR/solarpilot.so" | cut -d ' ' -f 1)
.venv/bin/python benchmarks/annual_matrix.py prepare
.venv/bin/python benchmarks/annual_matrix.py seed
.venv/bin/python benchmarks/annual_matrix.py run --mode refactored --id public-refactored
.venv/bin/python benchmarks/annual_matrix.py run --mode original --id public-original
.venv/bin/python benchmarks/verify_annual_matrix.py --mode original --id public-original \
  --reference artifacts/annual-matrix/cpu/campaigns/public-refactored
.venv/bin/python benchmarks/verify_annual_matrix.py --mode refactored --id public-refactored \
  --reference artifacts/annual-matrix/cpu/campaigns/public-original
```

Preparation regenerates the exact 8760-row Daggett TMY2 sequence with midpoint hours and the existing SOLPOS implementation: 4403 daylight states are retained, including zero-DNI states; 4357 nighttime states are omitted. There is no temporal interpolation. No private files or archived prior campaigns are used. Preparation/seed/verification occur outside the measured campaign window. Outputs are written under ignored `artifacts/annual-matrix`; `COPILOT_ANNUAL_OUTPUT` selects another local output directory.

The historical canonical CPU scheduler uses 12 complete SMT core pairs (24 logical CPUs). The existing affinity checks deliberately reject incompatible topology instead of silently changing that experiment. On this topology, `run --mode cpu --workers 24 --threads 1 --id public-cpu` reproduces the selected commercial allocation. Every worker keeps a context, evaluates assigned states directly, materializes complete outputs and writes them before accepting the next state. Dynamic dispatch uses reference-probe costs when available.

For CUDA, build a separate CUDA configuration with diagnostics and the sun bridge, update `COPILOT_LIB_DIR` and its declared SHA, and run `run --mode gpu --workers 24 --id public-gpu`. This uses the existing bounded FIFO scheduler with independent ordinary CUDA contexts and static residency disabled. Verify it against an explicit complete local CPU campaign using `--reference`. A compatible GPU/toolkit and sufficient CPUs are required. CUDA validation must be performed on suitable hardware; a CPU-only build cannot establish it.

Evaluation timing includes state updates, simulation, complete output/metric materialization, NPZ writes and metadata flushes. Total wall adds context/worker setup and teardown. Post-run validation is excluded. Fresh builds and this portable harness have their own identities; historical measured times are not attributed to them.

Full campaigns require substantial disk space and runtime. The export validation only reconstructs the annual plan and runs functional tests; it does not fabricate or replace annual measurements.

## Optional containers

`scripts/annual_container.sh` accepts an explicitly supplied `COPILOT_CONTAINER_IMAGE`. No personal transport, implicit image, archived reference mount or app configuration is required. Configure toolchains and numerical environment explicitly inside that image. Local execution is the documented default.
