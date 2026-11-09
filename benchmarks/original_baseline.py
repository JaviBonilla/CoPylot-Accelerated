#!/usr/bin/env python3
"""Eight ordinary-API Legacy states only; raw CESA data never leave the server."""
import argparse,ctypes,hashlib,json,os,resource,subprocess,tempfile,time
from pathlib import Path
from unittest.mock import patch
import cpu_repeatability as f
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/original-baseline'
LIBRARY='545775e26ca3588c9a65c56c93e6f3f93d480446e4a04272497fad27acb5e017'
CASES={'cesa':'cesa-i-private-restored','commercial':'ssc-mspt-8790-optical-reference'}
LABELS={'high-elevation':'High','moderate-elevation':'Moderate','morning-offdesign':'Morning','afternoon-offdesign':'Afternoon','high':'High','moderate':'Moderate','morning':'Morning','afternoon':'Afternoon'}

def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');tmp.replace(path)

def owned_target(argv,identifier):
    return len(argv)>4 and argv[1:3]==[b'benchmarks/original_baseline.py',b'campaign'] and identifier.encode() in argv

def require(condition,message):
    if not condition:raise RuntimeError(message)

def idle():
    import cpu_multicore as c
    accepted=0;deadline=time.monotonic()+120
    while accepted<2:
        before=c.cpu_window();time.sleep(1);after=c.cpu_window()
        try:v=c.validate_window(before,after);accepted=accepted+1 if v['external_average_cores']<.25 else 0
        except RuntimeError:accepted=0
        require(time.monotonic()<deadline,'No clean CPU admission window; no service was stopped')

def check_values(expected,actual):
    require(set(expected)==set(actual),'Full observable schema differs')
    require(all(expected[k].dtype==v.dtype and expected[k].shape==v.shape and expected[k].tobytes()==v.tobytes() for k,v in actual.items()),'Legacy differs from accepted full Flat1T oracle')

def campaign(a):
    import numpy as np
    import cpu_multicore as c
    from cpu_hardening_equivalence import arrays
    from check_gpu_temporal import optical_capture
    for key in list(os.environ):
        if key.startswith('SOLARPILOT_'):os.environ.pop(key)
    for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:require(os.environ.get(key)=='1','Numerical pools must be one before Python starts')
    directory=Path(a.library_dir or ROOT/'build/phase4s-cuda/lib');os.environ['COPILOT_LIB_DIR']=str(directory)
    library=directory/'solarpilot.so';expected_sha=a.library_sha256 or LIBRARY
    require(f.digest(library)==expected_sha,'Wrong declared library')
    c.topology_cache=c.topology();os.sched_setaffinity(0,{c.topology_cache['affinity_sets']['1'][0]})
    cp=c.api();capture=optical_capture();plan=json.loads((ROOT/'local-cases/example/phase3c-results/plan.json').read_text())
    destination=OUT/(a.id+'.json');require(not destination.exists(),'Refuse to overwrite a run')
    meta=c.metadata();meta['original_harness_sha256']=f.digest(__file__);meta['source_pin_for_measured_library']='0fd069b30343a08787f76247c4b1bb637e83bbe0' if expected_sha==LIBRARY else meta['commits']['ssc']
    result={'campaign_id':a.id,'status':'running','case':a.case,'threads':1,'affinity':sorted(os.sched_getaffinity(0)),
        'role':'correctness_only' if a.verify_only else 'formal','metadata':meta,'rows':[]}
    env={**c.PLAIN,'SOLARPILOT_INTERCEPT_PATH':'legacy','SOLARPILOT_FLUX_PATH':'legacy'}
    with patch.dict(os.environ,env):
      for sid,grid,point,ctx in c.contexts(cp,CASES[a.case],plan,True):
        try:
            if a.state and sid!=a.state:continue
            require(cp.set_compute_backend(ctx,'cpu'),'Cannot select CPU')
            require(cp.get_compute_backend(ctx)=='cpu','Wrong compute backend')
            before_identity=f.mapped_identity();idle()
            if a.verify_only:
                c.simulate(cp,ctx,1);timing={}
            else:
                first=c.simulate(cp,ctx,1);warmups=[c.simulate(cp,ctx,1) for _ in range(2)]
                before=c.cpu_window();policy_before=f.policy();begin=time.monotonic()
                samples=[c.simulate(cp,ctx,1) for _ in range(5)];end=time.monotonic();after=c.cpu_window();policy_after=f.policy()
                try:window={**c.validate_window(before,after),'accepted':True}
                except RuntimeError as error:window={'accepted':False,'reason':str(error),'before':before,'after':after}
                timing={'first_call_s':first,'warmup_samples_s':warmups,'samples_s':samples,'statistics_s':c.distribution(samples),
                        'measurement_monotonic':[begin,end],'cpu_window':window,'policy_unchanged':policy_before==policy_after}
            actual=c.state(cp,ctx);values=arrays(actual,capture(ctx))
            oracle=OUT/'reference-arrays'/f'{CASES[a.case]}-{sid}.npz'
            with np.load(oracle,allow_pickle=False) as old:check_values({k:old[k] for k in old.files},values)
            # An additional ordinary Legacy call checks repeat observability, outside timing.
            c.simulate(cp,ctx,1);check_values(values,arrays(c.state(cp,ctx),capture(ctx)))
            reference=(ROOT/'local-cases/example/phase3c-results/maps'/f'{sid}-level-5.npz') if a.case=='cesa' else (ROOT/'benchmarks/results/phase3a-grid-maps'/f'{sid}-level-5.npz')
            with np.load(reference,allow_pickle=False) as old:require(actual[0][::-1,:].copy().tobytes()==old['flat'].tobytes(),'Historical CONTROL map differs')
            if a.case=='cesa':
                frozen=json.loads((ROOT/'local-cases/example/phase3c-results/correctness-eight.json').read_text())['physics_checks'][sid]
                with tempfile.TemporaryDirectory(dir=OUT) as td:c.assert_frozen(frozen,c.frozen_state(cp,ctx,Path(td)))
            after_identity=f.mapped_identity();require(f.identity_signature(before_identity)==f.identity_signature(after_identity),'Mapped libraries changed')
            identities=[v for v in before_identity if v['name']=='solarpilot.so'];require(len(identities)==1 and identities[0]['sha256']==expected_sha and identities[0]['mapped_inode_matches_hashed_file'],'Wrong mapped ELF')
            result['rows'].append({'case_id':CASES[a.case],'state_id':sid,'label':LABELS[sid],'grid':grid,'operating_point':point,**timing,
                'all215_map_detail_summary_bitwise':True,'repeat_bitwise':True,'historical_control_map_bitwise':True,'frozen_physics_checked':a.case=='cesa',
                'loaded_before':before_identity,'loaded_after':after_identity})
            save(destination,result);print(a.id,LABELS[sid],('verified' if a.verify_only else 'median_s '+str(timing['statistics_s']['median'])),flush=True)
        finally:cp.data_free(ctx)
    require(len(result['rows'])==(1 if a.state else 4),'Expected exactly the requested scientific states')
    result['status']='passed';save(destination,result)

def host_run(a):
    prefix=OUT/a.id;OUT.mkdir(parents=True,exist_ok=True)
    require(not prefix.with_suffix('.json').exists() and not Path(str(prefix)+'-host.json').exists(),'Refuse to overwrite evidence')
    command=f'export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1; exec python benchmarks/original_baseline.py campaign --id {a.id} --case {a.case}'+(' --state '+a.state if a.state else '')
    host={'campaign_id':a.id,'utc':f.utc(),'policy_before':f.policy(),'sensors_before':f.sensors(),'sampling_interval_s':.1,'frames':[]}
    start=time.monotonic();initial=f.process_ticks();pid=None;tokens={}
    with Path(str(prefix)+'.log').open('x') as log:
        child=subprocess.Popen([str(ROOT/'scripts/annual_container.sh'),'bash','-c',command],stdout=log,stderr=subprocess.STDOUT)
        while child.poll() is None:
            if pid is None:
                for p in Path('/proc').glob('[0-9]*'):
                    try:
                        if owned_target((p/'cmdline').read_bytes().split(bytes([0])),a.id) and (p/'cwd').stat().st_ino==ROOT.stat().st_ino:pid=int(p.name);host['cgroup_before']=f.cgroups(pid);break
                    except OSError:pass
            if pid is not None:
                frame={'monotonic':time.monotonic(),**f.sensors(),'threads':[]}
                for p in Path(f'/proc/{pid}/task').glob('[0-9]*'):
                    try:
                        tid=int(p.name);tokens.setdefault(tid,len(tokens));r=f.proc_stat((p/'stat').read_text());r.update(f.status_fields(p/'status'));r['thread_token']=tokens[tid];frame['threads'].append(r)
                    except (OSError,ValueError,IndexError):pass
                if frame['threads']:host['frames'].append(frame)
                host['cgroup_last']=f.cgroups(pid)
            time.sleep(.1)
    usage=resource.getrusage(resource.RUSAGE_SELF)
    host.update(returncode=child.returncode,elapsed_s=time.monotonic()-start,policy_after=f.policy(),sensors_after=f.sensors(),
        external_process_activity=f.activity(initial,f.process_ticks(),time.monotonic()-start,{os.getpid(),pid,child.pid}),
        host_observer_cpu_s=usage.ru_utime+usage.ru_stime,frequency_interpretation='Sysfs snapshots, not effective APERF/MPERF frequency')
    save(Path(str(prefix)+'-host.json'),host)
    require(child.returncode==0 and host['frames'],'Failed campaign/observer; complete evidence retained')
    print(a.id,'host observation complete',flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['campaign','host-run']);p.add_argument('--id',required=True);p.add_argument('--case',choices=CASES,required=True)
    p.add_argument('--state',choices=list(LABELS));p.add_argument('--verify-only',action='store_true');p.add_argument('--library-dir');p.add_argument('--library-sha256');a=p.parse_args()
    require(a.id.replace('-','').isalnum(),'Safe immutable run ID required');require(a.action=='campaign' or not (a.verify_only or a.library_dir or a.library_sha256),'Host-run uses only the frozen measured binary')
    OUT.mkdir(parents=True,exist_ok=True);(campaign if a.action=='campaign' else host_run)(a)
if __name__=='__main__':main()
