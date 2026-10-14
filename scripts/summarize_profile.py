#!/usr/bin/env python3
"""Render measured inclusive/exclusive scope tables from saved raw CSV."""
import csv
import json
from pathlib import Path
import statistics
ROOT = Path(__file__).resolve().parents[1]
results = ROOT / 'benchmarks/results'
original = json.loads((results / 'cpu-original.json').read_text())
lines = ['# CPU profile: measured baseline', '',
    'Host: '+original['cpu']+'. Linux x86_64, GCC 13.3, CMake 3.30.5, Release/O3, double precision, one core simulation thread. Python 3.12, NumPy 1.26.4, pandas 2.2.3. No affinity/frequency locking; wall times depend on host load/thermal state.', '',
    'Weather: pinned Daggett TMY2; azimuth 180°, elevation 55°, DNI 950 W/m², external cylindrical receiver 17.65 m diameter ×21.6 m height, simple aimpoints, 25×25 flux map. Assigned concentric-ring layouts have exactly 1000/5000/10000 heliostats. Generated fields are a separate measurement (one design point with filtering).', '',
    'Raw timings/CSV are tracked under benchmarks/results. Original CPU numbers precede dispatch/profiling and use five serial simulations per case. Profile numbers are separate opt-in builds/runs. Warm repeated calls execute the full simulation; the first call is preserved separately in raw data.', '',
    '## Original CPU end-to-end medians (five calls)', '',
    '| Case | Generated count | generate_layout ms | assign_layout ms | simulate ms | get_fluxmap ms | detail_results ms |',
    '|---|---:|---:|---:|---:|---:|---:|']
for size, c in original['cases'].items():
    med = {k: statistics.median(s[k] for s in c['samples']) for k in ['simulate_s', 'get_fluxmap_s', 'detail_results_s']}
    lines.append(f'| {size} ({c["heliostats"]}) | {c["generated_heliostats"]} | {1000*c["generate_layout_s"]:.3f} | {1000*c["assign_layout_s"]:.3f} | {1000*med["simulate_s"]:.3f} | {1000*med["get_fluxmap_s"]:.3f} | {1000*med["detail_results_s"]:.3f} |')
lines += ['', '## Core scope measurements', '',
    'Mean per simulate across five calls. Percentages use instrumented C API wall time. Inclusive rows overlap; never add the parent and child percentages. Exclusive times subtract other instrumented scopes only, not every uninstrumented callee. CSV includes layout phases separately; tables below select phase=simulate. Main timers are compiled out with profiling OFF. Per-thread accounting is validated for nthreads=1, not for worker-thread aggregation.', '',
    'perf sampling was attempted but software events are blocked by perf_event_paranoid=4. No system settings were changed. Optional internal steady_clock scopes were used instead.', '']
for size in ['small', 'medium', 'large']:
    rows = [r for r in csv.reader((results / f'{size}.csv').open()) if r[0] == 'simulate']
    n = len([r for r in rows if r[1] == 'API'])
    total = sum(float(r[3]) for r in rows if r[1] == 'API')
    lines += [f'### {size}', '', '| Function | Calls/simulate | Inclusive ms | Exclusive ms | Inclusive % |', '|---|---:|---:|---:|---:|']
    for name in dict.fromkeys(r[1] for r in rows):
        rs = [r for r in rows if r[1] == name]
        inc = sum(float(r[3]) for r in rs); exc = sum(float(r[4]) for r in rs)
        lines.append(f'| {name} | {sum(int(r[2]) for r in rs)//n} | {inc/n*1000:.3f} | {exc/n*1000:.3f} | {inc/total*100:.2f} |')
    profile = json.loads((results / f'{size}-timings.json').read_text())['cases'][size]
    pm = statistics.median(s['simulate_s'] for s in profile['samples'])
    om = statistics.median(s['simulate_s'] for s in original['cases'][size]['samples'])
    lines += ['', f'Profile/original median wall-time ratio: {pm/om:.3f}. This mixes timer overhead and host variability; it is not a calibrated pure instrumentation overhead estimate.', '']
lines += ['## Hypotheses and implications', '',
    '* **A measured:** imagePlaneIntercept is ~9% of these simulate calls, exactly one call per heliostat. It matters, but it is not the dominant cost. The parent preparation scope is ~13–16%, including efficiency/tracking/neighbors.',
    '* **B measured:** fluxDensity is ~84–86%, essentially all AnalyticalFluxSimulation time. CalcDimensionalFluxProfiles is ~0.03–0.04%. These measurements support prioritizing the flux contribution kernel/reduction at this resolution.',
    '* **C measured:** the real shading/blocking neighbor loop is ~2%, 3.2%, 3.9% for small/medium/large. calcHeliostatShadows alone is ~0.25% and does not include those pair calculations. Neighbors grow in relevance with size here, but low elevation/dense layouts need separate profiling; no general bottleneck claim is made.',
    '* **D measured:** at 10000 heliostats, the export-overhead benchmark isolates the raw C allocation/export from full Python dictionary conversion; see table below. Repeated identical simulate calls show no large persistent computation cache benefit in this path. **Code-based inference:** preparation recreates receiver grids/cloud data, updates aim/tracking, rebuilds neighbor validity and recomputes images each call. Resident GPU data and device-side objectives can avoid some packing/returns. Deep layout-thread copies/multiprocessing/optimization overhead have not been timed; no percentage is assigned to them.', '',
    '## C array export versus Python conversion', '',
    'Separate Release run, 15 repetitions, 10000 heliostats. Raw C times include allocation/fill and ctypes call, excluding the explicit free; Python times include conversion and free. Their difference approximates conversion/wrapper overhead, not an exact separately sampled attribution.', '']
export = json.loads((results / 'export-overhead.json').read_text())['medians']
lines += ['| Result | Raw C median ms | Complete Python median ms |', '|---|---:|---:|',
    f'| detail_results | {export["raw_detail_s"]*1000:.3f} | {export["python_detail_s"]*1000:.3f} |',
    f'| get_fluxmap | {export["raw_flux_s"]*1000:.3f} | {export["python_flux_s"]*1000:.3f} |', '',
    'No GPU timings or speedup claims. The profiling distribution applies only to these fixed cases; more cells can increase flux cost, and different aiming/geometries/optimization workloads can change the candidate ranking. Full-precision snapshots and strict tolerances remain the gate for any pure CPU extraction or CUDA implementation.', '']
(ROOT / 'docs/cpu-profile.md').write_text('\n'.join(lines))
