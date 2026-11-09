#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

build=build/package-linux-portable
jobs=${BUILD_JOBS:-4}
python3 scripts/bootstrap.py
cmake -S . -B "$build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON -DCOPILOT_LOCAL_PACKAGE=ON -DCOPILOT_PORTABLE_LINUX_CPU=ON \
  -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON
cmake --build "$build" --parallel "$jobs"
ctest --test-dir "$build" --output-on-failure

# The repository tests use the upstream filename. Exercise the very same ELF.
ln -sfn hermite_optics.so "$build/lib/solarpilot.so"
export COPILOT_LIB_DIR="$root/$build/lib"
python3 benchmarks/smoke_test.py
python3 -m unittest discover -s tests -v

export SOURCE_DATE_EPOCH="$(git show -s --format=%ct HEAD)"
cpack --config "$build/CPackConfig.cmake" -C Release
revision="$(git rev-parse --short=12 HEAD)"
if [[ -n $(git status --porcelain) ]]; then revision+=-dirty; fi
archive="$build/packages/hermite-optics-local-$revision-linux-x86_64-cpu-glibc2.34.tar.gz"
python3 scripts/verify_package.py "$archive"
