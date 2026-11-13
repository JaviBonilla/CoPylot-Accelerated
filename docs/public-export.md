# Local public export

Source private integration commit: `564b3627583d6a9c154419959dae79ecdfe22eda`.

Only the current candidate's ancestry was exported. The other original branches
had no unique commits. Normal `main` is the sole intended public ref. Internal app
snapshots, backups, reflogs and unreachable source objects were not imported.
Author attribution, development timestamps, upstream headers and patch mailboxes
are preserved; these are software provenance, not private weather timestamps.

## History selection and exclusions

All manuscript paths were removed across history. Ambiguous private-study reports,
mixed later-phase result files, raw validation logs, initial environment/boundary
dumps and server convenience scripts were excluded by reviewed paths. The retained
early synthetic/public result-path allowlist is in `docs/result-history-allowlist.json`.
There was no blanket file-extension or blob-size filter. Manuscript-only and other
empty commits were pruned. Personal home paths/host identifiers were normalized,
and private input filename fixtures were replaced with generic examples.

Private inputs, calendars, coordinates, individual aims, private raw maps, workspace
bundles and app refs are absent from the intended export. Generic optional-project
code and ignore patterns do not distribute any input datasets. The public annual
entrypoint accepts the commercial case only.

## Reviewed aggregate replacements

Later results were reintroduced as explicit field projections after filtering.
The eight annual rows retain exact measured times, counts, rates, grids, output
sizes, validation flags and strategies. Original/CPU timing populations retain
sample values, statistics and qualification outcomes. Temporal group summaries
retain strategy counts, timing/throughput values and output validation. Receiver
convergence retains dimensions, cell sizes and aggregate relative-error metrics.
Private solar coordinates, weather states, input filenames, state configurations,
raw map data and process/environment dumps are excluded. Private operating-state
labels are replaced by opaque identifiers. No annual private state rows are copied.

`benchmarks/results/public-evidence-manifest.json` records source report hashes,
public hashes and the number of numerical leaves checked without rounding. The
export construction checked every projected value against the corresponding
source field (ordered subsequences where rows were selected). A private audit
outside this candidate retains the construction/verification details.

Measured library hashes and original source revision identifiers remain historical
provenance. Filtered root revisions have different hashes: see `history-map.csv`.
The dependency patch SHAs remain unchanged. A rebuilt binary or revised harness
must never inherit a historical timing result merely because tests pass.

## Scientific utilities

`benchmarks/analysis/` adapts the existing annual, Original, single-state CPU/CUDA,
CPU-temporal and GPU-temporal scientific audit logic. It checks sample statistics,
populations, rates, byte accounting, output coverage and case-matched ratios.
Document registries, editorial statuses, formatting and document generation were
removed. These utilities entered the candidate as reviewed new files.

## Remaining decisions and practical limits

The [README licensing section](../README.md#licensing) records the grants for
original code, data and documentation. The [third-party notices](../THIRD_PARTY_NOTICES)
record the upstream naming, source-availability and redistribution conditions for
future packages or raw input assets. This document records the original local export process, not the subsequent
GitHub release workflow. CPU tests, asset reconstruction and exact commercial
plan regeneration can be checked locally. The v0.1.0 release also passed a
manual synthetic-case device check on an RTX 6000 Ada; no complete annual
performance campaign is claimed for that package.
