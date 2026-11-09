"""Offline validation of the reviewed result closure; no numerical library required."""
import csv
import hashlib
import json
from pathlib import Path
from . import annual_figure_data,original_baseline_data,performance_data,temporal_data,gpu_temporal_data

ROOT=Path(__file__).resolve().parents[1]


def main():
    results=ROOT/'results'
    read=lambda name:json.loads((results/name).read_text())
    for file in read('public-evidence-manifest.json')['files']:
        path=ROOT.parent/file['path']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=file['public_sha256']:
            raise ValueError('Reviewed evidence hash changed: '+file['path'])
    with (results/'annual-benchmark-matrix.csv').open() as f:flat=list(csv.DictReader(f))
    annual_figure_data.audit(read('annual-benchmark-matrix.json'),read('annual-benchmark-validation.json'),flat)
    original_baseline_data.audit(read('original-baseline-single-state.json'),read('original-baseline-validation.json'))
    performance_data.audit(read('phase4s-final-cpu-baseline.json'),read('phase4s-cuda-control-timings.json'),read('phase4s-cpu-gpu-summary.json'))
    temporal_data.audit(read('phase5a-campaign-summary.json'))
    gpu_temporal_data.audit(read('phase5b-annual-summary.json'))
    print('Reviewed annual, Original, CPU and GPU evidence: PASS')

if __name__=='__main__':main()
