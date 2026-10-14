#!/usr/bin/env python3
"""Explicit baseline capture only; tests never rewrite reference files."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
from cases import ROOT, SIZES, run_case

for size in SIZES:
    result, timings = run_case(size, repeats=1, measure_generation=False)
    result['provenance'] = {'base_repos': json.loads((ROOT / 'repos.lock.json').read_text()),
                            'note': 'Original CPU algorithms, build-only fixes; captured before backend dispatch or profiling.'}
    path = ROOT / 'tests/baselines' / f'{size}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, allow_nan=False, separators=(',', ':')) + '\n')
    print(size, result['metrics'], timings, flush=True)
