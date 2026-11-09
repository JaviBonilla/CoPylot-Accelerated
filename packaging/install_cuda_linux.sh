#!/usr/bin/env bash
# Components and checksums from NVIDIA's CUDA 13.0.1 redistrib manifest.
set -euo pipefail
if [[ $# -lt 1 || $# -gt 2 || ( $# -eq 2 && $2 != --runtime-only ) ]]; then
  echo "Usage: $0 DESTINATION [--runtime-only]" >&2
  exit 2
fi
destination=$1
mode=${2:-}
if [[ -e $destination || -L $destination ]]; then
  echo "Choose a new CUDA installation directory: $destination" >&2
  exit 2
fi
base=https://developer.download.nvidia.com/compute/cuda/redist
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
layout="$scratch/layout"
mkdir -p "$layout/licenses"

fetch() {
  local component=$1 version=$2 sha=$3 name archive
  name="$component-linux-x86_64-$version-archive"
  archive="$scratch/$name.tar.xz"
  curl --fail --silent --show-error --location --retry 3 \
    "$base/$component/linux-x86_64/$name.tar.xz" -o "$archive"
  printf '%s  %s\n' "$sha" "$archive" | sha256sum -c -
  tar -xOJf "$archive" "$name/LICENSE" >"$layout/licenses/$component.txt"
  if [[ $mode == --runtime-only ]]; then
    tar -xJf "$archive" --strip-components=1 -C "$layout" \
      "$name/lib/libcudart.so.13" "$name/lib/libcudart.so.$version"
  else
    tar -xJf "$archive" --strip-components=1 -C "$layout" --exclude="$name/LICENSE"
  fi
  rm -- "$archive"
}

fetch cuda_cudart 13.0.88 bc44226f069402ab327bcf9e754660621aa6bc61fb7fc6afe03b794dfaaab658
if [[ $mode != --runtime-only ]]; then
  fetch cuda_nvcc 13.0.88 48e35be3cfbf4b4fbc16828eaec8a7048ee789403049dc409f7b643d6259cf7a
  fetch cuda_crt 13.0.88 5a3279a049ffc1cdb951c44cb95206acfdde9e9ae5e87825fc18d7e4a6878bb0
  fetch libnvvm 13.0.88 17ef1665b63670887eeba7d908da5669fa8c66bb73b5b4c1367f49929c086353
  fetch cuda_cccl 13.0.85 ed845eae8c1767706b6ee91e40c608a03f6f633551a849b63f7346d32d73ee60
  fetch cuda_cuobjdump 13.0.85 bd624dcb2089842add8f293efab1d21aa076c98b36d8dcb64347fe08fb03315d
  # The standalone archives use lib, while the Linux nvcc profile uses lib64.
  ln -s lib "$layout/lib64"
fi
mkdir -p "$(dirname "$destination")"
mv -T -- "$layout" "$destination"
