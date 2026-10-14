# CoPylot-GPU: Phase 0/1 preparation

Headless workspace for accelerating CoPylot's C++ core with CUDA while preserving the Python API and CPU reference. Hermite CPU simulation, three benchmark sizes and regressions work. The optical CUDA backend is not implemented. The optional toolchain/device probe has been validated on the remote RTX 6000 Ada host; optical CUDA remains unimplemented.

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

The measured first GPU candidate is `Flux::fluxDensity()` plus its reduction, after a pure CPU extraction and equivalence checks. That numerical Phase 2 work is deferred until the remote validation report has been reviewed. No optical CUDA algorithm has been ported.
