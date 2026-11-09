# Build and run CoPylot-GPU

Run the commands from the repository root. The build links the headless SSC
SolarPILOT library and SolTrace coretrace, then uses the pinned CoPylot wrapper
from the reconstructed SolarPILOT checkout.

## Verified environments

| Build | Environment |
| --- | --- |
| CPU | x86-64 Linux, GCC/G++ 13.3, CMake 3.30.5, Ninja 1.11.1 and Python 3.12 |
| CUDA | Archived x86-64 Linux validation with GCC 13.3, CUDA 13.0 (nvcc 13.0.88), driver 580.159.03 and RTX 6000 Ada (compute capability 8.9). See the [CUDA validation record](phase2dc-report.md). |

Install Git, Bash, a C/C++ build toolchain (including GNU Make for dependency
configuration), CMake 3.24 or later, Ninja, and Python 3.12 with venv and pip. The
Python versions of NumPy, pandas and their dependencies are pinned in
[requirements.txt](../requirements.txt). CPU builds need neither a GPU nor a
CUDA toolkit. The formal affinity and timing harnesses also need Linux
`/proc`, `/sys` and `lscpu`.

Native Windows and Intel macOS verification recipes are in the
[packaging guide](packaging.md). Those platform builds remain unverified.

## Reconstruct the dependencies

```sh
python3 scripts/bootstrap.py
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Bootstrap requires access to the public URLs in [repos.lock.json](../repos.lock.json).
It checks out exact upstream commits, applies the versioned
[patch mailboxes](../patches/), and verifies the resulting SHAs. A rerun accepts
matching clean tracked checkouts. For other revisions or local edits, start
with a separate workspace. The three dependency directories are ignored by the
root repository.

## Linux CPU

For distribution across Linux versions, use the separate
[portable CPack recipe](packaging.md#portable-linux-x86-64-cpu). The commands
below build against the current development host.

```sh
scripts/build_cpu.sh -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON
scripts/test_cpu.sh -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON
```

The first command builds `build/cpu/lib/solarpilot.so`. The second also builds and
runs the native CTest suite, Python smoke test and Python regression suite. The
CPU default is the refactored Flat path. Enable diagnostics to select both
Legacy paths for Original or to compare Legacy with Flat. Core profiling is a
separate optional CMake switch, `SOLARPILOT_ENABLE_CORE_PROFILE`. Leave profiling
and timing instrumentation inactive during benchmark runs.

`BUILD_JOBS` sets build parallelism. `BUILD_DIR` selects a different build tree and
`PYTHON_BIN` can select another Python environment for the test script. Set
`COPILOT_LIB_DIR` to the selected build's `lib` directory when running Python.
The example and benchmark loader use `build/cpu/lib` by default.

## Linux CUDA

Use a compatible NVIDIA driver and device, the CUDA toolkit with `nvcc`, and a
host compiler supported by that toolkit. For the verified Ada configuration,
use a separate build tree and set the architecture explicitly.

```sh
BUILD_DIR="$PWD/build/cuda" scripts/build_cpu.sh \
  -DSOLARPILOT_ENABLE_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89 \
  -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON
```

Use the compute capability of your target for `CMAKE_CUDA_ARCHITECTURES`.
If CMake cannot find the intended toolkit compiler, set `CUDACXX` before the
first configure in a new build directory. For validation on an available device,
use `scripts/test_cpu.sh` with the same `BUILD_DIR` and flags. Schedule those
tests when the device is available for your run. The build checks and examples
here use the library in place. See the [packaging guide](packaging.md) for
local binary archives and redistribution requirements.

## Run the example

```sh
.venv/bin/python examples/optical_simulation.py
.venv/bin/python examples/optical_simulation.py --mode original --compare
.venv/bin/python examples/optical_simulation.py --mode multicore --threads 2 --compare
```

[The example](../examples/optical_simulation.py) creates a synthetic field and
uses the pinned public Daggett weather asset for the site configuration. It
assigns the field, selects the backend and simulates at a specified sun position.
It reads the map with `get_fluxmap`, the receiver summary with `summary_results`
and the heliostat rows with `detail_results`. `--flux-csv PATH` saves the
25 × 25 incident flux map in kW/m². Use a fresh output path for each export.

Original requires the diagnostics build above. Refactored and Multicore both
select the CPU backend, with one or multiple simulation threads respectively.
The CPU comparisons check bitwise agreement of the receiver map against a
fresh refactored run.

On a suitable CUDA build and device, the same example can compare the CUDA
map with the CPU map using `rtol=1e-9` and `atol=1e-10`.

```sh
COPILOT_LIB_DIR="$PWD/build/cuda/lib" \
  .venv/bin/python examples/optical_simulation.py --mode cuda --compare
```

These are functional examples. For workload matching, timing and validation of
complete output payloads, see the [benchmark workflow](public-reproducibility.md).
