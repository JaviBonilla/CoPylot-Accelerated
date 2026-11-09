#!/usr/bin/env python3
"""Verify every direct annual payload; never publish private per-state information."""
import argparse,json
from pathlib import Path
import numpy as np
import annual_matrix as a
import temporal_campaign as t
import gpu_temporal as g
from verify_temporal_outputs import verify as verify_cpu_storage

def rows(folder):
    files=sorted(folder.glob('worker-*.jsonl'))
    if not files:files=[folder/'states.jsonl']
    return [json.loads(line) for f in files for line in f.read_text().splitlines()]

def normalized_point(point):return {k:v for k,v in point.items() if k!='dispatch_index'}

def verify(case,mode,identifier,reference=None):
    gpu=mode=='gpu';folder=(a.OUT/'gpu/runs' if gpu else a.OUT/'cpu/campaigns')/identifier
    result=json.loads((folder/'result.json').read_text());plan=json.loads((t.OUT/(case+'-plan.json')).read_text());records=rows(folder)
    t.require(result['status']=='passed' and result['cpu_window']['accepted'],'Campaign status/window not qualified')
    expected={p['id']:p for p in plan['states']}
    t.require(len(records)==len(expected)==result['completed'] and {r['id'] for r in records}==set(expected),'Missing/duplicate annual states')
    t.require(all(normalized_point(r['state'])==expected[r['id']] for r in records),'Annual calendar/weather metadata differ')
    if not gpu:verify_cpu_storage(folder,plan)
    # Explicit local reference; no archived server paths and no implicit self-oracle.
    t.require(reference is not None,'An explicit full CPU reference campaign is required')
    reference=Path(reference).resolve()
    t.require(reference.is_dir(),'CPU reference campaign directory is missing')
    t.require(reference!=folder.resolve(),'Independent cross-mode reference required')
    ref_result=json.loads((reference/'result.json').read_text())
    t.require(ref_result['status']=='passed' and ref_result['case']==case and
              ref_result['completed']==len(expected),'Reference case/count/status differ')
    ref_records=rows(reference)
    t.require(len(ref_records)==len(expected) and
              {r['id'] for r in ref_records}==set(expected),'Reference coverage differs')
    t.require(all(normalized_point(r['state'])==expected[r['id']] for r in ref_records),
              'Reference annual calendar/weather differs')
    checked=0;maximum=0.;total=0;zero=0
    for record in records:
        file=folder/(str(record['id'])+'.npz')
        with np.load(file,allow_pickle=False) as arrays:values={k:arrays[k] for k in arrays.files}
        t.require(t.signature(values)==record['signature'],'Persisted output differs from runtime bytes')
        t.require(values['map'].shape==(plan['grid']['ny'],plan['grid']['nx']),'Wrong annual receiver shape')
        t.require(set(values)=={'map','detail_keys','summary_keys','summary_values','resolved_sun'}|{'detail_'+str(i) for i in range(len(values['detail_keys']))},'Incomplete standard schema')
        t.require(all(np.isfinite(v).all() for v in values.values() if v.dtype.kind in 'fiu'),'Nonfinite persisted value')
        t.require(values['resolved_sun'].tolist()==expected[record['id']]['sun'],'Wrong resolved sun')
        if expected[record['id']]['dni']==0:
            zero+=1;t.require(np.count_nonzero(values['map'])==0 and record['metrics']['incident_power_kw']==record['metrics']['absorbed_power_kw']==0,'Nonzero zero-DNI output')
        if folder!=reference:
            with np.load(reference/file.name,allow_pickle=False) as arrays:maximum=max(maximum,g.compare({k:arrays[k] for k in arrays.files},values,bitwise=not gpu))
            checked+=1
        total+=file.stat().st_size
    t.require(total==result['output_bytes'],'Annual payload size differs')
    t.require(len(list(folder.glob('*.npz')))==len(expected),'Unexpected extra/missing payload')
    v={'passed':True,'campaign_id':identifier,'case':case,'mode':mode,'expected_payloads':len(expected),'persisted_payloads_verified':len(records),
       'all_arrays_bitwise_equal_to_runtime':True,'complete_standard_schema':True,'all_numeric_arrays_finite':True,'exact_annual_state_metadata':True,
       'cross_mode_reference_states':checked,'cross_mode_bitwise':not gpu if checked else None,'cpu_cuda_existing_rtol':1e-9 if gpu else None,'cpu_cuda_existing_atol':1e-10 if gpu else None,
       'maximum_absolute_observable_error':maximum,'daylight_zero_dni_maps_verified_zero':zero,'stored_npz_bytes':total,
       'flushed_state_metadata_bytes':sum(f.stat().st_size for f in folder.glob('worker-*.jsonl')) if list(folder.glob('worker-*.jsonl')) else (folder/'states.jsonl').stat().st_size,
       'verification_outside_benchmark_window':True,'first_full_cpu_reference':folder==reference}
    t.write(folder/'annual-validation.json',v);print(identifier,'all',len(records),'annual payloads validated',flush=True)
    return v

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',choices=['commercial'],default='commercial')
    p.add_argument('--mode',choices=['original','refactored','cpu','gpu'],required=True)
    p.add_argument('--id',required=True)
    p.add_argument('--reference',type=Path,required=True,help='Another complete local CPU campaign; never the campaign being checked')
    args=p.parse_args();verify(args.case,args.mode,args.id,args.reference)
if __name__=='__main__':main()
