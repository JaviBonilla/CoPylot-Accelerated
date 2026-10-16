#!/usr/bin/env python3
"""Retain all Phase 4S attempts and enforce stack/ordinary API regression gates."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import statistics
from cpu_hardening import OLD_LIBRARY,NEW_LIBRARY
from cpu_repeatability import identity_signature
from summarize_cpu_repeatability import stability,summarize_host


def save(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def role(identifier):
    for pattern,name in [(r'R\d+','rsp'),(r'F\d+','final_24t'),(r'N1-\d+','new_1t'),(r'N12-\d+','new_12t'),
                         (r'B1-\d+','old_1t'),(r'B12-\d+','old_12t'),
                         (r'D12-old','old_12t_rsp'),(r'D12-new','new_12t_rsp')]:
        if re.fullmatch(pattern,identifier):return name
    return 'pilot'


def distribution(values):
    if not values:return None
    return {'samples':len(values),'median_s':statistics.median(values),'minimum_s':min(values),'maximum_s':max(values),
            'cv':statistics.stdev(values)/statistics.mean(values) if len(values)>1 else 0.}


def placement_matches(observation,affinity):
    def cpus(value):
        result=set()
        for part in value.split(','):
            ends=[int(v) for v in part.split('-')]
            result.update(range(ends[0],ends[-1]+1))
        return result
    return bool(observation.get('observed') and observation.get('maximum_runnable_tasks',0)>=len(affinity)
                and observation.get('maximum_distinct_last_cpus_of_runnable_tasks',0)>=len(affinity)
                and observation.get('allowed_cpu_sets')
                and all(cpus(value)==set(affinity) for value in observation['allowed_cpu_sets'])
                and not observation.get('thermal_throttle_increased',True))


def group(blocks):
    accepted=[b for b in blocks if b['source_valid'] and b['cpu_window']['accepted']]
    complete=[b for b in accepted if b['statistics_s']['coefficient_of_variation']<=.05 and b['placement_verified']]
    between=stability([b['statistics_s']['median'] for b in accepted]) if accepted else None
    reference=stability([b['statistics_s']['median'] for b in complete]) if complete else None
    return {'all_campaign_ids':[b['campaign_id'] for b in blocks],
            'window_accepted_campaign_ids':[b['campaign_id'] for b in accepted],
            'complete_protocol_campaign_ids':[b['campaign_id'] for b in complete],
            'window_accepted_stability':between,'reference_stability':reference,
            'all_retained_sample_distribution':distribution([v for b in blocks for v in b['samples_s']]),
            'window_accepted_sample_distribution':distribution([v for b in accepted for v in b['samples_s']]),
            'all_within_process_cv_gates_passed':all(b['statistics_s']['coefficient_of_variation']<=.05 for b in blocks),
            'within_process_cv_failures':[b['campaign_id'] for b in blocks if b['statistics_s']['coefficient_of_variation']>.05],
            'passed':bool(reference and reference['meets_declared_between_campaign_gates'] and between and between['meets_declared_between_campaign_gates'])}


def rsp_groups(rows):
    result=[]
    for case in sorted({r['case_id'] for r in rows if r['role']=='rsp'}):
        selected=[r for r in rows if r['case_id']==case and r['role']=='rsp']
        phases=[]
        for phase in (0,16,32,48):
            blocks=[{**s,'campaign_id':r['campaign_id'],'source_valid':r['source_valid']} for r in selected
                    for s in r['stack_contrasts'] if s['callsite_mod64']==phase]
            phases.append({'callsite_mod64':phase,**group(blocks)})
        medians=[p['window_accepted_stability']['median_of_medians_s'] for p in phases if p['window_accepted_stability']]
        ratio=max(medians)/min(medians) if len(medians)==4 else None
        process_ratios=[]
        for row in selected:
            blocks=[s for s in row['stack_contrasts'] if s['cpu_window']['accepted']]
            if len(blocks)==4:
                values=[s['statistics_s']['median'] for s in blocks]
                process_ratios.append({'campaign_id':row['campaign_id'],'slowest_over_fastest_position_median':max(values)/min(values)})
        passed=ratio is not None and ratio<=1.10 and all(p['passed'] for p in phases) and all(p['slowest_over_fastest_position_median']<=1.10 for p in process_ratios)
        result.append({'case_id':case,'positions':phases,'slowest_over_fastest_position_median':ratio,
                       'per_process_position_ratios':process_ratios,'passed':passed})
    return result


def baseline_groups(rows):
    output=[]
    for kind in ('final_24t','new_1t','new_12t','old_1t','old_12t'):
        selected=[r for r in rows if r['role']==kind]
        keys=sorted({(r['case_id'],r['state_id'],r['threads']) for r in selected})
        for case,state,threads in keys:
            blocks=[r for r in selected if (r['case_id'],r['state_id'],r['threads'])==(case,state,threads)]
            output.append({'role':kind,'case_id':case,'state_id':state,'threads':threads,**group(blocks)})
    return output


def reduced_scaling(groups,rows):
    """Compare like-for-like high states; old three-process controls stay descriptive."""
    output=[]
    for case in sorted({g['case_id'] for g in groups}):
        state='high-elevation' if case=='cesa-i-private-restored' else 'high'
        selected={g['role']:g for g in groups if g['case_id']==case and g['state_id']==state}
        if not all(k in selected for k in ('new_1t','new_12t','final_24t','old_1t','old_12t')):continue
        def reference(kind):
            g=selected[kind]
            return g['reference_stability'] or g['window_accepted_stability']
        refs={key:reference(key) for key in selected}
        if not all(refs.values()):continue
        medians={key:value['median_of_medians_s'] for key,value in refs.items()}
        controlled=[]
        for row in rows:
            if row['case_id']==case and row['role'] in ('old_12t_rsp','new_12t_rsp'):
                controlled.append({'campaign_id':row['campaign_id'],'library_comparison':row['library_comparison'],
                                   'source_valid':row['source_valid'],
                                   'positions':[{k:s[k] for k in ('callsite_mod64','samples_s','statistics_s','cpu_window','placement_verified')}
                                                for s in row['stack_contrasts']]})
        old_zero=next((s for r in controlled if r['library_comparison']=='old' and r['source_valid']
                       for s in r['positions'] if s['callsite_mod64']==0 and s['cpu_window']['accepted'] and s['placement_verified']),None)
        output.append({'case_id':case,'state_id':state,'median_s':medians,
                       'new_over_old_1t':medians['new_1t']/medians['old_1t'],
                       'new_over_old_12t':medians['new_12t']/medians['old_12t'],
                       'new_1t_over_12t':medians['new_1t']/medians['new_12t'],
                       'new_1t_over_24t':medians['new_1t']/medians['final_24t'],
                       'new_12t_over_24t_smt_benefit':medians['new_12t']/medians['final_24t'],
                       'new_12t_over_old_controlled_phase0':medians['new_12t']/old_zero['statistics_s']['median'] if old_zero else None,
                       'matched_12t_stack_interventions':controlled,
                       'process_statistics':refs,
                       'old_control_scope':'Three fresh processes per count, descriptive matched controls; not a five-process stable baseline.'})
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--gpu-json',type=Path)
    parser.add_argument('--check-rsp',action='store_true');parser.add_argument('--check-final',action='store_true')
    args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    rows=[];environments=[];identities={};failures=[]
    for path in sorted(args.input_dir.glob('*.json')):
        data=json.loads(path.read_text())
        if not isinstance(data,dict) or data.get('phase')!='4S' or not all(k in data for k in ('campaign_id','mode','metadata','rows')):continue
        expected=NEW_LIBRARY if data['library_comparison']=='new' else OLD_LIBRARY
        if data['metadata']['library_sha256']!=expected:raise ValueError('Campaign target hash changed')
        if data['affinity']!=data['metadata']['topology']['affinity_sets'][str(data['threads'])]:
            raise ValueError('Campaign affinity differs from the established topology')
        identifier=data['campaign_id'];host_path=path.with_name(path.stem+'-host.json')
        host=json.loads(host_path.read_text()) if host_path.exists() else None
        kind=role(identifier)
        expected_threads={'rsp':24,'final_24t':24,'new_1t':1,'new_12t':12,'old_1t':1,'old_12t':12,
                          'old_12t_rsp':12,'new_12t_rsp':12}.get(kind)
        if expected_threads is not None and data['threads']!=expected_threads:
            raise ValueError('Campaign role and thread count disagree')
        declared_library='old' if kind in ('old_1t','old_12t','old_12t_rsp') else 'new'
        if kind!='pilot' and data['library_comparison']!=declared_library:
            raise ValueError('Campaign role and numerical library disagree')
        source_pin='0fd069b30343a08787f76247c4b1bb637e83bbe0' if declared_library=='new' else '581a006ec4afb0f0d1f34b1d0d8382736e83d865'
        if kind!='pilot' and data['metadata']['source_pin_for_library']!=source_pin:
            raise ValueError('Campaign source pin differs from its declared binary')
        environments.append({'campaign_id':identifier,'role':kind,'metadata':data['metadata'],'mode':data['mode'],
                             'library_comparison':data['library_comparison'],'environment':data['environment'],
                             'python_executable_sha256':data['python_executable_sha256'],'affinity':data['affinity'],
                             'host_policy_before':host['policy_before'] if host else None,'host_policy_after':host['policy_after'] if host else None,
                             'raw_campaign_sha256':sha(path),'raw_host_sha256':sha(host_path) if host else None})
        for item in data['rows']:
            signature=identity_signature(item['loaded_after']);identity_key=hashlib.sha256(json.dumps(signature).encode()).hexdigest()
            identities.setdefault(identity_key,item['loaded_after'])
            loaded_ok=identity_signature(item['loaded_before'])==signature and all(x.get('mapped_inode_matches_hashed_file',False) for x in item['loaded_after'])
            bridge_loaded=any(x['name']=='libcpu_fp_probe.so' for x in item['loaded_after'])
            if data['mode']=='ordinary' and bridge_loaded:raise ValueError('Ordinary API campaign loaded the RSP bridge')
            numerical=all(item.get(k,False) for k in ('bitwise_maps_details_summary','all215_bitwise','flat_1t_oracle_bitwise','historical_control_map_bitwise'))
            policy_unchanged=bool(host and host['policy_before']==host['policy_after'])
            valid=bool(host and host.get('returncode')==0 and policy_unchanged and data['status']!='running' and not data['metadata']['source_worktree_dirty'] and loaded_ok and numerical
                       and len(item['warmup_samples_s'])==2 and len(item['samples_s'])>=5)
            observed=summarize_host(host,item) if host else {'observed':False}
            def placed(observation):
                return placement_matches(observation,data['affinity'])
            row={k:v for k,v in item.items() if k not in ('loaded_before','loaded_after')}
            row.update(campaign_id=identifier,role=kind,threads=data['threads'],mode=data['mode'],library_comparison=data['library_comparison'],
                       campaign_status=data['status'],source_valid=valid,loaded_identity_group=identity_key,
                       rsp_bridge_loaded=bridge_loaded,policy_unchanged=policy_unchanged,
                       observation=observed,placement_verified=placed(observed),raw_campaign_sha256=sha(path),
                       raw_host_sha256=sha(host_path) if host else None)
            for contrast in row['stack_contrasts']:
                observation=summarize_host(host,contrast) if host else {'observed':False}
                contrast['observation']=observation;contrast['placement_verified']=placed(observation)
                if contrast['observed_phases']!=[contrast['callsite_mod64']]:raise ValueError('Forced phase was not verified')
            rows.append(row)
        if host and host.get('returncode'):failures.append({'campaign_id':identifier,'returncode':host['returncode'],'raw_host_sha256':sha(host_path)})
    rsp=rsp_groups(rows);baselines=baseline_groups(rows)
    rsp_pass=len(rsp)==2 and all(c['passed'] for c in rsp)
    final=[g for g in baselines if g['role']=='final_24t'];ones=[g for g in baselines if g['role']=='new_1t']
    twelves=[g for g in baselines if g['role']=='new_12t']
    final_pass=rsp_pass and len(final)==8 and len(ones)==8 and len(twelves)==8 and all(g['passed'] for g in final+ones+twelves)
    protocol={'within_process_cv_max':.05,'inter_process_median_cv_max':.03,'max_min_process_median_max':1.10,
              'max_min_position_median_max':1.10,'minimum_complete_processes':5,'external_cpu_average_cores_max':.5,
              'rejected_samples_retained':True,'individual_samples_trimmed':False}
    save(args.output_dir/'phase4s-rsp-regression.json',{'phase':'4S','passed':rsp_pass,'gates':protocol,'cases':rsp,
                                                     'rows':[r for r in rows if r['mode']=='rsp']})
    save(args.output_dir/'phase4s-final-cpu-baseline.json',{'phase':'4S','passed':final_pass,'gates':protocol,'groups':baselines,
                                                         'rows':[r for r in rows if r['mode']=='ordinary'],'startup_failures':failures})
    save(args.output_dir/'phase4s-reduced-scaling.json',{'phase':'4S','rows':reduced_scaling(baselines,rows),
                                                     'candidate_groups':[g for g in baselines if g['role'] in ('new_1t','new_12t','final_24t')],
                                                     'counts_remeasured':[1,12,24],'counts_not_remeasured':[2,4,8]})
    plan_path=args.input_dir/'campaign-plan.json'
    amendments=[]
    for name in ('additional-attempts.json','scaling-amendment.json','supplemental-attempts.json'):
        path=args.input_dir/name
        if path.exists():amendments.append({'id':name,'sha256':sha(path),'declaration':json.loads(path.read_text())})
    save(args.output_dir/'phase4s-environment.json',{'phase':'4S','campaigns':environments,'loaded_identity_groups':identities,
                                                  'campaign_plan':json.loads(plan_path.read_text()) if plan_path.exists() else None,
                                                  'protocol_amendments':amendments,'publisher_source_sha256':sha(Path(__file__))})
    fields=['campaign_id','role','case_id','state_id','threads','campaign_status','source_valid','placement_verified',
            'cpu_window_accepted','within_process_cv_passed','first_call_s','warmup_samples_s','samples_s','median_s','minimum_s','maximum_s','cv','loaded_identity_group']
    with (args.output_dir/'phase4s-final-cpu-baseline.csv').open('w',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for row in rows:
            if row['role'] not in ('final_24t','new_1t','new_12t'):continue
            result={k:row[k] for k in fields if k in row}
            result.update(cpu_window_accepted=row['cpu_window']['accepted'],within_process_cv_passed=row['statistics_s']['coefficient_of_variation']<=.05,
                          median_s=row['statistics_s']['median'],minimum_s=row['statistics_s']['minimum'],maximum_s=row['statistics_s']['maximum'],cv=row['statistics_s']['coefficient_of_variation'])
            for k in ('warmup_samples_s','samples_s'):result[k]=json.dumps(row[k])
            writer.writerow(result)
    if args.gpu_json:
        gpu=json.loads(args.gpu_json.read_text())
        if gpu['status']!='passed' or gpu['stage']!='cuda':raise ValueError('GPU campaign did not pass')
        if gpu['metadata']['library_sha256'] not in (OLD_LIBRARY,NEW_LIBRARY):raise ValueError('GPU campaign uses an undeclared binary')
        if not all(len(row['samples_s'])==10 and row['cpu_window'].get('external_average_cores',1)<.5
                   and not row['cpu_window'].get('thermal_throttle_count_increased',True) for row in gpu['rows']):
            raise ValueError('CUDA sample count or CPU window did not meet the established protocol')
        if len(gpu['rows'])!=8 or len({(r['case_id'],r['state_id']) for r in gpu['rows']})!=8:
            raise ValueError('CUDA comparison requires all eight distinct states')
        save(args.output_dir/'phase4s-cuda-control-timings.json',gpu)
        comparisons=[]
        for mt in final:
            one=next((g for g in ones if (g['case_id'],g['state_id'])==(mt['case_id'],mt['state_id'])),None)
            cuda=next((r for r in gpu['rows'] if (r['case_id'],r['state_id'])==(mt['case_id'],mt['state_id'])),None)
            if not(one and cuda and mt['reference_stability'] and one['reference_stability']):continue
            candidates=[g for g in baselines if g['role'] in ('new_1t','new_12t','final_24t') and g['case_id']==mt['case_id'] and g['state_id']==mt['state_id'] and g['passed']]
            if not candidates:continue
            best=min(candidates,key=lambda g:g['reference_stability']['median_of_medians_s'])
            t1=one['reference_stability']['median_of_medians_s'];tm=best['reference_stability']['median_of_medians_s'];tg=cuda['statistics_s']['median']
            comparisons.append({'case_id':mt['case_id'],'state_id':mt['state_id'],'best_revalidated_cpu_threads':best['threads'],
                                'revalidated_candidate_counts':[g['threads'] for g in candidates],
                                'flat_1t_median_s':t1,'best_cpu_mt_median_s':tm,'cuda_median_s':tg,
                                'flat_1t_over_best_cpu_mt':t1/tm,'flat_1t_over_cuda':t1/tg,'best_cpu_mt_over_cuda':tm/tg,
                                'cpu_complete_processes':best['reference_stability']['campaigns'],'cpu_inter_process_cv':best['reference_stability']['inter_campaign_median_cv'],
                                'cpu_1t_complete_processes':one['reference_stability']['campaigns'],'cuda_samples_s':cuda['samples_s'],
                                'stable_cpu_reference':best['passed'] and one['passed']})
        save(args.output_dir/'phase4s-cpu-gpu-summary.json',{'phase':'4S','stable_claims_promotable':final_pass and len(comparisons)==8,
                                                         'gpu_provenance':{'source_sha256':sha(args.gpu_json),'metadata':gpu['metadata'],
                                                                           'historical_phase4_reuse':gpu['metadata']['library_sha256']==OLD_LIBRARY},
                                                         'rows':comparisons,'scope':'Best stable revalidated count among the per-state candidates listed in each row; no universal CPU optimum is claimed.'})
    print('Retained rows',len(rows),'RSP passed',rsp_pass,'final baseline passed',final_pass,flush=True)
    if args.check_rsp and not rsp_pass:raise SystemExit('RSP regression gates not met; all attempts retained')
    if args.check_final and not final_pass:raise SystemExit('Final CPU gates not met; all attempts retained')


if __name__=='__main__':main()
