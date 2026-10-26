#!/usr/bin/env python3
"""Render the compact report only from the validated aggregate annual dataset."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 folder=ROOT/'benchmarks/results';s=json.loads((folder/'annual-benchmark-matrix.json').read_text());v=json.loads((folder/'annual-benchmark-validation.json').read_text())
 assert s['passed'] and v['passed'] and len(s['rows'])==8
 rows=s['rows'];lines=['# Complete annual optical benchmark matrix','',
 'All eight rows are measured complete annual workloads. Six missing campaigns were directly executed and two accepted commercial campaigns were reused. No annual time is extrapolated. No numerical implementation or manuscript is changed.','',
 '## Workload and execution','',
 'CESA-I uses the authoritative existing private EPW hourly DNI sequence, restored canonical project, Keep existing aims and CONTROL 217 × 256. Each hour-ending EPW row is evaluated at its midpoint in local standard time, using the existing API non-leap 2011 Hour/Day SOLPOS. This is a new annual weather-driven workload; the previous four-day constant-DNI seasonal sweep remains a separate experiment. Private site/calendar/weather/aims/maps and per-state data stay on the server.','',
 'Commercial reuses the exact accepted Daggett TMY2 plan and CONTROL 222 × 87: 8760 requests, 4403 evaluated daylight states, 4357 nighttime omissions. Both cases retain all elevation >0 states, including daylight DNI zero. There is no temporal interpolation.','',
 'Original means the retained original/legacy Hermite path with documented safety/restoration fixes, not an untouched historical upstream binary. Original and Refactored1T use one spawned process × one thread, pinned to CPU0. Original selects both Legacy paths; Refactored selects Flat.','',
 'CESA selected CPU is 12 independent spawned states × 2 threads, one physical SMT pair per worker, bounded dynamic_lpt dispatch. Selected GPU is 24 independent rolling contexts, one pinned CPU submission thread per context, bounded FIFO, ordinary eager CUDA calls on the existing default stream, static residency off. These selections reuse the best applicable previous CESA seasonal evaluation-throughput strategies; no universal annual optimum is claimed.','',
 'Accepted commercial CPU is Y2-commercial-24x1: 24 independent states × 1 thread, disjoint logical CPUs, dynamic_lpt. Accepted final commercial GPU is F-commercial-K24: 24 rolling contexts, bounded FIFO, static residency off. Their original measured provenance is retained.','',
 'CPU uses the preserved accepted Phase4S library SHA256 545775e26ca3588c9a65c56c93e6f3f93d480446e4a04272497fad27acb5e017 (SSC 0fd069b30343a08787f76247c4b1bb637e83bbe0). GPU uses final Phase5B d71dd38579fe9ea9038474371e233b2d7abc931f4770ea209e5b49275cdf98d8 (SSC 1233c8eb99f2650071b4386e918844d67709178b). The hardware and pinned compiler image are recorded in JSON.','',
 '## Measured results','',
 'States/s below uses the evaluation boundary; total-wall states/s is reported separately. NPZ bytes are the complete standard map/detail/numeric-summary payloads, consistent with earlier benchmarks. Flushed per-state JSONL bytes and their sum with NPZ bytes are also included in the machine-readable files.','',
 '| Case | Mode | Strategy | Requests | Daylight | Night omitted | Total s | Total min | Evaluation states/s | Total states/s | NPZ bytes |',
 '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
 for r in rows:
  strategy=f"{r['concurrent_states_or_contexts']} contexts" if r['execution_mode']=='gpu' else f"{r['concurrent_states_or_contexts']} × {r['cpu_threads_per_state']}"
  lines.append(f"| {r['case']} | {r['execution_mode']} | {strategy} | {r['requested_annual_hours']} | {r['evaluated_daylight_states']} | {r['omitted_nighttime_states']} | {r['total_wall_s']:.6f} | {r['total_wall_min']:.6f} | {r['evaluation_states_per_s']:.6f} | {r['total_wall_states_per_s']:.6f} | {r['standard_output_npz_bytes']} |")
 lines+=['','## Ratios','', 'All main ratios use unrounded measured total scheduler wall times. Ratios based on evaluation wall times are separately retained in JSON. Cases are never mixed.','', '| Ratio | CESA-I | Commercial |','|---|---:|---:|']
 for key in s['speedups_by_case']['cesa']['total_wall']:
  lines.append(f"| {key} | {s['speedups_by_case']['cesa']['total_wall'][key]:.6f}× | {s['speedups_by_case']['commercial']['total_wall'][key]:.6f}× |")
 lines+=['','## Timing and validation','',s['timing_boundary']+'. First calls are included, with no removed warmups. File writes are not a claim of fsync durability. Per-worker output costs overlap and are not subtracted from wall time. CPU admission and measurement windows preserve the existing policy, affinity and thermal checks. Campaigns run sequentially.','',
 'Every expected annual state produces a complete persisted standard payload. All archives are checked against runtime signatures, complete schema, finite numeric arrays, exact state coverage/metadata, resolved sun, zero-DNI outputs and byte totals. Original and Refactored1T are checked bitwise against full annual CPU references for every state. GPU uses the unchanged CPU comparison tolerances rtol=1e-9, atol=1e-10. Fresh representative probes additionally compare all 215 optical values per heliostat between Flat and Legacy. Verification is outside benchmark timing.','',
 'The accepted commercial CPU/GPU validation is reused with its exact original scope; those annual performances were not rerun. CPU/GPU source code and compiled binaries were unchanged. Timing sessions differ between retained and new runs, so the table is not described as a simultaneous paired measurement. One complete new campaign per missing row is provided; no new annual repeatability population is implied.','',
 'Tooling tests cover full non-leap calendar coverage, midpoint handling, missing/duplicate weather rejection, zero-DNI daylight retention, unrounded ratio computation, privacy whitelisting and publication rejection of incomplete campaigns. Existing temporal and CPU hardening tests also pass.','',
 'Failed or incomplete new campaign IDs: '+(', '.join(s['failed_or_incomplete_campaign_ids']) if s['failed_or_incomplete_campaign_ids'] else 'none')+'.','',
 'Results: `benchmarks/results/annual-benchmark-matrix.json`, `.csv`, and `annual-benchmark-validation.json`. Protocol: `docs/annual-matrix-design.md`. Tools: `benchmarks/annual_matrix.py`, `verify_annual_matrix.py`, `summarize_annual_matrix.py`, `validate_annual_publication.py`, `annual_matrix_report.py`, `scripts/annual_container.sh`. Tests: `tests/test_annual_matrix.py`. Campaign IDs, source revisions, binary identities and evidence hashes are in the dataset. No push was performed.','']
 (ROOT/'docs/annual-matrix-report.md').write_text('\n'.join(lines))
if __name__=='__main__':main()
