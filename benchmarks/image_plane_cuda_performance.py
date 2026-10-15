#!/usr/bin/env python3
"""Controlled Phase 2D-C measurements, retaining the exact full-output v1 baseline."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
import os
import statistics
from pathlib import Path
import subprocess
import tempfile
import time
from unittest.mock import patch
import numpy as np
from cases import ROOT,SIZES,api
from cuda_flux_correctness import collect
from cuda_flux_performance import (Window,GPU_FIELDS,public_snapshot,
    metadata,context_for,simulate_once,correctness)


def distribution(values):
    mean=statistics.mean(values);sd=statistics.stdev(values) if len(values)>1 else 0.
    return {'median':statistics.median(values),'minimum':min(values),'maximum':max(values),
        'mean':mean,'stdev':sd,'coefficient_of_variation':sd/mean if mean else None}


def gpu_snapshot(environment=None):
    # Timed calls change diagnostic environment variables on the main thread.
    # Give exec an explicit stable environment instead of libc's mutable environ.
    environment=os.environ.copy() if environment is None else environment
    def query(*args):
        return subprocess.check_output(['nvidia-smi',*args],text=True,env=environment).strip()
    row=next(csv.reader([query('--query-gpu='+','.join(GPU_FIELDS),'--format=csv,noheader,nounits')]))
    result=dict(zip(GPU_FIELDS,(x.strip() for x in row)))
    result['utc']=datetime.now(timezone.utc).isoformat()
    result['_pids']=[int(x) for x in query('--query-compute-apps=pid','--format=csv,noheader,nounits').splitlines() if x.strip()]
    return result


class PipelineWindow(Window):
    def __init__(self,monitor_cpu):
        super().__init__(monitor_cpu);self.telemetry_env=os.environ.copy()
    def sample(self,initial=False):
        value=gpu_snapshot(self.telemetry_env)
        if set(value['_pids'])-self.allowed:
            raise RuntimeError('External GPU process invalidates this performance window')
        if float(value['memory.used'])>(128 if initial else 4096):
            raise RuntimeError('GPU memory exceeds the controlled pipeline window')
        if initial and float(value['utilization.gpu'])!=0:
            raise RuntimeError('GPU must be idle before pipeline measurement')
        if float(value['temperature.gpu'])>=80 or any(value[k]=='Active' for k in
                ['clocks_throttle_reasons.hw_thermal_slowdown','clocks_throttle_reasons.sw_thermal_slowdown']):
            raise RuntimeError('Thermal GPU window rejected')
        self.samples.append(public_snapshot(value));return value


def wait_idle():
    deadline=time.monotonic()+30;quiet=0
    while quiet<3:
        s=gpu_snapshot()
        if s['_pids']:raise RuntimeError('External GPU process before performance campaign')
        if float(s['memory.used'])<=128 and float(s['utilization.gpu'])==0 and float(s['temperature.gpu'])<80:
            quiet+=1
        else:quiet=0
        if time.monotonic()>deadline:raise RuntimeError('No stable idle GPU window')
        if quiet<3:time.sleep(.5)


def stats(samples):
    result={k:distribution([s[k] for s in samples]) for k,v in samples[0].items() if isinstance(v,float)}
    result['profile']={name:{kind:distribution([s['profile'][name][kind] for s in samples])
        for kind in ['inclusive_s','exclusive_s']} for name in samples[0]['profile']}
    return result


def call(cp,context,directory,cuda,image,instrumented):
    image_file=directory/'image.csv';image_file.write_text('')
    materialize_file=directory/'materialize.csv';materialize_file.write_text('')
    handoff_file=directory/'handoff.csv';handoff_file.write_text('')
    if not instrumented:
        with patch.dict(os.environ,{'SOLARPILOT_PROFILE_FILE':'','SOLARPILOT_CUDA_TIMING_FILE':'','SOLARPILOT_IMAGE_TIMING_FILE':'',
                                   'SOLARPILOT_IMAGE_MATERIALIZE_FILE':'','SOLARPILOT_IMAGE_HANDOFF_FILE':''}):
            start=time.perf_counter();assert cp.simulate(context,nthreads=1),cp.get_last_backend_error(context)
            return time.perf_counter()-start
    with patch.dict(os.environ,{'SOLARPILOT_IMAGE_TIMING_FILE':str(image_file) if image else '',
                               'SOLARPILOT_IMAGE_MATERIALIZE_FILE':str(materialize_file),
                               'SOLARPILOT_IMAGE_HANDOFF_FILE':str(handoff_file),
                               'SOLARPILOT_INTERCEPT_PROFILE':'1'}):
        sample=simulate_once(cp,context,cuda,directory)
    if image:
        rows=list(csv.reader(image_file.read_text().splitlines()));assert len(rows)==1
        h,prep,inp,tab,kernel,d2h,writeback,total=map(float,rows[0])
        sample.update(image_preparation_s=prep,image_input_h2d_s=inp/1000,image_tables_h2d_s=tab/1000,
            image_kernel_s=kernel/1000,image_d2h_s=d2h/1000,image_writeback_s=writeback,image_total_s=total)
        sample.update(image_initial_s=total,image_required_d2h_s=0.,image_complete_d2h_s=d2h/1000,
            image_materialize_s=0.,image_host_validation_s=None,image_validation_kernel_s=0.)
        if materialize_file.stat().st_size:
            rows=list(csv.reader(materialize_file.read_text().splitlines()));assert len(rows)==1
            values=list(map(float,rows[0]));mh,md2h,mwrite,mtotal,mbytes,host_validation,health,required_bytes,input_bytes,table_bytes=values[:10];assert mh==h
            sample.update(image_host_validation_s=host_validation,image_validation_kernel_s=health/1000)
            if len(values)>=12:sample.update(image_finite_output_scan_s=values[10],image_object_writeback_s=values[11])
            if mbytes:
                assert mbytes==1728*h and required_bytes==16*h
                sample.update(image_required_d2h_s=d2h/1000,image_complete_d2h_s=md2h/1000,
                    image_materialize_s=mtotal,image_d2h_s=(d2h+md2h)/1000,
                    image_writeback_s=writeback+mwrite,image_total_s=total+mtotal)
    if cuda and handoff_file.stat().st_size:
        rows=list(csv.reader(handoff_file.read_text().splitlines()));assert len(rows)==1
        h,resident,metadata_bytes,cell_bytes,handoff,allocations,hcap,ccap,ocap=map(float,rows[0])
        sample.update(resident_handoff=bool(resident),handoff_s=handoff/1000,
            density_heliostat_h2d_bytes=int(metadata_bytes),density_cell_h2d_bytes=int(cell_bytes),
            density_allocations=int(allocations),density_h_capacity=int(hcap),density_cell_capacity=int(ccap),density_output_capacity=int(ocap))
    return sample


def full_case(cp,size,grid,modes,directory,window):
    result={'heliostats':SIZES[size],'grid':[grid,grid],'pipelines':{}};reference=None
    for mode in modes:
        context=context_for(cp,size,grid)
        try:
            cuda=mode not in ['legacy','flat'];image=mode in ['v1','final']
            env={'SOLARPILOT_INTERCEPT_PATH':'legacy' if mode=='legacy' else ('cuda' if image else 'flat'),
                'SOLARPILOT_FLUX_PATH':'legacy' if mode=='legacy' else 'flat','SOLARPILOT_CUDA_BLOCK_SIZE':'256',
                'SOLARPILOT_IMAGE_PIPELINE':'v1' if mode=='v1' else 'resident',
                'SOLARPILOT_IMAGE_BLOCK_SIZE':'128' if mode=='v1' else '64',
                'SOLARPILOT_IMAGE_COMPARE_FILE':''}
            with patch.dict(os.environ,env):
                start=time.perf_counter();assert cp.set_compute_backend(context,'cuda' if cuda else 'cpu')
                selection=time.perf_counter()-start
                first=call(cp,context,directory,cuda,image,False)
                warmups=3 if cuda else 2;repeats=5 if not cuda and SIZES[size]>=5000 and grid>=50 else 10
                for _ in range(warmups):call(cp,context,directory,cuda,image,False)
                plain=[call(cp,context,directory,cuda,image,False) for _ in range(repeats)]
                samples=[call(cp,context,directory,cuda,image,True) for _ in range(repeats)]
                if mode=='final':assert all(s.get('resident_handoff') for s in samples)
                observed=collect(cp,context)
                if mode in ['legacy','flat']:
                    if reference is not None:assert np.array_equal(reference[0].view(np.uint64),observed[0].view(np.uint64))
                    reference=observed
                check=correctness(reference,observed) if reference is not None else None
                previous=observed[0].copy();call(cp,context,directory,cuda,image,False)
                assert np.array_equal(previous.view(np.uint64),collect(cp,context)[0].view(np.uint64))
            result['pipelines'][mode]={'backend_selection_s':selection,'first_call_s':first,'warmups_excluded':warmups,
                'repetitions':repeats,'plain_samples_s':plain,'plain_statistics':distribution(plain),
                'instrumented_samples':samples,'instrumented_statistics':stats(samples),'correctness':check,
                'repeated_map_bitwise':True,'physical_metrics':observed[1]}
            window.validate();print(size,grid,mode,'PASS',flush=True)
        finally:assert cp.data_free(context)
    return result


def sweep(args,result,cpus):
    result['resources']=[];feasible=[]
    for block in [64,128,256,512]:
        wait_idle();env={**os.environ,'SOLARPILOT_IMAGE_BLOCK_SIZE':str(block)}
        row=json.loads(subprocess.check_output([str(args.resource_binary.resolve())],env=env,text=True))
        result['resources'].append(row)
        if not row['launch_feasible']:continue
        feasible.append(block)
        for h in [1000,5000,10000]:
            wait_idle()
            row=json.loads(subprocess.check_output([str(args.direct_binary.resolve()),str(h),'10','timing','3'],
                env={**env,'SOLARPILOT_INTERCEPT_PATH':'flat'},text=True))
            assert row['errors']['global']['passed'] and row['block_size']==block
            row['cuda_statistics']={k:distribution([s[k]/1000 if k.endswith('_ms') else s[k] for s in row['cuda_samples']]) for k in row['cuda_samples'][0]}
            result['direct'].append(row)
    wait_idle();cp=api();window=PipelineWindow(cpus[-1]);result['runtime_probe_s']=window.initialize(cp)
    try:
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            for size in SIZES:
                for grid in [25,50,100]:
                    context=context_for(cp,size,grid)
                    try:
                        env={'SOLARPILOT_INTERCEPT_PATH':'flat','SOLARPILOT_FLUX_PATH':'flat','SOLARPILOT_CUDA_BLOCK_SIZE':'256',
                            'SOLARPILOT_IMAGE_PIPELINE':'v1','SOLARPILOT_IMAGE_COMPARE_FILE':''}
                        with patch.dict(os.environ,env):
                            call(cp,context,directory,False,False,False);reference=collect(cp,context)
                            cp.set_compute_backend(context,'cuda');os.environ['SOLARPILOT_INTERCEPT_PATH']='cuda'
                            runs={b:{'plain':[],'instrumented':[]} for b in feasible};observed={}
                            for instrumented in [False,True]:
                                for b in feasible:
                                    os.environ['SOLARPILOT_IMAGE_BLOCK_SIZE']=str(b)
                                    for _ in range(3):call(cp,context,directory,True,True,instrumented)
                                for repeat in range(10):
                                    order=feasible[repeat%len(feasible):]+feasible[:repeat%len(feasible)]
                                    for b in order:
                                        os.environ['SOLARPILOT_IMAGE_BLOCK_SIZE']=str(b)
                                        sample=call(cp,context,directory,True,True,instrumented)
                                        runs[b]['instrumented' if instrumented else 'plain'].append(sample)
                                        if repeat in [0,9]:
                                            actual=collect(cp,context)
                                            if b in observed:assert np.array_equal(observed[b][0].view(np.uint64),actual[0].view(np.uint64))
                                            observed[b]=actual
                                    window.validate()
                        row={'heliostats':SIZES[size],'grid':[grid,grid],'blocks':[]}
                        for b in feasible:
                            r=runs[b]
                            row['blocks'].append({'block_size':b,'warmups_excluded_per_group':3,'repetitions':10,
                                'plain_samples_s':r['plain'],'plain_statistics':distribution(r['plain']),
                                'instrumented_samples':r['instrumented'],'instrumented_statistics':stats(r['instrumented']),
                                'correctness':correctness(reference,observed[b]),'repeated_map_bitwise':True})
                        result['cases'].append(row);print('sweep',size,grid,'PASS',flush=True)
                    finally:assert cp.data_free(context)
        window.close();result.update(status='valid',gpu_telemetry=window.samples)
    finally:window.stop.set()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['v1','sweep','final'],required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--direct-binary',type=Path,default=Path('build/cuda/image_plane_cuda_benchmark'))
    p.add_argument('--resource-binary',type=Path,default=Path('build/cuda/cuda_image_plane_resources'))
    p.add_argument('--skip-direct',action='store_true');args=p.parse_args()
    if args.output.exists():raise RuntimeError('Refusing to overwrite benchmark evidence')
    cpus=sorted(os.sched_getaffinity(0));assert len(cpus)>1;os.sched_setaffinity(0,{cpus[0]})
    for k in list(os.environ):
        if k.startswith('SOLARPILOT_'):os.environ.pop(k)
    result={'status':'running_unvalidated','stage':args.stage,'metadata':metadata(cpus[0],cpus[-1]),'direct':[],'cases':[]}
    result['metadata'].update(phase='2D-C',image_kernel_sha256=hashlib.sha256((ROOT/'ssc/solarpilot/ImagePlaneInterceptKernels.cu').read_bytes()).hexdigest(),
        baseline_label={'v1':'CUDA imagePlane v1 / Phase 2D-B baseline','sweep':'Bounded image-plane block experiment','final':'Phase 2D-C selected final pipeline'}[args.stage],
        monitoring='Stable idle preflight; exact owned GPU process; <=4096 MiB after context creation; <80 C and no thermal slowdown; no concurrent server jobs.')
    window=None
    try:
        if args.stage=='sweep':
            sweep(args,result,cpus)
            args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');return
        if not args.skip_direct:
            for h in [1000,5000,10000]:
                wait_idle()
                command=[str(args.direct_binary.resolve()),str(h),'10','timing','3']
                if args.stage=='final':command.append('resident')
                raw=subprocess.check_output(command,text=True,
                    env={**os.environ,'SOLARPILOT_INTERCEPT_PATH':'flat','SOLARPILOT_IMAGE_PIPELINE':'resident' if args.stage=='final' else 'v1'})
                row=json.loads(raw);assert row['errors']['global']['passed']
                row['cpu_flat_statistics']=distribution(row['cpu_flat_total_samples_s'])
                row['cuda_statistics']={k:distribution([s[k]/1000 if k.endswith('_ms') else s[k] for s in row['cuda_samples']]) for k in row['cuda_samples'][0]}
                result['direct'].append(row);print('direct',h,'PASS',flush=True)
        wait_idle();cp=api();window=PipelineWindow(cpus[-1]);result['runtime_probe_s']=window.initialize(cp)
        modes=['legacy','flat','density_only','v1'] if args.stage=='v1' else ['legacy','flat','density_only','v1','final']
        with tempfile.TemporaryDirectory() as temp:
            for size in SIZES:
                for grid in [25,50,100]:
                    window.validate();result['cases'].append(full_case(cp,size,grid,modes,Path(temp),window))
        window.close();result.update(status='valid',gpu_telemetry=window.samples)
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    except Exception as e:
        if window:window.stop.set()
        result.update(status='invalid',reason=str(e),gpu_telemetry=window.samples if window else [])
        fail=ROOT/'artifacts/phase2dc/invalid-campaign.json';fail.parent.mkdir(parents=True,exist_ok=True)
        fail.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');raise


if __name__=='__main__':main()
