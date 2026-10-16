#!/usr/bin/env python3
"""Phase 4S: ordinary API campaigns and four-phase regression on fixed workloads."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import time
import cpu_repeatability as forensic

ROOT=Path(__file__).resolve().parents[1]
OLD_LIBRARY=forensic.EXPECTED_LIBRARY
NEW_LIBRARY='545775e26ca3588c9a65c56c93e6f3f93d480446e4a04272497fad27acb5e017'
LIBRARIES={'old':('phase4-cuda',OLD_LIBRARY),'new':('phase4s-cuda',NEW_LIBRARY)}
OUT=ROOT/'artifacts/phase4s'


def save(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def owned_target(argv,campaign_id):
    return len(argv)>4 and argv[1]==b'benchmarks/cpu_hardening.py' and argv[2]==b'campaign' and campaign_id.encode() in argv


def campaign(args):
    import cpu_multicore as c
    import numpy as np
    import tempfile
    from unittest.mock import patch
    for key in list(os.environ):
        if key.startswith('SOLARPILOT_'):os.environ.pop(key)
    directory,expected_library=LIBRARIES[args.library]
    os.environ['COPILOT_LIB_DIR']=str(ROOT/'build'/directory/'lib')
    c.topology_cache=c.topology();affinity=c.topology_cache['affinity_sets'][str(args.threads)]
    os.sched_setaffinity(0,set(affinity));cp=c.api()
    plan=json.loads((ROOT/'local-cases/example/phase3c-results/plan.json').read_text())
    metadata=c.metadata()
    if metadata['library_sha256']!=expected_library:raise RuntimeError('Numerical library does not match declared target')
    density_source=(ROOT/'ssc/solarpilot/Flux.cpp').read_bytes() if args.library=='new' else subprocess.check_output(['git','-C',str(ROOT/'ssc'),'show','581a006ec4afb0f0d1f34b1d0d8382736e83d865:solarpilot/Flux.cpp'])
    metadata['density_source_sha256']=hashlib.sha256(density_source).hexdigest()
    metadata['source_worktree_dirty']=bool(subprocess.check_output(['git','-C',str(ROOT/'ssc'),'status','--porcelain'],text=True).strip())
    metadata['source_pin_for_library']=metadata['commits']['ssc'] if args.library=='new' else '581a006ec4afb0f0d1f34b1d0d8382736e83d865'
    metadata['forensic_harness_sha256']=forensic.digest(__file__)
    probe=None
    if args.mode=='rsp':
        probe=ctypes.CDLL(str(ROOT/'artifacts/phase4r/libcpu_fp_probe.so'))
        probe.phase4r_call_with_stack_phase.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_uint]
        probe.phase4r_call_with_stack_phase.restype=ctypes.c_bool
        probe.phase4r_last_callsite_mod64.restype=ctypes.c_uint32
        signature=ctypes.CFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_int,ctypes.c_bool)
        noop=signature(lambda context,threads,aim:True);function=ctypes.cast(cp.pdll.sp_simulate,ctypes.c_void_p)
    optical_path=OUT/'libold_optical_export.so' if args.library=='old' else ROOT/'build'/directory/'libcpu_optical_state_bridge.so'
    optical=ctypes.CDLL(str(optical_path))
    optical.phase4_optical_capture.argtypes=[ctypes.c_void_p];optical.phase4_optical_capture.restype=ctypes.c_void_p
    optical.phase4_optical_equal.argtypes=[ctypes.c_void_p,ctypes.c_void_p];optical.phase4_optical_equal.restype=ctypes.c_bool
    optical.phase4_optical_free.argtypes=[ctypes.c_void_p];optical.phase4_optical_free.restype=None
    optical.phase4_optical_size.argtypes=[ctypes.c_void_p];optical.phase4_optical_size.restype=ctypes.c_size_t
    optical.phase4_optical_copy.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t];optical.phase4_optical_copy.restype=ctypes.c_bool
    result={'phase':'4S','campaign_id':args.campaign_id,'status':'running','mode':args.mode,
            'library_comparison':args.library,'threads':args.threads,'affinity':affinity,
            'all_states':args.all_states,'phase_rotation':args.rotation,'case_order':args.cases.split(','),
            'metadata':metadata,'environment':{k:os.environ.get(k) for k in forensic.ENV_KEYS},
            'python_executable_sha256':forensic.digest('/proc/self/exe'),'rows':[]}
    destination=OUT/(args.campaign_id+'.json')
    if destination.exists():raise RuntimeError('Refuse to overwrite evidence')
    for name in args.cases.split(','):
        case=forensic.CASES[name]
        for sid,grid,point,context in c.contexts(cp,case,plan,args.all_states):
            snapshot=None
            try:
                loaded_before=forensic.mapped_identity()
                with patch.dict(os.environ,{**c.PLAIN,'SOLARPILOT_INTERCEPT_PATH':'flat'}):
                    def measure(call):
                        first=call();warm=[call() for _ in range(2)]
                        before=c.cpu_window();usage_before=resource.getrusage(resource.RUSAGE_SELF);start=time.monotonic()
                        samples=[call() for _ in range(args.repetitions)]
                        end=time.monotonic();usage_after=resource.getrusage(resource.RUSAGE_SELF);after=c.cpu_window()
                        try:window=c.validate_window(before,after);window['accepted']=True
                        except RuntimeError as error:window={'accepted':False,'reason':str(error),'before':before,'after':after}
                        return {'first_call_s':first,'warmup_samples_s':warm,'samples_s':samples,
                                'statistics_s':c.distribution(samples),'measurement_monotonic':[start,end],'cpu_window':window,
                                'usage':{'user_s':usage_after.ru_utime-usage_before.ru_utime,'system_s':usage_after.ru_stime-usage_before.ru_stime,
                                         'voluntary_context_switches':usage_after.ru_nvcsw-usage_before.ru_nvcsw,
                                         'involuntary_context_switches':usage_after.ru_nivcsw-usage_before.ru_nivcsw}}
                    primary=measure(lambda:c.simulate(cp,context,args.threads));expected=c.state(cp,context)
                    snapshot=optical.phase4_optical_capture(context);c.require(bool(snapshot),'Optical snapshot failed')
                    c.simulate(cp,context,args.threads);c.equal(expected,c.state(cp,context))
                    contrasts=[]
                    if probe:
                        phases=(0,16,32,48);phases=phases[args.rotation:]+phases[:args.rotation]
                        for phase in phases:
                            c.require(probe.phase4r_call_with_stack_phase(noop,None,args.threads,0),'Calibration failed')
                            padding=(int(probe.phase4r_last_callsite_mod64())-phase)%64;observed=[]
                            def call():
                                start=time.perf_counter();ok=probe.phase4r_call_with_stack_phase(function,context,args.threads,padding)
                                elapsed=time.perf_counter()-start;actual=int(probe.phase4r_last_callsite_mod64());observed.append(actual)
                                c.require(ok and actual==phase,'Actual callsite phase differs');return elapsed
                            contrast=measure(call);c.equal(expected,c.state(cp,context))
                            c.require(optical.phase4_optical_equal(snapshot,context),'Full optical state differs')
                            contrasts.append({**contrast,'callsite_mod64':phase,'observed_phases':sorted(set(observed)),
                                              'bitwise_maps_details_summary':True,'all215_bitwise':True})
                    # Frozen original-binary 1T oracle was captured before this campaign.
                    # Compare every optical/map/detail/summary byte outside timing.
                    from cpu_hardening_equivalence import arrays
                    size=optical.phase4_optical_size(snapshot);values=np.empty(size,dtype=np.float64)
                    c.require(optical.phase4_optical_copy(snapshot,values.ctypes.data,size),'Optical export failed')
                    current=arrays(expected,values)
                    with np.load(OUT/'cross-binary-arrays'/f'{case}-{sid}.npz',allow_pickle=False) as saved:
                        c.require(set(saved.files)==set(current),'Original 1T schema differs')
                        c.require(all(saved[k].dtype==v.dtype and saved[k].shape==v.shape and saved[k].tobytes()==v.tobytes() for k,v in current.items()),'Original 1T numerical bytes differ')
                    reference=(ROOT/'local-cases/example/phase3c-results/maps'/f'{sid}-level-5.npz') if name=='cesa' else (ROOT/'benchmarks/results/phase3a-grid-maps'/f'{sid}-level-5.npz')
                    with np.load(reference) as saved:c.require(expected[0][::-1,:].copy().tobytes()==saved['flat'].tobytes(),'Historical CONTROL differs')
                    if name=='cesa':
                        frozen=json.loads((ROOT/'local-cases/example/phase3c-results/correctness-eight.json').read_text())['physics_checks'][sid]
                        with tempfile.TemporaryDirectory(dir=OUT) as td:c.assert_frozen(frozen,c.frozen_state(cp,context,Path(td)))
                loaded_after=forensic.mapped_identity()
                c.require(forensic.identity_signature(loaded_before)==forensic.identity_signature(loaded_after),'Mapped library identity changed')
                result['rows'].append({'case_id':case,'state_id':sid,'grid':grid,'operating_point':point,**primary,
                                       'stack_contrasts':contrasts,'bitwise_maps_details_summary':True,'flat_1t_oracle_bitwise':True,
                                       'flat_1t_oracle_library_sha256':OLD_LIBRARY,
                                       'all215_bitwise':True,'historical_control_map_bitwise':True,'frozen_physics_checked':name=='cesa',
                                       'loaded_before':loaded_before,'loaded_after':loaded_after})
                save(destination,result)
                print(args.campaign_id,name,sid,'median ms',round(primary['statistics_s']['median']*1000,3),flush=True)
            finally:
                if snapshot:optical.phase4_optical_free(snapshot)
                cp.data_free(context)
    accepted=all(r['cpu_window']['accepted'] and all(s['cpu_window']['accepted'] for s in r['stack_contrasts']) for r in result['rows'])
    result['status']='passed' if accepted else 'retained_rejected_window';save(destination,result)


def host_run(args):
    OUT.mkdir(parents=True,exist_ok=True);prefix=OUT/args.campaign_id
    if prefix.with_suffix('.json').exists() or Path(str(prefix)+'-host.json').exists():raise RuntimeError('Refuse to overwrite evidence')
    environment='export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1'
    command=f'{environment}; exec python benchmarks/cpu_hardening.py campaign --campaign-id {args.campaign_id} --cases {args.cases} --threads {args.threads} --mode {args.mode} --library {args.library} --rotation {args.rotation} --repetitions {args.repetitions} '+('--all-states' if args.all_states else '')
    host={'phase':'4S','campaign_id':args.campaign_id,'utc':forensic.utc(),'uptime_before':forensic.read('/proc/uptime'),
          'loadavg_before':forensic.read('/proc/loadavg'),'policy_before':forensic.policy(),'sensors_before':forensic.sensors(),
          'execution_context':'Fresh ordinary Python process in fresh unchanged pinned container; no RSP bridge loaded in ordinary mode',
          'sampling_interval_s':.1,'frames':[]}
    start=time.monotonic();initial=forensic.process_ticks();previous=initial;previous_scan=start;pid=None;tokens={};cgroup_before=None
    with Path(str(prefix)+'.log').open('w') as log:
        process=subprocess.Popen([str(ROOT/'scripts/remote_container.sh'),'--gpu','bash','-c',command],stdout=log,stderr=subprocess.STDOUT)
        while process.poll() is None:
            if pid is None:
                for p in Path('/proc').glob('[0-9]*'):
                    try:
                        if owned_target((p/'cmdline').read_bytes().split(b'\0'),args.campaign_id) and (p/'cwd').stat().st_ino==ROOT.stat().st_ino:
                            pid=int(p.name);cgroup_before=forensic.cgroups(pid);break
                    except OSError:pass
            if pid is not None:
                frame={'monotonic':time.monotonic(),'elapsed_s':time.monotonic()-start,**forensic.sensors(),'threads':[]}
                for p in Path(f'/proc/{pid}/task').glob('[0-9]*'):
                    try:
                        tid=int(p.name);tokens.setdefault(tid,len(tokens));row=forensic.proc_stat((p/'stat').read_text())
                        row.update(forensic.status_fields(p/'status'));row['thread_token']=tokens[tid]
                        row['migrations']=next((int(s.split(':',1)[1]) for s in (forensic.read(p/'sched') or '').splitlines() if s.strip().startswith('se.nr_migrations')),None)
                        frame['threads'].append(row)
                    except (OSError,ValueError,IndexError):pass
                if frame['threads']:host['frames'].append(frame)
                cg=forensic.cgroups(pid)
                if cg.get('available'):host['cgroup_last']=cg
                if time.monotonic()-previous_scan>=1:
                    now=time.monotonic();current=forensic.process_ticks()
                    frame['external_process_activity']=forensic.activity(previous,current,now-previous_scan,{os.getpid(),pid,process.pid})
                    previous=current;previous_scan=now
            time.sleep(.1)
    usage=resource.getrusage(resource.RUSAGE_SELF)
    host.update(returncode=process.returncode,elapsed_s=time.monotonic()-start,uptime_after=forensic.read('/proc/uptime'),
                loadavg_after=forensic.read('/proc/loadavg'),policy_after=forensic.policy(),sensors_after=forensic.sensors(),cgroup_before=cgroup_before,
                external_process_activity=forensic.activity(initial,forensic.process_ticks(),time.monotonic()-start,{os.getpid(),pid,process.pid}),
                host_observer_cpu_s=usage.ru_utime+usage.ru_stime,
                frequency_interpretation='Read-only sysfs snapshots; not effective APERF/MPERF frequency')
    save(Path(str(prefix)+'-host.json'),host)
    if process.returncode:raise RuntimeError('Campaign failed; complete evidence retained')
    if not host['frames']:raise RuntimeError('No owned numerical target observed')
    print(args.campaign_id,'host observation complete',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['campaign','host-run'])
    parser.add_argument('--campaign-id',required=True);parser.add_argument('--cases',choices=['cesa','commercial','cesa,commercial','commercial,cesa'],default='cesa,commercial')
    parser.add_argument('--threads',type=int,choices=[1,12,24],default=24);parser.add_argument('--mode',choices=['ordinary','rsp'],default='ordinary')
    parser.add_argument('--library',choices=['old','new'],default='new');parser.add_argument('--rotation',type=int,choices=range(4),default=0)
    parser.add_argument('--all-states',action='store_true');parser.add_argument('--repetitions',type=int,default=5)
    args=parser.parse_args()
    if not args.campaign_id or not args.campaign_id.replace('-','').isalnum() or args.repetitions<5:parser.error('Require a safe identifier and at least five measured samples')
    OUT.mkdir(parents=True,exist_ok=True)
    (campaign if args.action=='campaign' else host_run)(args)


if __name__=='__main__':main()
