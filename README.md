# CoPylot-GPU: hybrid CUDA Hermite optics

Headless workspace for accelerating CoPylot's C++ core with CUDA while preserving the Python API and original CPU reference. Legacy and Flat CPU remain available. The CUDA backend evaluates the double-precision image-plane intercept and flux density for the validated single cylindrical or rectangular flat receiver, simple or Keep existing aiming, and specified-sun or Hour/Day path. Object preparation, complete optical writeback, normalization and post-processing remain on CPU.

```bash
# Reconstruct the pinned repositories and local commit series:
python3 scripts/bootstrap.py
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
scripts/build_cpu.sh
scripts/test_cpu.sh
.venv/bin/python benchmarks/run_cpu.py --repeats 10
scripts/profile_cpu.sh
```

Library: `build/cpu/lib/solarpilot.so`. The build uses SSC solarpilot-develop and legacy SolTrace; it does not build the SolarPILOT GUI, wxWidgets, LK or WEX. Exact source and patched commit SHAs are in [repos.lock.json](repos.lock.json).

Documentation:

* [Phase 4 deterministic CPU multicore and best measured CPU/GPU comparison](docs/phase4-report.md), [threading design](docs/cpu-multicore-design.md), [aggregate summary](benchmarks/results/phase4-cpu-gpu-summary.json), [all CPU samples](benchmarks/results/phase4-flat-multicore-scaling.csv), [separate timing regimes](benchmarks/results/phase4-timing-repeatability.json).

* [Phase 3C CESA-I grid convergence and CPU/GPU characterization](docs/phase3c-report.md), [study design](docs/phase3c-design.md), [approved aggregate results](benchmarks/results/phase3c-cesa1-grid-convergence-summary.json), [timing CSV](benchmarks/results/phase3c-cesa1-grid-performance.csv).

* [Phase 3B physical compatibility and flat receivers](docs/phase3b-report.md), [restoration design](docs/phase3b-design.md), [public-safe validation](benchmarks/results/phase3b-validation.json).

* [Phase 3A scientific reference and convergence](docs/phase3a-report.md), [public commercial case](docs/commercial-reference-case.md), [physical receiver grids](docs/receiver-grid-convergence.md), [future SolTrace study](docs/soltrace-convergence-plan.md).

* [Phase 2D-C report](docs/phase2dc-report.md), [resident handoff](docs/cuda-imageplane-fluxdensity-handoff.md).
* [Phase 2D-B report](docs/phase2db-report.md), [image-plane CUDA design](docs/image-plane-cuda-design.md).
* [Phase 2D-A report](docs/phase2da-report.md), [image-plane analysis](docs/image-plane-intercept-analysis.md).

* [Phase 2C performance report](docs/phase2c-report.md), [measurement protocol](docs/phase2c-methodology.md).

* [Phase 2B report](docs/phase2b-report.md), [implemented CUDA contract](docs/cuda-flux-density.md).
* [Python SPT load/save, preparation semantics and limits](docs/spt-files.md), [validation report](docs/spt-validation-report.md).
* [Phase 2A report](docs/phase2a-report.md), [flux density analysis](docs/flux-density-analysis.md), [scaling evidence](docs/flux-density-scaling.md), [CUDA design](docs/flux-density-cuda-design.md).
* [Remote CPU/CUDA validation report](docs/remote-validation.md), [remote environment](docs/remote-gpu-environment.md).
* [Phase 0/1 report](docs/report.md).
* [Repository/branch decision](docs/dependencies.md), [build and tests](docs/build.md).
* [Measured CPU profile](docs/cpu-profile.md), [raw results](benchmarks/results).
* [Backend and proposed input versions](docs/backend.md), [GPU data model](docs/gpu-data-model.md).
* [Roadmap](docs/roadmap.md), [SolTrace/OptiX analysis](docs/soltrace.md).
* [Validation plan](docs/plan.md).

Local workspace authority: integration branch `main`, with the original 14 Phase 0/1 commits preserved. The root `.git` file points to `.workspace-git`, exposing the existing history to ordinary Git without recreating it. In the desktop sandbox, `scripts/workspace_git.sh` also works around the protected `.git` path. The three inner working trees retain independent Git repositories on `feature/copilot-gpu` and are ignored by the integration repository, not registered as submodules/gitlinks. No branches have been pushed.

The tracked mailbox patches preserve the inner repositories' small commits. `bootstrap.py` reproduces identical patched SHAs and refuses to overwrite nonmatching checkouts. Generated environments/builds are ignored; deliberate benchmark results are versioned. Remote validation uses a dedicated reproduction of a committed local integration snapshot; local remains authoritative.

Cases: exactly 1000/5000/10000 deterministically assigned heliostats, 25×25 flux map, one simulation thread, double precision, Hermite, DNI 950 W/m², azimuth 180°, elevation 55°. Regression JSON contains every flux cell and heliostat result column; `rtol=1e-9`, `atol=1e-10`. Original results were captured before dispatch/profiling; tests never regenerate them.

Phase 2A extracted the pure contribution and validated bitwise legacy/flat equality. Phase 2B adds a real one-block-per-cell double CUDA kernel, reusable RAII buffers and strict contribution/map comparisons. Nine 1k/5k/10k × 25/50/100 cases pass. Phase 2C measured all nine cases against same-server Flat CPU, retained the 256-thread kernel after a controlled block sweep, and identified CPU imagePlaneIntercept as the next hotspot. See the report for scoped timings and limits. Phase 2D-A extracted a bitwise-equivalent Flat image-plane core. Phase 2D-B adds its first one-thread-per-heliostat CUDA implementation with complete intermediate and downstream verification, keeping the density kernel unchanged. Phase 2D-C selects 64 image threads per block and a checked resident handoff into the unchanged density kernel, eagerly completing every C++ optical getter before return. Formal nine-case Flat CPU 1T to CUDA speedups are 5.42–43.95x; the incremental exact v1 to final gain is 1.057–1.137x. See the Phase 2D-C report for same-server controls, transfer accounting, profiles and limits.

Phase 3A adds a public 8790-heliostat SSC optical reference and physically defined
cylindrical/rectangular grid tooling. Scientific resolution is selected from
convergence across operating points; the Phase 2 square grids remain scaling
fixtures. See the report for conditional recommendations and the normalized-map
energy limitation. No CUDA tuning, experimental compatibility or annual API is
introduced.


Phase 3B adds explicit serialized-project geometry restoration, portable weather
reference resolution and bitwise-validated flat rectangular Hermite CPU/CUDA
support. Public synthetic and private compatibility gates preserve saved geometry,
Keep existing aims and normal Hour/Day semantics. Weather-aware preparation can
refresh site metadata, which is distinguished from restoring the saved state.
The Phase 3B native private grid is a compatibility check only; Phase 3C below studies spatial resolution.
Historical performance figures above describe their frozen phase snapshots;
Phase 3B introduces no new performance claim or CUDA tuning.


Phase 3C reuses the conservative grid framework for the restored CESA-I flat
receiver, with a fixed reference-EPW site and four normal Hour/Day states.
The conditional 1% CONTROL recommendation is 217x256; the numerical reference is
867x1024. The extra reference refinement rejects the earlier 109x128 candidate.
At the selected grid, same-server Flat CPU 1T takes about 1.29 s versus 15.4 ms
CUDA (about 84x). Every timing sample, first call and controlled-window telemetry
is retained. No independent ENERGY/ANNUAL resolution follows from normalized
power invariance. Nested core, patches and pins were unchanged in that phase; it included no new
CUDA tuning or multicore/annual work.


Phase 4 audits the original serial Hermite behavior, preserves Legacy, and adds
bounded deterministic Flat CPU work over independent heliostat images and receiver
cell ranges. The caller participates, all workers join, and each cell retains its
original heliostat addition order. The fixed CESA-I and commercial CONTROL grids
are retained. The report distinguishes Flat 1T/CUDA from best measured Flat
multicore/CUDA and publishes every sample, historical control checks, sanitizer
results and exact reconstruction evidence. An earlier complete same-binary CPU
campaign was slower; both regimes remain public and their cause is unresolved.
The measured optimum is conditional on the observed faster regime. No new CUDA
tuning or annual/temporal parallelism is introduced. Phase 5 has not started.
