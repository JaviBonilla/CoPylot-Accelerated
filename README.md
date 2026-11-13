# CoPylot-Accelerated

CoPylot-Accelerated simulates heliostat-field optics in concentrating solar power
towers. Use it from Python to assign a field, calculate receiver flux, and inspect
receiver summaries and per-heliostat results.

SolarPILOT(TM) is the original optical simulation software, and CoPylot is its
Python API. CoPylot-Accelerated retains the original CPU calculation paths in a
patched build as a numerical reference and adds three accelerated implementations.
[Original SolarPILOT(TM) project](https://github.com/NatLabRockies/SolarPILOT)

**[Official project website](https://copylot-accelerated.github.io/)**

<p align="center">
  <a href="https://github.com/JaviBonilla/CoPylot-Accelerated/actions/workflows/build-validate-all.yml"><img alt="Build &amp; Validate · All status" src="https://github.com/JaviBonilla/CoPylot-Accelerated/actions/workflows/build-validate-all.yml/badge.svg?branch=main"></a>
  <a href="docs/packaging.md#platform-status"><img alt="Platforms: Linux, Windows and macOS" src="https://img.shields.io/badge/platforms-Linux%20%2F%20Windows%20%2F%20macOS-blue"></a>
  <a href="docs/backend.md"><img alt="Backends: CPU and CUDA" src="https://img.shields.io/badge/backends-CPU%20%2F%20CUDA-blue"></a>
  <a href="LICENSE"><img alt="Eligible original project code: MIT" src="https://img.shields.io/badge/project%20code-MIT-green"></a>
</p>

## Execution modes

All four modes use the same Hermite optical formulation.

| Mode | Execution |
| --- | --- |
| Original SolarPILOT/CoPylot | Retained original image-plane and receiver-flux paths on one CPU thread |
| Refactored CPU | Optimized image-plane and receiver-flux paths on one CPU thread |
| Multicore CPU | Refactored paths with parallel work within a state and optional independent contexts across states |
| CUDA GPU | GPU image-plane evaluation and receiver flux accumulation, with CPU preparation and result handling |

The API supports generated and assigned fields and compatible saved layouts.
See the [backend guide](docs/backend.md) for mode selection and CUDA's supported configurations.

## Quick start with a binary package

Choose the release archive for your OS, architecture and backend, then check
it against `SHA256SUMS.txt`. [GitHub Releases](https://github.com/JaviBonilla/CoPylot-Accelerated/releases)

Extract the archive and open `copylot-accelerated/`, which contains
`requirements.txt` and `example.py`. Python 3.12 is recommended.

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
`BUILD.json`. Use `--mode cuda --compare` with the CUDA package and a compatible
GPU. Native runtimes such as glibc, Visual C++ and CUDA come from the host.
[Package installation and usage](docs/packaging.md#install-and-run-an-extracted-archive)

## Build from source

On Linux, install the prerequisites and run these commands from the repository
root to build and exercise the CPU library.

```sh
python3.12 -m venv .venv
.venv/bin/python scripts/bootstrap.py
.venv/bin/python -m pip install -r requirements.txt
scripts/build_cpu.sh -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON
.venv/bin/python examples/optical_simulation.py --flux-csv artifacts/example/receiver-flux.csv
```

The diagnostics flag enables the retained Original path. See the [build guide](docs/build.md)
for toolchains and tests and the [packaging guide](docs/packaging.md) for native package builds.

## Platforms and compatibility

| Platform | Package backends | Runtime requirements |
| --- | --- | --- |
| Linux x86-64 | CPU and CUDA | glibc 2.34 or later and a compatible C++ runtime. The CUDA package also needs external CUDA Runtime 13.0.88. Device execution requires an SM 89 NVIDIA GPU and a compatible driver. |
| Windows x86-64 | CPU | x64 Visual C++ runtime |
| macOS Intel and Apple Silicon | CPU | macOS 15 or later and a matching Python architecture |

The hosted CUDA validation checks loading and CPU modes across Linux distributions.
The **v0.1.0 Linux CUDA package** was also tested manually on an NVIDIA RTX 6000 Ada
(SM 89) with Ubuntu 24.04.4, driver 580.159.03 and CUDA Runtime 13.0.88.
Its 25 × 25 receiver-flux map agreed with CPU (`rtol=1e-9`, `atol=1e-10`;
maximum absolute difference `1.07e-14 kW/m²`). All 29 receiver summary
values and 25 detail columns for 12 heliostats agreed bitwise. The test used
embedded SM 89 code with PTX JIT disabled. This was a functional synthetic-case
check, not a performance benchmark. [Platform and GPU validation evidence](docs/packaging.md#gpu-execution-of-the-reference-archive)

## Benchmarks and reproducibility

The repository includes numerical checks, benchmark protocols and measured results
for the public commercial case. The CESA-I results are available as approved
aggregate evidence. For the packaged synthetic check on Apple Silicon, Original
receiver maps use a per-cell tolerance against both optimized CPU modes.
Refactored and Multicore maps and all CPU summaries and heliostat details are
checked bitwise. [Package validation policy](docs/packaging.md#windows-and-macos-cpu-workflows)

- [Reproducibility guide](docs/public-reproducibility.md)
- [Benchmark evidence and timing boundaries](docs/benchmark-evidence.md)
- [Annual benchmark results](benchmarks/results/annual-benchmark-matrix.csv)

## Citation

For work that uses CoPylot-Accelerated, cite Javier Bonilla, the software name and
the exact release tag or Git commit used. Cite M. J. Wagner and T. Wendelin
(2018) for the underlying optical software. [SolarPILOT(TM) paper](https://doi.org/10.1016/j.solener.2018.06.063)

## Acknowledgements

We thank the original SolarPILOT(TM), CoPylot, SSC and SolTrace developers and
acknowledge Alliance for Sustainable Energy, LLC. The source pins and notices
record the upstream components and their attribution. [SSC upstream](https://github.com/NatLabRockies/ssc) · [SolTrace upstream](https://github.com/NLR-SolTrace/SolTrace) · [Pinned revisions](repos.lock.json)

## Licensing

- Eligible original project code is licensed under [MIT](LICENSE).
- Eligible original benchmark results and datasets are released under [CC0 1.0](benchmarks/results/LICENSE).
- Original documentation is licensed under [CC BY 4.0](docs/LICENSE). Credit Javier Bonilla and CoPylot-Accelerated, link to the license and indicate changes.

Upstream components, patches derived from upstream code and third-party inputs
retain their applicable terms and notices. The project includes upstream
attribution, source reconstruction details and the relevant redistribution terms.
[Third-party notices](THIRD_PARTY_NOTICES) · [Licensing inventory](docs/licensing-inventory.json) · [Package contents and third-party terms](docs/packaging.md#contents-and-redistribution-review)
