#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

operation=$1
backend=$2
shift 2

case "$backend" in
  cpu|cuda) ;;
  *) echo "Expected cpu or cuda backend" >&2; exit 2 ;;
esac

case "$operation" in
  build)
    image=copilot-linux-portable
    docker build --platform linux/amd64 -t "$image" - < packaging/linux-portable.Dockerfile
    if [[ $backend == cuda ]]; then
      image=copilot-linux-cuda-portable
      docker build --platform linux/amd64 -t "$image" \
        -f packaging/linux-cuda-portable.Dockerfile packaging
    fi
    docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
      --volume "$root:/workspace" --env PIP_NO_CACHE_DIR=1 "$image" bash -ec '
        python3 -m venv /tmp/verify-python
        . /tmp/verify-python/bin/activate
        python3 -m pip install --only-binary=:all: -r requirements.txt
        python3 scripts/native_package.py build --platform linux-x86_64 "$@"
      ' -- --backend "$backend" "$@"
    ;;
  validate|validate-gpu)
    artifact=$(cd "$1" && pwd)
    shift
    source_dir=${PACKAGE_SOURCE_DIRECTORY:-.}
    runtime_args=(--source-directory "$source_dir")
    mounts=()
    temp=$(mktemp -d)
    trap 'rm -rf -- "$temp"' EXIT
    if [[ $backend == cuda ]]; then
      packaging/install_cuda_linux.sh "$temp/runtime" --runtime-only
      if [[ $operation == validate-gpu ]]; then
        runtime_args+=(--cuda --cuda-runtime-dir "$temp/runtime/lib")
      else
        runtime_args+=(--cuda-runtime-dir /cuda-runtime/lib)
        mounts=(--volume "$temp/runtime:/cuda-runtime:ro")
      fi
    fi

    if [[ $operation == validate-gpu ]]; then
      [[ $backend == cuda ]] || exit 2
      gpus=$(nvidia-smi --query-gpu=uuid,compute_cap,utilization.gpu --format=csv,noheader,nounits)
      apps=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits)
      processes=$(nvidia-smi pmon -c 1)
      if [[ -n "${apps//[[:space:]]/}" ]] ||
         awk -F ', *' '$3 != "0" {busy=1} END{exit !busy}' <<<"$gpus" ||
         awk '$1 ~ /^[0-9]+$/ && $2 != "-" {busy=1} END{exit !busy}' <<<"$processes" ||
         pgrep -fi 'v[l]lm|V[L]LM' >/dev/null; then
        echo "GPU activity or vLLM detected. Skipping CUDA execution." >&2
        exit 1
      fi
      device=$(awk -F ', *' '$2 == "8.9" && !uuid {uuid=$1} END{print uuid}' <<<"$gpus")
      if [[ -z $device ]]; then
        echo "No compatible SM 89 GPU found." >&2
        exit 1
      fi
      nvidia-smi -i "$device" --query-gpu=name,compute_cap,driver_version --format=csv
      unset CUDA_FORCE_PTX_JIT CUDA_FORCE_JIT
      CUDA_VISIBLE_DEVICES="$device" CUDA_DISABLE_PTX_JIT=1 python3 scripts/native_package.py validate \
        --platform linux-x86_64 --backend cuda --directory "$artifact" "${runtime_args[@]}" "$@"
      exit
    fi

    images=(
      ubuntu:22.04@sha256:8a2321a92b438238f93b4346fff61bc4259c99fdd4d9b52ee86f153fee0c344f
      debian:12-slim@sha256:c67e92c8099ba22853ab4cfda7cfb494d253d6012ca82dee98ba8976772af018
      ubuntu:24.04@sha256:78d4744ead1f5b19b04d0df558ab182a5300903900755e515b2ca4d10eb2044d
      almalinux:9@sha256:465a5007813f19b5ac8a88cd161f3d8dcc6b1958e0c03c31f7c9a1b079d0a7da
    )
    mkdir "$temp/context"
    cp "$source_dir/requirements.txt" "$temp/context/requirements.txt"
    for image in "${images[@]}"; do
      echo "Provisioning validation image from $image"
      # Only dependency provisioning uses host DNS. The build context contains
      # requirements.txt, and the selected binary is mounted only for offline tests.
      docker build --platform linux/amd64 --network=host --iidfile "$temp/image-id" \
        --build-arg "BASE_IMAGE=$image" -f packaging/linux-validation.Dockerfile "$temp/context"
      validation_image=$(cat "$temp/image-id")
      rm "$temp/image-id"
      docker run --rm --pull=never --platform linux/amd64 --network=none \
        --user "$(id -u):$(id -g)" \
        --volume "$root:/workspace:ro" --workdir /workspace \
        --volume "$artifact:/packages:ro" "${mounts[@]}" "$validation_image" bash -ec '
          cat /etc/os-release
          /opt/package-validation/bin/python scripts/native_package.py validate \
            --platform linux-x86_64 --directory /packages "$@"
        ' -- --backend "$backend" "${runtime_args[@]}" "$@"
    done
    ;;
  *)
    echo "Expected build, validate or validate-gpu" >&2
    exit 2
    ;;
esac
