"""Fixed double-precision, single-thread Hermite cases; no GUI imports."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'SolarPILOT/deploy/api'))
from copylot import CoPylot

SIZES = {'small': 1000, 'medium': 5000, 'large': 10000}
WEATHER = ROOT / 'SolarPILOT/deploy/climate_files/USA CA Daggett (TMY2).csv'
PARAMETERS = {
    'solarfield.0.des_sim_detail': 0,
    'fluxsim.0.flux_model': 0,
    'fluxsim.0.flux_time_type': 0,
    'fluxsim.0.flux_solar_az_in': 180.,
    'fluxsim.0.flux_solar_el_in': 55.,
    'fluxsim.0.flux_dni': 950.,
    'fluxsim.0.aim_method': 0,
    'fluxsim.0.x_res': 25,
    'fluxsim.0.y_res': 25,
    'land.0.is_bounds_scaled': 0,
    'land.0.max_fixed_rad': 5000.,
}


def api():
    # Upstream loads its library relative to cwd. Keep this compatibility contract.
    previous = Path.cwd()
    library = Path(os.environ.get('COPILOT_LIB_DIR', ROOT / 'build/cpu/lib')).resolve()
    try:
        os.chdir(library)
        return CoPylot()
    finally:
        os.chdir(previous)


def configure(cp, r, size):
    if not cp.data_set_string(r, 'ambient.0.weather_file', str(WEATHER)):
        raise RuntimeError('Failed to set weather file')
    for key, value in {**PARAMETERS, 'solarfield.0.q_des': SIZES[size] / 10}.items():
        if not cp.data_set_number(r, key, value):
            raise RuntimeError(f'Failed to set {key}')


def layout(n):
    """Concentric rings, 35 m radial and >=35 m tangential spacing, z=0."""
    positions = []
    ring = 0
    while len(positions) < n:
        radius = 160. + 35. * ring
        count = int(2 * math.pi * radius / 35.)
        phase = (ring % 2) * math.pi / count
        for j in range(count):
            angle = phase + 2 * math.pi * j / count
            positions.append([0, radius * math.sin(angle), radius * math.cos(angle), 0.])
            if len(positions) == n:
                break
        ring += 1
    return positions


def timed(fn, *args, **kwargs):
    start = time.perf_counter()
    value = fn(*args, **kwargs)
    return value, time.perf_counter() - start


def collect(cp, r):
    flux, flux_time = timed(cp.get_fluxmap, r)
    details, detail_time = timed(cp.detail_results, r, restype='dictionary')
    summary = cp.summary_results(r)
    if len(summary) != 1:
        raise AssertionError(f'Expected one receiver, got {summary.keys()}')
    values = next(iter(summary.values()))
    fa = np.asarray(flux, dtype=np.float64)
    if fa.shape != (25, 25) or not np.isfinite(fa).all() or fa.max() <= 0:
        raise AssertionError('Invalid flux map')
    if not details or not details.get('id'):
        raise AssertionError('Missing heliostat results')
    for key, column in details.items():
        if not np.isfinite(column).all():
            raise AssertionError(f'Non-finite heliostat column: {key}')
    numeric = {key: value for key, value in values.items() if isinstance(value, (float, int))}
    if not all(math.isfinite(v) for v in numeric.values()):
        raise AssertionError('Non-finite summary')
    if numeric['Power absorbed by the receiver'] <= 0:
        raise AssertionError('Receiver power must be positive')
    # External cylindrical receiver: equal-area cells; flux is incident kW/m2.
    area = math.pi * cp.data_get_number(r, 'receiver.0.rec_diameter') * cp.data_get_number(r, 'receiver.0.rec_height')
    metrics = {
        'receiver_power_kw': numeric['Power absorbed by the receiver'],
        'optical_efficiency_pct': numeric['Solar field optical efficiency'],
        'cosine_efficiency_pct': numeric['Cosine efficiency'],
        'intercept_efficiency_pct': numeric['Image intercept efficiency'],
        'attenuation_efficiency_pct': numeric['Attenuation efficiency'],
        'blocking_efficiency_pct': numeric['Blocking efficiency'],
        'shading_efficiency_pct': numeric['Shading efficiency'],
        'peak_receiver_flux_kw_m2': float(fa.max()),
        'integrated_incident_flux_kw': float(fa.sum() * area / fa.size),
    }
    return {'metrics': metrics, 'summary': numeric, 'flux': flux, 'details': details}, {
        'get_fluxmap_s': flux_time, 'detail_results_s': detail_time}


def run_case(size, repeats=3, measure_generation=True):
    if repeats < 1:
        raise ValueError('repeats must be positive')
    cp = api()
    r = cp.data_create()
    if not r:
        raise AssertionError('Failed to create CoPylot context')
    try:
        configure(cp, r, size)
        timings = {}
        if measure_generation:
            ok, timings['generate_layout_s'] = timed(cp.generate_layout, r, nthreads=1)
            if not ok:
                raise AssertionError('generate_layout failed')
            timings['generated_heliostats'] = len(cp.get_layout_info(r, restype='dictionary')['id'])
        positions = layout(SIZES[size])
        ok, timings['assign_layout_s'] = timed(cp.assign_layout, r, positions, nthreads=1)
        if not ok:
            raise AssertionError('assign_layout failed')
        actual = len(cp.get_layout_info(r, restype='dictionary')['id'])
        if actual != SIZES[size]:
            raise AssertionError(f'Expected {SIZES[size]} heliostats, got {actual}')
        samples = []
        # First simulation retained separately: distinguishes warm repeated calls.
        for _ in range(repeats):
            ok, dt = timed(cp.simulate, r, nthreads=1)
            if not ok:
                raise AssertionError('simulate failed')
            result, output_times = collect(cp, r)
            samples.append({'simulate_s': dt, **output_times})
        timings['samples'] = samples
        result['case'] = size
        result['heliostats'] = actual
        result['parameters'] = PARAMETERS
        result['weather_sha256'] = hashlib.sha256(WEATHER.read_bytes()).hexdigest()
        result['layout_sha256'] = hashlib.sha256(json.dumps(positions).encode()).hexdigest()
        return result, timings
    finally:
        if not cp.data_free(r):
            raise AssertionError('data_free failed')
