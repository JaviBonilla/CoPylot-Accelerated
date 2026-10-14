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

Library: `build/cpu/lib/solarpilot.so`. Upstream CMake also copies it into workspace root. Benchmarks load the build-specific file and briefly set cwd because upstream `CoPylot()` loads relative to cwd. Set `COPILOT_LIB_DIR=/absolute/path/build/other/lib` to test another build without copying over the CPU reference.

Build-only compatibility fixes: SolTrace's treemesh.cpp explicitly includes `<limits>`; SSC's HELIO_INTERCEPT macro is `0` rather than invalid `false;`, preserving its disabled state. These are required before a clean Linux baseline can compile. SSC shared's unrelated MPFIT produces a GCC 13 `-Werror=alloc-size-larger-than` diagnostic; our dependency closure excludes it instead of modifying numerical code or disabling warnings globally.

The generator requires an enabled land bounds mode. Disabling scaled bounds without enabling fixed bounds leaves zero extents and can throw from radialStaggerPositions. The fixtures explicitly select fixed radii; no generator algorithm was changed. Smoke generates a bounded single-design-point field; benchmarks separately generate/filter fields and assign deterministic 1000/5000/10000-position layouts with filtering disabled. Timings label these distinct operations.

Baseline capture is deliberate: `tests/capture_baseline.py`. Do not regenerate baselines to make a regression pass. Baselines were captured before backend dispatch/profiling. The upstream summary rounds numbers, so strict comparison also checks full precision flux values and every per-heliostat column. Integrated flux is incident flux, before receiver absorptance; compare to absorbed power only with the absorptance factor.
