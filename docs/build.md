# Headless Linux build

Dependencies: Git, CMake >=3.24 and <4 for bundled legacy CMake, Ninja, GCC/G++ (tested 13.3), Python 3.12 + venv/pip. CUDA is optional and OFF by default. No GUI, wxWidgets, LK or WEX.

From this workspace:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
scripts/build_cpu.sh
.venv/bin/python benchmarks/smoke_test.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python benchmarks/run_cpu.py --repeats 5
```

Equivalent build:

```bash
cmake -S . -B build/cpu -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_COPILOT_API=ON
cmake --build build/cpu --target solarpilot -j8
ldd -r build/cpu/lib/solarpilot.so
```

`CMakeLists.txt` includes only SolTrace/coretrace (legacy release) and SSC's headless superbuild. A generated NLopt `config.h` is produced by its bundled configure script under `build/cpu/nlopt-config`, never in the source checkout. The solarpilot target links coretrace + shared (weather/util only) + nlopt + lpsolve + Threads. `--no-undefined` rejects incomplete linking. CORETRACEDIR is set internally to the pinned sibling repository; no persistent shell environment variables are needed.

Library: `build/cpu/lib/solarpilot.so`. Upstream CMake also copies it into `SolarPILOT/deploy/api`; that copy reflects the last linked build. Use the explicit build/lib path below when testing multiple configurations. Benchmarks load the build-specific file and briefly set cwd because upstream `CoPylot()` loads relative to cwd. Set `COPILOT_LIB_DIR=/absolute/path/build/other/lib` to test another build without copying over the CPU reference.

Build-only compatibility fixes: SolTrace's treemesh.cpp explicitly includes `<limits>`; SSC's HELIO_INTERCEPT macro is `0` rather than invalid `false;`, preserving its disabled state. These are required before a clean Linux baseline can compile. SSC shared's unrelated MPFIT produces a GCC 13 `-Werror=alloc-size-larger-than` diagnostic; our dependency closure excludes it instead of modifying numerical code or disabling warnings globally.

The generator requires an enabled land bounds mode. Disabling scaled bounds without enabling fixed bounds leaves zero extents and can throw from radialStaggerPositions. The fixtures explicitly select fixed radii; no generator algorithm was changed. Smoke generates a bounded single-design-point field; benchmarks separately generate/filter fields and assign deterministic 1000/5000/10000-position layouts with filtering disabled. Timings label these distinct operations.

Baseline capture is deliberate: `tests/capture_baseline.py`. Do not regenerate baselines to make a regression pass. Baselines were captured before backend dispatch/profiling. The upstream summary rounds numbers, so strict comparison also checks full precision flux values and every per-heliostat column. Integrated flux is incident flux, before receiver absorptance; compare to absorbed power only with the absorptance factor.

Optional instrumentation is compile-time disabled by default:

```bash
scripts/profile_cpu.sh
COPILOT_LIB_DIR="$PWD/build/profile/lib" .venv/bin/python -m unittest discover -s tests -v
```

CSV rows contain phase, function, call count, inclusive seconds, exclusive seconds. Phases distinguish layout preparation from simulate. Nested scopes preserve inclusive/exclusive accounting on one thread; benchmark threads are explicitly one. These selected scopes do not claim a full call graph. Set `SOLARPILOT_PROFILE_FILE` only when collecting profiles. Timers disappear entirely when the option is OFF.

## Recreate source dependencies and local commits

```bash
python3 scripts/bootstrap.py
```

This reads upstream pins and patched SHAs from repos.lock.json, clones on `feature/copilot-gpu`, then applies the tracked mailbox patch series. It refuses to overwrite existing nonmatching/modified checkouts. The committer metadata and original author dates recreate identical local commit SHAs. The exact clone → patch → clean configure/build → smoke/regression workflow was independently exercised under `/tmp/copilot-repro`. Updating tracked patch series during development uses `scripts/export_patches.py`; baseline capture remains a separate deliberate action.

## CUDA probe (requires a separate NVIDIA/CUDA environment)

```bash
BUILD_DIR="$PWD/build/cuda" scripts/test_cpu.sh -DSOLARPILOT_ENABLE_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=75
COPILOT_LIB_DIR="$PWD/build/cuda/lib" .venv/bin/python -c 'import sys; sys.path.insert(0,"benchmarks"); from cases import api; cp=api(); print(cp.cuda_available(), cp.cuda_device_count()); r=cp.data_create(); cp.set_cuda_device(r,0); cp.data_free(r)'
```

Default architecture is 75; explicitly select your deployment architecture(s). CUDA language/Toolkit are detected only with ON. The probe allocates a single integer, runs a kernel writing 42, synchronizes/copies/checks/frees it and restores the prior device, with explicit error checking and RAII cleanup. This is setup verification, not part of an optical hot loop. No CUDA compiler, driver or device is available on the local development host. The existing .cu compilation/runtime has now been verified remotely with CUDA 13.0 and sm_89; see [remote-validation.md](remote-validation.md). ON without nvcc has been checked to fail clearly. That probe-only milestone made no optical acceleration claim; the later CUDA numerical stages are documented in their phase reports.

## CPU sanitizers

```bash
BUILD_DIR="$PWD/build/asan" scripts/build_cpu.sh -DCMAKE_BUILD_TYPE=Debug -DSOLARPILOT_ENABLE_SANITIZERS=ON
cmake --build build/asan --target copilot_native_smoke
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1 build/asan/copilot_native_smoke
COPILOT_LIB_DIR="$PWD/build/asan/lib" LD_PRELOAD="$(g++ -print-file-name=libasan.so)" ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=halt_on_error=1 .venv/bin/python benchmarks/smoke_test.py
```

Native test avoids Python/NumPy lifetime allocations in leak reports. LeakSanitizer needs permission to inspect process threads; this desktop sandbox required running the native check outside the sandbox. No system sysctl changes were made. Native ASan/UBSan/LSan and Python ASan/UBSan smoke pass after two localized legacy corrections: factorial_d computes in double rather than overflowing int at 13!, and optical tree nodes initialize their pointers/terminal flag. The full Release baselines remain equivalent; no tolerances were loosened.

`BUILD_DIR=... scripts/test_cpu.sh` runs build + native CTest + Python smoke + the full Python suite. GCC/Clang sanitizer builds are CPU-only. CPU and profile OFF/ON both work without CUDA installed.

## Phase 2A flat flux CPU validation

The production CPU path uses the fixed numerical helper with an internal legacy fallback for unavailable coefficient packing. The original body remains a private oracle. Diagnostic selection is compiled out by default and does not change the public Python/C API:

```bash
BUILD_DIR="$PWD/build/flux-profile" scripts/test_cpu.sh \
  -DSOLARPILOT_ENABLE_CORE_PROFILE=ON -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON \
  -DCMAKE_CXX_COMPILER_LAUNCHER=ccache -DCMAKE_C_COMPILER_LAUNCHER=ccache
COPILOT_LIB_DIR="$PWD/build/flux-profile/lib" .venv/bin/python benchmarks/flux_density_scaling.py \
  --mode legacy --output artifacts/flux-legacy.json
COPILOT_LIB_DIR="$PWD/build/flux-profile/lib" .venv/bin/python benchmarks/flux_density_scaling.py \
  --mode flat --output artifacts/flux-flat.json
COPILOT_LIB_DIR="$PWD/build/flux-profile/lib" .venv/bin/python benchmarks/flux_density_scaling.py \
  --mode verify --output artifacts/flux-verify.json
```

Omit the launcher flags on machines without ccache. No CUDA launcher is added. `ccache --zero-stats` and `ccache --show-stats` delimit the native development run. Timing commands must run serially, after all builds/tests finish on that host. Three measured repetitions follow one excluded warm simulation. `verify` executes both routes on the same prepared heliostats/surface, restores initial raw flux between routes, asserts each raw cell at atol=1e-10 + rtol=1e-9×abs(reference), and leaves the flat result for normal post-processing. Its timing includes both paths and comparison and must not be reported as flat performance.

Internal environment variables: `SOLARPILOT_FLUX_PATH=legacy|flat|verify` and optional `SOLARPILOT_FLUX_COMPARE_FILE`. Differential CSV columns are cells, max_abs, max_rel, abs_x, abs_y, rel_x, rel_y, bitwise, evaluated_pairs; coordinates are original grid[x][y], zero-based, with first (0,0) retained if all errors are zero. Profiling measures adapter packing/scattering too. Controls and counters require the diagnostic option and are intended for single-thread test runs. Missing comparison output makes the verification benchmark fail rather than accepting an uninstrumented build.

CTest includes `flux_density_numerics` (24 direct Toolbox + legacy Hermite versus pure-helper cases), alongside the existing native smoke. `test_flux_density.py` runs the internal comparison on a 20×30 map when diagnostics are enabled, otherwise reports an explicit skip. The remote nine-case evidence also checks exported map hashes, peaks, integrated incident power and absorbed receiver power between selected legacy/flat runs. The unchanged baselines remain the independent full-output regression reference.

## Phase 2B CUDA correctness

See [the hybrid backend contract](cuda-flux-density.md) for supported configurations, SoA/AoS payload, RAII and optional event timing. The generic CUDA numerical test is built only when CUDA is ON and skips explicitly if no device is visible. The existing probe remains available. `set_compute_backend('cuda')` now selects a real flux-density kernel; unsupported physical configurations return false/error instead of falling back.

`benchmarks/cuda_flux_correctness.py` writes machine-readable provenance, nine-case raw/dimensional errors, peak/integral/power comparisons, contribution versus reduction diagnostics, transfer sizes and capacity reuse, without GPU performance timings. Its same-state diagnostic requires `SOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON`. The default production CPU/CUDA builds do not expose the internal selector/block-size tests.

`tests/test_cuda_flux.py` validates explicit capability errors and a rectangular map. Event timing plumbing is a separate functional test gated by `COPILOT_GPU_TIMING_ALLOWED=1`; set it only after verifying an idle GPU. It is not a block-size/performance campaign. No GPU speedup should be derived from correctness runtimes or a single functional timing sample.


## Phase 2D-B image-plane validation

CUDA builds add `cuda_image_plane_numerics` (the shared 60 Phase 2D-A fixtures,
complete outputs, layout probe, H/block edges, capacity reuse and determinism).
CPU-only builds still compile without nvcc/CUDA headers or runtime dependencies.
`image_plane_numerics` retains Legacy/Flat bitwise verification.

```sh
COPILOT_LIB_DIR="$PWD/build/cuda/lib" .venv/bin/python \
  benchmarks/image_plane_cuda_correctness.py --output artifacts/phase2db/downstream.json
.venv/bin/python scripts/check_phase2da_boundaries.py --allow-image-plane-cuda
```

The explicit boundary-check flag authorizes the subsequent 2D-B kernel while
retaining all Phase 2D-A oracle and Phase 2C byte checks. The default check still
enforces the original 2D-A no-image-CUDA condition at its historical revision.
For optional preliminary timing, first finish every server build/test and verify
an idle GPU; `image_plane_cuda_baseline.py --timing` also checks before each child,
and its native executable guards the exact GPU process set around every sample.
It never starts/stops services, changes clocks or performs a block sweep.
See `phase2db-report.md` for resource/precision evidence and timing limitations.
