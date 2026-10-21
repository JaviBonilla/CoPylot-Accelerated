#!/usr/bin/env python3
"""Positive-schema publication of eight Original API populations and reused Phase4S."""
import argparse,csv,hashlib,json,statistics
from pathlib import Path
from original_baseline import ROOT,OUT,LIBRARY,CASES,LABELS,save
from summarize_cpu_hardening import group,placement_matches
from summarize_cpu_repeatability import summarize_host

def collect(directory=OUT):
    blocks=[]
    for file in sorted(directory.glob('O-*.json')):
        if file.name.endswith('-host.json'):continue
        raw=json.loads(file.read_text());hostpath=directory/(raw['campaign_id']+'-host.json')
        if not hostpath.exists() or raw['role']!='formal':continue
        host=json.loads(hostpath.read_text())
        for r in raw['rows']:
            observation=summarize_host(host,r)
            valid=(raw['metadata']['library_sha256']==LIBRARY and host['returncode']==0 and r['all215_map_detail_summary_bitwise'] and r['repeat_bitwise'] and r['historical_control_map_bitwise'])
            placement=placement_matches(observation,[0])
            blocks.append({**{k:r[k] for k in ['case_id','state_id','label','first_call_s','warmup_samples_s','samples_s','statistics_s','cpu_window','measurement_monotonic']},
                'campaign_id':raw['campaign_id'],'source_valid':valid,'placement_verified':placement,
                'policy_unchanged':r['policy_unchanged'] and host['policy_before']==host['policy_after'],
                'raw_campaign_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'raw_host_sha256':hashlib.sha256(hostpath.read_bytes()).hexdigest(),
                'all215_map_detail_summary_bitwise':True,'raw_sample_reference':file.name,'grid':r['grid'],'operating_point':r['operating_point'],
                'source_metadata':raw['metadata'],'observation':observation})
            blocks[-1]['source_valid'] &= blocks[-1]['policy_unchanged']
    return blocks

def populations(blocks):
    expected=[(case,sid) for case in CASES.values() for sid in (['high-elevation','moderate-elevation','morning-offdesign','afternoon-offdesign'] if case==CASES['cesa'] else ['high','moderate','morning','afternoon'])]
    return [{'case_id':case,'state_id':sid,'label':LABELS[sid],**group([r for r in blocks if (r['case_id'],r['state_id'])==(case,sid)])} for case,sid in expected]

def public_attempt(row):
    keys=['case_id','state_id','label','campaign_id','first_call_s','warmup_samples_s','samples_s','source_valid','placement_verified','policy_unchanged','raw_campaign_sha256','raw_host_sha256','raw_sample_reference','all215_map_detail_summary_bitwise']
    v={k:row[k] for k in keys};w=row['cpu_window']
    v['statistics_s']={k:row['statistics_s'][k] for k in ['median','minimum','maximum','mean','stdev','coefficient_of_variation']}
    v['cpu_window']={k:w[k] for k in ['accepted','external_average_cores','thermal_throttle_count_increased'] if k in w}
    if not w['accepted']:v['cpu_window']['reason']='CPU window rejected; full reason retained in server raw evidence'
    return v

def stable_hardware(meta):
    t=meta['topology'];l={r['field']:r['data'] for r in t['lscpu']['lscpu']}
    return {**{k:t[k] for k in ['logical_cpus','physical_cores','sockets','affinity_sets']},
            'cpu':{k:l[k] for k in ['Architecture:','Vendor ID:','Model name:','CPU family:','Model:','Stepping:','Thread(s) per core:','Core(s) per socket:','Socket(s):','CPU max MHz:','CPU min MHz:']}}

def publish(output):
    rows=collect();groups=populations(rows);assert len(groups)==8 and all(g['passed'] for g in groups),'Eight qualified groups required'
    oldfile=ROOT/'benchmarks/results/phase4s-cpu-gpu-summary.json';old=json.loads(oldfile.read_text());assert old['stable_claims_promotable']
    accepted={(r['case_id'],r['state_id']):r for r in old['rows']};comparisons=[]
    sciencefile=ROOT/'benchmarks/results/phase4s-final-cpu-baseline.json';science=json.loads(sciencefile.read_text());assert science['passed']
    scientific={(r['case_id'],r['state_id']):r for r in science['rows'] if r['role']=='new_1t' and r['source_valid']}
    for g in groups:
        r=accepted[(g['case_id'],g['state_id'])];assert r['best_revalidated_cpu_threads']==24
        selected=[b for b in rows if b['case_id']==g['case_id'] and b['state_id']==g['state_id']]
        reference=scientific[(g['case_id'],g['state_id'])]
        assert all(b['grid']==reference['grid'] and b['operating_point']==reference['operating_point'] for b in selected),'Scientific preparation differs'
        original=g['reference_stability']['median_of_medians_s'];one=r['flat_1t_median_s'];mt=r['best_cpu_mt_median_s'];gpu=r['cuda_median_s']
        comparisons.append({'case_id':g['case_id'],'state_id':g['state_id'],'label':g['label'],'grid_nx':217 if g['case_id']==CASES['cesa'] else 222,'grid_ny':256 if g['case_id']==CASES['cesa'] else 87,
            'original_median_s':original,'flat_1t_median_s':one,'flat_24t_median_s':mt,'cuda_median_s':gpu,
            'original_over_flat1t':original/one,'original_over_flat24t':original/mt,'original_over_cuda':original/gpu,'flat1t_over_flat24t':one/mt,'flat24t_over_cuda':mt/gpu,
            'qualified_processes':len(g['complete_protocol_campaign_ids']),'inter_process_cv':g['reference_stability']['inter_campaign_median_cv'],'process_median_max_over_min':g['reference_stability']['maximum_over_minimum'],
            'correctness_bitwise_full_original_flat':True,'samples_trimmed':0})
    meta=rows[0]['source_metadata'];gpumeta=old['gpu_provenance']['metadata']
    assert stable_hardware(meta)==stable_hardware(gpumeta) and meta['compiler']==gpumeta['compiler'],'Hardware/compiler mismatch'
    assert meta['library_sha256']==gpumeta['library_sha256']==LIBRARY
    assert all(stable_hardware(b['source_metadata'])==stable_hardware(gpumeta) and b['source_metadata']['compiler']==gpumeta['compiler'] and b['source_metadata']['library_sha256']==LIBRARY and b['source_metadata']['original_harness_sha256']==meta['original_harness_sha256'] for b in rows),'Campaign hardware/compiler/binary/harness mismatch'
    output.mkdir(parents=True,exist_ok=True)
    audit=json.loads((OUT/'source-audit.json').read_text())
    value={'scope':'Eight scientific ordinary single-state APIs; no annual Original campaign','passed':True,'terminology':audit['recommended_label'],'source_audit':audit,
        'measured_library_sha256':LIBRARY,'measured_ssc_source':'0fd069b30343a08787f76247c4b1bb637e83bbe0',
        'measurement_root_revisions':sorted({r['source_metadata']['commits']['.'] for r in rows}),
        'harness_sha256':meta['original_harness_sha256'],'toolchain_image':'sha256:8e6e3752946ff2dde451b313cbaec2ea8e7b52221b21bfbcf53fb68dd4f4c42e',
        'environment':{k:meta[k] for k in ['machine','compiler','build_settings','precision','fast_math','topology','numerical_thread_environment']},
        'protocol':{'api':'CoPylot.simulate(nthreads=1)','backend':'cpu','intercept_path':'legacy','flux_path':'legacy','affinity':[0],'first_call_separate':True,'warmups':2,'samples_per_process':5,'minimum_qualified_processes':5,'within_process_cv_max':.05,'inter_process_median_cv_max':.03,'process_median_max_over_min':1.10,'no_trim':True,'getters_verification_outside_timing':True},
        'accepted_phase4s_reuse':{'directly_comparable':True,'same_binary':True,'same_machine_topology_compiler':True,'same_states_grids_physics_and_output_oracles':True,'same_ordinary_api_timing_boundary':True,'flat_or_cuda_performance_rerun':False,'source_file':oldfile.name,'source_sha256':hashlib.sha256(oldfile.read_bytes()).hexdigest(),'scientific_reference_file':sciencefile.name,'scientific_reference_sha256':hashlib.sha256(sciencefile.read_bytes()).hexdigest(),'cuda_original_protocol':'10 samples, separate first and3warmups; retained unchanged, not repackaged as five independent GPU processes'},
        'rows':comparisons,'groups':groups,'attempts':[public_attempt(r) for r in rows],
        'raw_private_inputs_arrays_and_host_frames':'Retained only in ignored server artifacts/original-baseline','annual_original_executed':False}
    save(output/'original-baseline-single-state.json',value)
    with (output/'original-baseline-single-state.csv').open('w',newline='') as stream:
        table=csv.DictWriter(stream,fieldnames=list(comparisons[0]),lineterminator='\n');table.writeheader();table.writerows(comparisons)
    print('Published eight states;',len(rows),'untrimmed process blocks')

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'benchmarks/results');p.add_argument('--status',action='store_true');a=p.parse_args()
    if a.status:print(json.dumps([{k:g[k] for k in ['case_id','state_id','passed','complete_protocol_campaign_ids','window_accepted_stability','reference_stability']} for g in populations(collect())],indent=2))
    else:publish(a.output)
if __name__=='__main__':main()
