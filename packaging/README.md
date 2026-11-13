# CoPylot-Accelerated

This headless bundle exposes the CoPylot Python API for Hermite optical
simulations. It builds on the original SolarPILOT(TM) software, SSC and SolTrace.
See the [original SolarPILOT(TM) project](https://github.com/NatLabRockies/SolarPILOT)
and the Alliance for Sustainable Energy, LLC and contributor notices in
`THIRD_PARTY_NOTICES` and `licenses/`.

`BUILD.json` records the source revision, pinned dependencies, compiler and
binary configuration. A GitHub Release may use a shorter download filename
for this archive. Use the release's `SHA256SUMS.txt` to verify a Release download.
The archive records its local-validation status. Redistribution is blocked
pending designation, corresponding-source and relinking review. Credit Javier
Bonilla and CoPylot-Accelerated when reusing this documentation under
CC BY 4.0.

## Run from the extracted directory

Open the directory containing `requirements.txt` and `example.py`. Python 3.12
is recommended on the matching OS and CPU architecture. The portable Linux CPU
archive was also tested with distro Python 3.10 and 3.11. The example generates
a small field and synthetic weather in a temporary directory.

**Linux and macOS**

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python example.py --mode refactored
```

**Windows PowerShell**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe example.py --mode refactored
```

Use the same interpreter with `--mode multicore --compare` or
`--mode original --compare` to compare with a fresh single-thread Refactored
run. Original requires `diagnostics: true` in `BUILD.json`. Use
`--mode cuda --compare` with a CUDA-enabled bundle and a compatible GPU.

For your own Python script, add the extracted `python/` directory to
`PYTHONPATH` and use `from copylot_accelerated import CoPylot`. This loader locates
the bundled library relative to the archive layout. Direct imports of the
upstream `copylot` module retain its original filename and working-directory
convention. SolTrace ray-tracing convenience methods need an additional
coretrace API library. The bundle is for headless optical simulation.

## Runtime prerequisites

The virtual environment manages Python packages. Native runtimes such as
glibc, Visual C++ and CUDA are provided by the host.

- Linux uses the host glibc, libstdc++ and GCC runtime. Start with the OS
  generation used to build a native bundle. The portable Linux variant
  requires `GLIBC_2.34`, `GLIBCXX_3.4.29` and `CXXABI_1.3.13`. Install
  `libstdc++6` and `libgcc-s1` on Ubuntu or Debian, or `libstdc++` and
  `libgcc` on EL9, if absent. Ubuntu 22.04 and 24.04, Debian 12 and
  AlmaLinux 9 were verified with the same portable archive.
- Windows uses the x64 Visual C++ runtime and Windows system libraries.
- The macOS CI packages target macOS 15 or later. Use a Python interpreter
  matching the Intel or Apple Silicon archive. The library uses system
  runtimes and keeps the `.so` suffix used by the pinned build's copy step.
- CUDA builds use the host NVIDIA driver and the matching CUDA runtime
  shared library. For the portable Linux CUDA archive, provide external
  `libcudart.so.13` from NVIDIA CUDA Runtime 13.0.88, even when using CPU
  modes. Make it visible via the system linker configuration or
  `LD_LIBRARY_PATH`. GPU execution additionally requires an Ada SM 89
  device and a compatible NVIDIA driver. NVIDIA lists 580.82.07 or newer
  for CUDA 13.0 Update 1. Standard hosted Linux CUDA validation checks loading
  and CPU modes. Device execution was verified separately for an earlier
  portable archive on an RTX 6000 Ada. Check the validation record for your
  archive. On Windows set `CUDA_PATH` to the matching toolkit installation so
  the loader can find its `bin` directory. The compiled architecture and toolkit
  version are in `BUILD.json`.

Runtime libraries and Python wheels are installed separately. Each extracted
archive is self-contained with respect to its project scripts and generated
example inputs.
