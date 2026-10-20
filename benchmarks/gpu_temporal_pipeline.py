#!/usr/bin/env python3
"""Bounded rolling ordinary-CUDA contexts; complete outputs, no batch barrier."""
import argparse,json,os,queue,resource,subprocess,threading,time,traceback
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import gpu_temporal as g
import temporal_campaign as t
from check_gpu_temporal import optical_capture


def union_duration(intervals):
    total=0.;end=None
    for begin,finish in sorted(intervals):
        if end is None or begin>end:total+=finish-begin;end=finish
        elif finish>end:total+=finish-end;end=finish
    return total


def instances(case,count,resident):
    # api() temporarily changes cwd; do not construct wrappers concurrently.
    result=[]
    try:
        for _ in range(count):
            cp=t.api();r,grid=g.open_context(cp,case,'resident' if resident else 'sequential');result.append((cp,r,grid))
        return result
    except BaseException:
        for cp,r,_ in result:cp.data_free(r)
        raise


def check(args):
    g.configure_environment();cpus=sorted(os.sched_getaffinity(0));t.require(1<=args.workers<=min(24,len(cpus)),'Invalid CPU budget')
    library=Path(os.environ['COPILOT_LIB_DIR'])/'solarpilot.so';t.require(args.library_sha256 and t.digest(library)==args.library_sha256,'Explicit exact library required')
    plan=json.loads((t.OUT/(args.case+'-plan.json')).read_text());points=plan['diagnostic'];positive=[p for p in points if not p.get('probe')]
    high=max(positive,key=lambda p:p['sun'][1]);low=min(positive,key=lambda p:p['sun'][1]);moderate=min(positive,key=lambda p:abs(p['sun'][1]-30.))
    seq=[high,moderate,low,high,points[-1],high,low,moderate,high]
    t.LIB_SHA=args.library_sha256
    pool=instances(args.case,args.workers,args.residency);mapped=t.loaded_library();errors=queue.Queue();counts=[];threads=[]
    def run(slot,owned):
        cp,r,grid=owned
        try:
            os.sched_setaffinity(0,{cpus[slot]});capture=optical_capture()
            for point in seq:
                t.set_state(cp,r,point);t.require(cp.simulate(r,nthreads=1),cp.get_last_backend_error(r));values,_=t.payload(cp,r,point,grid);values['optical']=capture(r)
                with np.load(g.OUT/'correctness'/args.case/(str(point['id'])+'.npz'),allow_pickle=False) as ref:g.compare({k:ref[k] for k in ref.files},values,bitwise=True)
            counts.append(len(seq))
        except BaseException:errors.put(traceback.format_exc())
    try:
        for i,owned in enumerate(pool):
            th=threading.Thread(target=run,args=(i,owned));threads.append(th);th.start()
        for th in threads:th.join()
        t.require(errors.empty(),'Rolling full-state check failed: '+('' if errors.empty() else errors.get()))
        value={'case':args.case,'mode':'pipeline','workers':args.workers,'static_residency_enabled':args.residency,
               'loaded_library':mapped,'library_sha256':t.digest(library),'harness_sha256':t.digest(__file__),'checked':sum(counts),'all215_and_full_outputs_bitwise_direct_cuda':True,
               'every_context_reused_across_high_moderate_low_zero_and_repeated_states':True}
        file=g.OUT/'correctness'/args.case/('pipeline-'+args.library_sha256[:12]+'-'+str(args.workers)+'-'+str(int(args.residency))+'.json')
        t.require(not file.exists(),'Refuse correctness overwrite');t.write(file,value);print('Rolling correctness',args.case,args.workers,sum(counts),'bitwise checks passed',flush=True)
    finally:
        for th in threads:th.join()
        for cp,r,_ in pool:cp.data_free(r)


def campaign(args):
    g.configure_environment();cpus=sorted(os.sched_getaffinity(0));t.require(1<=args.workers<=min(24,len(cpus)),'Invalid CPU budget')
    directory=g.OUT/'runs'/args.id;directory.mkdir(parents=True,exist_ok=False)
    library=Path(os.environ['COPILOT_LIB_DIR'])/'solarpilot.so';t.require(t.digest(library)==args.library_sha256,'Wrong exact numerical library');t.LIB_SHA=args.library_sha256
    plan=json.loads((t.OUT/(args.case+'-plan.json')).read_text());points=plan[args.series]
    t.write(directory/'plan.json',{'case':args.case,'points':points,'grid':plan['grid'],'output_contract':t.CONTRACT})
    os.sched_setaffinity(0,{cpus[0]});g.wait_idle();probe_cp=t.api();window=g.PipelineWindow(cpus[-1]);probe=window.initialize(probe_cp)
    pool=[];threads=[];rows=[];errors=queue.Queue();cancel=threading.Event();start=threading.Event();jobs=queue.Queue(maxsize=2*args.workers)
    overall=time.perf_counter();setup_costs=[];before=None
    def worker(slot,owned):
        cp,r,grid=owned
        try:
            os.sched_setaffinity(0,{cpus[slot]});start.wait()
            call_index=0
            with (directory/('worker-'+str(slot)+'.jsonl')).open('x') as log:
                while not cancel.is_set():
                    try:point=jobs.get(timeout=.2)
                    except queue.Empty:continue
                    if point is None:break
                    begin=time.perf_counter();t.set_state(cp,r,point);sim=time.perf_counter();t.require(cp.simulate(r,nthreads=1),cp.get_last_backend_error(r));simulate=time.perf_counter()-sim
                    materialize=time.perf_counter();values,metrics=t.payload(cp,r,point,grid);sig=t.signature(values);materialize=time.perf_counter()-materialize
                    write_begin=time.perf_counter();file=directory/(str(point['id'])+'.npz');np.savez(file,**values);write_cost=time.perf_counter()-write_begin
                    row={'simulate_begin':sim,'simulate_end':sim+simulate,'worker_call_index':call_index,'id':point['id'],'state':point,'signature':sig,'metrics':metrics,'slot':slot,'cpu':cpus[slot],
                         'simulate_batch_s':simulate,'materialize_analysis_s':materialize,'npz_serialize_write_s':write_cost,
                         'state_batch_completion_latency_s':time.perf_counter()-begin,'output_bytes':file.stat().st_size}
                    flush=time.perf_counter();log.write(json.dumps(row,allow_nan=False)+'\n');log.flush();row['jsonl_flush_s']=time.perf_counter()-flush
                    rows.append(row);call_index+=1
                    if window.failure:raise RuntimeError(window.failure)
        except BaseException:errors.put(traceback.format_exc());cancel.set()
    try:
        for _ in range(args.workers):
            begin=time.perf_counter();pool.extend(instances(args.case,1,args.residency));setup_costs.append(time.perf_counter()-begin)
        mapped=t.loaded_library()
        for i,owned in enumerate(pool):
            th=threading.Thread(target=worker,args=(i,owned));threads.append(th);th.start()
        setup_end=time.perf_counter();freq_before=g.frequency();before=g.cpu_window();eval_start=time.perf_counter();start.set()
        os.sched_setaffinity(0,set(cpus))
        for point in [*points,*([None]*args.workers)]:
            while not cancel.is_set():
                try:jobs.put(point,timeout=.2);break
                except queue.Full:continue
            if cancel.is_set():break
        for th in threads:th.join()
        eval_end=time.perf_counter();after=g.cpu_window();freq_after=g.frequency()
        t.require(errors.empty(),'Rolling worker failed: '+('' if errors.empty() else errors.get()))
        t.require(sorted(r['id'] for r in rows)==sorted(p['id'] for p in points),'Incomplete or duplicate rolling outputs')
        window.sample()
        for cp,r,_ in pool:t.require(cp.data_free(r),'Context free failed')
        pool=[];end=time.perf_counter();window.close()
        elapsed=after['wall']-before['wall'];own=after['own_cpu_s']-before['own_cpu_s'];system=(after['busy_ticks']-before['busy_ticks'])/os.sysconf('SC_CLK_TCK')
        throttle=any(after['throttle'].get(k,v)>v for k,v in before['throttle'].items());policy=t.frequency_policy(freq_before)==t.frequency_policy(freq_after)
        accepted=max(0.,(system-own)/elapsed)<.5 and not throttle and policy
        # Auxiliary post-timing index; original per-worker JSONLs were flushed in time.
        with (directory/'states.jsonl').open('x') as index:
            for file in sorted(directory.glob('worker-*.jsonl')):index.write(file.read_text())
        services=[r['state_batch_completion_latency_s'] for r in rows];sims=[r['simulate_batch_s'] for r in rows]
        value={'phase':'5B','status':'passed','identifier':args.id,'case':args.case,'series':args.series,'mode':'pipeline',
            'batch_size':1,'active_states':args.workers,'state_slots':args.workers,'maximum_cpu_preparations':args.workers,
            'static_residency_enabled':args.residency,'instrumented':False,'completed':len(rows),'control_grid':[plan['grid']['nx'],plan['grid']['ny']],
            'contract':t.CONTRACT,'runtime_probe_s':probe,'context_setup_s':setup_costs,'setup_wall_s':setup_end-overall,
            'evaluation_wall_s':eval_end-eval_start,'total_wall_s':end-overall,'states_per_s':len(rows)/(eval_end-eval_start),
            'total_states_per_s':len(rows)/(end-overall),'simulate_batch_wall_s':g.stats(sims),'batch_complete_wall_s':g.stats(services),
            'simulation_only_states_per_s':len(rows)/union_duration([(r['simulate_begin'],r['simulate_end']) for r in rows]),
            'api_active_union_wall_s':union_duration([(r['simulate_begin'],r['simulate_end']) for r in rows]),'summed_worker_api_s':sum(sims),
            'simulation_only_note':'Observed union of API-active wall intervals; other workers can write outputs during these intervals. Not a counterfactual output-free run',
            'materialize_analysis_s':sum(r['materialize_analysis_s'] for r in rows),
            'serialize_write_s':sum(r['npz_serialize_write_s']+r['jsonl_flush_s'] for r in rows),'output_cost_includes_jsonl_flush':True,
            'output_cost_scope':'Summed worker service intervals; concurrent intervals may overlap and must not be subtracted from total wall',
            'output_bytes':sum(r['output_bytes'] for r in rows),'first_batch_wall_s':None,'first_simulate_batch_s':None,
            'first_calls_api_s':[r['simulate_batch_s'] for r in rows if r['worker_call_index']==0],
            'first_calls_service_s':[r['state_batch_completion_latency_s'] for r in rows if r['worker_call_index']==0],
            'first_call_included':True,'warmups_excluded':0,'state_batch_completion_latency_s':g.stats(services),
            'cpu_window':{'accepted':accepted,'average_owned_cores':own/elapsed,'external_average_cores':max(0.,(system-own)/elapsed),
                          'thermal_throttle_increased':throttle,'frequency_policy_unchanged':policy},
            'gpu_telemetry':window.samples,'peak_device_used_mib_sampled':max(float(s['memory.used']) for s in window.samples),
            'gpu_utilization_percent_sampled_mean':sum(float(s['utilization.gpu']) for s in window.samples)/len(window.samples),
            'cpu_affinity':cpus,'worker_cpu_masks':[[c] for c in cpus[:args.workers]],'queue_capacity':2*args.workers,
            'loaded_library':mapped,'library_sha256':args.library_sha256,'harness_sha256':t.digest(__file__),
            'commits':{k:subprocess.check_output(['git','-C',str(t.ROOT/k),'rev-parse','HEAD'],text=True).strip() for k in ('.','ssc','SolarPILOT','SolTrace')},
            'utc':datetime.now(timezone.utc).isoformat(),'validation_outside_timing':True,'states_jsonl_is_posttiming_index':True,
            'gpu_execution':'Rolling independent ordinary CUDA calls; existing default stream; no fused kernel or new streams'}
        t.require(t.digest(library)==args.library_sha256,'Library changed');t.write(directory/'result.json',value)
        print(args.id,'completed',len(rows),'states/s',value['states_per_s'],'wall',value['total_wall_s'],'clean',accepted,flush=True)
    finally:
        cancel.set();start.set()
        for th in threads:th.join()
        for cp,r,_ in pool:cp.data_free(r)
        window.stop.set()
        if hasattr(window,'thread'):window.thread.join()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['check','campaign']);p.add_argument('--case',choices=['cesa','commercial'],required=True)
    p.add_argument('--workers',type=int,required=True);p.add_argument('--residency',action='store_true');p.add_argument('--series',choices=['seasonal','long','states'],default='seasonal')
    p.add_argument('--id');p.add_argument('--library-sha256');a=p.parse_args()
    if a.command=='check':check(a)
    else:
        t.require(a.id and all(c.isalnum() or c in '-_' for c in a.id),'Unique campaign ID required');t.require(a.library_sha256,'Explicit binary hash required');campaign(a)
if __name__=='__main__':main()
