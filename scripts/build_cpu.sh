#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
build=${BUILD_DIR:-"$root/build/cpu"}
cmake -S "$root" -B "$build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_COPILOT_API=ON "$@"
cmake --build "$build" --target solarpilot -j "${BUILD_JOBS:-8}"
