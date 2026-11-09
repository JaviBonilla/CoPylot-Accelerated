#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

gpu_args=()
ctest_args=()
if [[ ${1:-} == --gpu ]]; then
  gpu_args=(--cuda)
  shift
else
  export CUDA_VISIBLE_DEVICES=-1
  ctest_args=(-E '^(cuda_|temporal_gpu_|image_plane_pipeline_state$)')
fi
if (($#)); then
  echo "Usage: $0 [--gpu]" >&2
  exit 2
fi

build=build/package-linux-cuda-portable
jobs=${BUILD_JOBS:-4}
toolkit=${CUDAToolkit_ROOT:-/opt/copilot-cuda}
if ((${#gpu_args[@]})) && [[ -n ${LD_LIBRARY_PATH:-} ]]; then
  export LD_LIBRARY_PATH="$toolkit/lib:$LD_LIBRARY_PATH"
else
  export LD_LIBRARY_PATH="$toolkit/lib"
fi
python3 scripts/bootstrap.py
cmake -S . -B "$build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON -DCOPILOT_LOCAL_PACKAGE=ON -DCOPILOT_PORTABLE_LINUX_CUDA=ON \
  -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON -DSOLARPILOT_ENABLE_CUDA=ON \
  -DCMAKE_CUDA_ARCHITECTURES=89 -DCUDAToolkit_ROOT="$toolkit" \
  -DCMAKE_CUDA_COMPILER="$toolkit/bin/nvcc" -DCMAKE_CUDA_HOST_COMPILER="$(command -v g++)"
cmake --build "$build" --parallel "$jobs"
ctest --test-dir "$build" --output-on-failure "${ctest_args[@]}"

# Exercise the packaged ELF under the filename used by the repository tests.
ln -sfn hermite_optics.so "$build/lib/solarpilot.so"
export COPILOT_LIB_DIR="$root/$build/lib"
python3 benchmarks/smoke_test.py
if ((${#gpu_args[@]})); then
  python3 -m unittest discover -s tests -v
else
  # These suites check optical maps and outputs without probing a CUDA driver.
  PYTHONPATH="$root/tests" python3 -m unittest -v test_flux_density test_regression
fi

export SOURCE_DATE_EPOCH="$(git show -s --format=%ct HEAD)"
cpack --config "$build/CPackConfig.cmake" -C Release
revision="$(git rev-parse --short=12 HEAD)"
if [[ -n $(git status --porcelain) ]]; then revision+=-dirty; fi
archive="$build/packages/hermite-optics-local-$revision-linux-x86_64-cuda13.0-sm89-glibc2.34.tar.gz"
python3 scripts/verify_package.py "$archive" --cuda-runtime-dir "$toolkit/lib" \
  --cuobjdump "$toolkit/bin/cuobjdump" "${gpu_args[@]}"
