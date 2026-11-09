#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
: "${COPILOT_CONTAINER_IMAGE:?Set a locally available build image with the required CPU/CUDA toolchain}"
flags=()
if [[ ${1:-} == --gpu ]]; then shift; flags=(--gpus all); fi
exec docker run --rm --read-only --user "$(id -u):$(id -g)" \
 --tmpfs /tmp:rw,nosuid,size=2g "${flags[@]}" \
 --volume "$root:/workspace" --workdir /workspace \
 --env COPILOT_LIB_DIR="${COPILOT_CONTAINER_LIB_DIR:-/workspace/build/cpu/lib}" \
 --env OMP_NUM_THREADS=1 --env OPENBLAS_NUM_THREADS=1 --env MKL_NUM_THREADS=1 --env NUMEXPR_NUM_THREADS=1 \
 --env COPILOT_EXPECTED_LIBRARY_SHA256 \
 --entrypoint /bin/bash "$COPILOT_CONTAINER_IMAGE" -c 'exec "$@"' -- "$@"
