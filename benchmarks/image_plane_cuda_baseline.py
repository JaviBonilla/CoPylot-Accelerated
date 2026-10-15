#!/usr/bin/env python3
"""Optional guarded Phase 2D-B preliminary baseline; no tuning or final speedups."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from image_plane import statistics_s
from cuda_flux_correctness import metadata
from cuda_flux_performance import gpu_snapshot,check_gpu


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,default=Path('build/cuda/image_plane_cuda_benchmark'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timing',action='store_true')
    parser.add_argument('--cpu',type=int,default=0)
    args=parser.parse_args()
    os.sched_setaffinity(0,{args.cpu})
    env=os.environ.copy()
    for key in ['SOLARPILOT_IMAGE_TIMING_FILE','SOLARPILOT_IMAGE_COMPARE_FILE','SOLARPILOT_CUDA_TIMING_FILE',
                'SOLARPILOT_PROFILE_FILE','SOLARPILOT_INTERCEPT_PROFILE','COPILOT_GPU_TIMING_ALLOWED']:
        env.pop(key,None)
    env['SOLARPILOT_INTERCEPT_PATH']='flat'
    info=metadata();info['execution_hostname']='pinned-cuda-container';info['hostname']='canonical-gpu-server'
    info.update({'phase':'2D-B preliminary baseline','formal_performance_campaign':False,
        'image_plane_block_size':128,'cpu_affinity':[args.cpu],'warmups':2,'repetitions':5,
        'gpu_timings_collected':args.timing,'timing_guard':'Native idle check before context creation, exact owned process set and thermal/memory checks outside each sample',
        'fma_enabled':True,'fast_math':False,'image_plane_source_options':['--fmad=true','--ptxas-options=-v']})
    result={'metadata':info,'status':'running','cases':[]}
    for count in [1000,5000,10000]:
        command=[str(args.binary.resolve()),str(count),'5','timing' if args.timing else 'correctness']
        if args.timing:
            # Previous child teardown can precede the utilization counter's return to zero.
            deadline=time.monotonic()+30.
            while True:
                quiet=gpu_snapshot()
                try:
                    check_gpu(quiet,initial=True)
                    if float(quiet['temperature.gpu'])>=80.: raise RuntimeError('GPU above preliminary temperature limit')
                    break
                except RuntimeError:
                    if time.monotonic()>=deadline: raise RuntimeError('No idle window before the next preliminary case')
                    time.sleep(0.5)
        completed=subprocess.run(command,env=env,text=True,capture_output=True)
        if completed.returncode:
            result['status']='aborted'
            result['failed_heliostat_count']=count
            result['failure']=completed.stderr.strip()
            args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
            raise RuntimeError('Preliminary child failed: '+completed.stderr.strip())
        row=json.loads(completed.stdout)
        assert row['errors']['global']['passed'] and row['errors']['global']['count']==215*count
        assert row['deterministic'] and row['allocation_reuse']
        if args.timing:
            assert row['gpu_window']['checks']>=2*5+2
            row['cpu_flat_total']=statistics_s(row['cpu_flat_total_samples_s'])
            row['cuda_summary']={key:statistics_s([sample[key]/1000 if key.endswith('_ms') else sample[key] for sample in row['cuda_samples']])
                for key in row['cuda_samples'][0]}
        result['cases'].append(row)
        if len(result['cases'])==3: result['status']='complete'
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        print(count,'PASS; preliminary timing' if args.timing else 'PASS; correctness only',flush=True)
if __name__=='__main__': main()
