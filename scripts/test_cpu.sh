#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build=${BUILD_DIR:-"$root/build/cpu"}
"$root/scripts/build_cpu.sh" "$@"
cmake --build "$build" --target copilot_native_smoke flux_density_numerics image_plane_numerics flat_image_plane_numerics static_parallel temporal_image_partition temporal_sun_bridge -j "${BUILD_JOBS:-8}"
# Build the CUDA-only native test when the option is enabled in this build.
if grep -q '^SOLARPILOT_ENABLE_CUDA:BOOL=ON$' "$build/CMakeCache.txt"; then
  cmake --build "$build" --target cuda_flux_numerics cuda_image_plane_numerics -j "${BUILD_JOBS:-8}"
  if grep -q '^SOLARPILOT_ENABLE_FLUX_DIAGNOSTICS:BOOL=ON$' "$build/CMakeCache.txt"; then
    cmake --build "$build" --target image_plane_pipeline_state -j "${BUILD_JOBS:-8}"
  fi
fi
cmake --build "$build" -j "${BUILD_JOBS:-8}"
ctest --test-dir "$build" --output-on-failure
export COPILOT_LIB_DIR="$build/lib"
"${PYTHON_BIN:-$root/.venv/bin/python}" "$root/benchmarks/smoke_test.py"
"${PYTHON_BIN:-$root/.venv/bin/python}" -m unittest discover -s "$root/tests" -v
