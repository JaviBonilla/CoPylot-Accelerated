#!/usr/bin/env python3
"""Measure C array export versus the complete existing Python result conversion."""
import argparse
import ctypes as c
import json
from pathlib import Path
import statistics
from cases import ROOT, api, configure, layout, timed

p = argparse.ArgumentParser()
p.add_argument('--repeats', type=int, default=15)
p.add_argument('--output', type=Path, default=ROOT / 'artifacts/export-overhead.json')
args = p.parse_args()
if args.repeats < 1:
    p.error('repeats must be positive')
cp = api()
r = cp.data_create()
assert r
try:
    configure(cp, r, 'large')
    assert cp.assign_layout(r, layout(10000), nthreads=1)
    assert cp.simulate(r, nthreads=1)
    cp.pdll.sp_detail_results.restype = c.POINTER(c.c_double)
    cp.pdll.sp_get_fluxmap.restype = c.POINTER(c.c_double)
    result = {'heliostats': 10000, 'repeats': args.repeats, 'samples': []}
    for _ in range(args.repeats):
        rows, cols = c.c_int(), c.c_int()
        raw_details, dt = timed(cp.pdll.sp_detail_results, c.c_void_p(r), c.byref(rows), c.byref(cols),
                                 c.POINTER(c.c_double)(), c.c_int(0), c.c_bool(False))
        assert raw_details
        cp._free_result_array(raw_details)
        _, full_dt = timed(cp.detail_results, r, restype='dictionary')
        raw_flux, ft = timed(cp.pdll.sp_get_fluxmap, c.c_void_p(r), c.byref(rows), c.byref(cols), c.c_int(0), c.c_int(0))
        assert raw_flux
        cp._free_result_array(raw_flux)
        _, full_ft = timed(cp.get_fluxmap, r)
        result['samples'].append({'raw_detail_s': dt, 'python_detail_s': full_dt,
                                  'raw_flux_s': ft, 'python_flux_s': full_ft})
    result['medians'] = {key: statistics.median(s[key] for s in result['samples']) for key in result['samples'][0]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['medians'], indent=2))
finally:
    assert cp.data_free(r)
