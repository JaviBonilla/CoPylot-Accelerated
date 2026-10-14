#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build=${BUILD_DIR:-"$root/build/cpu"}
"$root/scripts/build_cpu.sh" "$@"
cmake --build "$build" --target copilot_native_smoke flux_density_numerics -j "${BUILD_JOBS:-8}"
ctest --test-dir "$build" --output-on-failure
export COPILOT_LIB_DIR="$build/lib"
"${PYTHON_BIN:-$root/.venv/bin/python}" "$root/benchmarks/smoke_test.py"
"${PYTHON_BIN:-$root/.venv/bin/python}" -m unittest discover -s "$root/tests" -v
