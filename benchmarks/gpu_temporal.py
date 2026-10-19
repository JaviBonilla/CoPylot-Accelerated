#!/usr/bin/env python3
"""Direct full-output GPU temporal campaigns; raw private evidence stays on server."""
import argparse
import ctypes
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import time
import numpy as np
import temporal_campaign as temporal
from temporal_campaign import ROOT,CONTRACT,write,digest,require,set_state,payload,signature
from image_plane_cuda_performance import PipelineWindow,wait_idle
from cpu_multicore import cpu_window,frequency

STAGE_FIELDS=('preparation_inclusive_s','image_input_preparation_s','image_host_validation_s',
 'image_input_h2d_s','image_tables_h2d_s','image_kernel_s','image_health_s','image_full_d2h_s',
 'image_host_writeback_s','density_preparation_s','density_metadata_h2d_s','density_cells_h2d_s',
 'density_handoff_s','density_kernel_s','map_d2h_s','density_postprocess_s','api_s',
 'image_input_h2d_bytes','image_tables_h2d_bytes','density_metadata_h2d_bytes','density_cells_h2d_bytes',
 'image_full_d2h_bytes','density_allocations','image_allocations','temporal_input_update_s')
OUT=ROOT/'artifacts/phase5b'
REFERENCE=Path(os.environ.get('COPILOT_PHASE5A_REFERENCE','/phase5a-reference'))


def compare(expected,actual,bitwise=False):
    require(set(expected)==set(actual),'Observable schema differs')
    maximum=0.
    for key,a in actual.items():
        e=expected[key]
        require(a.dtype==e.dtype and a.shape==e.shape,'Observable dtype/shape differs')
        if bitwise or a.dtype.kind not in 'fiu':
            require(a.tobytes()==e.tobytes(),'Direct CUDA observable bytes differ: '+key)
        else:
            require(np.isfinite(a).all() and np.isfinite(e).all(),'Nonfinite observable')
            require(np.all(np.abs(a-e)<=1e-10+1e-9*np.abs(e)),'Existing CPU/CUDA tolerance exceeded: '+key)
            maximum=max(maximum,float(np.max(np.abs(a-e),initial=0.)))
    return maximum


def cpu_reference(case,point):
    p=REFERENCE/'artifacts/phase5a'
    fresh=p/'correctness'/case/(str(point['id'])+'.npz')
    if fresh.exists():return fresh
    if case=='commercial':return p/'campaigns/Y2-commercial-24x1'/(str(point['id'])+'.npz')
    raise RuntimeError('Missing established CPU observation')


def configure_environment():
    for key in list(os.environ):
        if key.startswith('SOLARPILOT_'):os.environ.pop(key)
    os.environ.update({**temporal.PLAIN,'SOLARPILOT_INTERCEPT_PATH':'cuda'})
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
        require(os.environ.get(key)=='1','Set numerical pools to one before Python')


def stats(v):
    return {'count':len(v),'median':float(np.median(v)),'p95':float(np.percentile(v,95)),
            'p99':float(np.percentile(v,99)),'min':min(v),'max':max(v),'sum':sum(v)}


def open_context(cp,case,mode):
    r,grid=temporal.context(cp,case)
    try:
        require(cp.set_compute_backend(r,'cuda'),cp.get_last_backend_error(r))
        if mode!='sequential':
            f=cp.pdll.sp_set_temporal_residency;f.argtypes=[ctypes.c_void_p,ctypes.c_bool];f.restype=ctypes.c_bool
            require(f(r,True),cp.get_last_backend_error(r))
        return r,grid
    except BaseException:cp.data_free(r);raise


def campaign(args):
    configure_environment();cpus=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpus[0]})
    require(args.batch_size>=1 and args.batch_size<=32,'Bound batch size to 1..32')
    require(args.mode=='batch' or args.batch_size==1,'Sequential/resident mode is one state at a time')
    require(not args.no_residency or args.mode=='batch','No-residency is an explicit batch control')
    directory=OUT/'runs'/args.id;directory.mkdir(parents=True,exist_ok=False)
    library=Path(os.environ['COPILOT_LIB_DIR'])/'solarpilot.so'
    require(digest(library)==args.library_sha256,'Numerical binary identity differs')
    temporal.LIB_SHA=args.library_sha256
    plan=json.loads((ROOT/'artifacts/phase5a'/(args.case+'-plan.json')).read_text())
    points=plan[args.series]
    write(directory/'plan.json',{'case':args.case,'points':points,'grid':plan['grid'],'output_contract':CONTRACT})
    wait_idle();cp=temporal.api();window=PipelineWindow(cpus[-1]);probe=window.initialize(cp)
    contexts=[];rows=[];total_start=time.perf_counter();sim_walls=[];batch_walls=[];setup_rows=[];jsonl_costs=[]
    freq_before=frequency();before=None
    try:
        for _ in range(min(args.batch_size,len(points))):
            begin=time.perf_counter();r,grid=open_context(cp,args.case,'sequential' if args.no_residency else args.mode);contexts.append(r);setup_rows.append(time.perf_counter()-begin)
            if args.instrumented:
                f=cp.pdll.sp_set_temporal_timing;f.argtypes=[ctypes.c_void_p,ctypes.c_bool];f.restype=ctypes.c_bool
                require(f(r,True),'Cannot enable separate stage diagnostics')
        setup_end=time.perf_counter()
        # All contexts use the one process's verified CUDA primary context.
        mapped_library=temporal.loaded_library()
        if args.mode=='batch':
            os.sched_setaffinity(0,set(cpus))
            batch=cp.pdll.sp_simulate_batch;batch.argtypes=[ctypes.POINTER(ctypes.c_void_p),ctypes.c_int,ctypes.c_int];batch.restype=ctypes.c_bool
        before=cpu_window();usage_before=resource.getrusage(resource.RUSAGE_SELF);eval_start=time.perf_counter()
        with (directory/'states.jsonl').open('x') as log:
            for first in range(0,len(points),args.batch_size):
                selected=points[first:first+args.batch_size];batch_start=time.perf_counter()
                for r,p in zip(contexts,selected):set_state(cp,r,p)
                begin=time.perf_counter()
                if args.mode=='batch':
                    handles=(ctypes.c_void_p*len(selected))(*contexts[:len(selected)])
                    require(batch(handles,len(selected),min(24,len(selected))), 'Temporal batch failed: '+'; '.join(cp.get_last_backend_error(r) for r in contexts[:len(selected)]))
                else:require(cp.simulate(contexts[0],nthreads=1),cp.get_last_backend_error(contexts[0]))
                sim_elapsed=time.perf_counter()-begin;sim_walls.append(sim_elapsed)
                for slot,(r,point) in enumerate(zip(contexts,selected)):
                    begin=time.perf_counter();values,metrics=payload(cp,r,point,grid);sig=signature(values)
                    materialize=time.perf_counter()-begin
                    begin=time.perf_counter();file=directory/(str(point['id'])+'.npz');np.savez(file,**values)
                    write_elapsed=time.perf_counter()-begin
                    stages=None
                    if args.instrumented:
                        f=cp.pdll.sp_get_temporal_statistics;f.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_double),ctypes.c_int];f.restype=ctypes.c_bool
                        measured=(ctypes.c_double*len(STAGE_FIELDS))();require(f(r,measured,len(measured)),'Missing stage diagnostics')
                        stages=dict(zip(STAGE_FIELDS,measured))
                    row={'stages':stages,'id':point['id'],'state':point,'signature':sig,'metrics':metrics,'slot':slot,
                         'simulate_batch_s':sim_elapsed,'materialize_analysis_s':materialize,'npz_serialize_write_s':write_elapsed,
                         'state_batch_completion_latency_s':time.perf_counter()-batch_start,'output_bytes':file.stat().st_size}
                    write_begin=time.perf_counter();log.write(json.dumps(row,allow_nan=False)+'\n');log.flush();jsonl_costs.append(time.perf_counter()-write_begin);rows.append(row)
                batch_walls.append(time.perf_counter()-batch_start)
                if len(rows)%96==0 or len(rows)==len(points):print(args.id,'completed',len(rows),'/',len(points),flush=True)
                if window.failure:raise RuntimeError(window.failure)
        evaluation_end=time.perf_counter();usage_after=resource.getrusage(resource.RUSAGE_SELF);after=cpu_window()
        window.sample() # Observe live persistent allocations before freeing them.
        for r in contexts:require(cp.data_free(r),'Context teardown failed')
        contexts=[];total_end=time.perf_counter();window.close();freq_after=frequency()
        own=(usage_after.ru_utime+usage_after.ru_stime)-(usage_before.ru_utime+usage_before.ru_stime)
        elapsed=after['wall']-before['wall'];system=(after['busy_ticks']-before['busy_ticks'])/os.sysconf('SC_CLK_TCK')
        thermal=any(after['throttle'].get(k,v)>v for k,v in before['throttle'].items())
        accepted=(system-own)/elapsed<.5 and not thermal and temporal.frequency_policy(freq_before)==temporal.frequency_policy(freq_after)
        require(sorted(p['id'] for p in points)==sorted(r['id'] for r in rows),'Incomplete/duplicate states')
        require(digest(library)==args.library_sha256,'Library changed during campaign')
        result={'phase':'5B','status':'passed','identifier':args.id,'case':args.case,'series':args.series,
                'mode':args.mode,'static_residency_enabled':args.mode!='sequential' and not args.no_residency,'instrumented':args.instrumented,'batch_size':args.batch_size,'active_states':min(args.batch_size,24),'state_slots':min(args.batch_size,len(points)),
                'maximum_cpu_preparations':min(args.batch_size,len(points),24),
                'gpu_execution':'Existing default-stream kernels; no fused multi-state kernel or streams',
                'completed':len(rows),'control_grid':[grid['nx'],grid['ny']],'contract':CONTRACT,
                'runtime_probe_s':probe,'context_setup_s':setup_rows,'setup_wall_s':setup_end-total_start,
                'evaluation_wall_s':evaluation_end-eval_start,'total_wall_s':total_end-total_start,
                'states_per_s':len(rows)/(evaluation_end-eval_start),'total_states_per_s':len(rows)/(total_end-total_start),
                'simulate_batch_wall_s':stats(sim_walls),'batch_complete_wall_s':stats(batch_walls),
                'simulation_only_states_per_s':len(rows)/sum(sim_walls),
                'materialize_analysis_s':sum(r['materialize_analysis_s'] for r in rows),
                'npz_serialize_write_s':sum(r['npz_serialize_write_s'] for r in rows),'jsonl_serialize_flush_s':sum(jsonl_costs),
                'serialize_write_s':sum(r['npz_serialize_write_s'] for r in rows)+sum(jsonl_costs),'output_cost_includes_jsonl_flush':True,
                'output_bytes':sum(r['output_bytes'] for r in rows),'first_batch_wall_s':batch_walls[0],
                'first_simulate_batch_s':sim_walls[0],'first_call_included':True,'warmups_excluded':0,
                'state_batch_completion_latency_s':stats([r['state_batch_completion_latency_s'] for r in rows]),
                'cpu_window':{'accepted':accepted,'average_owned_cores':own/elapsed,'external_average_cores':max(0.,(system-own)/elapsed),
                              'thermal_throttle_increased':thermal,'frequency_policy_unchanged':temporal.frequency_policy(freq_before)==temporal.frequency_policy(freq_after)},
                'gpu_telemetry':window.samples,'peak_device_used_mib_sampled':max(float(r['memory.used']) for r in window.samples),
                'gpu_utilization_percent_sampled_mean':statistics.mean(float(r['utilization.gpu']) for r in window.samples),
                'loaded_library':mapped_library,'cpu_affinity':sorted(os.sched_getaffinity(0)),'library_sha256':args.library_sha256,'harness_sha256':digest(__file__),
                'commits':{k:subprocess.check_output(['git','-C',str(ROOT/k),'rev-parse','HEAD'],text=True).strip() for k in ('.','ssc','SolarPILOT','SolTrace')},
                'utc':datetime.now(timezone.utc).isoformat(),'validation_outside_timing':True}
        write(directory/'result.json',result)
        print(args.id,'states/s',result['states_per_s'],'total wall',result['total_wall_s'],'clean',accepted,flush=True)
    finally:
        for r in contexts:cp.data_free(r)
        window.stop.set()
        if hasattr(window,'thread'):window.thread.join()


def verify_run(args):
    directory=OUT/'runs'/args.id;result=json.loads((directory/'result.json').read_text())
    rows=[json.loads(s) for s in (directory/'states.jsonl').read_text().splitlines()]
    require(len(rows)==result['completed'],'Incomplete trace')
    maximum=0.;direct=0;total=0
    for row in rows:
        file=directory/(str(row['id'])+'.npz')
        with np.load(file,allow_pickle=False) as src:actual={k:src[k] for k in src.files}
        require(signature(actual)==row['signature'],'Stored bytes differ from runtime')
        reference=cpu_reference(result['case'],row['state'])
        with np.load(reference,allow_pickle=False) as src:maximum=max(maximum,compare({k:src[k] for k in src.files},actual))
        if args.direct_reference:
            with np.load(OUT/'runs'/args.direct_reference/(str(row['id'])+'.npz'),allow_pickle=False) as src:
                compare({k:src[k] for k in src.files},actual,bitwise=True);direct+=1
        total+=file.stat().st_size
    require(total==result['output_bytes'],'Stored size differs')
    validation={'passed':True,'persisted_payloads_verified':len(rows),'cpu_agreement_existing_tolerance':True,
                'maximum_absolute_observable_error':maximum,'direct_cuda_bitwise_states':direct,
                'stored_bytes':total,'timing_excludes_verification':True}
    write(directory/'validation.json',validation);print(args.id,'persisted / CPU / direct CUDA checks passed:',len(rows),direct,flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('campaign');a.add_argument('--case',choices=['cesa','commercial'],required=True)
    a.add_argument('--series',choices=['seasonal','long','states'],default='seasonal')
    a.add_argument('--mode',choices=['sequential','resident','batch'],default='sequential');a.add_argument('--batch-size',type=int,default=1)
    a.add_argument('--no-residency',action='store_true',help='Batch control with ordinary static uploads');a.add_argument('--instrumented',action='store_true',help='Separate CUDA-event diagnostics, excluded from plain timing groups');a.add_argument('--library-sha256',required=True);a.add_argument('--id',required=True)
    a=sub.add_parser('verify');a.add_argument('--id',required=True);a.add_argument('--direct-reference')
    args=p.parse_args()
    require(bool(args.id) and all(c.isalnum() or c in '-_' for c in args.id),'Invalid campaign ID')
    if args.command=='campaign':campaign(args)
    else:verify_run(args)


if __name__=='__main__':main()
