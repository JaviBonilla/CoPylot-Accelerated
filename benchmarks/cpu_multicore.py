#!/usr/bin/env python3
"""Single-state CPU scaling on fixed scientific grids; private inputs stay ignored."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import tempfile
import threading
import time
from unittest.mock import patch

import numpy as np
from cases import ROOT, api
from commercial_reference import load_manifest, configure
from project_grid_campaign import prepare, PLAIN, require, frozen_state, assert_frozen
from image_plane_cuda_performance import distribution, PipelineWindow, wait_idle
from summarize_project_grid import safe_point, safe_errors
from receiver_grid_convergence import backend_check

COUNTS = (1, 2, 4, 8, 12, 24)


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def topology():
    rows = []
    allowed = os.sched_getaffinity(0)
    for path in sorted(Path('/sys/devices/system/cpu').glob('cpu[0-9]*'), key=lambda p: int(p.name[3:])):
        cpu = int(path.name[3:])
        if cpu not in allowed: continue
        top = path / 'topology'
        rows.append({'cpu': cpu, 'core': int((top/'core_id').read_text()),
                     'socket': int((top/'physical_package_id').read_text()),
                     'siblings': (top/'thread_siblings_list').read_text().strip()})
    first = {}
    for row in rows: first.setdefault((row['socket'], row['core']), row['cpu'])
    physical = list(first.values())
    sets = {str(n): physical[:n] if n <= len(physical) else [r['cpu'] for r in rows][:n] for n in COUNTS}
    require(all(len(sets[str(n)]) == n for n in COUNTS), 'Scientific scaling requires 24 available CPUs')
    return {'logical_cpus': rows, 'physical_cores': len(physical), 'sockets': len({r['socket'] for r in rows}),
            'affinity_sets': sets, 'lscpu': json.loads(subprocess.check_output(['lscpu','-J'], text=True))}


def frequency():
    result = {}
    for path in sorted(Path('/sys/devices/system/cpu/cpufreq').glob('policy*')):
        values = {}
        for key in ('scaling_governor','scaling_driver','scaling_available_governors',
                    'scaling_cur_freq','scaling_min_freq','scaling_max_freq','cpuinfo_max_freq'):
            file = path/key
            if file.exists(): values[key] = file.read_text().strip()
        result[path.name] = values
    return result


def cpu_window():
    ticks = [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:]]
    # guest times are already included in user/nice; idle and iowait are excluded.
    busy = sum(ticks[:3]) + sum(ticks[5:8])
    usage = resource.getrusage(resource.RUSAGE_SELF)
    throttle = {p.parent.parent.name: int(p.read_text()) for p in
                Path('/sys/devices/system/cpu').glob('cpu[0-9]*/thermal_throttle/core_throttle_count')}
    temps = {p.parent.name: int(p.read_text()) for p in Path('/sys/class/thermal').glob('thermal_zone*/temp')}
    return {'wall': time.perf_counter(), 'busy_ticks': busy, 'own_cpu_s': usage.ru_utime+usage.ru_stime,
            'throttle': throttle, 'temperature_millidegrees': temps}


def validate_window(before, after):
    elapsed = after['wall']-before['wall']
    external = max(0., (after['busy_ticks']-before['busy_ticks'])/os.sysconf('SC_CLK_TCK')
                   - (after['own_cpu_s']-before['own_cpu_s']))
    extra = external/elapsed
    thermal = any(after['throttle'][key] > value for key,value in before['throttle'].items())
    require(extra < .5, 'External CPU workload invalidates this timing window')
    require(not thermal, 'CPU thermal throttling invalidates this timing window')
    return {'elapsed_s': elapsed, 'external_cpu_s': external, 'external_average_cores': extra,
            'thermal_throttle_count_increased': thermal,
            'temperature_before': before['temperature_millidegrees'], 'temperature_after': after['temperature_millidegrees']}


def state(cp, context):
    flux = np.asarray(cp.get_fluxmap(context), dtype=np.float64)
    detail = cp.detail_results(context, restype='dictionary')
    summary = next(iter(cp.summary_results(context).values()))
    numeric = {k: float(v) for k,v in summary.items() if isinstance(v,(float,int))}
    return flux, {k: np.asarray(v, dtype=np.float64) for k,v in detail.items()}, numeric


def equal(a, b):
    require(a[0].tobytes() == b[0].tobytes(), 'Receiver maps differ bitwise')
    require(a[1].keys() == b[1].keys(), 'Detailed result schema changed')
    require(all(a[1][k].tobytes() == b[1][k].tobytes() for k in a[1]), 'Detailed heliostat outputs differ bitwise')
    require(a[2].keys() == b[2].keys(), 'Summary schema changed')
    require(all(np.float64(a[2][k]).tobytes() == np.float64(b[2][k]).tobytes() for k in a[2]), 'Summary differs bitwise')


def simulate(cp, context, n):
    start = time.perf_counter()
    require(cp.simulate(context,nthreads=n), 'Single-state simulation failed')
    return time.perf_counter()-start


def observe(cp, context, n):
    stop = threading.Event(); ready = threading.Event(); observed = []
    def monitor():
        os.sched_setaffinity(0, {max(topology_cache['affinity_sets']['24'])})
        tid = threading.get_native_id(); ready.set()
        while not stop.is_set():
            runnable = 0; total = 0
            for p in Path('/proc/self/task').glob('[0-9]*'):
                if int(p.name) == tid: continue
                try:
                    status = (p/'stat').read_text().split(') ',1)[1].split()[0]
                    total += 1; runnable += status == 'R'
                except FileNotFoundError: pass
            observed.append((total,runnable)); stop.wait(.005)
    worker = threading.Thread(target=monitor); worker.start(); ready.wait()
    try: simulate(cp,context,n)
    finally: stop.set(); worker.join()
    return {'maximum_observed_process_threads_excluding_observer': max(x[0] for x in observed),
            'maximum_sampled_runnable_threads_excluding_observer': max(x[1] for x in observed),
            'samples': len(observed), 'diagnostic_only': True,
            'interpretation': 'Sampled runnable count is an observation, not exact simultaneous worker utilization'}


def contexts(cp, case, plan, all_states):
    if case == 'cesa-i-private-restored':
        points = plan['operating_points']; grid = plan['grids'][5]
        for point in points if all_states else points[:1]:
            yield point['id'], grid, safe_point(point), prepare(cp,Path(plan['project']),point,grid)
    else:
        manifest = load_manifest()
        span=np.pi*manifest['parameters']['receiver.0.rec_diameter']['value']
        height=manifest['parameters']['receiver.0.rec_height']['value']
        grid={'receiver_type':'cylindrical','nx':222,'ny':87,'cells':19314,
              'surface_width_m':span,'height_m':height,'cell_width_m':span/222,'cell_height_m':height/87,
              'target_cell_m':None}
        for point in manifest['operating_points'] if all_states else manifest['operating_points'][:1]:
            context = cp.data_create()
            configure(cp,context,manifest,222,87,point)
            yield point['id'], grid, point, context


def metadata():
    git = lambda *a: subprocess.check_output(['git',*a],text=True).strip()
    library = Path(os.environ['COPILOT_LIB_DIR'])/'solarpilot.so'
    cache=library.parent.parent/'CMakeCache.txt'
    settings={}
    if cache.exists():
        allowed={'CMAKE_BUILD_TYPE','CMAKE_CXX_FLAGS','CMAKE_CXX_FLAGS_RELEASE','CMAKE_CUDA_FLAGS',
                 'CMAKE_CUDA_FLAGS_RELEASE','CMAKE_CUDA_ARCHITECTURES','SOLARPILOT_ENABLE_FLUX_DIAGNOSTICS',
                 'SOLARPILOT_ENABLE_CORE_PROFILE'}
        for line in cache.read_text().splitlines():
            if ':' in line and '=' in line:
                key=line.split(':',1)[0]
                if key in allowed:settings[key]=line.split('=',1)[1]
    numerical=[ROOT/'ssc/solarpilot'/name for name in ('ImagePlaneInterceptKernels.cu','FluxDensityKernels.cu',
                'ImagePlaneIntercept.cpp','ImagePlaneInterceptNumerics.h','FluxDensityNumerics.h')]
    return {'utc':datetime.now(timezone.utc).isoformat(), 'machine':'canonical-gpu-server',
            'commits':{name:git('-C',name,'rev-parse','HEAD') for name in ('.','ssc','SolarPILOT','SolTrace')},
            'library_sha256':hashlib.sha256(library.read_bytes()).hexdigest(),
            'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'compiler':subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
            'build_settings':settings,'precision':'double','fast_math':False,
            'cuda_image_block':64,'cuda_density_block':256,
            'numerical_source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in numerical},
            'topology':topology_cache, 'frequency_before':frequency(),
            'numerical_threads':'Only independent work within one simulation; BLAS/OMP/MKL pools fixed to one',
            'build':'Existing pinned Release CUDA-capable diagnostic/profile-enabled library; files/events OFF during timings',
            'window_policy':'Reject external CPU work >=0.5 average core or increased thermal throttle counts; no system settings changed'}


def campaign(args):
    cp = api(); plan = json.loads(args.plan.read_text())
    result = {'phase':'4','stage':args.stage,'status':'running','metadata':metadata(),'rows':[]}
    modes = ('legacy','flat') if args.stage == 'preexisting' else (('cuda',) if args.stage=='cuda' else ('flat',))
    window = None
    if args.stage == 'cuda':
        wait_idle(); window = PipelineWindow(max(topology_cache['affinity_sets']['24'])); result['runtime_probe_s']=window.initialize(cp)
    try:
        for case in ('cesa-i-private-restored','ssc-mspt-8790-optical-reference'):
            for sid,grid,point,context in contexts(cp,case,plan,args.stage!='preexisting'):
                try:
                    oracle = None
                    for mode in modes:
                        if mode=='cuda':
                            cp.set_compute_backend(context,'cpu')
                            with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'flat'}):simulate(cp,context,1)
                            oracle=state(cp,context)
                        cp.set_compute_backend(context,'cuda' if mode=='cuda' else 'cpu')
                        counts = (1,) if mode=='cuda' else COUNTS
                        for n in counts:
                            os.sched_setaffinity(0,set(topology_cache['affinity_sets'][str(n)]))
                            env={**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'cuda' if mode=='cuda' else mode,
                                 'SOLARPILOT_FLUX_PATH':'legacy' if mode=='legacy' else 'flat'}
                            with patch.dict(os.environ,env):
                                # Restore a fresh context for every configuration, keeping first use separate.
                                if n != 1 or mode != modes[0]:
                                    cp.data_free(context)
                                    if case=='cesa-i-private-restored':
                                        raw=next(p for p in plan['operating_points'] if p['id']==sid)
                                        context=prepare(cp,Path(plan['project']),raw,grid)
                                    else:
                                        context=cp.data_create();configure(cp,context,load_manifest(),222,87,point)
                                first = simulate(cp,context,n)
                                warmups = 3 if mode=='cuda' else 2
                                repetitions = 10 if mode=='cuda' else (3 if mode=='legacy' else 5)
                                for _ in range(warmups):simulate(cp,context,n)
                                before=cpu_window();samples=[simulate(cp,context,n) for _ in range(repetitions)];after=cpu_window()
                                cpu_check=validate_window(before,after)
                                actual=state(cp,context)
                                if oracle is None:oracle=actual
                                if mode!='cuda':equal(oracle,actual)
                                else:
                                    backend_errors=backend_check(oracle[0],actual[0],grid)
                                    for key in oracle[1]:np.testing.assert_allclose(actual[1][key],oracle[1][key],rtol=1e-9,atol=1e-10)
                                    for key in oracle[2]:np.testing.assert_allclose(actual[2][key],oracle[2][key],rtol=1e-9,atol=1e-10)
                                observation=observe(cp,context,n) if mode!='cuda' else None
                                equal(actual,state(cp,context))
                                if case=='cesa-i-private-restored':
                                    prior=ROOT/'local-cases/example/phase3c-results/correctness-eight.json'
                                    expected=json.loads(prior.read_text())['physics_checks'][sid]
                                    with tempfile.TemporaryDirectory(dir=args.output.parent) as td:
                                        assert_frozen(expected,frozen_state(cp,context,Path(td)))
                            row={'case_id':case,'state_id':sid,'grid':grid,'operating_point':point,'path':mode,
                                 'requested_threads':n,'cpu_affinity':topology_cache['affinity_sets'][str(n)],
                                 'physical_cores_used':min(n,topology_cache['physical_cores']),'smt':n>topology_cache['physical_cores'],
                                 'first_call_s':first,'warmups_excluded_after_first':warmups,'repetitions':repetitions,
                                 'samples_s':samples,'statistics_s':distribution(samples),'cpu_window':cpu_check,
                                 'worker_observation':observation,'bitwise_maps_details_summary':mode!='cuda'}
                            if mode=='cuda':row['backend_errors']=safe_errors(backend_errors)
                            if window:window.validate()
                            result['rows'].append(row);write(args.output,result)
                            print(case,sid,mode,n,'median ms',round(row['statistics_s']['median']*1000,3),'PASS',flush=True)
                finally:cp.data_free(context)
        if window:window.close();result['gpu_telemetry']=window.samples
        result['metadata']['frequency_after']=frequency();result['status']='passed';write(args.output,result)
    finally:
        if window:window.stop.set()


def profiles(args):
    cp=api();plan=json.loads(args.plan.read_text());scaling=json.loads(args.scaling.read_text())
    require(scaling['status']=='passed','Profiling requires validated scaling')
    result={'phase':'4','status':'running','metadata':metadata(),'rows':[],
            'interpretation':'Diagnostic caller-thread stage wall scopes; inclusive scopes overlap; excluded from formal statistics'}
    for case in ('cesa-i-private-restored','ssc-mspt-8790-optical-reference'):
        candidates=[n for n in COUNTS if n<=topology_cache['physical_cores']]
        best=min(candidates,key=lambda n:np.median([r['statistics_s']['median'] for r in scaling['rows']
                                                   if r['case_id']==case and r['requested_threads']==n]))
        for sid,grid,point,context in contexts(cp,case,plan,False):
            try:
                for n in dict.fromkeys((1,best,24)):
                    os.sched_setaffinity(0,set(topology_cache['affinity_sets'][str(n)]))
                    with tempfile.TemporaryDirectory(dir=args.output.parent) as td:
                        file=Path(td)/'profile.csv'
                        with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'flat'}):
                            simulate(cp,context,n)
                        with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'flat','SOLARPILOT_PROFILE_FILE':str(file)}):
                            elapsed=simulate(cp,context,n)
                        import csv
                        values={row[1]:{'calls':int(row[2]),'inclusive_s':float(row[3]),'exclusive_s':float(row[4])}
                                for row in csv.reader(file.read_text().splitlines())}
                    result['rows'].append({'case_id':case,'state_id':sid,'grid':grid,'threads':n,
                                           'simulate_wall_s':elapsed,'scopes':values})
                    print(case,'profile',n,'PASS',flush=True)
            finally:cp.data_free(context)
    result['status']='passed';write(args.output,result)


def main():
    global topology_cache
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['preexisting','flat','cuda','profile'],required=True)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--scaling',type=Path)
    args=p.parse_args();require(not args.output.exists(),'Refusing to overwrite benchmark evidence')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    require(args.output.resolve().is_relative_to(ROOT/'artifacts') or args.output.resolve().is_relative_to(ROOT/'local-cases'),
            'Detailed campaign output must remain in ignored directories')
    for key in list(os.environ):
        if key.startswith('SOLARPILOT_'):os.environ.pop(key)
    topology_cache=topology()
    if args.stage=='profile':
        require(args.scaling is not None,'Profile requires --scaling');profiles(args)
    else:campaign(args)


if __name__=='__main__':main()
