#!/usr/bin/env python3
"""Phase 4R forensic sampling; numerical code and system policies stay unchanged."""
import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
EXPECTED_LIBRARY='68bfa6a02a2933a17d6b314c690787eaaa1ba8d27a2e45ae010fcc1d02d090ab'
CASES={'cesa':'cesa-i-private-restored','commercial':'ssc-mspt-8790-optical-reference'}
ENV_KEYS=('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS',
          'LD_LIBRARY_PATH','LD_PRELOAD','GLIBC_TUNABLES','MALLOC_ARENA_MAX','PYTHONHASHSEED')


def save(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()
def read(path):
    try:return Path(path).read_text().strip()
    except (OSError,ValueError):return None


def proc_stat(text):
    fields=text.rsplit(') ',1)[1].split()
    return {'state':fields[0],'cpu_ticks':int(fields[11])+int(fields[12]),
            'priority':int(fields[15]),'nice':int(fields[16]),'threads':int(fields[17]),'last_cpu':int(fields[36])}


def status_fields(path):
    text=read(path)
    if text is None:return {}
    values=dict(line.split(':',1) for line in text.splitlines() if ':' in line)
    return {k:values[k].strip() for k in ('Cpus_allowed_list','voluntary_ctxt_switches','nonvoluntary_ctxt_switches','Speculation_Store_Bypass','SpeculationIndirectBranch','Seccomp','Seccomp_filters') if k in values}


def cgroups(pid):
    text=read(f'/proc/{pid}/cgroup') or ''
    group=next((line[3:] for line in text.splitlines() if line.startswith('0::')),None)
    if group is None:return {'available':False}
    base=Path('/sys/fs/cgroup');path=base/group.lstrip('/');rows=[]
    for depth in range(16):
        values={k:read(path/k) for k in ('cpu.max','cpu.weight','cpu.stat','cpu.pressure','cpuset.cpus.effective','cpuset.mems.effective')}
        rows.append({'ancestor_depth':depth,'values':values})
        if path==base:break
        if base not in path.parents:break
        path=path.parent
    return {'available':True,'ancestors':rows}


def policy():
    base=Path('/sys/devices/system/cpu')
    pstate={p.name:read(p) for p in (base/'intel_pstate').glob('*') if p.is_file()}
    rows={}
    for path in sorted((base/'cpufreq').glob('policy*')):
        rows[path.name]={k:read(path/k) for k in ('scaling_driver','scaling_governor','scaling_min_freq','scaling_max_freq',
                       'energy_performance_preference','cpuinfo_max_freq')}
    return {'intel_pstate':pstate,'cpufreq':rows}


def sensors():
    base=Path('/sys/devices/system/cpu')
    return {'frequency_khz':{p.parent.name:read(p) for p in (base/'cpufreq').glob('policy*/scaling_cur_freq')},
            'thermal_throttle':{str(p.relative_to(base)):read(p) for p in base.glob('cpu[0-9]*/thermal_throttle/*_throttle_count')},
            'temperatures_millidegrees':{p.parent.name:read(p) for p in Path('/sys/class/thermal').glob('thermal_zone*/temp')}}


def process_ticks():
    result={}
    for p in Path('/proc').glob('[0-9]*'):
        try:
            text=(p/'stat').read_text();s=proc_stat(text)
            result[int(p.name)]={'ticks':s['cpu_ticks'],'name':text.split('(',1)[1].rsplit(') ',1)[0]}
        except (OSError,ValueError,IndexError):pass
    return result


def activity(before,after,elapsed,exclude):
    rows=[]
    for pid,row in after.items():
        if pid in exclude or pid not in before:continue
        ticks=row['ticks']-before[pid]['ticks']
        if ticks>0:rows.append({'process_name':row['name'],'average_cores':ticks/os.sysconf('SC_CLK_TCK')/elapsed})
    return sorted(rows,key=lambda r:r['average_cores'],reverse=True)[:12]


def mapped_identity():
    paths={Path('/proc/self/exe').resolve():None};bases={}
    for line in Path('/proc/self/maps').read_text().splitlines():
        fields=line.split(None,5)
        if len(fields)==6 and fields[5].startswith('/') and ('.so' in fields[5] or 'x' in fields[1]):
            path=Path(fields[5]);paths[path]=(fields[3],int(fields[4]))
            base=int(fields[0].split('-')[0],16)-int(fields[2],16)
            bases[path]=min(bases.get(path,base),base)
    rows=[]
    for path,mapping in sorted(paths.items()):
        try:
            stat=path.stat();device=f'{os.major(stat.st_dev):02x}:{os.minor(stat.st_dev):02x}'
            matches=mapping is None or mapping==(device,stat.st_ino)
            rows.append({'name':path.name,'mapped_path':str(path).replace(str(ROOT),'<workspace>'),
                         'sha256':digest(path),'bytes':stat.st_size,'mapped_inode_matches_hashed_file':matches,
                         'image_base_mod_2m':bases.get(path,0)%(2*1024*1024)})
        except OSError:rows.append({'name':path.name,'unreadable':True})
    return rows


def identity_signature(rows):return sorted((r['name'],r.get('sha256')) for r in rows)


def fp_environment(probe):
    if probe is None:return {'available':False}
    mxcsr=int(probe.phase4r_mxcsr())
    return {'available':True,'mxcsr':mxcsr,'mxcsr_control':mxcsr & 0xffc0,
            'flush_to_zero':bool(mxcsr & (1<<15)),'denormals_are_zero':bool(mxcsr & (1<<6)),
            'x87_control':int(probe.phase4r_x87_control())}


def math_bindings(library):
    class DlInfo(ctypes.Structure):
        _fields_=[('filename',ctypes.c_char_p),('base',ctypes.c_void_p),('symbol',ctypes.c_char_p),('symbol_address',ctypes.c_void_p)]
    dladdr=ctypes.CDLL(None).dladdr;dladdr.argtypes=[ctypes.c_void_p,ctypes.POINTER(DlInfo)];dladdr.restype=ctypes.c_int
    result={}
    for name in ('exp','atan2','acos','sin','cos','sincos'):
        pointer=ctypes.cast(getattr(library,name),ctypes.c_void_p).value;info=DlInfo()
        if dladdr(pointer,ctypes.byref(info)):
            result[name]={'library':Path(info.filename.decode()).name,'offset':pointer-info.base,
                          'symbol':info.symbol.decode() if info.symbol else None}
    return result


def benchmark(args):
    import cpu_multicore as c
    from unittest.mock import patch
    for key in list(os.environ):
        if key.startswith('SOLARPILOT_'):os.environ.pop(key)
    c.topology_cache=c.topology();os.sched_setaffinity(0,set(c.topology_cache['affinity_sets'][str(args.threads)]))
    cp=c.api();plan=json.loads(args.plan.read_text())
    probe_path=ROOT/'artifacts/phase4r/libcpu_fp_probe.so';probe=None
    if probe_path.exists():
        probe=ctypes.CDLL(str(probe_path));probe.phase4r_mxcsr.restype=ctypes.c_uint32;probe.phase4r_x87_control.restype=ctypes.c_uint16
    allocation_probe=None
    if os.environ.get('PHASE4R_ALLOCATION_TRACE')=='1':
        allocation_probe=ctypes.CDLL(None);allocation_probe.phase4r_allocation_count.restype=ctypes.c_uint
        allocation_probe.phase4r_allocation_value.argtypes=[ctypes.c_uint,ctypes.c_uint];allocation_probe.phase4r_allocation_value.restype=ctypes.c_uint64
    result={'phase':'4R','campaign_id':args.campaign_id,'status':'running','threads':args.threads,
            'history':{'allocation_trace_enabled':bool(allocation_probe),'order':args.cases.split(','),'sustained_calls_before_measurement':args.sustained,'idle_seconds_before_measurement':args.idle_seconds,'profile_contrast_after_measurement':args.profile_contrast},
            'utc':utc(),'environment':{k:os.environ.get(k) for k in ENV_KEYS},
            'metadata':c.metadata(),'forensic_harness_sha256':digest(__file__),'python_executable_sha256':digest('/proc/self/exe'),
            'process_affinity':sorted(os.sched_getaffinity(0)),'math_bindings':math_bindings(cp.pdll),'rows':[]}
    if result['metadata']['library_sha256']!=EXPECTED_LIBRARY:raise RuntimeError('Frozen Phase 4 library differs')
    for name in args.cases.split(','):
        generator=c.contexts(cp,CASES[name],plan,False);sid,grid,point,context=next(generator)
        try:
            before_identity=mapped_identity();fp_before=fp_environment(probe)
            with patch.dict(os.environ,{**c.PLAIN,'SOLARPILOT_INTERCEPT_PATH':'flat'}):
                first=c.simulate(cp,context,args.threads)
                warm=[c.simulate(cp,context,args.threads) for _ in range(2)]
                sustained=[c.simulate(cp,context,args.threads) for _ in range(args.sustained)]
                if args.idle_seconds:time.sleep(args.idle_seconds)
                before=c.cpu_window();usage_before=resource.getrusage(resource.RUSAGE_SELF);measurement_start=time.monotonic()
                samples=[c.simulate(cp,context,args.threads) for _ in range(args.repetitions)]
                measurement_end=time.monotonic();usage_after=resource.getrusage(resource.RUSAGE_SELF);after=c.cpu_window()
                try:window=c.validate_window(before,after);window['accepted']=True
                except RuntimeError as error:window={'accepted':False,'reason':str(error),'before':before,'after':after}
                expected=c.state(cp,context);c.simulate(cp,context,args.threads);c.equal(expected,c.state(cp,context))
                contrast=None
                if args.profile_contrast:
                    file=args.output.parent/f'{args.campaign_id}-{name}-profile.csv'
                    with patch.dict(os.environ,{'SOLARPILOT_PROFILE_FILE':str(file),'SOLARPILOT_INTERCEPT_PROFILE':'1'}):
                        profile_wall=c.simulate(cp,context,args.threads)
                    import csv
                    scopes={r[1]:{'calls':int(r[2]),'inclusive_s':float(r[3]),'exclusive_s':float(r[4])} for r in csv.reader(file.read_text().splitlines())}
                    follow=[c.simulate(cp,context,args.threads) for _ in range(5)]
                    c.equal(expected,c.state(cp,context))
                    contrast={'profile_wall_s':profile_wall,'scopes':scopes,'unprofiled_followup_samples_s':follow,'bitwise_equal':True}

            after_identity=mapped_identity()
            import numpy as np
            if name=='cesa':reference=ROOT/'local-cases/example/phase3c-results/maps'/f'{sid}-level-5.npz'
            else:reference=ROOT/'benchmarks/results/phase3a-grid-maps'/f'{sid}-level-5.npz'
            with np.load(reference) as saved:historical_equal=expected[0][::-1,:].copy().tobytes()==saved['flat'].tobytes()
            if not historical_equal:raise RuntimeError('Historical CONTROL map changed')
            loaded_core=[r for r in after_identity if r['name']=='solarpilot.so']
            if len(loaded_core)!=1 or loaded_core[0].get('sha256')!=EXPECTED_LIBRARY:raise RuntimeError('Actually loaded core differs from frozen target')
            result['rows'].append({'case_id':CASES[name],'state_id':sid,'grid':grid,'operating_point':point,
                    'profile_contrast':contrast,'floating_point_before':fp_before,'floating_point_after':fp_environment(probe),'first_call_s':first,'warmup_samples_s':warm,'sustained_samples_s':sustained,'samples_s':samples,
                    'statistics_s':c.distribution(samples),'measurement_monotonic':[measurement_start,measurement_end],'cpu_window':window,'bitwise_repeat':True,
                    'usage':{'user_s':usage_after.ru_utime-usage_before.ru_utime,'system_s':usage_after.ru_stime-usage_before.ru_stime,
                             'voluntary_context_switches':usage_after.ru_nvcsw-usage_before.ru_nvcsw,
                             'involuntary_context_switches':usage_after.ru_nivcsw-usage_before.ru_nivcsw},
                    'loaded_before':before_identity,'loaded_after':after_identity,
                    'allocation_layout':([{'bytes':int(allocation_probe.phase4r_allocation_value(i,0)),
                         'address_mod_4k':int(allocation_probe.phase4r_allocation_value(i,1))%4096,
                         'address_mod_2m':int(allocation_probe.phase4r_allocation_value(i,1))%(2*1024*1024)}
                         for i in range(min(4096,allocation_probe.phase4r_allocation_count()))] if allocation_probe else None),
                    'historical_control_map_bitwise':historical_equal,'loaded_set_unchanged':identity_signature(before_identity)==identity_signature(after_identity)})
            save(args.output,result)
            print(args.campaign_id,name,args.threads,'median ms',round(result['rows'][-1]['statistics_s']['median']*1000,3),flush=True)
        finally:cp.data_free(context)
    result['status']='passed' if all(r['cpu_window']['accepted'] for r in result['rows']) else 'retained_rejected_window'
    save(args.output,result)


def target_argv(argv,campaign_id):
    return (len(argv)>4 and argv[1]==b'benchmarks/cpu_repeatability.py'
            and argv[2]==b'campaign' and campaign_id.encode() in argv)


def host_run(args):
    """Host observer sees external processes and cgroup ancestors outside Docker."""
    output=ROOT/'artifacts/phase4r';output.mkdir(parents=True,exist_ok=True)
    prefix=output/args.campaign_id
    if prefix.with_suffix('.json').exists() or Path(str(prefix)+'-host.json').exists():raise RuntimeError('Refusing to overwrite evidence')
    env='export COPILOT_LIB_DIR=/workspace/build/phase4-cuda/lib OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1'
    if args.hash_seed!='inherit':env+=' PYTHONHASHSEED='+args.hash_seed
    if args.allocation_trace:env+=' PHASE4R_ALLOCATION_TRACE=1 LD_PRELOAD=/workspace/artifacts/phase4r/libcpu_allocation_probe.so'
    # These arguments are validated CLI choices or an alphanumeric identifier.
    command=f'{env}; exec python benchmarks/cpu_repeatability.py campaign --campaign-id {args.campaign_id} --cases {args.cases} --threads {args.threads} --sustained {args.sustained} --repetitions {args.repetitions} --idle-seconds {args.idle_seconds} {'--profile-contrast' if args.profile_contrast else ''} --plan local-cases/example/phase3c-results/plan.json --output artifacts/phase4r/{args.campaign_id}.json'
    result={'phase':'4R','campaign_id':args.campaign_id,'utc':utc(),'uptime_before':read('/proc/uptime'),
            'loadavg_before':read('/proc/loadavg'),'policy_before':policy(),'sensors_before':sensors(),
            'execution_context':'Fresh Python process in fresh pinned Phase 4 Docker container, unchanged limits',
            'sampling_interval_s':args.sample_interval,'frames':[]}
    start=time.monotonic();before_processes=process_ticks();previous_processes=before_processes;previous_scan=start;pid=None;tokens={};cgroup_before=None
    with Path(str(prefix)+'.log').open('w') as log:
        process=subprocess.Popen([str(ROOT/'scripts/remote_container.sh'),'--gpu','bash','-c',command],stdout=log,stderr=subprocess.STDOUT)
        while process.poll() is None:
            if pid is None:
                for p in Path('/proc').glob('[0-9]*'):
                    try:
                        argv=(p/'cmdline').read_bytes().split(b'\0')
                        if target_argv(argv,args.campaign_id):
                            if (p/'cwd').stat().st_ino==ROOT.stat().st_ino:pid=int(p.name);cgroup_before=cgroups(pid);break
                    except OSError:pass
            if pid is not None:
                frame={'monotonic':time.monotonic(),'elapsed_s':time.monotonic()-start,**sensors(),'threads':[]}
                for p in Path(f'/proc/{pid}/task').glob('[0-9]*'):
                    try:
                        tid=int(p.name);tokens.setdefault(tid,len(tokens));row=proc_stat((p/'stat').read_text())
                        row.update(status_fields(p/'status'));row['thread_token']=tokens[tid]
                        sched=read(p/'sched') or ''
                        row['migrations']=next((int(s.split(':',1)[1]) for s in sched.splitlines() if s.strip().startswith('se.nr_migrations')),None)
                        frame['threads'].append(row)
                    except (OSError,ValueError,IndexError):pass
                cg=cgroups(pid)
                frame['cgroup_leaf']=cg.get('ancestors',[])[:1]
                if frame['threads']:result['frames'].append(frame)
                if cg.get('available'):result['cgroup_last']=cg
                if time.monotonic()-previous_scan>=1:
                    now=time.monotonic();current=process_ticks()
                    frame['external_process_activity']=activity(previous_processes,current,now-previous_scan,{os.getpid(),pid,process.pid})
                    previous_processes=current;previous_scan=now
            time.sleep(.1 if pid is None else args.sample_interval)
    result.update(returncode=process.returncode,elapsed_s=time.monotonic()-start,uptime_after=read('/proc/uptime'),
                  loadavg_after=read('/proc/loadavg'),policy_after=policy(),sensors_after=sensors(),cgroup_before=cgroup_before)
    result['external_process_activity']=activity(before_processes,process_ticks(),result['elapsed_s'],{os.getpid(),pid,process.pid})
    own=resource.getrusage(resource.RUSAGE_SELF)
    result['host_observer_cpu_s']=own.ru_utime+own.ru_stime
    result['frequency_interpretation']='scaling_cur_freq snapshots are reported frequency, not an APERF/MPERF effective-frequency measurement'
    save(Path(str(prefix)+'-host.json'),result)
    if process.returncode:raise RuntimeError('Diagnostic process failed; complete log retained')
    if not result['frames']:raise RuntimeError('No owned numerical process observed')
    print(args.campaign_id,'host observation complete',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['campaign','host-run'])
    p.add_argument('--campaign-id',required=True);p.add_argument('--cases',choices=['cesa','commercial','cesa,commercial','commercial,cesa'],required=True)
    p.add_argument('--threads',type=int,choices=[1,12,24],default=24);p.add_argument('--sustained',type=int,default=0)
    p.add_argument('--sample-interval',type=float,default=.1)
    p.add_argument('--allocation-trace',action='store_true')
    p.add_argument('--hash-seed',choices=['inherit','0','1','2'],default='inherit')
    p.add_argument('--idle-seconds',type=float,default=0);p.add_argument('--profile-contrast',action='store_true')
    p.add_argument('--repetitions',type=int,default=5);p.add_argument('--plan',type=Path);p.add_argument('--output',type=Path)
    args=p.parse_args()
    if not args.campaign_id.replace('-','').isalnum():p.error('Campaign identifier must be alphanumeric with hyphens')
    if args.sample_interval<=0 or args.sustained<0 or args.idle_seconds<0 or args.repetitions<5:p.error('Require nonnegative history and at least five measured samples')
    if args.action=='campaign':
        if args.plan is None or args.output is None:p.error('Campaign requires private plan and ignored output')
        if args.output.exists():p.error('Refusing to overwrite evidence')
        if not args.output.resolve().is_relative_to(ROOT/'artifacts'):p.error('Raw evidence must stay ignored')
        benchmark(args)
    else:host_run(args)


if __name__=='__main__':main()
