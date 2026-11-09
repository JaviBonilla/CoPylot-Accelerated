# CoPylot GPU: optical simulation and reproducibility

This local publication candidate preserves the software development of the retained SolarPILOT Hermite execution path, refactored CPU implementation, multicore CPU and CUDA implementation. It contains source patches, tests, public commercial-case reconstruction and reviewed computational evidence.

**The root license is pending an explicit decision.** See `THIRD_PARTY_NOTICES` and `docs/licensing-inventory.json`. Existing upstream terms and copyright headers remain applicable. No repository-wide license is implied.

## Build and test

Requirements: Git, Python 3.11 or newer, CMake 3.24 or newer, Ninja, a C/C++ toolchain and Linux for the affinity/counter diagnostics. The pinned dependency downloads require network access. CUDA builds also require a compatible CUDA toolkit and NVIDIA device.

```sh
python3 scripts/bootstrap.py
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
scripts/test_cpu.sh -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON -DSOLARPILOT_ENABLE_CORE_PROFILE=ON
```

Bootstrap reconstructs the three exact dependency revisions from pinned public upstream commits plus the committed mailboxes. It refuses to overwrite incompatible or dirty dependency checkouts. The upstream repositories are ignored working dependencies, not submodules or vendored source trees.

For CUDA, use a separate build and specify the target architecture explicitly, for example `BUILD_DIR="$PWD/build/cuda" scripts/test_cpu.sh -DSOLARPILOT_ENABLE_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89 -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON`. Architecture 89 corresponds to the measured Ada GPU; select the appropriate value for your hardware.

## Public commercial case

```sh
COPILOT_LIB_DIR="$PWD/build/cpu/lib" .venv/bin/python benchmarks/commercial_reference.py \
  --output artifacts/commercial-check.json
```

`cases/commercial-reference/case_manifest.json` records the upstream source, exact asset hashes and parameter classifications. Layout and weather assets are reconstructed from those dependencies; raw upstream input assets are not copied into this repository.

See `docs/public-reproducibility.md` for the complete commercial annual workflow and validation boundaries. Small functional tests are distinct from full annual benchmark campaigns.

## Reviewed evidence

```sh
.venv/bin/python -m benchmarks.analysis.validate
.venv/bin/python -m unittest discover -s tests -p 'test_public_evidence.py' -v
```

`benchmarks/results/public-evidence-manifest.json` binds the reviewed aggregate replacements to their authoritative source-report hashes. Values are retained without rounding or new benchmark measurements. Historical measured binary hashes remain historical identities; a local rebuild must declare its own identity. Private case inputs and state records are not distributed, so those results cannot be independently rerun from this public candidate.

`docs/public-export.md` describes history selection, privacy exclusions and remaining publication decisions. `docs/history-map.csv` maps retained private integration revision identifiers to the filtered public history. Author attribution and upstream patch histories are retained.
