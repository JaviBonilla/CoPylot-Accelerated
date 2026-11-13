# Build and verify CoPylot-Accelerated packages

The headless CMake target exposes the CoPylot Python API. With
`COPILOT_LOCAL_PACKAGE=ON`, CPack stages a relocatable loader, synthetic example,
build metadata and license notices. CI uses the internal `copylot-accelerated-local-`
archive prefix. GitHub Release downloads use the public `copylot-accelerated-`
prefix. Redistribution clearance is pending.

## Platform status

| Target | Build and validation |
| --- | --- |
| Linux x86-64 portable CPU | Built with AlmaLinux 9 and GCC 11.5. Tested the same archive on AlmaLinux 9, Debian 12, and Ubuntu 22.04 and 24.04. |
| Linux x86-64 native CPU | Host-specific build verified with GCC 13.3, CMake 3.30.5 and Python 3.12. |
| Linux x86-64 portable CUDA | Built on AlmaLinux 9 with CUDA 13.0 Update 1. Host loading and three CPU modes passed on four distributions. An earlier portable archive passed device tests on an RTX 6000 Ada (SM 89) under Ubuntu 24.04.4. |
| Windows x64 CPU | Native MSVC 2022 build and artifact validation passed on `windows-2022`. |
| Windows x64 CUDA | Manual recipe prepared, conditional on a CUDA 13.0 toolkit supporting the installed MSVC toolset. DLL exports, CUDA linkage and device execution remain unverified. |
| Intel macOS CPU | Native build and artifact validation passed on `macos-15-intel`. |
| Apple Silicon macOS CPU | Native build and artifact validation passed on `macos-15` with the architecture-specific numerical policy below. |
| macOS CUDA | Outside the packaging targets. |
| SolarPILOT desktop executable | Blocked on a separately pinned and tested GUI build. Upstream uses a distinct CMake entry point, wxWidgets, LK, WEX, RapidJSON and other platform dependencies and resources. The headless CUDA dispatch does not establish GUI CUDA support. |

## Package workflows

| Target | Build | Validate |
| --- | --- | --- |
| Linux CPU | [Build · Linux · CPU](../.github/workflows/build-linux-cpu.yml) | [Validate · Linux · CPU](../.github/workflows/validate-linux-cpu.yml) |
| Linux CUDA | [Build · Linux · CUDA](../.github/workflows/build-linux-cuda.yml) | [Validate · Linux · CUDA](../.github/workflows/validate-linux-cuda.yml) |
| Windows CPU | [Build · Windows · CPU](../.github/workflows/build-windows-cpu.yml) | [Validate · Windows · CPU](../.github/workflows/validate-windows-cpu.yml) |
| macOS CPU | [Build · macOS · CPU](../.github/workflows/build-macos-cpu.yml) | [Validate · macOS · CPU](../.github/workflows/validate-macos-cpu.yml) |

Dispatch a Build workflow and wait for it to succeed. Each job uploads
the CPack archive, its SHA-256 sidecar and `artifact.json`. Then dispatch the
matching Validate workflow. Leave `build_run_id` blank to use the latest
successful Build on `main` with all required artifacts still available. The
resolver orders candidates by the last job completion in each attempt. To
validate a particular Build on `main`, enter its numeric run ID.
The resolver checks the workflow, repository, revision and attempt and logs
the Build URL and artifact IDs. The validator downloads those artifacts by ID
and verifies the manifest, archive checksum, architecture, backend and licenses.
For a partial macOS rerun, rerun all jobs or dispatch a new Build so both
architecture artifacts come from the same attempt.

Validation runs scripts from the revision of the dispatched Validate workflow
and checks archive contents against a separate checkout of the Build revision.
Both revisions appear in the validation log. Existing packages with the
supported layout can be validated without recompilation. After successful
host validation, each platform job uploads `validation.json` with the
Build artifact ID, the archive checksum and the validation run identity.

Artifact names use
`copylot-accelerated-<backend>-<platform>-<run-id>-<attempt>`.
For Linux, `platform` is `linux-x86_64` for both backends.
Both Linux Build workflows use the pinned AlmaLinux 9 builder and retain
the glibc 2.34 ABI. Each Validate workflow checks the same archive in
Ubuntu 22.04, Debian 12, Ubuntu 24.04 and AlmaLinux 9. Docker prepares the
validation images using the host network and the Build revision's pinned Python
requirements. The tests then run with Docker networking disabled and the
archive mounted read-only. The normal CUDA validation uses an external CUDA
runtime to check loading and the CPU modes.

Enable `run_gpu` in **Validate · Linux · CUDA** to also run the packaged
CUDA example on a self-hosted Linux x64 runner labelled `cuda-13-0` and
`gpu`. The job requires an SM 89 NVIDIA device and compatible driver.
It checks GPU utilization, GPU processes and vLLM before running CUDA.
When it detects activity, it stops the GPU job before launching the example.
The hosted runtime job finishes independently of GPU availability.

These packages are validation artifacts subject to the redistribution
requirements below. Use access-controlled runs while redistribution
clearance is pending.

### Build and validate all platforms

In Actions, run [**Build & Validate · All**](../.github/workflows/build-validate-all.yml)
from `main`. It captures the dispatch commit, requests the four Build run IDs
directly from GitHub, and waits for their jobs and five packages. It then
dispatches each matching Validate workflow with its specific `build_run_id`.
Both macOS architecture jobs must pass. Linux CUDA runs the hosted load and
CPU checks, with device execution available separately through `run_gpu`.

Keep `main` at the selected commit until both waves have been dispatched. The
GitHub dispatch API uses a branch or tag, and the orchestrator checks each
child's full SHA. If `main` moved before or during dispatch and a child uses a
different commit, start a new global run at the intended revision. The summary
links to the child runs. Download `build-validate-manifest-<run-id>-<attempt>`
for machine-readable evidence. A failed run keeps the available diagnostics
and cannot be used for a release draft. If the parent is cancelled or times
out, independently dispatched children may still be running. Rerun the global
workflow to create a fresh set after a failure or child rerun.

### Prepare a release draft

In Actions, run [**Release · Publish**](../.github/workflows/release-publish.yml)
from `main` with a SemVer `version` such as `v0.1.0-rc1`. The `v` prefix is
added if omitted. An existing version tag, draft or release stops the workflow.
Set `build_validate_run_id` to use one exact successful global run. Leave it
blank to try successful dispatches from newest to oldest until one has all
its original attempts, artifacts and validation records available. Skipped
runs and their reasons appear in the job log. An explicit run ID has no fallback.

The workflow creates a draft titled **CoPylot-Accelerated vX.Y.Z**, with the tag
`vX.Y.Z` pointing to the source SHA of the selected global run. It contains
five [versioned archives](#release-assets),
`SHA256SUMS.txt` and release notes with compatibility, prerequisites and CI
provenance. The archives retain their original bytes and embedded metadata.
SemVer build metadata keeps its `+` in the tag and uses `_` in asset names.
Each package already includes its synthetic example, Python wrappers,
requirements, README and license notices.

The workflow checks all evidence and stages the files before creating the
draft. If an upload or tag operation fails, inspect the linked draft. The
workflow leaves it for review and refuses to overwrite the version on retry.
Use a new version or resolve the incomplete draft and any associated tag
manually before retrying. GitHub uses the repository's built-in Actions token.
Repository policies must allow workflow dispatches and draft creation. Tag
rules or GitHub's workflow-file permissions can restrict tagging historical
commits. Resolve those restrictions with a repository maintainer if GitHub
rejects the request. Public redistribution remains a separate decision.

## Portable Linux x86-64 CPU

Use the `cpu-glibc2.34` variant for cross-distribution testing. The
[builder Dockerfile](../packaging/linux-portable.Dockerfile) pins the official
AlmaLinux 9 amd64 base image and uses EL9's system GCC 11 and glibc 2.34.
It pins CMake 3.30.5 and the Ninja 1.11.1.4 wheel. DNF applies EL9 repository
updates, so the recipe targets a stable ABI across updates. It does not pin
the entire RPM transaction or guarantee identical binaries across updates.

From the repository root on an x86-64 Linux Docker host:

```sh
docker build --platform linux/amd64 -t copilot-linux-portable - < packaging/linux-portable.Dockerfile
docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
  --volume "$PWD:/workspace" --env HOME=/tmp copilot-linux-portable bash -ec '
    python3 -m venv /tmp/verify-python
    . /tmp/verify-python/bin/activate
    python3 -m pip install --only-binary=:all: -r requirements.txt
    scripts/package_linux_portable.sh
  '
```

The script reconstructs the pinned checkouts, enables Original diagnostics,
builds and tests the same shared library that CPack puts in
`build/package-linux-portable/packages/`. It uses GCC's `-march=x86-64
-mtune=generic` and keeps the standard project build separate. The final
archive is named
`copylot-accelerated-local-<revision>-linux-x86_64-cpu-glibc2.34.tar.gz`.
CPack writes a SHA-256 sidecar alongside it.

The verified binary requires up to `GLIBC_2.34`, `GLIBCXX_3.4.29` and
`CXXABI_1.3.13`. It uses host glibc (including libm and the loader),
libstdc++ and libgcc_s. On Ubuntu and Debian the latter two are
`libstdc++6` and `libgcc-s1`. On EL9 they are `libstdc++` and `libgcc`.
No native runtime is bundled. GNU binutils is only needed for the verifier.
The previous host build reached `GLIBC_2.38` through `__isoc23_sscanf`,
`__isoc23_strtol` and `fmod`, and `GLIBCXX_3.4.32` through GCC 13's
libstdc++ iostream initializer.

| Fresh image tested | glibc | Distro Python | Extracted Original, Refactored and Multicore |
| --- | --- | --- | --- |
| Ubuntu 22.04.5 | 2.35 | 3.10.12 | Passed, bitwise equal |
| Debian 12 | 2.36 | 3.11.2 | Passed, bitwise equal |
| Ubuntu 24.04.5 | 2.39 | 3.12.3 | Passed, bitwise equal |
| AlmaLinux 9.8 | 2.34 | 3.12.15 | Passed, bitwise equal |

These checks used the four official amd64 image filesystems and one host
kernel and CPU. RHEL and Rocky Linux 9 are ABI targets that were not tested
separately. The library targets baseline x86-64. The tested EL9 userspace has
its own x86-64-v2 requirement, and older physical CPUs were not tested.
Installed Python and its NumPy and pandas wheels have their own runtime
requirements. The synthetic map digest matched across the four environments
and matched the earlier GCC 13 archive when both ran on the same host.

For a local runtime check on a host without the source dependencies, first
install the Python requirements from the extracted archive in a virtual
environment. Then run the example for each mode or use the verifier with
`--runtime-only` and the original archive. Use the verifier only with a trusted
archive, since it loads and executes packaged code. The runtime check verifies
the allowed files, the ELF ABI and relocations, then runs the packaged example.
The example also prints a SHA-256 of the receiver map to compare across hosts.
The full verification in the build checks the exact pinned sources and notices.

```sh
.venv/bin/python /path/to/verify_package.py --runtime-only /path/to/package.tar.gz
```

lp_solve embeds optional loader entry points for external factorization,
language-interface and BLAS modules. The built-in routes need none of those
modules. They are outside the package verification. The Python requirements
are installed separately, and the optical example exercises their used
native extensions. The separate SolTrace ray-tracing API is outside the
bundle.

## Portable Linux x86-64 CUDA

The CUDA recipe reuses the AlmaLinux 9 CPU builder and adds the
[checksum-pinned NVIDIA toolkit components](../packaging/install_cuda_linux.sh).
It uses CUDA 13.0 Update 1 (`nvcc` and `libcudart` 13.0.88), GCC/G++ 11.5,
CMake 3.30.5 and the same generic x86-64 host target as the CPU package.
The native build takes a configurable CUDA architecture. The portable
archive contains SM 89 (Ada) cubins and PTX targeting compute capability
8.9, inspected with `cuobjdump`. Only this toolkit and target were built
for the portable CUDA package. Other toolkit versions and GPU targets are
unverified. See the [archived Ada execution record](build.md#verified-environments)
for the earlier native build.

From the repository root on an x86-64 Linux Docker host:

```sh
docker build --platform linux/amd64 -t copilot-linux-portable - < packaging/linux-portable.Dockerfile
docker build --platform linux/amd64 -t copilot-linux-cuda-portable \
  -f packaging/linux-cuda-portable.Dockerfile packaging
docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
  --volume "$PWD:/workspace" --env HOME=/tmp copilot-linux-cuda-portable bash -ec '
    python3 -m venv /tmp/verify-python
    . /tmp/verify-python/bin/activate
    python3 -m pip install --only-binary=:all: -r requirements.txt
    scripts/package_linux_cuda_portable.sh
  '
```

The script builds and checks the package without device access by default.
It checks the host optical paths, the ELF ABI and the device code embedded
in the library. CPack places the archive and SHA-256 sidecar under
`build/package-linux-cuda-portable/packages/`. The archive name ends in
`linux-x86_64-cuda13.0-sm89-glibc2.34.tar.gz`.

### Runtime and driver

The archive has one ELF, `lib/copylot_accelerated.so`. It requires
`GLIBC_2.34`, `GLIBCXX_3.4.29` and `CXXABI_1.3.13`, with the same
system libraries as the portable CPU archive and one additional ELF
dependency, `libcudart.so.13`. Install NVIDIA CUDA Runtime 13.0.88
externally for the tested configuration. The vendor library itself
imports glibc symbols up to `GLIBC_2.17`. It uses host libc, libdl,
libpthread, librt and the dynamic loader. The archive carries the usual
project and upstream notices and has no NVIDIA driver, CUDA runtime,
compiler binaries or Python wheels. Review the [CUDA Toolkit terms][cuda-eula]
for any future public distribution of embedded toolkit components or
proposed runtime bundling.

Use a driver matching [NVIDIA's toolkit guidance][cuda-driver] for device
execution. NVIDIA lists Linux driver **580.82.07 or newer** for CUDA 13.0
Update 1. The reference archive passed device tests on driver 580.159.03.
The driver supplies `libcuda.so.1` when CUDA initializes. A driver and GPU are unnecessary for CPU-mode execution from
the CUDA archive, but `libcudart.so.13` is needed even for loading it.

With Python requirements installed in the repository's `.venv`, provide the
runtime through the system linker configuration or an explicit directory.
The following commands use a fresh, external runtime directory under the
user's home. The installer checks NVIDIA's checksum and preserves the
vendor's license with the separately installed files.

```sh
runtime="$HOME/.local/cuda-runtime-13.0.88"
packaging/install_cuda_linux.sh "$runtime" --runtime-only
.venv/bin/python scripts/verify_package.py --runtime-only --cuda-runtime-dir "$runtime/lib" /path/to/package.tar.gz
```

Ubuntu 22.04.5 (glibc 2.35), Debian 12 (2.36), Ubuntu 24.04.5 (2.39) and
AlmaLinux 9.8 (2.34) all loaded the same archive with only the external
CUDA runtime and the documented host prerequisites. Original, Refactored
and Multicore agreed bitwise, and the receiver map matched the portable
CPU archive's synthetic result. These are host checks. The tests did not
use an NVIDIA GPU.

### GPU execution of the reference archive

The archive built at `7c7ce27` was tested on an NVIDIA RTX 6000 Ada
Generation (SM 89) under Ubuntu 24.04.4 with driver 580.159.03 and external
CUDA Runtime 13.0.88. Its SHA-256 is
`57c74d4b75d51a16446ab3070a7a56c69a6b5f7e953a80fe8fb15463a78fd640`.
The tests loaded the extracted library and ran with
`CUDA_DISABLE_PTX_JIT=1`, exercising the embedded SM 89 cubins.

Original, Refactored and Multicore were bitwise identical across all
625 flux cells, 29 receiver summary values and 25 detail columns for
each of 12 synthetic heliostats. CUDA matched the CPU summary and
details exactly. Its maximum flux difference was
`1.0658141036401503e-14 kW/m²`, within `rtol=1e-9` and `atol=1e-10`.

Seven native CUDA checks and 15 Python checks passed. One Python timing
instrumentation check was omitted. The canonical optical-state test checked
215 values per heliostat for 257 heliostats across three CUDA runs. Full
and resident CUDA paths materialized the same state bitwise. Switching
back to CPU reproduced the initial CPU state bitwise. This GPU result
applies to the recorded archive, driver, device and Ubuntu environment.
The four-distribution checks above cover loading and CPU modes.

On a machine with a compatible idle GPU and driver, append `--cuda` to the
verifier command to exercise CUDA and compare receiver flux against the
CPU using `rtol=1e-9` and `atol=1e-10`. Alternatively run the builder's
`scripts/package_linux_cuda_portable.sh --gpu` on a GPU-enabled host or
container to run the full native and Python suites as well. Select an
available device before invoking either GPU check.

[cuda-driver]: https://docs.nvidia.com/cuda/archive/13.0.1/cuda-toolkit-release-notes/index.html#cuda-driver
[cuda-eula]: https://docs.nvidia.com/cuda/archive/13.0.1/eula/index.html

## Windows and macOS CPU workflows

| Runner | Actions artifact name | Archive inside it |
| --- | --- | --- |
| `windows-2022` | `copylot-accelerated-cpu-windows-x86_64-<run-id>-<attempt>` | `copylot-accelerated-local-<sha12>-windows-x86_64-cpu.zip` |
| `macos-15-intel` | `copylot-accelerated-cpu-macos-x86_64-<run-id>-<attempt>` | `copylot-accelerated-local-<sha12>-macos-x86_64-cpu.tar.gz` |
| `macos-15` | `copylot-accelerated-cpu-macos-arm64-<run-id>-<attempt>` | `copylot-accelerated-local-<sha12>-macos-arm64-cpu.tar.gz` |

If native configuration, compilation or packaging fails, the build job
uploads `copylot-accelerated-diagnostics-<platform>-<run-id>-<attempt>`. For
NLopt configuration failures, the job log also includes the configure
output and the last probe diagnostics available from `config.log`. The
artifact excludes raw Autoconf logs and CMake caches.

On macOS, CMake first links a small C program with the SDK, architecture
and deployment target it passes to NLopt. If SDK discovery or linking
fails, the configure log includes the selected Xcode developer directory
and the relevant tool error.

The validation workflow uses the downloaded bytes. It checks the archive
checksum, run and attempt, source revision, host architecture, archive
contents and license inventory. It checks native imports and uses the
packaged Python loader to run the synthetic case in Original, Refactored and
Multicore modes. Validation reports missing DLLs and dyld or loader errors.
The jobs install Python requirements from the matching checkout.

The receiver map, receiver summaries and per-heliostat details agreed bitwise
in the tested Linux CPU, Linux CUDA (CPU modes), Windows CPU and macOS Intel
packages, and these comparisons require bitwise equality. macOS Apple Silicon
also requires bitwise equality for Refactored versus Multicore and for all CPU
receiver summaries and per-heliostat details.

On a native macOS arm64 host with a macOS arm64 package, the receiver map from
Original may differ from Refactored or Multicore because of floating-point
rounding consistent with fused multiply-add (FMA) contraction. FMA remains
enabled under the normal compiler settings. Each cell must satisfy
`abs(original - optimized) <= 1e-15 kW/m² + 1e-15 * abs(optimized)`, with the
optimized result as the reference. The relative term covers the observed maximum
relative difference with roughly a factor of 2.4, and the absolute term sets the
limit at zero. Both maps must have the expected shape and contain finite,
nonnegative values with a positive peak. Opposite signs on zero-valued pairs
fail validation. The CUDA-versus-CPU tolerance is unchanged.

In the 25 × 25 synthetic example from [macOS Build 43024746862](https://github.com/JaviBonilla/CoPylot-Accelerated/actions/runs/43024746862)
(`368599e`), each Original comparison differed at 88 of 625 cells (14.08%).
The largest differences were `1.4210854715202004e-14 kW/m²`,
`4.131375826319544e-16` relative, and 3 ULP. Refactored and Multicore maps,
all receiver summaries and all per-heliostat details agreed bitwise. These
measurements describe this example and build.

macOS validation reports all three CPU mode pairs. Each comparison reports
the count and percentage of changed flux cells, the maximum absolute and
relative differences and the maximum finite ULP distance. Relative differences
use the second mode as the reference. Sample indices are zero-based receiver
map indices. The log includes signed-zero and non-finite diagnostics, plus
differences in the receiver summary and heliostat details. `cpu_outputs_bitwise`
reports exact agreement. `validation_passed` reports whether the comparison
satisfies the indicated `flux_policy` and the other output checks.

The macOS workflow uses `packaging/example.py` from the validation checkout
and loads the selected Build's packaged wrapper and library. Run a new Build
with the `copylot-accelerated-local-` layout before validating or staging a new
release. Older artifacts keep the filenames, contents and checksums recorded
by their original build. To run the same checks
against an extracted CPU package on a matching macOS host, use the interpreter
from a Python 3.12 environment with the pinned requirements installed:

```sh
.venv/bin/python packaging/example.py --package-directory ./extracted-package --compare-cpu-modes
```

To validate a downloaded artifact manually on a matching host, provide a
checkout of the Build's full source revision. On Linux or macOS, use the
following commands. In Windows Developer PowerShell, create the environment
with `py -3.12 -m venv .venv` and use `.\.venv\Scripts\python.exe` for both
Python commands.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r ./build-source/requirements.txt
.venv/bin/python scripts/native_package.py validate --directory ./downloaded-artifact \
  --source-directory ./build-source \
  --platform PLATFORM --revision FULL_SHA --run-id BUILD_RUN_ID --run-attempt ATTEMPT
```

Use `windows-x86_64`, `macos-x86_64` or `macos-arm64` for `PLATFORM`.
Windows validation expects the x64 Visual C++ runtime and MSVC 2022
`dumpbin`. macOS validation expects Xcode's `otool`. macOS packages target
macOS 15.0 and retain the `.so` suffix used by the pinned SSC copy step.
They contain a native, single-architecture Mach-O dylib. Both macOS jobs
take the architecture from CMake after removing the pinned Intel-only
flags on the packaged targets. Signing, notarization and testing on earlier
macOS releases are outside these checks.

The Windows and macOS package workflows run native build and validation jobs
for each architecture in the platform table above.

## Native Linux and macOS

From a clean checkout use Git, Python 3.12, a native C/C++ toolchain, GNU Make
for the dependency configuration, and Ninja. Linux also needs binutils
(`readelf`), and macOS needs the Xcode command-line tools. Pin CMake to
3.30.5 to avoid CMake 4's compatibility changes for the older upstream builds.
On macOS append `-DCMAKE_OSX_DEPLOYMENT_TARGET=15.0` and use
`-DCMAKE_OSX_ARCHITECTURES=x86_64` on Intel or `-DCMAKE_OSX_ARCHITECTURES=arm64`
on Apple Silicon.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install cmake==3.30.5 -r requirements.txt
.venv/bin/python scripts/bootstrap.py

build=build/package-cpu
.venv/bin/cmake -S . -B "$build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=OFF -DCOPILOT_LOCAL_PACKAGE=ON \
  -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON
.venv/bin/cmake --build "$build" --target solarpilot --config Release --parallel 4
export SOURCE_DATE_EPOCH="$(git show -s --format=%ct HEAD)"
.venv/bin/cpack --config "$build/CPackConfig.cmake" -C Release
.venv/bin/python scripts/verify_package.py "$build"/packages/copylot-accelerated-local-*.tar.gz
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
& $cmake --build $build --target copilot_package_library --config Release --parallel 4
$env:SOURCE_DATE_EPOCH = git show -s --format=%ct HEAD
& $cpack --config "$build/CPackConfig.cmake" -C Release
$archives = @(Get-ChildItem "$build/packages/copylot-accelerated-local-*.zip")
if ($archives.Count -ne 1) { throw "Expected exactly one package in the build directory" }
& $python scripts/verify_package.py $archives[0].FullName
```

For Windows CUDA use a fresh `build/package-cuda`, CUDA 13.0 including
Visual Studio integration, and the same two CUDA options as Linux. Use the
CUDA installer to configure `CUDA_PATH`. Run the CPU package first to
establish the baseline. The same optional `--cuda` verification runs only
when explicitly requested.

## Install and run an extracted archive

Extract the archive and enter the directory containing `requirements.txt`
and `example.py`. Python 3.12 is recommended. The portable Linux CPU archive
was also verified with distro Python 3.10 and 3.11.

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
`--mode original --compare`. Original requires `diagnostics: true` in
`BUILD.json`. Use `--mode cuda --compare` with the CUDA archive and a
compatible GPU and driver.
The example creates synthetic weather and a 12-heliostat field and evaluates
one optical state. CPU comparisons apply the [package validation policy above](#windows-and-macos-cpu-workflows)
in packages built with the updated example. For other programs, add the
extracted `python/` directory to `PYTHONPATH` and use
`from copylot_accelerated import CoPylot`.

The virtual environment manages Python packages. Install native runtimes such
as glibc, Visual C++ and CUDA separately. The host-built Linux reference binary
requires glibc symbols up to
`GLIBC_2.38` and libstdc++ symbols up to `GLIBCXX_3.4.32`. For the older
runtime baseline use the portable variant described above. Windows expects a
compatible x64 Visual C++ runtime. macOS expects system libraries. CUDA
expects a compatible installed driver and the shared CUDA runtime from the
matching toolkit. On Linux make the runtime visible to the system linker.
On Windows the loader checks the `bin` directory under `CUDA_PATH`.
The archive contains no host runtimes or Python wheels.

## Contents and redistribution review

The archive contains `lib/copylot_accelerated.so` on Linux and macOS or
`lib/copylot_accelerated.dll` on Windows. It includes the loader
`python/copylot_accelerated.py`, the pinned upstream Python modules including
`python/copylot.py`, the example and Python requirements, the
readme, `BUILD.json`, and the project and upstream license materials.
It contains no compiled development objects, benchmark data, stored weather,
or field files. Build metadata identifies the source and dependency revisions,
compiler, toolchain, architecture, and options. A dirty checkout is labelled
in the archive name and metadata. Use separate build directories for each
variant and a clean checkout for reproducibility. CPack source archiving
is disabled to prevent copying the working directory into an archive.

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
configuration and satisfies applicable license terms. A modified desktop GUI or
a separately distributed SolTrace binary would require its own packaging and
license review.

## Release assets

The release contains these five archives and `SHA256SUMS.txt`. The `<version>`
in each filename includes the `v` prefix. Only the external asset names change.
The CPack filenames used in CI, the archive contents and `BUILD.json` still
identify the original validated builds. Use `SHA256SUMS.txt` for Release downloads
and the original CI artifacts when running the repository's package verifier.

| Target | Asset |
| --- | --- |
| Linux portable CPU | `copylot-accelerated-<version>-linux-x86_64-cpu.tar.gz` |
| Linux portable CUDA | `copylot-accelerated-<version>-linux-x86_64-cuda.tar.gz` |
| Windows CPU | `copylot-accelerated-<version>-windows-x86_64-cpu.zip` |
| Intel macOS CPU | `copylot-accelerated-<version>-macos-x86_64-cpu.tar.gz` |
| Apple Silicon macOS CPU | `copylot-accelerated-<version>-macos-arm64-cpu.tar.gz` |
