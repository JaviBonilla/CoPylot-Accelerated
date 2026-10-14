#!/usr/bin/env python3
"""Correctness-only legacy/flat/CUDA matrix; records no GPU performance timings."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import tempfile
from unittest.mock import patch

import numpy as np
from cases import ROOT, SIZES, PARAMETERS, WEATHER, api, configure, layout

RTOL, ATOL = 1.e-9, 1.e-10
COLUMNS = ('heliostats nx ny block raw_max_abs raw_max_rel raw_rms raw_abs_x raw_abs_y '
           'raw_rel_x raw_rel_y contribution_max_abs contribution_max_rel contribution_rms contribution_abs_h '
           'reduction_only_max_abs reduction_only_max_rel reduction_x reduction_y allocations h_capacity cell_capacity output_capacity').split()


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def metadata():
    library = Path(os.environ['COPILOT_LIB_DIR']).resolve()
    cache = (library.parent / 'CMakeCache.txt').read_text()
    entries = {line.split(':')[0]: line.split('=', 1)[1] for line in cache.splitlines()
               if ':' in line and '=' in line and not line.startswith('//')}
    gpu = command('nvidia-smi', '--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu', '--format=csv,noheader').split(',')
    return dict(commits={repo: command('git', '-C', str(ROOT / repo), 'rev-parse', 'HEAD')
                         for repo in ('.', 'ssc', 'SolarPILOT', 'SolTrace')},
                hostname=os.environ.get('COPILOT_HOSTNAME', socket.gethostname()),
                execution_hostname=socket.gethostname(), platform=platform.platform(),
                cpu_model=Path('/proc/cpuinfo').read_text().split('model name')[1].split('\n')[0].split(':')[1].strip(),
                gpu_model=gpu[0].strip(), driver=gpu[1].strip(), gpu_memory_total=gpu[2].strip(), gpu_memory_used=gpu[3].strip(),
                external_gpu_workload=os.environ.get('COPILOT_EXTERNAL_GPU_WORKLOAD', 'unspecified'),
                cuda_compiler=command(shutil.which('nvcc'), '--version'), cxx_compiler=command('g++', '--version'),
                cmake=command('cmake', '--version'), build_type=entries['CMAKE_BUILD_TYPE'],
                build_settings={key: value for key, value in entries.items() if key.startswith(('CMAKE_CUDA_', 'CMAKE_CXX_FLAGS', 'SOLARPILOT_ENABLE_'))},
                block_size=256, precision='double', cpu_threads=1, rtol=RTOL, atol=ATOL,
                gpu_timings_collected=False, scientific_speedups_reported=False,
                test_configuration='same-state raw map, complete dimensional map, peak-cell device-term reduction diagnosis',
                parameters=PARAMETERS, weather_sha256=hashlib.sha256(WEATHER.read_bytes()).hexdigest())


def errors(expected, actual):
    expected, actual = np.asarray(expected), np.asarray(actual)
    np.testing.assert_allclose(actual, expected, rtol=RTOL, atol=ATOL, equal_nan=False)
    difference = np.abs(actual-expected)
    relative = np.divide(difference, np.abs(expected), out=np.zeros_like(difference), where=expected != 0)
    return dict(max_abs=float(difference.max()), max_rel=float(relative.max()), rms=float(np.sqrt(np.mean(difference*difference))),
                abs_cell=list(map(int, np.unravel_index(difference.argmax(), difference.shape))),
                rel_cell=list(map(int, np.unravel_index(relative.argmax(), relative.shape))),
                zero_reference_nonzero_cells=int(np.count_nonzero((expected == 0) & (actual != 0))))


def collect(cp, context):
    flux = np.asarray(cp.get_fluxmap(context), dtype=np.float64)
    assert np.isfinite(flux).all()
    power = next(iter(cp.summary_results(context).values()))['Power absorbed by the receiver']
    area = np.pi * cp.data_get_number(context, 'receiver.0.rec_diameter') * cp.data_get_number(context, 'receiver.0.rec_height')
    return flux, dict(peak_flux_kw_m2=float(flux.max()), integrated_incident_flux_kw=float(flux.sum()*area/flux.size),
                      receiver_power_kw=power, flux_sha256=hashlib.sha256(flux.tobytes()).hexdigest())


def run(size, grid):
    cp = api(); context = cp.data_create(); assert context
    try:
        configure(cp, context, size)
        for axis in ('x_res', 'y_res'):
            assert cp.data_set_number(context, 'fluxsim.0.'+axis, grid)
        assert cp.assign_layout(context, layout(SIZES[size]), nthreads=1)
        actual = len(cp.get_layout_info(context, restype='dictionary')['id'])
        assert actual == SIZES[size]
        with tempfile.TemporaryDirectory() as directory:
            legacy_compare = str(Path(directory)/'legacy.csv')
            cuda_compare = Path(directory)/'cuda.csv'
            with patch.dict(os.environ, {'SOLARPILOT_FLUX_PATH':'legacy'}):
                assert cp.simulate(context, nthreads=1), cp.get_last_backend_error(context)
                legacy_flux, legacy = collect(cp, context)
            with patch.dict(os.environ, {'SOLARPILOT_FLUX_PATH':'verify', 'SOLARPILOT_FLUX_COMPARE_FILE':legacy_compare}):
                assert cp.simulate(context, nthreads=1), cp.get_last_backend_error(context)
                flat_flux, flat = collect(cp, context)
            checks = list(csv.reader(Path(legacy_compare).read_text().splitlines()))
            assert len(checks)==1 and float(checks[0][1])==float(checks[0][2])==0 and int(checks[0][7])==1
            assert np.array_equal(legacy_flux, flat_flux) and legacy == flat
            assert cp.set_compute_backend(context, 'cuda')
            diagnostics = []
            with patch.dict(os.environ, {'SOLARPILOT_FLUX_PATH':'verify_cuda', 'SOLARPILOT_CUDA_COMPARE_FILE':str(cuda_compare),
                                         'SOLARPILOT_CUDA_BLOCK_SIZE':'256'}):
                previous = None
                for repeat in range(2):
                    assert cp.simulate(context, nthreads=1), cp.get_last_backend_error(context)
                    cuda_flux, cuda = collect(cp, context)
                    if previous is not None: assert np.array_equal(previous, cuda_flux)
                    previous = cuda_flux.copy()
            for row in csv.reader(cuda_compare.read_text().splitlines()):
                values = dict(zip(COLUMNS, map(float, row)))
                assert values['block']==256 and values['heliostats']==actual and values['nx']==values['ny']==grid
                diagnostics.append(values)
            assert len(diagnostics)==2
            assert diagnostics[0]['allocations']==diagnostics[1]['allocations'], 'Repeated simulation reallocated CUDA buffers'
            dimensional = errors(flat_flux, cuda_flux)
            for key in ('peak_flux_kw_m2','integrated_incident_flux_kw','receiver_power_kw'):
                np.testing.assert_allclose(cuda[key], flat[key], rtol=RTOL, atol=ATOL)
            # Infinity in a raw relative error is represented explicitly, not as nonstandard JSON.
            for row in diagnostics:
                for key,value in row.items():
                    if not np.isfinite(value): row[key]=None
        return dict(heliostats=actual, grid=[grid,grid], cells=grid*grid, block_size=256,
                    legacy_flat_bitwise=True, repeated_cuda_bitwise=True, diagnostics=diagnostics,
                    dimensional_errors=dimensional, flat=flat, cuda=cuda,
                    transfer_bytes=dict(heliostat_h2d=200*actual, cell_h2d=48*grid*grid, output_d2h=8*grid*grid),
                    layout_sha256=hashlib.sha256(json.dumps(layout(actual)).encode()).hexdigest())
    finally:
        assert cp.data_free(context)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--native-results',type=Path)
    args=parser.parse_args()
    assert api().cuda_available(), 'CUDA device required'
    os.environ.pop('SOLARPILOT_CUDA_TIMING_FILE',None)
    output=dict(metadata=metadata(),cases=[])
    if args.native_results: output['native_tests']=json.loads(args.native_results.read_text())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for size in SIZES:
        for grid in (25,50,100):
            result=run(size,grid); output['cases'].append(result)
            args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
            print(f'{size} {grid} PASS: raw_abs={result["diagnostics"][0]["raw_max_abs"]:.3e}, map_abs={result["dimensional_errors"]["max_abs"]:.3e}',flush=True)


if __name__=='__main__': main()
