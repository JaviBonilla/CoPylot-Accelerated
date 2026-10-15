#!/usr/bin/env python3
"""Single-thread Phase 2D-A baseline, differential snapshots and CPU timings."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {'sun': (0,49), 'errors': (49,98), 'mirror': (98,147),
            'flux_moments': (147,196), 'coefficients': (196,212),
            'sigmas': (212,214), 'intercept': (214,215)}


def statistics_s(samples):
    return {'samples_s': samples, 'median_s': statistics.median(samples),
            'min_s': min(samples), 'max_s': max(samples)}


def metadata():
    def git(path):
        return subprocess.check_output(['git','-C',str(ROOT/path),'rev-parse','HEAD'],text=True).strip()
    cpu = next(line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name'))
    return {'phase':'2D-A', 'repositories':{p:git(p) for p in ['.','ssc','SolarPILOT','SolTrace']},
            'cpu':cpu, 'platform':platform.system(), 'compiler':subprocess.check_output(['c++','--version'],text=True).splitlines()[0],
            'build_type':'Release', 'flags':'-O3 -DNDEBUG; no fast-math', 'threads':1,
            'cpu_affinity':sorted(os.sched_getaffinity(0)), 'warmups':2, 'repetitions':7,
            'rtol':1e-9, 'atol':1e-10, 'snapshot_values_per_heliostat':215,
            'snapshot_families':FAMILIES}


def read_snapshot(path, count):
    values=np.fromfile(path,dtype=np.float64).reshape(count,215)
    if not np.isfinite(values).all():
        raise AssertionError('Non-finite optical snapshot')
    return values


def fingerprint(values):
    return {name:hashlib.sha256(np.ascontiguousarray(values[:,a:b]).tobytes()).hexdigest() for name,(a,b) in FAMILIES.items()}


def errors(expected, actual):
    report={}
    for name,(a,b) in FAMILIES.items():
        e, v=expected[:,a:b],actual[:,a:b]
        d=np.abs(e-v)
        idx=np.unravel_index(np.argmax(d),d.shape)
        report[name]={'bitwise':bool(np.array_equal(e.view(np.uint64),v.view(np.uint64))),
                      'max_abs':float(d.max()),'max_rel':float((d/np.maximum(np.abs(e),np.finfo(float).tiny)).max()),
                      'rms':float(np.sqrt(np.mean(d*d))),'heliostat_index':int(idx[0]),'family_index':int(idx[1])}
        np.testing.assert_allclose(v,e,rtol=1e-9,atol=1e-10)
    return report


def direct(binary, count, grid, repeats, snapshot, env):
    result=subprocess.run([str(binary),str(count),str(grid),str(repeats),str(snapshot)],env=env,text=True,capture_output=True,check=True)
    row=json.loads(result.stdout)
    row.update(statistics_s(row.pop('samples_s')))
    return row


def profile_rows(path, phase='direct_intercept'):
    rows={}
    for p,name,calls,inclusive,exclusive in csv.reader(path.read_text().splitlines()):
        if p==phase:
            rows.setdefault(name,[]).append({'calls':int(calls),'inclusive_s':float(inclusive),'exclusive_s':float(exclusive)})
    return {name:{'samples':v,'median_inclusive_s':statistics.median(x['inclusive_s'] for x in v),
                  'median_exclusive_s':statistics.median(x['exclusive_s'] for x in v)} for name,v in rows.items()}


def run(args):
    artifacts=ROOT/'artifacts/phase2da'; artifacts.mkdir(parents=True,exist_ok=True)
    binary=(ROOT/args.build/'image_plane_benchmark').resolve()
    result=metadata();result['stage']=args.stage
    result['binary_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
    result['library_sha256']=hashlib.sha256((ROOT/args.build/'lib/solarpilot.so').read_bytes()).hexdigest()
    base_env=os.environ.copy()
    for key in ['SOLARPILOT_PROFILE_FILE','SOLARPILOT_INTERCEPT_PROFILE','SOLARPILOT_CUDA_TIMING_FILE','SOLARPILOT_INTERCEPT_FILE']:
        base_env.pop(key,None)
    result['direct']=[]; result['profiles']=[]; result['grid_snapshots']=[]
    for count in [1000,5000,10000]:
        paths=['legacy'] if args.stage=='baseline' else ['legacy','flat']
        for mode in paths:
            env={**base_env,'SOLARPILOT_INTERCEPT_PATH':mode}
            snap=artifacts/f'{args.stage}-{mode}-{count}-25.bin'
            row=direct(binary,count,25,7,snap,env); row['path']=mode
            result['direct'].append(row)
            profile=artifacts/f'{args.stage}-{mode}-{count}-profile.csv'
            if profile.exists(): profile.unlink() # This harness owns this per-run temporary.
            direct(binary,count,25,7,snap,{**env,'SOLARPILOT_PROFILE_FILE':str(profile),'SOLARPILOT_INTERCEPT_PROFILE':'1'})
            result['profiles'].append({'heliostats':count,'path':mode,'scopes':profile_rows(profile)})
        reference=None
        for grid in [25,50,100]:
            mode='legacy' if args.stage=='baseline' else 'flat'
            snapshot=artifacts/f'{args.stage}-{mode}-{count}-{grid}.bin'
            direct(binary,count,grid,1,snapshot,{**base_env,'SOLARPILOT_INTERCEPT_PATH':mode})
            values=read_snapshot(snapshot,count)
            row={'heliostats':count,'grid':grid,'hashes':fingerprint(values)}
            if reference is None: reference=values
            row['vs_grid25']=errors(reference,values)
            if args.stage!='baseline':
                old=read_snapshot(artifacts/f'baseline-legacy-{count}-{grid}.bin',count)
                row['vs_pre_extraction_legacy']=errors(old,values)
                legacy=read_snapshot(artifacts/f'final-legacy-{count}-25.bin',count)
                row['vs_preserved_legacy']=errors(legacy,values)
            result['grid_snapshots'].append(row)
    output=ROOT/'benchmarks/results'/('phase2da-legacy-profile.json' if args.stage=='baseline' else 'phase2da-cpu-performance.json')
    output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'output':output.name,'direct':[(r['heliostats'],r['path'],r['median_s']) for r in result['direct']]}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['baseline','final'],required=True)
    parser.add_argument('--build',type=Path,default=Path('build/phase2da'))
    run(parser.parse_args())
