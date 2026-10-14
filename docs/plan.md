# Phase 0/1 plan and validation gates

This preparation phase is complete. The plan below records its sequence; it is not an instruction to repeat the phase.

1. Pin repositories and branch choices (`repos.lock.json`, `docs/dependencies.md`).
2. Headless superbuild (`CMakeLists.txt`, `scripts/build_cpu.sh`, `docs/build.md`): Release, ctypes loading and complete linking before numerical changes.
3. Python cases (`benchmarks/cases.py`, `smoke_test.py`, `run_cpu.py`): generated-layout smoke and deterministic 1000/5000/10000-position benchmarks; generation and assignment timed separately.
4. Readable original CPU reference (`tests/baselines/*.json`): metrics, flux and all heliostat columns captured before dispatch/profiling.
5. Optional profiling (`ssc/solarpilot/CoreProfile.*`, selected scopes): inclusive/exclusive times and counts, avoiding sums of nested scopes.
6. Backend/API boundary (`ComputeBackend.*`, `CoPilot_API.*`, `copylot.py`): CPU retains the existing implementation; CUDA rejects unsupported optical simulation explicitly; rerun full regression.
7. Optional CUDA (`CudaProbe.cu`, CMake): CPU-only without a Toolkit, clear configure failure when ON without nvcc, real device verification on a suitable remote environment.
8. Data/residency/epochs and numerical roadmap documented without implementing optical kernels.

## Validation matrix

| Change | Required validation |
|---|---|
| Build | Release, no GUI/wx, ldd -r, no unresolved symbols |
| Cases | Context, layout, simulate, finite/nonempty/positive flux/results, context release in finally |
| Baseline | Three exact assigned sizes, every cell and heliostat column, explicit tolerances, DNI/sun restoration |
| Profile | OFF/ON numerical equivalence, scope counts and inclusive/exclusive times |
| Backend/API | CPU default/selection, invalid inputs, unsupported CUDA, visible errors, legacy output forms |
| CUDA build | OFF without CUDA, explicit failure if ON without Toolkit, real probe/device execution remotely |
| Memory | Native ASan/UBSan/LSan and Python ASan/UBSan checks |

Current continuation scope: preserve integration Git, reproduce the committed snapshot on the configured remote GPU host, validate CPU and the existing trivial CUDA probe, and record the same-machine CPU baseline. Do not begin numerical Phase 2 before user review.
