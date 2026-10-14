#!/usr/bin/env python3
"""Nine CPU-only flux-density cases with profiling and optional differential checks."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile

import numpy as np
from cases import ROOT, SIZES, PARAMETERS, WEATHER, api, configure, layout, timed


def distribution(values):
    return dict(median=statistics.median(values), minimum=min(values), maximum=max(values))


def run(size, resolution, repeats, mode):
    cp = api()
    r = cp.data_create()
    if not r:
        raise AssertionError('Context creation failed')
    try:
        configure(cp, r, size)
        for axis in ('x_res', 'y_res'):
            assert cp.data_set_number(r, 'fluxsim.0.' + axis, resolution)
        positions = layout(SIZES[size])
        assert cp.assign_layout(r, positions, nthreads=1)
        actual = len(cp.get_layout_info(r, restype='dictionary')['id'])
        assert actual == SIZES[size]
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / 'profile.csv'
            differential = Path(directory) / 'differential.csv'
            os.environ['SOLARPILOT_PROFILE_FILE'] = str(profile)
            os.environ['SOLARPILOT_FLUX_PATH'] = mode
            os.environ['SOLARPILOT_FLUX_COMPARE_FILE'] = str(differential)
            # Warm simulation excluded from distributions (including verification overhead).
            assert cp.simulate(r, nthreads=1)
            profile.write_text('')
            if differential.exists():
                differential.write_text('')
            samples = []
            flux_samples = []
            for _ in range(repeats):
                ok, elapsed = timed(cp.simulate, r, nthreads=1)
                assert ok, 'Simulation failed'
                samples.append(elapsed)
            rows = list(csv.reader(profile.read_text().splitlines()))
            flux_samples = [float(row[3]) for row in rows
                            if row[0] == 'simulate' and row[1] == 'Flux::fluxDensity']
            if len(flux_samples) != repeats or min(flux_samples) <= 0:
                raise AssertionError('A profile-enabled build with one receiver is required')
            checks = []
            if mode == 'verify':
                if not differential.exists():
                    raise AssertionError('A flux-diagnostics build is required for verification')
                for row in csv.reader(differential.read_text().splitlines()):
                    checks.append(dict(zip(('cells', 'max_abs', 'max_rel', 'max_abs_x', 'max_abs_y',
                                            'max_rel_x', 'max_rel_y', 'bitwise', 'evaluated'), map(float, row))))
                assert len(checks) == repeats
        flux = np.asarray(cp.get_fluxmap(r), dtype=np.float64)
        assert flux.shape == (resolution, resolution) and np.isfinite(flux).all()
        power = next(iter(cp.summary_results(r).values()))['Power absorbed by the receiver']
        area = np.pi * cp.data_get_number(r, 'receiver.0.rec_diameter') * cp.data_get_number(r, 'receiver.0.rec_height')
        return dict(heliostats=actual, grid=resolution, cells=flux.size,
                    candidate_interactions=actual * flux.size, mode=mode, repeats=repeats,
                    parameters={**PARAMETERS, "fluxsim.0.x_res": resolution, "fluxsim.0.y_res": resolution},
                    simulate_s=distribution(samples), density_s=distribution(flux_samples),
                    simulate_samples_s=samples, density_samples_s=flux_samples,
                    peak_flux_kw_m2=float(flux.max()), integrated_incident_flux_kw=float(flux.sum() * area / flux.size),
                    receiver_power_kw=power, flux_sha256=hashlib.sha256(flux.tobytes()).hexdigest(),
                    layout_sha256=hashlib.sha256(json.dumps(positions).encode()).hexdigest(),
                    differential=checks)
    finally:
        assert cp.data_free(r)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('legacy', 'flat', 'verify'), default='legacy')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--sizes', nargs='+', choices=SIZES, default=list(SIZES))
    parser.add_argument('--grids', nargs='+', type=int, default=[25, 50, 100])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.repeats < 1 or any(grid < 1 for grid in args.grids):
        parser.error('Repetitions and grid sizes must be positive')
    output = dict(platform=platform.platform(), cpu=Path('/proc/cpuinfo').read_text().split('model name')[1].split('\n')[0].split(':')[1].strip(),
                  python=platform.python_version(), parameters=PARAMETERS,
                  weather_sha256=hashlib.sha256(WEATHER.read_bytes()).hexdigest(),
                  commits={repo: subprocess.check_output(['git', '-C', str(ROOT / repo), 'rev-parse', 'HEAD'], text=True).strip()
                           for repo in ('.', 'ssc', 'SolarPILOT', 'SolTrace')}, cases=[])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for size in args.sizes:
        for grid in args.grids:
            result = run(size, grid, args.repeats, args.mode)
            output['cases'].append(result)
            args.output.write_text(json.dumps(output, indent=2) + '\n')
            print(f'{size} {grid} {args.mode}: simulate={result["simulate_s"]["median"]:.6f}s density={result["density_s"]["median"]:.6f}s', flush=True)


if __name__ == '__main__':
    main()
