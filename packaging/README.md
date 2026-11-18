# CoPylot-Accelerated

This headless bundle exposes the CoPylot Python API for Hermite optical
simulations. It builds on the original SolarPILOT(TM) software, SSC and SolTrace.
See the [original SolarPILOT(TM) project](https://github.com/NatLabRockies/SolarPILOT)
and the Alliance for Sustainable Energy, LLC and contributor notices in
`THIRD_PARTY_NOTICES` and `licenses/`.

`BUILD.json` uses schema version `1` and identifies the package as
`copylot-accelerated`. It records the full source revision, pinned dependencies,
toolchain and binary configuration. The Git tag, GitHub Release and versioned
download filenames listed in `SHA256SUMS.txt` identify the release version.
Use `SHA256SUMS.txt` to verify a release download. Credit Javier Bonilla and
CoPylot-Accelerated when reusing this documentation under CC BY 4.0.

## Run from the extracted directory

Open the extracted `copylot-accelerated/` directory containing `requirements.txt`
and `quickstart.py`. Use Python 3.12 on the matching OS and CPU architecture.

**Linux and macOS**

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python quickstart.py
```

**Windows PowerShell**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe quickstart.py
```

Quick Start runs one optical calculation for 12 synthetic heliostats on one CPU
thread. The weather CSV is required for layout preparation. The optical
calculation uses the explicitly set sun position and irradiance (DNI). It
prints field optical efficiency, absorbed receiver power (kW), peak incident
flux (kW/m²) and the 25 × 25 flux grid. See [QUICKSTART.md](QUICKSTART.md).

## Run the Commercial Demo

The advanced example uses the bundled 8,790-heliostat reference case and
generates an offline HTML report. Use the same Python environment.

```sh
.venv/bin/python -m pip install -r commercial_demo/requirements.txt
.venv/bin/python commercial_demo/commercial_demo.py --no-open
```

On Windows, use the same `.\.venv\Scripts\python.exe` as above. See
[the Commercial Demo guide](commercial_demo/README.md) for backend selection,
inputs and outputs. Once the Python requirements have been installed, both
examples run without internet access or a source checkout.

`example.py` is the packaged validation script. Use
`python example.py --compare-cpu-modes` to compare CPU modes or
`python example.py --mode cuda --compare` on a CUDA build with a compatible GPU.

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
