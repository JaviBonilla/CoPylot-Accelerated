# Hermite Optics local validation bundle

This headless bundle exposes the CoPylot Python API and its Hermite optical
simulation library, based on the original SolarPILOT(TM) software and
SolTrace from Alliance for Sustainable Energy, LLC. It is a local build
and test artifact. Redistribution is
blocked pending naming, corresponding-source and relinking review. See
`THIRD_PARTY_NOTICES` and `licenses/` for the terms and upstream attribution.
`BUILD.json` records the source revision, pinned dependencies, compiler and
binary configuration. Credit Javier Bonilla and CoPylot-GPU when reusing
this documentation under the included CC BY 4.0 license.

## Run from the extracted directory

Use Python 3.12 on the matching OS and CPU architecture. Portable Linux
(`variant: cpu-glibc2.34` in `BUILD.json`) was also tested with distro Python
3.10 and 3.11. Install the Python requirements and run the example. It generates a small field and synthetic
weather in a temporary directory.

```sh
python -m pip install -r requirements.txt
python example.py --mode refactored
python example.py --mode multicore --compare
python example.py --mode original --compare
```

Original requires `diagnostics: true` in the build metadata. The example checks
receiver maps against a fresh single-thread refactored CPU run. Use
`python example.py --mode cuda --compare` only with a CUDA-enabled bundle and
an available compatible GPU.

For your own Python script, add the extracted `python/` directory to
`PYTHONPATH` and use `from hermite_optics import CoPylot`. This loader locates
the bundled library relative to the archive layout. Direct imports of the
upstream `copylot` module retain its original filename and working-directory
convention. SolTrace ray-tracing convenience methods need an additional
coretrace API library. The bundle is for headless optical simulation.

## Runtime prerequisites

- Linux uses the host glibc, libstdc++ and GCC runtime. Start with the OS
  generation used to build a native bundle. The portable Linux variant
  requires `GLIBC_2.34`, `GLIBCXX_3.4.29` and `CXXABI_1.3.13`. Install
  `libstdc++6` and `libgcc-s1` on Ubuntu or Debian, or `libstdc++` and
  `libgcc` on EL9, if absent. Ubuntu 22.04 and 24.04, Debian 12 and
  AlmaLinux 9 were verified with the same portable archive.
- Windows uses the x64 Visual C++ runtime and Windows system libraries.
- macOS uses system libraries. The Mach-O library keeps the `.so`
  suffix used by the pinned build's post-build copy step.
- CUDA builds use the host NVIDIA driver and the matching CUDA runtime
  shared library. For the portable Linux CUDA archive, provide external
  `libcudart.so.13` from NVIDIA CUDA Runtime 13.0.88, even when using CPU
  modes. Make it visible via the system linker configuration or
  `LD_LIBRARY_PATH`. GPU execution additionally requires an Ada SM 89
  device and a compatible NVIDIA driver. NVIDIA lists 580.82.07 or newer
  for CUDA 13.0 Update 1. This archive was verified in CPU modes, and GPU
  execution is unverified. On Windows set `CUDA_PATH` to the matching
  toolkit installation so the loader can find its `bin` directory. The compiled
  architecture and toolkit version are in `BUILD.json`.

Runtime libraries and Python wheels are installed separately. Each extracted
archive is self-contained with respect to its project scripts and generated
example inputs.
