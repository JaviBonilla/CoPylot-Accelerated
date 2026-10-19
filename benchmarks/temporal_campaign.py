#!/usr/bin/env python3
"""Direct temporal correctness and independent-process CPU throughput (Phase 5A)."""
import argparse
import csv
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing as mp
from multiprocessing.connection import wait as wait_connections
import os
from pathlib import Path
import queue
import resource
import subprocess
import threading
import time
import traceback

import numpy as np
import cpu_multicore as cpu
from cases import ROOT, api
from commercial_reference import configure, load_manifest
from project_grid_campaign import prepare, require, verify_inputs, SITE, PLAIN
from cpu_hardening_equivalence import arrays as optical_arrays

OUT = ROOT/'artifacts/phase5a'
CANONICAL_LIB_SHA = '545775e26ca3588c9a65c56c93e6f3f93d480446e4a04272497fad27acb5e017'
# Explicit identity pin for a separately validated rebuild; canonical by default.
LIB_SHA = os.environ.get('COPILOT_EXPECTED_LIBRARY_SHA256',CANONICAL_LIB_SHA)
STRATEGIES = ((1,24),(2,12),(4,6),(6,4),(12,2),(24,1))
PUBLIC_SEASONS = ((3,21),(6,21),(9,21),(12,21))
CONTRACT = 'full-f64-map+all-heliostat-details+numeric-summary+state-metrics-v1'


def frequency_policy(values):
    return {p:{k:v for k,v in row.items() if k!='scaling_cur_freq'} for p,row in values.items()}


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n'); tmp.replace(path)


def digest(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def environment():
    for key in list(os.environ):
        if key.startswith('SOLARPILOT_'): os.environ.pop(key)
    os.environ.update({**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'flat'})
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
        require(os.environ.get(key)=='1', 'Numerical pools must be fixed before starting Python')
    require(digest(Path(os.environ['COPILOT_LIB_DIR'])/'solarpilot.so')==LIB_SHA,'Wrong frozen numerical library')


def partitions(topology, workers, threads):
    """Disjoint whole physical-core groups, then sibling pairs, for full 24-way use."""
    require((workers,threads) in STRATEGIES+((1,1),(1,12)), 'Unsupported hardware allocation')
    groups = {}
    for row in topology['logical_cpus']:
        groups.setdefault((row['socket'],row['core']),[]).append(row['cpu'])
    cores = [sorted(v) for k,v in sorted(groups.items())]
    require(len(cores)==12 and all(len(v)==2 for v in cores),'Require 12 complete SMT core pairs')
    if workers==1 and threads in (1,12):
        return [[pair[0] for pair in cores[:threads]]]
    if threads == 1: result = [[pair[s]] for s in range(2) for pair in cores]
    else:
        count = threads//2
        result = [sum((cores[j] for j in range(i*count,(i+1)*count)),[]) for i in range(workers)]
    require(len(result)==workers and all(len(v)==threads for v in result),'Invalid mask sizes')
    flat = sum(result,[])
    require(len(set(flat))==24 and len(flat)==24,'Overlapping or missing CPUs')
    return result


def sun_function():
    bridge = ctypes.CDLL(str(OUT/'libtemporal_sun_bridge.so'))
    f = bridge.phase5a_sun
    f.argtypes = [ctypes.c_double]*3+[ctypes.c_int]*2+[ctypes.c_double,ctypes.POINTER(ctypes.c_double)]
    f.restype = ctypes.c_bool
    def sun(site, month, day, hour):
        values = (ctypes.c_double*2)()
        require(f(*site,month,day,hour,values),'Core sun derivation failed')
        return list(values)
    return sun


def context(cp, case):
    if case=='cesa':
        plan = json.loads((ROOT/'local-cases/example/phase3c-results/plan.json').read_text())
        verify_inputs(plan)
        require((plan['grids'][5]['nx'],plan['grids'][5]['ny'])==(217,256),'CESA CONTROL grid changed')
        r = prepare(cp,Path(plan['project']),grid=plan['grids'][5])
        grid = plan['grids'][5]
    else:
        m = load_manifest(); r = cp.data_create()
        try: configure(cp,r,m,222,87,m['operating_points'][0])
        except BaseException: cp.data_free(r); raise
        width = np.pi*m['parameters']['receiver.0.rec_diameter']['value']
        height = m['parameters']['receiver.0.rec_height']['value']
        grid = {'nx':222,'ny':87,'surface_width_m':width,'height_m':height,
                'cell_width_m':width/222,'cell_height_m':height/87}
    require(cp.data_set_number(r,'fluxsim.0.flux_time_type',1),'Cannot select Hour/Day')
    require(cp.set_compute_backend(r,'cpu'),'CPU backend unavailable')
    return r,grid


def set_state(cp, r, point):
    for name,value in (('flux_month',point['month']),('flux_day',point['day']),
                       ('flux_hour',point['hour']),('flux_dni',point['dni'])):
        require(cp.data_set_number(r,'fluxsim.0.'+name,value),'Cannot update temporal state')


def resolved(cp, r):
    return [cp.data_get_number(r,'fluxsim.0.flux_solar_'+name) for name in ('az','el')]


def build_plan(case):
    cp = api(); r,grid = context(cp,case)
    try:
        site = [cp.data_get_number(r,k) for k in SITE[:3]]
        if case=='commercial':
            m=load_manifest();dates=PUBLIC_SEASONS
            with (ROOT/m['assets']['weather']['path']).open() as stream:
                next(stream);next(stream); rows=list(csv.DictReader(stream))
            require(len(rows)==8760,'Expected 8760 public weather records')
            candidates=[{'month':int(v['Month']),'day':int(v['Day']),'hour':float(v['Hour'])+.5,
                         'dni':float(v['DNI'])} for v in rows]
            policy='Pinned public TMY2 hourly DNI, row hour + 0.5 local standard time; zeros retained'
        else:
            dni=cp.data_get_number(r,'fluxsim.0.flux_dni')
            schedule=json.loads((ROOT/'local-cases/example/phase5a-inputs.json').read_text())
            dates=[tuple(v) for v in schedule['dates']];hours=schedule['hours']
            require(len(set(dates))==4 and len(set(hours))==24,'Require four private full-day hourly series')
            require(all(0<=h<24 for h in hours),'Invalid private clock time')
            candidates=[{'month':m,'day':d,'hour':h,'dni':dni} for m,d in dates for h in hours]
            policy='Unchanged saved project flux_dni; EPW supplies site; four seasonal local-standard-time days'
        sun=sun_function();states=[];night=0
        for i,p in enumerate(candidates):
            p={'id':i,**p,'sun':sun(site,p['month'],p['day'],p['hour'])}
            require(np.isfinite(p['dni']) and p['dni']>=0,'Invalid DNI')
            if p['sun'][1] <= 0: night+=1
            else: states.append(p)
        seasonal=[p for p in states if (p['month'],p['day']) in dates]
        # Morning/noon/afternoon on every season, plus an explicit zero-DNI probe.
        diagnostic=[]
        for date in dates:
            points=[p for p in seasonal if (p['month'],p['day'])==date]
            require(len(points)>=3,'Insufficient seasonal daylight')
            diagnostic.extend([points[0],points[len(points)//2],points[-1]])
        probe={**diagnostic[4],'id':len(candidates),'dni':0.,'probe':True}
        diagnostic.append(probe)
        return {'case':case,'grid':grid,'dni_policy':policy,'requested':len(candidates),'nighttime':night,
                'states':states,'seasonal':seasonal,'diagnostic':diagnostic,
                'solar_year':2011,'sun_derivation':'Existing Ambient Hour/Day SOLPOS, no interval correction',
                'aim_method':int(cp.data_get_number(r,'fluxsim.0.aim_method')),'output_contract':CONTRACT,
                'public_weather_asset':load_manifest()['assets']['weather'] if case=='commercial' else None}
    finally: cp.data_free(r)


def payload(cp, r, point, grid):
    actual = cpu.state(cp,r)
    flux,detail,summary=actual
    require(flux.shape==(grid['ny'],grid['nx']),'Incorrect CONTROL map shape')
    require(np.isfinite(flux).all() and all(np.isfinite(v).all() for v in detail.values())
            and all(np.isfinite(v) for v in summary.values()),'Nonfinite temporal output')
    require(resolved(cp,r)==point['sun'],'Calendar helper and ordinary API solar position differ')
    values=optical_arrays(actual,np.empty(0))
    values.pop('optical')
    values['resolved_sun']=np.asarray(resolved(cp,r),dtype=np.float64)
    mean=float(flux.mean()); std=float(flux.std());total=float(flux.sum())
    metrics={'peak_kw_m2':float(flux.max()),'mean_kw_m2':mean,'std_kw_m2':std,
             'uniformity_cv':std/mean if mean else None,
             'incident_power_kw':mean*grid['surface_width_m']*grid['height_m'],
             'centroid_column':float(np.einsum('ij,j->',flux,np.arange(grid['nx']))/total) if total else None,
             'centroid_row':float(np.einsum('ij,i->',flux,np.arange(grid['ny']))/total) if total else None,
             'absorbed_power_kw':summary['Power absorbed by the receiver']}
    return values,metrics


def signature(values):
    sha=hashlib.sha256()
    for name,value in sorted(values.items()):
        sha.update(name.encode());sha.update(value.dtype.str.encode())
        sha.update(str(value.shape).encode());sha.update(value.tobytes())
    return sha.hexdigest()


def optics_function():
    bridge=ctypes.CDLL(str(ROOT/'build/phase4s-cuda/libcpu_optical_state_bridge.so'))
    bridge.phase4_optical_capture.argtypes=[ctypes.c_void_p];bridge.phase4_optical_capture.restype=ctypes.c_void_p
    bridge.phase4_optical_size.argtypes=[ctypes.c_void_p];bridge.phase4_optical_size.restype=ctypes.c_size_t
    bridge.phase4_optical_copy.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t];bridge.phase4_optical_copy.restype=ctypes.c_bool
    bridge.phase4_optical_free.argtypes=[ctypes.c_void_p]
    def capture(r):
        ptr=bridge.phase4_optical_capture(r);require(bool(ptr),'Cannot capture optical state')
        try:
            size=bridge.phase4_optical_size(ptr);value=np.empty(size,dtype=np.float64)
            require(bridge.phase4_optical_copy(ptr,value.ctypes.data,size),'Cannot export optical state')
            return value
        finally: bridge.phase4_optical_free(ptr)
    return capture


def immutable(cp,r):
    positions=np.asarray(cp.get_layout_info(r,get_optical_details=True,restype='matrix')[0],dtype=np.float64)
    # id, xyz, template dimensions: ranking/efficiencies excluded.
    detail=cp.detail_results(r,restype='dictionary')
    return positions[:,:5].tobytes(),np.asarray([detail[k+'_aimpoint'] for k in 'xyz'],dtype=np.float64).tobytes()


def correctness(case):
    environment();directory=OUT/'correctness'/case;directory.mkdir(parents=True,exist_ok=False)
    plan=build_plan(case);write(OUT/(case+'-plan.json'),plan)
    cp=api();capture=optics_function();references={};rows=[]
    # Every seasonal state is independent and serial, before any throughput run.
    all_points={p['id']:p for p in plan['seasonal']+plan['diagnostic']}
    invariant=None
    for i,point in enumerate(all_points.values()):
        r,grid=context(cp,case)
        try:
            set_state(cp,r,point);elapsed=cpu.simulate(cp,r,1);values,metrics=payload(cp,r,point,grid)
            references[str(point['id'])]=signature(values)
            np.savez(directory/(str(point['id'])+'.npz'),**values)
            if point['id'] in {p['id'] for p in plan['diagnostic']}:
                np.save(directory/(str(point['id'])+'-optics.npy'),capture(r))
            current=immutable(cp,r)
            if invariant is None:invariant=current
            require(current==invariant,'Layout or invariant aiming changed across fresh states')
            rows.append({'id':point['id'],'simulate_s':elapsed,'signature':references[str(point['id'])], 'metrics':metrics})
        finally:cp.data_free(r)
        print(case,'fresh serial',i+1,'/',len(all_points),flush=True)
    write(directory/'references.json',references)
    diag=plan['diagnostic'];checks=[]
    for n in (1,2,4,6,12,24):
        os.sched_setaffinity(0,set(cpu.topology_cache['affinity_sets']['24']))
        r,grid=context(cp,case)
        try:
            sequences=[('forward',diag),('reverse',list(reversed(diag))),('repeated',[diag[0],diag[4],diag[0],diag[-1],diag[0]])]
            # Full forward/reverse/repeated for 1T; all seasonal transitions forward for every API N.
            if n!=1: sequences=[('forward',diag)]
            for order,points in sequences:
                for point in points:
                    set_state(cp,r,point);cpu.simulate(cp,r,n);values,metrics=payload(cp,r,point,grid)
                    require(signature(values)==references[str(point['id'])],'Reused context differs from fresh serial reference')
                    expected=np.load(directory/(str(point['id'])+'-optics.npy'))
                    require(expected.tobytes()==capture(r).tobytes(),'Reused full optical state differs')
                    require(immutable(cp,r)==invariant,'Runtime geometry/aiming drift')
                    checks.append({'id':point['id'],'threads':n,'order':order,'bitwise_full_outputs':True,'bitwise_all215':True})
            print(case,'reused context',n,'PASS',flush=True)
        finally:cp.data_free(r)
    write(directory/'result.json',{'status':'passed','case':case,'fresh_serial_states':len(rows),'reference_rows':rows,
                                 'transition_checks':checks,'immutable_geometry_aim':True,'zero_dni_probe':True,
                                 'library_sha256':LIB_SHA,'harness_sha256':digest(__file__)})


def usage():
    v=resource.getrusage(resource.RUSAGE_SELF);return v.ru_utime+v.ru_stime


def proc_sample(pids, masks):
    result={'time':time.perf_counter(),'workers':{}}
    for pid,mask in zip(pids,masks):
        tasks=[]
        for task in Path('/proc',str(pid),'task').glob('[0-9]*'):
            try:
                stat=(task/'stat').read_text().split(') ',1)[1].split()
                allowed=sorted(os.sched_getaffinity(int(task.name)))
                tasks.append({'tid':int(task.name),'state':stat[0],'last_cpu':int(stat[36]),'allowed':allowed})
            except (FileNotFoundError,ProcessLookupError): continue
        if tasks:
            require(all(set(t['allowed'])==set(mask) for t in tasks),'A task escaped its worker mask')
            require(len(tasks)<=len(mask),'Worker task count exceeds threads_per_state')
        result['workers'][str(pid)]=tasks
    return result


def loaded_library():
    mappings=[]
    for line in Path('/proc/self/maps').read_text().splitlines():
        fields=line.split(None,5)
        if len(fields)==6 and Path(fields[5]).name=='solarpilot.so':mappings.append(fields)
    paths={v[5] for v in mappings}
    require(len(paths)==1,'Expected one actually mapped numerical library')
    path=Path(next(iter(paths)));stat=path.stat()
    device=f'{os.major(stat.st_dev):02x}:{os.minor(stat.st_dev):02x}'
    require(all((v[3],int(v[4]))==(device,stat.st_ino) for v in mappings),'Mapped inode differs from hashed file')
    value=digest(path);require(value==LIB_SHA,'Actually mapped binary is not the accepted Phase 4S library')
    return {'sha256':value,'mapped_inode_matches_hashed_file':True,'bytes':stat.st_size}


def assigned_points(points, jobs, cancelled):
    if jobs is None:
        for point in points:
            if cancelled.is_set(): return
            yield point
    else:
        while not cancelled.is_set():
            try: point=jobs.get(timeout=.2)
            except queue.Empty: continue
            if point is None: return
            yield point


def receive_workers(pipes, children, kind):
    pending=list(pipes); values={}
    while pending:
        for pipe in wait_connections(pending,timeout=1.):
            value=pipe.recv()
            require(value['kind']==kind,str(value))
            values[value['pid']]=value;pending.remove(pipe)
    return [values[p.pid] for p in children]


def equal_metrics(actual, expected):
    require(actual.keys()==expected.keys(),'Derived metric schema changed')
    for key,value in actual.items():
        if value is None or expected[key] is None:
            require(value is None and expected[key] is None,'Undefined metric changed')
        else: require(abs(value-expected[key])<=1e-10+1e-9*abs(expected[key]),'Derived metric differs from serial reference')


def worker(pipe, start, finish, cancelled, jobs, case, points, mask, threads, directory, references, reference_metrics, fresh_reference_ids):
    cp=None;r=None
    try:
        os.sched_setaffinity(0,set(mask));environment()
        init=time.perf_counter();cp=api();load_s=time.perf_counter()-init
        init=time.perf_counter();r,grid=context(cp,case);setup_s=time.perf_counter()-init
        pipe.send({'kind':'ready','pid':os.getpid(),'load_s':load_s,'setup_s':setup_s,
                   'mask':sorted(os.sched_getaffinity(0)),'loaded_library':loaded_library(),'cpu_start':usage()})
        start.wait();rows=[];bytes_written=0
        with (directory/('worker-'+str(os.getpid())+'.jsonl')).open('x') as stream:
            for point in assigned_points(points,jobs,cancelled):
                begin=time.perf_counter();set_state(cp,r,point)
                sim=cpu.simulate(cp,r,threads)
                output_start=time.perf_counter();values,metrics=payload(cp,r,point,grid);sig=signature(values)
                if str(point['id']) in references:
                    require(sig==references[str(point['id'])],'Strategy output differs from independent serial oracle')
                    equal_metrics(metrics,reference_metrics[str(point['id'])])
                file=directory/(str(point['id'])+'.npz')
                require(not file.exists(),'Duplicate state output')
                np.savez(file,**values);bytes_written+=file.stat().st_size
                end=time.perf_counter()
                row={'id':point['id'],'state':point,'signature':sig,'metrics':metrics,'simulate_s':sim,
                     'output_s':end-output_start,'state_latency_s':end-begin,'worker_pid':os.getpid(),
                     'completed_monotonic':end,'serial_oracle_checked':str(point['id']) in fresh_reference_ids,
                     'ordinary_api_reference_checked':str(point['id']) in references}
                stream.write(json.dumps(row,allow_nan=False)+'\n');stream.flush();rows.append(row)
        pipe.send({'kind':'done','pid':os.getpid(),'cpu_end':usage(),'completed':len(rows),'bytes':bytes_written,
                   'end':time.perf_counter()})
        finish.wait()
    except BaseException:
        cancelled.set()
        pipe.send({'kind':'error','traceback':traceback.format_exc()})
    finally:
        if cp and r:cp.data_free(r)
        pipe.close()


def stats(values):
    return {'count':len(values),'median':float(np.median(values)), 'p95':float(np.percentile(values,95)),
            'p99':float(np.percentile(values,99)),'min':min(values),'max':max(values)}


def load_references(reference,case):
    references=json.loads(reference.read_text());fresh_reference_ids=set(references)
    reference_rows=json.loads((reference.parent/'result.json').read_text())['reference_rows']
    reference_metrics={str(r['id']):r['metrics'] for r in reference_rows}
    costs={str(r['id']):r['simulate_s'] for r in reference_rows}
    extra=reference.parent/'extra-references.json'
    if extra.exists():
        observed=json.loads(extra.read_text())
        require(observed['library_sha256']==LIB_SHA,'Additional reference has another numerical binary')
        require(observed['case']==case,'Additional reference has another case')
        for row in observed['rows']:
            key=str(row['id'])
            if key in references:
                require(references[key]==row['signature'],'Independent reference bundles disagree')
                equal_metrics(reference_metrics[key],row['metrics'])
            else:
                references[key]=row['signature'];reference_metrics[key]=row['metrics'];costs[key]=row['simulate_s']
    return references,reference_metrics,costs,fresh_reference_ids


def campaign(case, workers, threads, series, identifier, scheduler='dynamic_lpt',role='formal'):
    environment();plan=json.loads((OUT/(case+'-plan.json')).read_text());points=plan[series]
    reference=OUT/'correctness'/case/'references.json'
    require(reference.is_file(),'Serial correctness must precede campaigns')
    require(json.loads((reference.parent/'result.json').read_text())['status']=='passed','Correctness did not pass')
    references,reference_metrics,costs,fresh_reference_ids=load_references(reference,case)
    masks=partitions(cpu.topology_cache,workers,threads)
    ordered=sorted(points,key=lambda p:(-costs.get(str(p['id']),0.),p['id'])) if scheduler=='dynamic_lpt' else points
    dispatched=[{**p,'dispatch_index':i} for i,p in enumerate(ordered)]
    directory=OUT/'campaigns'/identifier;directory.mkdir(parents=True,exist_ok=False)
    write(directory/'plan.json',{'case':case,'series':series,'points':points,'workers':workers,'threads':threads,
                               'masks':masks,'contract':CONTRACT,'identifier':identifier,'scheduler':scheduler,'role':role,
                               'dispatch_order_ids':[p['id'] for p in dispatched]})
    ctx=mp.get_context('spawn');start=ctx.Event();finish=ctx.Event();cancelled=ctx.Event();children=[];pipes=[]
    jobs=ctx.Queue(maxsize=2*workers) if scheduler!='round_robin' else None
    overall=time.perf_counter();ready=[];done=[];frames=[];monitor_errors=[];stop=threading.Event()
    feeder=None;observer=None
    frequency_before=cpu.frequency()
    try:
        for i,mask in enumerate(masks):
            parent,child=ctx.Pipe(duplex=False)
            p=ctx.Process(target=worker,args=(child,start,finish,cancelled,jobs,case,
                          points[i::workers] if jobs is None else [],mask,threads,directory,references,reference_metrics,fresh_reference_ids))
            p.start();child.close();children.append(p);pipes.append(parent)
        ready=receive_workers(pipes,children,'ready')
        setup_end=time.perf_counter();pids=[p.pid for p in children]
        require(all(v['mask']==sorted(mask) for v,mask in zip(ready,masks)),'Wrong initial worker masks')
        def observe():
            while not stop.is_set():
                try:frames.append(proc_sample(pids,masks))
                except BaseException:monitor_errors.append(traceback.format_exc());break
                stop.wait(.05)
        observer=threading.Thread(target=observe);observer.start()
        if jobs is not None:
            def feed():
                start.wait()
                for point in [*dispatched,*([None]*workers)]:
                    while not cancelled.is_set():
                        try: jobs.put(point,timeout=.2);break
                        except queue.Full: continue
                    if cancelled.is_set(): return
            feeder=threading.Thread(target=feed);feeder.start()
        before=cpu.cpu_window();parent_cpu_before=usage();evaluation_start=time.perf_counter();start.set()
        done=receive_workers(pipes,children,'done')
        evaluation_end=time.perf_counter();after=cpu.cpu_window();parent_cpu_after=usage()
        stop.set();observer.join()
        require(not monitor_errors,str(monitor_errors))
        finish.set()
        for child in children:child.join();require(child.exitcode==0,'Worker did not exit cleanly')
        overall_end=time.perf_counter()
        rows=[]
        for file in directory.glob('worker-*.jsonl'):rows.extend(json.loads(line) for line in file.read_text().splitlines())
        require(sorted(r['id'] for r in rows)==sorted(p['id'] for p in points),'Incomplete or duplicate state coverage')
        own_cpu=sum(v['cpu_end']-r['cpu_start'] for r,v in zip(ready,done))+parent_cpu_after-parent_cpu_before
        elapsed=after['wall']-before['wall'];system_cpu=(after['busy_ticks']-before['busy_ticks'])/os.sysconf('SC_CLK_TCK')
        external=max(0.,system_cpu-own_cpu)/elapsed
        thermal=any(after['throttle'].get(k,v)>v for k,v in before['throttle'].items())
        elapsed_eval=evaluation_end-evaluation_start
        services=[sum(r['state_latency_s'] for r in rows if r['worker_pid']==pid) for pid in pids]
        frequency_after=cpu.frequency()
        policy_unchanged=frequency_policy(frequency_before)==frequency_policy(frequency_after)
        require(digest(Path(os.environ['COPILOT_LIB_DIR'])/'solarpilot.so')==LIB_SHA,'Library changed during campaign')
        result={'phase':'5A','status':'passed','identifier':identifier,'case':case,'series':series,'contract':CONTRACT,
                'scheduler':scheduler,'role':role,'queue_capacity':2*workers if jobs is not None else 0,
                'state_latency_mean_s':sum(services)/len(rows),'worker_service_s':services,
                'load_balance_efficiency':sum(services)/(workers*elapsed_eval),
                'states_in_parallel':workers,'threads_per_state':threads,'masks':masks,'completed':len(rows),
                'evaluation_wall_s':elapsed_eval,'total_wall_s':overall_end-overall,'setup_wall_s':setup_end-overall,
                'states_per_s':len(rows)/elapsed_eval,'total_states_per_s':len(rows)/(overall_end-overall),
                'simulation_latency_s':stats([r['simulate_s'] for r in rows]),
                'state_latency_s':stats([r['state_latency_s'] for r in rows]),
                'output_materialization_s':stats([r['output_s'] for r in rows]),
                'output_total_worker_s':sum(r['output_s'] for r in rows),'output_bytes':sum(d['bytes'] for d in done),
                'checked_against_serial_oracle':sum(r['serial_oracle_checked'] for r in rows),
                'checked_against_ordinary_api_reference':sum(r['ordinary_api_reference_checked'] for r in rows),
                'workers':ready,'cpu_window':{'accepted':external<.5 and not thermal and policy_unchanged,'frequency_policy_unchanged':policy_unchanged,'external_average_cores':external,
                'owned_cpu_s':own_cpu,'average_owned_cores':own_cpu/elapsed,'logical_cpu_utilization':own_cpu/(24*elapsed),
                'system_cpu_s':system_cpu,'thermal_throttle_increased':thermal,'before':before,'after':after},
                'affinity_observation':{'passed':True,'frames':len(frames),'maximum_tasks':[max((len(f['workers'][str(pid)]) for f in frames),default=0) for pid in pids],
                                      'maximum_runnable':[max((sum(t['state']=='R' for t in f['workers'][str(pid)]) for f in frames),default=0) for pid in pids]},
                'frequency_before':frequency_before,'frequency_after':frequency_after,
                'library_sha256':LIB_SHA,'harness_sha256':digest(__file__),'utc':datetime.now(timezone.utc).isoformat(),
                'commits':{name:subprocess.check_output(['git','-C',str(ROOT/name),'rev-parse','HEAD'],text=True).strip() for name in ('.','ssc','SolarPILOT','SolTrace')}}
        write(directory/'task-observations.json',frames);write(directory/'result.json',result)
        print(identifier,'completed',len(rows),'states/s',round(result['states_per_s'],4),'total wall',round(result['total_wall_s'],3),
              'clean',result['cpu_window']['accepted'],flush=True)
    finally:
        cancelled.set();stop.set();start.set();finish.set()
        if observer is not None:observer.join(timeout=2)
        if feeder is not None:feeder.join(timeout=2)
        for child in children:
            child.join(timeout=1)
            if child.is_alive():child.terminate();child.join()
        for pipe in pipes:pipe.close()
        if jobs is not None:jobs.cancel_join_thread();jobs.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('correctness');a.add_argument('--case',choices=['cesa','commercial'],required=True)
    a=sub.add_parser('campaign');a.add_argument('--case',choices=['cesa','commercial'],required=True)
    a.add_argument('--workers',type=int,required=True);a.add_argument('--threads',type=int,required=True)
    a.add_argument('--series',choices=['seasonal','long','states'],default='seasonal');a.add_argument('--id',required=True)
    a.add_argument('--scheduler',choices=['dynamic_lpt','dynamic','round_robin'],default='dynamic_lpt')
    a.add_argument('--role',choices=['formal','pilot'],default='formal')
    args=p.parse_args();cpu.topology_cache=cpu.topology();environment()
    if args.command=='correctness':correctness(args.case)
    else:campaign(args.case,args.workers,args.threads,args.series,args.id,args.scheduler,args.role)


if __name__=='__main__':main()
