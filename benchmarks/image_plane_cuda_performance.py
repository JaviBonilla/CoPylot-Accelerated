#!/usr/bin/env python3
"""Controlled Phase 2D-C measurements, retaining the exact full-output v1 baseline."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from unittest.mock import patch
import numpy as np
from cases import ROOT,SIZES,api
from cuda_flux_correctness import collect
from cuda_flux_performance import (Window,gpu_snapshot,public_snapshot,distribution,
    metadata,context_for,simulate_once,correctness)


class PipelineWindow(Window):
    def sample(self,initial=False):
        value=gpu_snapshot()
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
    if not instrumented:
        with patch.dict(os.environ,{'SOLARPILOT_PROFILE_FILE':'','SOLARPILOT_CUDA_TIMING_FILE':'','SOLARPILOT_IMAGE_TIMING_FILE':''}):
            start=time.perf_counter();assert cp.simulate(context,nthreads=1),cp.get_last_backend_error(context)
            return time.perf_counter()-start
    with patch.dict(os.environ,{'SOLARPILOT_IMAGE_TIMING_FILE':str(image_file) if image else ''}):
        sample=simulate_once(cp,context,cuda,directory)
    if image:
        rows=list(csv.reader(image_file.read_text().splitlines()));assert len(rows)==1
        h,prep,inp,tab,kernel,d2h,writeback,total=map(float,rows[0])
        sample.update(image_preparation_s=prep,image_input_h2d_s=inp/1000,image_tables_h2d_s=tab/1000,
            image_kernel_s=kernel/1000,image_d2h_s=d2h/1000,image_writeback_s=writeback,image_total_s=total)
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
                'SOLARPILOT_IMAGE_COMPARE_FILE':'','SOLARPILOT_INTERCEPT_PROFILE':'1'}
            with patch.dict(os.environ,env):
                start=time.perf_counter();assert cp.set_compute_backend(context,'cuda' if cuda else 'cpu')
                selection=time.perf_counter()-start
                first=call(cp,context,directory,cuda,image,False)
                warmups=3 if cuda else 2;repeats=5 if not cuda and SIZES[size]>=5000 and grid>=50 else 10
                for _ in range(warmups):call(cp,context,directory,cuda,image,False)
                plain=[call(cp,context,directory,cuda,image,False) for _ in range(repeats)]
                samples=[call(cp,context,directory,cuda,image,True) for _ in range(repeats)]
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


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['v1','final'],required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--direct-binary',type=Path,default=Path('build/cuda/image_plane_cuda_benchmark'))
    p.add_argument('--skip-direct',action='store_true');args=p.parse_args()
    if args.output.exists():raise RuntimeError('Refusing to overwrite benchmark evidence')
    cpus=sorted(os.sched_getaffinity(0));assert len(cpus)>1;os.sched_setaffinity(0,{cpus[0]})
    for k in list(os.environ):
        if k.startswith('SOLARPILOT_'):os.environ.pop(k)
    result={'status':'running_unvalidated','stage':args.stage,'metadata':metadata(cpus[0],cpus[-1]),'direct':[],'cases':[]}
    result['metadata'].update(phase='2D-C',image_kernel_sha256=hashlib.sha256((ROOT/'ssc/solarpilot/ImagePlaneInterceptKernels.cu').read_bytes()).hexdigest(),
        baseline_label='CUDA imagePlane v1 / Phase 2D-B baseline' if args.stage=='v1' else 'Phase 2D-C selected final pipeline',
        monitoring='Stable idle preflight; exact owned GPU process; <=4096 MiB after context creation; <80 C and no thermal slowdown; no concurrent server jobs.')
    window=None
    try:
        if not args.skip_direct:
            for h in [1000,5000,10000]:
                wait_idle()
                raw=subprocess.check_output([str(args.direct_binary.resolve()),str(h),'10','timing','3'],text=True,
                    env={**os.environ,'SOLARPILOT_INTERCEPT_PATH':'flat'})
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
