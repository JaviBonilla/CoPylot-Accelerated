#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BUILD_DIR="$root/build/profile" "$root/scripts/build_cpu.sh" -DSOLARPILOT_ENABLE_CORE_PROFILE=ON
mkdir -p "$root/artifacts/profile"
for size in small medium large; do
  csv="$root/artifacts/profile/$size.csv"
  : > "$csv"
  COPILOT_LIB_DIR="$root/build/profile/lib" SOLARPILOT_PROFILE_FILE="$csv" \
    "$root/.venv/bin/python" "$root/benchmarks/run_cpu.py" --case "$size" --repeats "${REPEATS:-5}" \
    --output "$root/artifacts/profile/$size-timings.json"
done
