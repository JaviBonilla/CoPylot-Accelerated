# Build and verify local binary packages

The headless CMake target exposes the CoPylot Python API. With
`COPILOT_LOCAL_PACKAGE=ON`, CPack stages the library under the provisional
name **Hermite Optics**, with a relocatable loader, synthetic example, build
metadata and license notices. The ordinary source build keeps its existing
name and behavior. The packages are for local validation while redistribution
clearance is pending.

## Platform status

| Target | Build and validation |
| --- | --- |
| Linux x86-64 CPU | Built and tested with GCC 13.3, CMake 3.30.5 and Python 3.12. The extracted package loaded and passed all three CPU modes. |
| Linux x86-64 CUDA | Build and CPU-side archive workflow prepared for CUDA 13.0 and Ada SM 89. No package or CUDA smoke test was run. |
| Windows x64 CPU | Native MSVC 2022 workflow prepared. DLL exports, C runtime linkage and the extracted smoke test still need native verification. |
| Windows x64 CUDA | Manual recipe prepared, conditional on a CUDA 13.0 toolkit supporting the installed MSVC toolset. DLL exports, CUDA linkage and device execution remain unverified. |
| Intel macOS CPU | Native workflow prepared. The pinned dependencies use Intel flags, and the SSC copy step expects `.so`, so the opt-in package keeps that suffix for a Mach-O library. The build and loader remain unverified. |
| Apple silicon CPU | Blocked on a native port and verification of the pinned SSC and SolTrace architecture settings. |
| macOS CUDA | Outside the packaging targets. |
| SolarPILOT desktop executable | Blocked on a separately pinned and tested GUI build. Upstream uses a distinct CMake entry point, wxWidgets, LK, WEX, RapidJSON and other platform dependencies and resources. The headless CUDA dispatch does not establish GUI CUDA support. |

The manual [CPU workflow](../.github/workflows/package-check.yml) targets
Ubuntu 24.04, Windows Server 2022 and Intel macOS 15. The manual
[CUDA workflow](../.github/workflows/package-cuda-check.yml) requires an
isolated, disposable x86-64 Linux runner labelled `cuda-13-0` with a compatible
host compiler and the toolkit preinstalled. It builds and verifies the archive
using CPU modes. Use that runner only for trusted refs. The workflows have
no upload or release steps and have not been run.

## Linux and Intel macOS

From a clean checkout use Git, Python 3.12, a native C/C++ toolchain, GNU Make
for the dependency configuration, and Ninja. Linux also needs binutils
(`readelf`), and Intel macOS needs the Xcode command-line tools. Pin CMake to
3.30.5 to avoid CMake 4's compatibility changes for the older upstream builds.
On Intel macOS append `-DCMAKE_OSX_ARCHITECTURES=x86_64` to the configure command.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install cmake==3.30.5 -r requirements.txt
python scripts/bootstrap.py

build=build/package-cpu
cmake -S . -B "$build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=OFF -DCOPILOT_LOCAL_PACKAGE=ON \
  -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON
cmake --build "$build" --target solarpilot --config Release --parallel 4
export SOURCE_DATE_EPOCH="$(git show -s --format=%ct HEAD)"
cpack --config "$build/CPackConfig.cmake" -C Release
python scripts/verify_package.py "$build"/packages/hermite-optics-local-*.tar.gz
```

For Linux CUDA use a fresh `build/package-cuda` and append
`-DSOLARPILOT_ENABLE_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89`. The recipe
expects NVIDIA CUDA 13.0 and a toolkit-compatible host compiler. Set
`CUDACXX` before configuration if needed. The packaging option requires
one explicit compute capability. The example configuration targets Ada SM 89.
The package verifier uses CPU modes by default. To compare one state against
CUDA on an available device, append `--cuda` to the verification command.
The verifier checks CUDA flux against CPU using `rtol=1e-9` and
`atol=1e-10`.

## Windows x64

Use an x64 Developer PowerShell for Visual Studio 2022 with the desktop C++
workload and Windows SDK, Git and x64 Python 3.12. This shell makes
`dumpbin` available for dependency inspection.

```powershell
py -3.12 -m venv .venv
$python = ".\.venv\Scripts\python.exe"
& $python -m pip install cmake==3.30.5 -r requirements.txt
$cmake = ".\.venv\Scripts\cmake.exe"
$cpack = ".\.venv\Scripts\cpack.exe"
$env:GIT_CONFIG_COUNT = "1"
$env:GIT_CONFIG_KEY_0 = "core.autocrlf"
$env:GIT_CONFIG_VALUE_0 = "false"
& $python scripts/bootstrap.py

$build = "build/package-cpu"
& $cmake -S . -B $build -G "Visual Studio 17 2022" -A x64 `
  -DBUILD_TESTING=OFF -DCOPILOT_LOCAL_PACKAGE=ON `
  -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON
& $cmake --build $build --target solarpilot --config Release --parallel 4
$env:SOURCE_DATE_EPOCH = git show -s --format=%ct HEAD
& $cpack --config "$build/CPackConfig.cmake" -C Release
$archives = @(Get-ChildItem "$build/packages/hermite-optics-local-*.zip")
if ($archives.Count -ne 1) { throw "Expected exactly one package in the build directory" }
& $python scripts/verify_package.py $archives[0].FullName
```

For Windows CUDA use a fresh `build/package-cuda`, CUDA 13.0 including
Visual Studio integration, and the same two CUDA options as Linux. Use the
CUDA installer to configure `CUDA_PATH`. Run the CPU package first to
establish the baseline. The same optional `--cuda` verification runs only
when explicitly requested.

## Install and run an extracted archive

Extract the archive to a user directory. From the extracted top level run
`python -m pip install -r requirements.txt` in a Python 3.12 virtual
environment, then run `python example.py --mode refactored --compare`.
Use `--mode original` or `--mode multicore` to select the other CPU paths.
The example creates synthetic weather and a 12-heliostat field and evaluates
one optical state. The two comparison modes check the receiver map bitwise
against Refactored. For other programs, add the extracted `python/` directory
to `PYTHONPATH` and use `from hermite_optics import CoPylot`.

The Linux reference binary requires glibc symbols up to `GLIBC_2.38` and
libstdc++ symbols up to `GLIBCXX_3.4.32`. Start with an OS providing those
versions. Older distributions have not been verified. Windows expects a
compatible x64 Visual C++ runtime. macOS expects system libraries. CUDA
expects a compatible installed driver and the shared CUDA runtime from the
matching toolkit. On Linux make the runtime visible to the system linker.
On Windows the loader checks the `bin` directory under `CUDA_PATH`.
The archive contains no host runtimes or Python wheels.

## Contents and redistribution review

The archive allowlist consists of the library, the Python loader and the
pinned upstream Python modules, the example and Python requirements, the
readme, `BUILD.json`, and the project and upstream license materials.
It contains no compiled development objects, benchmark data, stored weather,
or field files. Build metadata identifies the source and dependency revisions,
compiler, toolchain, architecture, and options. A dirty checkout is labelled
in the archive name and metadata. Use separate build directories for each
variant and a clean checkout for reproducibility.

- The Alliance licenses require binary notices, a distinct non-confusing
  designation for a modified distribution, and attribution to the underlying
  SolarPILOT(TM) and SolTrace. The requirements apply to the embedded modified
  SolarPILOT core and the modified upstream Python interface. SolTrace
  coretrace is linked into the shared library from the pinned checkout. Keep
  its upstream attribution and apply the same naming review to any separately
  distributed modified SolTrace executable or library. For research-entity
  redistribution, make the entire corresponding source available under the
  applicable terms for as long as the redistribution is available.
  [SolarPILOT terms](../licenses/SolarPILOT-LICENSE.md) and
  [SolTrace terms](../licenses/SolTrace-LICENSE.md).
- SSC's BSD terms and applicable file-level notices travel with distributions
  that include its code. The binary also embeds lp_solve and NLopt
  statically. Review LGPL 2.1 section 6 and the individual NLopt and lp_solve
  notices. Where LGPL applies, establish the exact corresponding source,
  required notices and an eligible way for recipients to modify or relink
  the LGPL portions. A static build may need a suitable object/source kit
  or a different link design. Test that arrangement before distribution.
  Dependency pins and patch reconstruction are provenance for this work.
  [SSC terms](../licenses/SSC-LICENSE.txt),
  [lp_solve terms](../licenses/lp_solve-LICENSE.htm) and
  [NLopt terms](../licenses/NLopt-LICENSE.htm).
- The root MIT license covers eligible original project code. The archive
  includes the existing upstream license copies, third-party notices, and the
  CC BY 4.0 terms for the original documentation. Review applicable
  component-level notices against the exact source used for each build before
  any public distribution. Review any proposed runtime bundling separately
  against the exact vendor and toolkit terms. The default archives rely on
  separately installed runtimes.
  [Third-party notices](../THIRD_PARTY_NOTICES) and
  [NVIDIA CUDA Toolkit terms](https://docs.nvidia.com/cuda/eula/index.html).

Clear the public designation, source access and LGPL redistribution
requirements before publishing any binary. The source reconstruction script,
patches, toolchain and build instructions should be part of the corresponding
source plan. Verify that the published material can rebuild the exact release
configuration and satisfies applicable license terms. The neutral local name
is provisional. A modified desktop GUI or a separately distributed SolTrace
binary would require its own packaging and license review.

## Proposed release asset names

These names illustrate the layout after the designation and redistribution
requirements are resolved.

| Target | Proposed asset |
| --- | --- |
| Linux CPU | `hermite-optics-<version>-linux-x86_64-cpu.tar.gz` |
| Linux CUDA | `hermite-optics-<version>-linux-x86_64-cuda13.0-sm89.tar.gz` |
| Windows CPU | `hermite-optics-<version>-windows-x86_64-cpu.zip` |
| Windows CUDA | `hermite-optics-<version>-windows-x86_64-cuda13.0-sm89.zip` |
| Intel macOS CPU | `hermite-optics-<version>-macos-x86_64-cpu.tar.gz` |
