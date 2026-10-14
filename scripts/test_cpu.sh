#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build=${BUILD_DIR:-"$root/build/cpu"}
"$root/scripts/build_cpu.sh" "$@"
cmake --build "$build" --target copilot_native_smoke flux_density_numerics -j "${BUILD_JOBS:-8}"
# Build the CUDA-only native test when the option is enabled in this build.
if grep -q '^SOLARPILOT_ENABLE_CUDA:BOOL=ON$' "$build/CMakeCache.txt"; then
  cmake --build "$build" --target cuda_flux_numerics -j "${BUILD_JOBS:-8}"
fi
ctest --test-dir "$build" --output-on-failure
export COPILOT_LIB_DIR="$build/lib"
"${PYTHON_BIN:-$root/.venv/bin/python}" "$root/benchmarks/smoke_test.py"
"${PYTHON_BIN:-$root/.venv/bin/python}" -m unittest discover -s "$root/tests" -v
