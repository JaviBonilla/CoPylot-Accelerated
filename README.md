# CoPylot-GPU

CoPylot-GPU evaluates heliostat-field optical performance and receiver flux for
concentrating solar power research. It builds a headless SolarPILOT numerical
library from pinned upstream sources and patches, with CoPylot as its Python
interface. All four execution approaches retain the Hermite optical formulation.

| Approach | Execution |
| --- | --- |
| Original | Retained Legacy image-plane and flux-density paths, with one CPU thread |
| Refactored CPU | Flat numerical paths, with one CPU thread |
| Multicore CPU | Flat numerical paths, with parallel work within a state and optional independent contexts across states |
| GPU (CUDA) | CUDA image-plane and flux-density stages, with CPU preparation and result handling |

The API supports generated and assigned fields, compatible saved SolarPILOT
layouts, receiver flux maps, receiver summaries and per-heliostat results.
CUDA has an explicit [configuration envelope](docs/backend.md).

## Quick start

The verified CPU environment is x86-64 Linux with GCC 13.3 and Python 3.12.
Linux CUDA evidence covers an RTX 6000 Ada with CUDA 13.0. See the
[build guide](docs/build.md) for prerequisites, flags and platform limits.

From the repository root, reconstruct the pinned dependencies and build the CPU
library. The diagnostics flag enables the optional Original comparison.

```sh
python3 scripts/bootstrap.py
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
scripts/build_cpu.sh -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON
.venv/bin/python examples/optical_simulation.py --flux-csv artifacts/example/receiver-flux.csv
```

The example assigns a synthetic 1,000-heliostat field, runs a single optical
state, prints the receiver summary and writes the incident flux map. See
[mode selection and comparison](docs/build.md#run-the-example) for the other
execution approaches.

## Binary packaging

The [packaging guide](docs/packaging.md) covers the verified Linux CPU
validation bundle, other platform recipes and the upstream redistribution
requirements.

## Benchmarks and reproducibility

- [Reproducibility workflow](docs/public-reproducibility.md) covers numerical checks, the public commercial case, short and temporal measurements, and optional annual campaigns.
- [Benchmark evidence](docs/benchmark-evidence.md) indexes the archived datasets, validation criteria and timing boundaries.
- [Annual measurements](benchmarks/results/annual-benchmark-matrix.csv) contain all four approaches for both study cases. CESA-I is available as approved aggregate evidence.

## Publication

Associated scientific publication and DOI to be added when available.

## Licensing

- [MIT](LICENSE) covers eligible original project code, including the build and benchmark tooling.
- [CC0 1.0](benchmarks/results/LICENSE) covers eligible original benchmark results and datasets, including the generated receiver maps and the synthetic baselines in `tests/baselines/`.
- [CC BY 4.0](docs/LICENSE) covers original project documentation, including this README. When sharing, credit Javier Bonilla and CoPylot-GPU, link to the license, and indicate any changes.

The root MIT grant is limited to original project code. Existing notices and terms continue to govern upstream-derived patches, separately marked files, and reconstructed dependencies. Copied external inputs and excerpts retain their source terms, including where they appear in results or case metadata. Public availability alone does not establish redistribution rights.

See [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES) and the [licensing inventory](docs/licensing-inventory.json) for the file-level exceptions, data provenance, and upstream terms.

## Acknowledgements

This work builds on SolarPILOT, its CoPylot API, SSC and SolTrace. Upstream
revisions and credits are recorded in [repos.lock.json](repos.lock.json) and
[THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).
