#!/usr/bin/env python3
"""Controlled same-machine Phase 2C timing, profiling and block-size comparison.

Only a fully validated monitoring window is published. Failed/partial samples
remain in ignored artifacts. This program never changes clocks or services.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import tempfile
import threading
import time
from unittest.mock import patch

import numpy as np
from cases import ROOT, SIZES, PARAMETERS, WEATHER, api, configure, layout
from cuda_flux_correctness import collect, errors, COLUMNS

GPU_FIELDS = ('name,driver_version,memory.used,memory.total,temperature.gpu,utilization.gpu,'
              'pstate,clocks.sm,clocks.mem,power.draw,clocks_throttle_reasons.hw_thermal_slowdown,'
              'clocks_throttle_reasons.sw_thermal_slowdown').split(',')


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def gpu_snapshot():
    row = next(csv.reader([command('nvidia-smi', '--query-gpu='+','.join(GPU_FIELDS), '--format=csv,noheader,nounits')]))
    result = dict(zip(GPU_FIELDS, (x.strip() for x in row)))
    result['utc'] = datetime.now(timezone.utc).isoformat()
    processes = command('nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits')
    result['_pids'] = [int(x) for x in processes.splitlines() if x.strip()]
    return result


def check_gpu(snapshot, allowed_pids=(), initial=False):
    if set(snapshot['_pids']) - set(allowed_pids):
        raise RuntimeError('Unexpected GPU compute process; performance window invalid')
    limit = 128 if initial else 1024
    if float(snapshot['memory.used']) > limit:
        raise RuntimeError('Significant external GPU memory use; performance window invalid')
    if initial and float(snapshot['utilization.gpu']) > 2:
        raise RuntimeError('GPU is not idle before the benchmark')
    if float(snapshot['temperature.gpu']) >= 85 or any(snapshot[k] == 'Active' for k in GPU_FIELDS[-2:]):
        raise RuntimeError('GPU thermal slowdown or excessive temperature; performance window invalid')


def public_snapshot(snapshot):
    return {**{k: v for k, v in snapshot.items() if k != '_pids'}, 'compute_process_count': len(snapshot['_pids'])}


class Window:
    def __init__(self, monitor_cpu):
        self.samples, self.failure, self.allowed = [], None, set()
        self.stop = threading.Event()
        self.monitor_cpu = monitor_cpu

    def sample(self, initial=False):
        value = gpu_snapshot()
        check_gpu(value, self.allowed, initial)
        self.samples.append(public_snapshot(value))
        return value

    def initialize(self, cp):
        self.sample(initial=True)
        context = cp.data_create()
        start = time.perf_counter()
        try:
            cp.set_compute_backend(context, 'cuda')
        finally:
            cp.data_free(context)
        elapsed = time.perf_counter()-start
        # The window began without compute processes. The API probe initializes
        # this process's primary CUDA context; only that PID may now be present.
        value = gpu_snapshot()
        if len(value['_pids']) != 1:
            raise RuntimeError('Cannot identify the sole benchmark CUDA process')
        self.allowed = set(value['_pids'])
        self.sample()
        self.thread = threading.Thread(target=self.monitor, daemon=True)
        self.thread.start()
        return elapsed

    def monitor(self):
        os.sched_setaffinity(0, {self.monitor_cpu})
        while not self.stop.wait(2):
            try:
                self.sample()
            except Exception as error:
                self.failure = str(error)
                return

    def validate(self):
        if self.failure:
            raise RuntimeError(self.failure)
        self.sample()

    def close(self):
        self.stop.set()
        self.thread.join()
        self.validate()


def distribution(values):
    return dict(median=statistics.median(values), minimum=min(values), maximum=max(values),
                mean=statistics.mean(values), stdev=statistics.stdev(values) if len(values)>1 else 0.,
                coefficient_of_variation=statistics.stdev(values)/statistics.mean(values) if len(values)>1 else 0.)


def metadata(benchmark_cpu, monitor_cpu):
    library = Path(os.environ['COPILOT_LIB_DIR']).resolve()
    cache = (library.parent/'CMakeCache.txt').read_text()
    entries = {line.split(':')[0]: line.split('=',1)[1] for line in cache.splitlines()
               if ':' in line and '=' in line and not line.startswith('//')}
    for key in ('SOLARPILOT_ENABLE_CUDA', 'SOLARPILOT_ENABLE_CORE_PROFILE', 'SOLARPILOT_ENABLE_FLUX_DIAGNOSTICS'):
        if entries.get(key) != 'ON':
            raise RuntimeError('CUDA, core profiling and flux diagnostics must be enabled')
    kernel = ROOT/'ssc/solarpilot/FluxDensityKernels.cu'
    library_file = library/'solarpilot.so'
    governor = Path(f'/sys/devices/system/cpu/cpu{benchmark_cpu}/cpufreq/scaling_governor')
    return dict(utc=datetime.now(timezone.utc).isoformat(), machine='canonical-gpu-server',
                commits={name:command('git','-C',str(ROOT/name),'rev-parse','HEAD') for name in ('.','ssc','SolarPILOT','SolTrace')},
                branches={name:command('git','-C',str(ROOT/name),'branch','--show-current') for name in ('.','ssc','SolarPILOT','SolTrace')},
                cpu_model=Path('/proc/cpuinfo').read_text().split('model name')[1].split('\n')[0].split(':')[1].strip(),
                cpu_affinity=[benchmark_cpu], monitor_cpu=monitor_cpu,
                cpu_governor=governor.read_text().strip() if governor.exists() else 'unavailable',
                cpu_threads=1, precision='double', fma=True, fast_math=False,
                nvcc=command('nvcc','--version'), compiler=command('g++','--version').splitlines()[0],
                cmake=command('cmake','--version').splitlines()[0],
                build_settings={k:entries.get(k) for k in ('CMAKE_BUILD_TYPE','CMAKE_CUDA_ARCHITECTURES','CMAKE_CUDA_FLAGS','CMAKE_CUDA_FLAGS_RELEASE','CMAKE_CXX_FLAGS','CMAKE_CXX_FLAGS_RELEASE','SOLARPILOT_ENABLE_CORE_PROFILE','SOLARPILOT_ENABLE_FLUX_DIAGNOSTICS')},
                kernel_source_sha256=hashlib.sha256(kernel.read_bytes()).hexdigest(),
                library_sha256=hashlib.sha256(library_file.read_bytes()).hexdigest(),
                weather_sha256=hashlib.sha256(WEATHER.read_bytes()).hexdigest(), parameters=PARAMETERS,
                rtol=1e-9, atol=1e-10, ncu_available=bool(__import__('shutil').which('ncu')),
                first_call_definition='First simulate on a fresh CoPylot/GpuContext. Backend probe and process runtime initialization recorded separately; not a cold CUDA process.',
                monitoring='No GPU process initially; sole API-probe process whitelisted; poll every 2 s plus case boundaries; memory <=1024 MiB, no thermal slowdown. No concurrent builds/tests.',
                simulate_wall_definition='perf_counter around public simulate including its profiling/timing CSV writes; all extraction/parsing/telemetry outside this interval')


def context_for(cp, size, grid):
    context = cp.data_create()
    try:
        configure(cp, context, size)
        for axis in ('x_res','y_res'):
            assert cp.data_set_number(context,'fluxsim.0.'+axis,grid)
        assert cp.assign_layout(context,layout(SIZES[size]),nthreads=1)
        assert len(cp.get_layout_info(context,restype='dictionary')['id']) == SIZES[size]
        return context
    except Exception:
        cp.data_free(context)
        raise


def simulate_once(cp, context, cuda, directory):
    profile, timing = directory/'profile.csv', directory/'cuda.csv'
    profile.write_text(''); timing.write_text('')
    os.environ['SOLARPILOT_PROFILE_FILE'] = str(profile)
    os.environ['SOLARPILOT_CUDA_TIMING_FILE'] = str(timing) if cuda else ''
    start = time.perf_counter()
    assert cp.simulate(context,nthreads=1), cp.get_last_backend_error(context)
    wall = time.perf_counter()-start
    rows = list(csv.reader(profile.read_text().splitlines()))
    prof = {r[1]:dict(calls=int(r[2]), inclusive_s=float(r[3]), exclusive_s=float(r[4])) for r in rows if r[0]=='simulate'}
    # Phase 2D-A adds opt-in optical subscopes; preserve the original required set.
    required = {'API','PerformanceSimulationPrep','calcHeliostatShadows','HermiteFluxSimulation',
                'AnalyticalFluxSimulation','CalcDimensionalFluxProfiles','Flux::fluxDensity',
                'Flux::imagePlaneIntercept','UpdateNeighborList','SolarField::Simulate','ShadingBlockingNeighbors'}
    assert required.issubset(prof) and prof['Flux::fluxDensity']['calls']==1
    result = dict(simulate_wall_s=wall, density_profile_s=prof['Flux::fluxDensity']['inclusive_s'],
                  optical_preparation_s=prof['PerformanceSimulationPrep']['inclusive_s'], profile=prof)
    if cuda:
        data = list(csv.reader(timing.read_text().splitlines())); assert len(data)==1
        h,c,prep,h2dh,h2dc,kernel,d2h,post,hybrid,total = map(float,data[0])
        result.update(heliostats=int(h),cells=int(c),preparation_s=prep,
                      h2d_heliostat_s=h2dh/1000,h2d_cell_s=h2dc/1000,h2d_total_s=(h2dh+h2dc)/1000,
                      kernel_s=kernel/1000,d2h_s=d2h/1000,postprocessing_s=post,
                      hybrid_density_s=hybrid,simulate_internal_s=total)
    return result


def summarize(samples):
    result={key:distribution([s[key] for s in samples]) for key,value in samples[0].items() if isinstance(value,float)}
    result['profile']={name:{kind:distribution([s['profile'][name][kind] for s in samples])
                             for kind in ('inclusive_s','exclusive_s')} for name in samples[0]['profile']}
    return result


def correctness(reference, actual):
    ref_flux,ref_metrics=reference; flux,metrics=actual
    result=errors(ref_flux,flux)
    result.update(peak_flux_difference_kw_m2=metrics['peak_flux_kw_m2']-ref_metrics['peak_flux_kw_m2'],
                  integrated_flux_difference_kw=metrics['integrated_incident_flux_kw']-ref_metrics['integrated_incident_flux_kw'],
                  receiver_power_difference_kw=metrics['receiver_power_kw']-ref_metrics['receiver_power_kw'])
    for key in ('peak_flux_kw_m2','integrated_incident_flux_kw','receiver_power_kw'):
        np.testing.assert_allclose(metrics[key],ref_metrics[key],rtol=1e-9,atol=1e-10)
    return result


def baseline(cp,size,grid,directory,window):
    result=dict(heliostats=SIZES[size],grid=[grid,grid],cells=grid*grid,
                transfer_bytes=dict(heliostat_h2d=200*SIZES[size],cell_h2d=48*grid*grid,
                                    total_h2d=200*SIZES[size]+48*grid*grid,output_d2h=8*grid*grid),backends={})
    reference=None
    for mode in ('legacy','flat','cuda'):
        context=context_for(cp,size,grid)
        try:
            cuda=mode=='cuda'; os.environ['SOLARPILOT_FLUX_PATH']='flat' if cuda else mode
            os.environ['SOLARPILOT_CUDA_BLOCK_SIZE']='256'
            selection=time.perf_counter();cp.set_compute_backend(context,'cuda' if cuda else 'cpu');selection=time.perf_counter()-selection
            first=simulate_once(cp,context,cuda,directory)
            warmups=3 if cuda else 2
            for _ in range(warmups):simulate_once(cp,context,cuda,directory)
            repeats=10 if cuda or not (SIZES[size]>=5000 and grid>=50) else 5
            samples=[simulate_once(cp,context,cuda,directory) for _ in range(repeats)]
            observed=collect(cp,context)
            if mode=='legacy':reference=observed
            if mode=='flat':
                assert np.array_equal(reference[0],observed[0]); reference=observed
                result['legacy_flat_bitwise']=True
            item=dict(block_size=256 if cuda else None,backend_selection_s=selection,first_call=first,
                      warmups_excluded=warmups,repetitions=repeats,samples=samples,statistics=summarize(samples),
                      physical_metrics=observed[1])
            if cuda:item['correctness']=correctness(reference,observed)
            result['backends'][mode]=item
            window.validate()
        finally:cp.data_free(context)
    return result


def sweep(cp,size,grid,directory,window):
    context=context_for(cp,size,grid)
    try:
        cp.set_compute_backend(context,'cpu');os.environ['SOLARPILOT_FLUX_PATH']='flat'
        simulate_once(cp,context,False,directory);reference=collect(cp,context)
        cp.set_compute_backend(context,'cuda')
        blocks=(64,128,256,512);runs={b:[] for b in blocks}
        for block in blocks:
            os.environ['SOLARPILOT_CUDA_BLOCK_SIZE']=str(block)
            for _ in range(3):simulate_once(cp,context,True,directory)
        for repeat in range(10):
            # Rotate execution order across rounds; one shared warmed context.
            order=blocks[repeat%4:]+blocks[:repeat%4]
            for block in order:
                os.environ['SOLARPILOT_CUDA_BLOCK_SIZE']=str(block)
                runs[block].append(simulate_once(cp,context,True,directory))
            window.validate()
        results=[]
        for block in blocks:
            os.environ['SOLARPILOT_CUDA_BLOCK_SIZE']=str(block)
            # Full same-state raw map and peak-cell contributions, excluded from timings.
            compare=directory/'compare.csv';compare.write_text('')
            with patch.dict(os.environ,{'SOLARPILOT_FLUX_PATH':'verify_cuda','SOLARPILOT_CUDA_TIMING_FILE':'',
                                       'SOLARPILOT_CUDA_COMPARE_FILE':str(compare),'SOLARPILOT_PROFILE_FILE':''}):
                assert cp.simulate(context,nthreads=1),cp.get_last_backend_error(context)
            actual=collect(cp,context);raw=dict(zip(COLUMNS,map(float,next(csv.reader(compare.read_text().splitlines())))))
            assert raw['block']==block
            previous=actual[0].copy()
            with patch.dict(os.environ,{'SOLARPILOT_FLUX_PATH':'flat','SOLARPILOT_CUDA_TIMING_FILE':'','SOLARPILOT_PROFILE_FILE':''}):
                assert cp.simulate(context,nthreads=1)
            assert np.array_equal(previous,collect(cp,context)[0])
            results.append(dict(heliostats=SIZES[size],grid=[grid,grid],block_size=block,warmups_excluded=3,
                                repetitions=10,samples=runs[block],statistics=summarize(runs[block]),
                                correctness=correctness(reference,actual),raw_correctness=raw,repeated_cuda_bitwise=True))
        return results
    finally:cp.data_free(context)


def final_case(cp,size,grid,directory,window):
    context=context_for(cp,size,grid)
    try:
        os.environ['SOLARPILOT_FLUX_PATH']='flat'
        os.environ.pop('SOLARPILOT_CUDA_BLOCK_SIZE',None)
        simulate_once(cp,context,False,directory);reference=collect(cp,context)
        cp.set_compute_backend(context,'cuda')
        first=simulate_once(cp,context,True,directory)
        for _ in range(3):simulate_once(cp,context,True,directory)
        samples=[simulate_once(cp,context,True,directory) for _ in range(10)]
        for _ in range(3):plain_call(cp,context)
        bare=[plain_call(cp,context) for _ in range(10)]
        actual=collect(cp,context)
        compare=directory/'final-compare.csv';compare.write_text('')
        with patch.dict(os.environ,{'SOLARPILOT_FLUX_PATH':'verify_cuda','SOLARPILOT_CUDA_TIMING_FILE':'',
                                   'SOLARPILOT_CUDA_COMPARE_FILE':str(compare),'SOLARPILOT_PROFILE_FILE':''}):
            assert cp.simulate(context,nthreads=1),cp.get_last_backend_error(context)
        raw=dict(zip(COLUMNS,map(float,next(csv.reader(compare.read_text().splitlines())))))
        assert raw['block']==256,'Final measurement must use the selected unchanged production default'
        window.validate()
        return dict(heliostats=SIZES[size],grid=[grid,grid],block_size=256,first_call=first,
                    warmups_excluded=3,repetitions=10,samples=samples,statistics=summarize(samples),
                    plain_samples_s=bare,plain_simulate_wall_s=distribution(bare),
                    correctness=correctness(reference,actual),raw_correctness=raw)
    finally:cp.data_free(context)


def plain_call(cp, context):
    # Instrumentation is disabled at runtime; compiled scope probes remain the
    # same for all backends. No event synchronization or per-call CSV writes.
    os.environ['SOLARPILOT_PROFILE_FILE']=''
    os.environ['SOLARPILOT_CUDA_TIMING_FILE']=''
    start=time.perf_counter()
    assert cp.simulate(context,nthreads=1),cp.get_last_backend_error(context)
    return time.perf_counter()-start


def plain(cp,size,grid,directory,window):
    result=dict(heliostats=SIZES[size],grid=[grid,grid],backends={},cuda_blocks=[])
    reference=None
    for mode in ('legacy','flat'):
        context=context_for(cp,size,grid)
        try:
            os.environ['SOLARPILOT_FLUX_PATH']=mode
            first=plain_call(cp,context)
            for _ in range(2):plain_call(cp,context)
            repeats=5 if SIZES[size]>=5000 and grid>=50 else 10
            samples=[plain_call(cp,context) for _ in range(repeats)]
            actual=collect(cp,context)
            if reference is not None:assert np.array_equal(reference[0],actual[0])
            reference=actual
            result['backends'][mode]=dict(first_call_s=first,warmups_excluded=2,repetitions=repeats,
                                          samples_s=samples,simulate_wall_s=distribution(samples))
            window.validate()
        finally:cp.data_free(context)
    context=context_for(cp,size,grid)
    try:
        os.environ['SOLARPILOT_FLUX_PATH']='flat'
        cp.set_compute_backend(context,'cuda')
        os.environ['SOLARPILOT_CUDA_BLOCK_SIZE']='256'
        first=plain_call(cp,context)
        result['cuda_v1_first_call_s']=first
        blocks=(64,128,256,512);runs={block:[] for block in blocks};observations={}
        for block in blocks:
            os.environ['SOLARPILOT_CUDA_BLOCK_SIZE']=str(block)
            for _ in range(3):plain_call(cp,context)
        for repeat in range(10):
            order=blocks[repeat%4:]+blocks[:repeat%4]
            for block in order:
                os.environ['SOLARPILOT_CUDA_BLOCK_SIZE']=str(block)
                runs[block].append(plain_call(cp,context))
                if repeat in (0,9):
                    observed=collect(cp,context)
                    if block in observations:assert np.array_equal(observations[block][0],observed[0])
                    observations[block]=observed
            window.validate()
        for block in blocks:
            result['cuda_blocks'].append(dict(block_size=block,warmups_excluded=3,repetitions=10,
                    samples_s=runs[block],simulate_wall_s=distribution(runs[block]),
                    correctness=correctness(reference,observations[block]),repeated_cuda_bitwise=True))
    finally:cp.data_free(context)
    return result


def allocation_growth(cp,directory):
    context=context_for(cp,'small',25);result=[]
    try:
        cp.set_compute_backend(context,'cuda')
        for grid in (25,25,50,50,100,100,50,25):
            for axis in ('x_res','y_res'):cp.data_set_number(context,'fluxsim.0.'+axis,grid)
            compare=directory/'allocations.csv';compare.write_text('')
            with patch.dict(os.environ,{'SOLARPILOT_FLUX_PATH':'verify_cuda','SOLARPILOT_CUDA_TIMING_FILE':'',
                                       'SOLARPILOT_CUDA_BLOCK_SIZE':'256','SOLARPILOT_CUDA_COMPARE_FILE':str(compare),'SOLARPILOT_PROFILE_FILE':''}):
                assert cp.simulate(context,nthreads=1)
            row=dict(zip(COLUMNS,map(float,next(csv.reader(compare.read_text().splitlines())))))
            result.append({k:int(row[k]) for k in ('nx','ny','allocations','h_capacity','cell_capacity','output_capacity')})
        assert [r['allocations'] for r in result]==[3,3,5,5,7,7,7,7]
        return result
    finally:cp.data_free(context)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('baseline','sweep','plain','final'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--sizes',nargs='+',choices=SIZES,default=list(SIZES))
    parser.add_argument('--grids',nargs='+',type=int,default=[25,50,100])
    args=parser.parse_args()
    if args.output.exists():raise RuntimeError('Refusing to overwrite an existing benchmark result')
    allowed=sorted(os.sched_getaffinity(0));benchmark_cpu,monitor_cpu=allowed[0],allowed[-1]
    if benchmark_cpu==monitor_cpu:raise RuntimeError('Two available CPUs required for independent telemetry monitoring')
    os.sched_setaffinity(0,{benchmark_cpu})
    cp=api();window=Window(monitor_cpu)
    result=dict(status='running_unvalidated',stage=args.stage,metadata=metadata(benchmark_cpu,monitor_cpu),cases=[])
    progress=ROOT/'artifacts/phase2c'/f'{args.stage}-progress.json';progress.parent.mkdir(parents=True,exist_ok=True)
    for key in ('SOLARPILOT_CUDA_TIMING_FILE','SOLARPILOT_FLUX_COMPARE_FILE','SOLARPILOT_CUDA_COMPARE_FILE','SOLARPILOT_PROFILE_FILE'):
        os.environ.pop(key,None)
    try:
        result['process_runtime_probe_s']=window.initialize(cp)
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            for size in args.sizes:
                for grid in args.grids:
                    window.validate()
                    runner={'baseline':baseline,'sweep':sweep,'plain':plain,'final':final_case}[args.stage]
                    item=runner(cp,size,grid,directory,window)
                    result['cases'].extend(item if isinstance(item,list) else [item])
                    progress.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
                    print(f'{args.stage}: completed {size} {grid}',flush=True)
            result['allocation_growth']=allocation_growth(cp,directory)
        window.close()
        result.update(status='valid',gpu_telemetry=window.samples)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        if args.output.exists():raise RuntimeError('Refusing to overwrite an existing benchmark result')
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    except Exception as error:
        window.stop.set()
        result.update(status='invalid',reason=str(error),gpu_telemetry=window.samples)
        progress.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        raise


if __name__=='__main__':main()
