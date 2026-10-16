#!/usr/bin/env python3
"""Retain every forensic campaign and assess independent-process repeatability."""
import argparse
import csv
import json
from pathlib import Path
import statistics
import hashlib
from cpu_repeatability import EXPECTED_LIBRARY,identity_signature
from timing_counters import turbostat_rows,align_turbostat


def save(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def cv(values):return statistics.stdev(values)/statistics.mean(values) if len(values)>1 else 0.


def stability(values):
    return {'campaigns':len(values),'median_of_medians_s':statistics.median(values),
            'minimum_median_s':min(values),'maximum_median_s':max(values),
            'inter_campaign_median_cv':cv(values),'maximum_over_minimum':max(values)/min(values),
            'meets_declared_between_campaign_gates':len(values)>=5 and cv(values)<=.03 and max(values)/min(values)<=1.10}


def replication_groups(rows):
    groups=[]
    for prefix,protocol in [('C','uncontrolled_python_api'),('L','fixed_c_api_callsite_mod64_0')]:
        for case in sorted({r['case_id'] for r in rows}):
            selected=[r for r in rows if r['campaign_id'].startswith(prefix) and r['case_id']==case and r['threads']==24]
            if not selected:continue
            accepted=[r for r in selected if r['measurement_window_accepted']]
            eligible=[r for r in accepted if r['within_campaign_cv_gate_passed']]
            result={'case_id':case,'protocol':protocol,'all_declared_campaign_ids':[r['campaign_id'] for r in selected],
                    'accepted_campaign_ids':[r['campaign_id'] for r in accepted],
                    'all_declared_samples_retained':True,
                    'complete_protocol_campaign_ids':[r['campaign_id'] for r in eligible],
                    'complete_protocol_stability':stability([r['statistics_s']['median'] for r in eligible]) if eligible else None,
                    'all_within_campaign_cv_gates_passed':all(r['within_campaign_cv_gate_passed'] for r in selected)}
            if accepted:result.update(stability([r['statistics_s']['median'] for r in accepted]))
            groups.append(result)
    return groups


def stack_reproduction(rows):
    cases=[]
    for case in sorted({r['case_id'] for r in rows if r['stack_contrasts']}):
        contrasts=[s for r in rows if r['case_id']==case for s in r['stack_contrasts']]
        phases=[]
        for phase in (0,16,32,48):
            selected=[s for s in contrasts if s['callsite_mod64']==phase]
            values=[s['statistics_s']['median'] for s in selected]
            if values:phases.append({'callsite_mod64':phase,'contrast_blocks':len(values),
                                    'minimum_block_median_s':min(values),'maximum_block_median_s':max(values),
                                    'all_bitwise_equal':all(s['bitwise_equal'] for s in selected)})
        slow=[s['statistics_s']['median'] for s in contrasts if s['callsite_mod64']==48]
        fast=[s['statistics_s']['median'] for s in contrasts if s['callsite_mod64']!=48]
        cases.append({'case_id':case,'phases':phases,
                      'minimum_slow_over_maximum_fast':min(slow)/max(fast) if slow and fast else None,
                      'phase_48_predicts_over_2x_slowdown':bool(slow and fast and min(slow)>2*max(fast))})
    return cases


def summarize_host(host,row):
    start,end=row['measurement_monotonic']
    frames=[f for f in host['frames'] if start<=f['monotonic']<=end]
    if not frames:return {'observed':False}
    frequencies=[];allowed=set();cpus=set();nice=set();priorities=set();maximum=0;distinct=0
    for frame in frames:
        running=[t for t in frame['threads'] if t['state']=='R'];maximum=max(maximum,len(running))
        distinct=max(distinct,len({t['last_cpu'] for t in running}))
        for thread in frame['threads']:
            allowed.add(thread.get('Cpus_allowed_list'));cpus.add(thread['last_cpu']);nice.add(thread['nice']);priorities.add(thread['priority'])
        for thread in running:
            value=frame['frequency_khz'].get('policy'+str(thread['last_cpu']))
            if value is not None:frequencies.append(int(value)/1000)
    throttle_increase=False
    first=host['sensors_before']['thermal_throttle'];last=host['sensors_after']['thermal_throttle']
    for key,value in first.items():
        if value is not None and last.get(key) is not None:throttle_increase|=int(last[key])>int(value)
    result={'observed':True,'measurement_frames':len(frames),'maximum_runnable_tasks':maximum,
            'maximum_distinct_last_cpus_of_runnable_tasks':distinct,'observed_last_cpus':sorted(cpus),
            'allowed_cpu_sets':sorted(v for v in allowed if v is not None),'nice':sorted(nice),'priority':sorted(priorities),
            'thermal_throttle_increased':throttle_increase,
            'temperature_before':host['sensors_before']['temperatures_millidegrees'],
            'temperature_after':host['sensors_after']['temperatures_millidegrees'],
            'observer_cpu_average_cores':host['host_observer_cpu_s']/host['elapsed_s'],
            'cgroup_before':host['cgroup_before'],'cgroup_last':host.get('cgroup_last'),
            'external_process_activity':host['external_process_activity']}
    tasks=[t for f in frames for t in f['threads']]
    result['maximum_observed_task_migration_counter']=max((t.get('migrations') or 0 for t in tasks),default=0)
    result['task_speculation_controls']={key:sorted({str(t[key]) for t in tasks if key in t}) for key in
                                        ('Speculation_Store_Bypass','SpeculationIndirectBranch','Seccomp','Seccomp_filters')}
    if frequencies:result['reported_frequency_mhz']={'minimum':min(frequencies),'median':statistics.median(frequencies),'maximum':max(frequencies)}
    result['frequency_interpretation']=host['frequency_interpretation']
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input-dir',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);args=p.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    rows=[];identities={};failures=[];environments=[]
    capture=args.input_dir/'turbostat-capture-2.txt'
    anchor=args.input_dir/'clock-alignment.json'
    counters=turbostat_rows(capture.read_text()) if capture.exists() else []
    clock=json.loads(anchor.read_text()) if anchor.exists() else {}
    offset=clock['utc_epoch_s']-clock['monotonic'] if clock else None
    for path in sorted(args.input_dir.glob('*.json')):
        if path.name.endswith('-host.json') or path.name in ('initial.json','tool-probes.json','idle-gate.json'):continue
        data=json.loads(path.read_text())
        if data.get('phase')!='4R' or 'metadata' not in data:continue
        host_path=path.with_name(path.stem+'-host.json')
        host=json.loads(host_path.read_text()) if host_path.exists() else None
        key=data['campaign_id'];library=data['metadata']['library_sha256']
        if library!=EXPECTED_LIBRARY:raise ValueError('Frozen numerical library changed')
        environments.append({'campaign_id':key,'environment':data['environment'],'metadata':data['metadata'],
                             'math_bindings':data.get('math_bindings'),'process_affinity':data.get('process_affinity'),
                             'python_executable_sha256':data['python_executable_sha256'],
                             'forensic_harness_sha256':data['forensic_harness_sha256'],
                             'utc':data['utc'],'host':{k:host[k] for k in ('utc','uptime_before','uptime_after','loadavg_before','loadavg_after','policy_before','policy_after','execution_context')} if host else None})
        for item in data['rows']:
            signature=identity_signature(item['loaded_after'])
            identity_key=hashlib.sha256(json.dumps(signature).encode()).hexdigest()
            identities.setdefault(identity_key,item['loaded_after'])
            observed=summarize_host(host,item) if host else {'observed':False}
            pilot=key=='A1-cesa'
            row={'campaign_id':key,'case_id':item['case_id'],'state_id':item['state_id'],'threads':data['threads'],
                 'campaign_status':data['status'],'measurement_window_accepted':item['cpu_window']['accepted'],
                 'pilot_wrong_observer_target':pilot,'history':data['history'],
                 'first_call_s':item['first_call_s'],'warmup_samples_s':item['warmup_samples_s'],
                 'sustained_samples_s':item['sustained_samples_s'],'samples_s':item['samples_s'],
                 'statistics_s':item['statistics_s'],'cpu_window':item['cpu_window'],'usage':item['usage'],
                 'loaded_identity_group':identity_key,'loaded_set_unchanged':item['loaded_set_unchanged'],
                 'all_mapped_file_inodes_verified':all(r.get('mapped_inode_matches_hashed_file',False) for r in item['loaded_after']),
                 'floating_point_before':item.get('floating_point_before'),'floating_point_after':item.get('floating_point_after'),
                 'historical_control_map_bitwise':item.get('historical_control_map_bitwise'),
                 'bitwise_repeat':item['bitwise_repeat'],'observation':observed,
                 'grid':item.get('grid'),'operating_point':item.get('operating_point'),
                 'measurement_monotonic':item['measurement_monotonic'],
                 'observed_fixed_callsite_phases':item.get('observed_fixed_callsite_phases',[]),
                 'stack_contrasts':item.get('stack_contrasts',[]),'profile_contrast':item.get('profile_contrast'),
                 'allocation_layout':item.get('allocation_layout'),
                 'mapped_image_layout':[{k:r[k] for k in ('name','image_base_mod2m') if k in r} for r in item['loaded_after']],
                 'within_campaign_cv_gate_passed':item['statistics_s']['coefficient_of_variation']<=.05,
                 'raw_campaign_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                 'raw_host_trace_sha256':hashlib.sha256(host_path.read_bytes()).hexdigest() if host else None}
            row['effective_counters']=align_turbostat(counters,item['measurement_monotonic'],offset,data['threads']) if counters and clock else None
            for contrast in row['stack_contrasts']:
                contrast['observation']=summarize_host(host,contrast) if host else {'observed':False}
            rows.append(row)
    for host_path in sorted(args.input_dir.glob('*-host.json')):
        host=json.loads(host_path.read_text())
        if host.get('returncode',0):failures.append({'campaign_id':host['campaign_id'],'returncode':host['returncode'],'classification':'container_or_process_startup_failure','measurement_samples_retained':False})
    # Keep the original uncontrolled replication separate from controlled calling-stack runs.
    groups=replication_groups(rows)
    stack=stack_reproduction(rows)
    report={'phase':'4R','status':'causal_callsite_variable_reproduced' if len(stack)==2 and all(c['phase_48_predicts_over_2x_slowdown'] for c in stack) else 'forensic_evidence_retained','frozen_library_sha256':EXPECTED_LIBRARY,
            'declared_gates':{'external_cpu_average_cores_max':.5,'within_campaign_cv_max':.05,'inter_campaign_median_cv_max':.03,'maximum_over_minimum_median_max':1.10},
            'clean_fresh_process_groups':groups,'stack_reproduction':stack,'rows':rows,'startup_failures':failures,
            'limitations':['Reported sysfs frequency is not effective frequency; timestamped turbostat provides separate effective-frequency evidence only in overlapping windows',
                           'Host observer is active; its cost is reported and not subtracted',
                           'Old Phase 4 mapped-library sets were not captured retrospectively',
                           'Unobserved historical causes cannot be rejected from current clean runs alone',
                           'Controlled callsite timings describe the diagnostic bridge, not an automatic repair of the normal Python API']}
    save(args.output_dir/'phase4r-repeatability.json',report)
    save(args.output_dir/'phase4r-environment.json',{'phase':'4R','campaigns':environments,'loaded_library_groups':identities,
                                                  'available_tool_probes':json.loads((args.input_dir/'tool-probes.json').read_text()),
                                                  'idle_gate':json.loads((args.input_dir/'idle-gate.json').read_text()) if (args.input_dir/'idle-gate.json').exists() else None,
                                                  'boundary_verification':json.loads((args.input_dir/'boundaries.json').read_text()) if (args.input_dir/'boundaries.json').exists() else None,
                                                  'counter_capture':{'clock_anchor':clock,'clock_anchor_final':json.loads((args.input_dir/'clock-alignment-final.json').read_text()) if (args.input_dir/'clock-alignment-final.json').exists() else None,
                                                                     'turbostat_sha256':hashlib.sha256(capture.read_bytes()).hexdigest() if capture.exists() else None}})
    fields=['campaign_id','case_id','state_id','threads','campaign_status','measurement_window_accepted',
            'pilot_wrong_observer_target','fixed_c_api_callsite_mod64','first_call_s','warmup_samples_s','sustained_samples_s','samples_s','median_s','mean_s','minimum_s','maximum_s','stdev_s','cv',
            'within_campaign_cv_gate_passed','loaded_identity_group','raw_campaign_sha256']
    with (args.output_dir/'phase4r-campaigns.csv').open('w',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for row in rows:
            item={k:row[k] for k in fields if k in row}
            item['fixed_c_api_callsite_mod64']=row['history'].get('fixed_c_api_callsite_mod64')
            for key in ('warmup_samples_s','sustained_samples_s','samples_s'):item[key]=json.dumps(row[key])
            for name in ('median','mean','minimum','maximum','stdev'):item[name+'_s']=row['statistics_s'][name]
            item['cv']=row['statistics_s']['coefficient_of_variation'];writer.writerow(item)
    print('Retained campaigns:',len(rows),'loaded-library groups:',len(identities),'startup failures:',len(failures))

if __name__=='__main__':main()
