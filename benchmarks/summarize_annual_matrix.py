#!/usr/bin/env python3
"""One authoritative eight-row annual dataset, strictly aggregate for private CESA."""
import argparse,csv,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/annual-matrix'
CPU_REFERENCE=Path('/annual-cpu-reference');GPU_REFERENCE=Path('/annual-gpu-reference')
PAIRS=(('original','refactored'),('original','cpu'),('original','gpu'),('refactored','cpu'),('refactored','gpu'),('cpu','gpu'))

def digest(p):return hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
def save(p,value):Path(p).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def ratios(rows,field):
 by={r['execution_mode']:r for r in rows};assert set(by)=={'original','refactored','cpu','gpu'}
 return {left+'_over_'+right:by[left][field]/by[right][field] for left,right in PAIRS}

def public_row(case,mode,result,validation,plan,*,reused,source_reference,source_sha256,metadata_bytes):
 n=len(plan['states']);gpu=mode=='gpu';assert result['status']=='passed' and result['cpu_window']['accepted'] and result['completed']==n
 if not reused:assert validation['passed'] and validation['persisted_payloads_verified']==n
 elif gpu:assert validation['passed'] and validation['persisted_payloads_verified']==n and validation['cpu_agreement_existing_tolerance']
 else:assert validation['persisted_full_payloads_verified']==n and validation['all_arrays_bitwise_equal_to_runtime'] and validation['complete_schema']
 workers=result['active_states'] if gpu else result['states_in_parallel'];threads=1 if gpu else result['threads_per_state']
 strategy=(f'{workers} rolling independent GPU contexts; 1 CPU thread/context; FIFO; residency off' if gpu else f'{workers} independent states x {threads} CPU threads; '+result['scheduler'])
 assert not gpu or result['mode']=='pipeline' and not result['static_residency_enabled']
 assert result['states_per_s']==n/result['evaluation_wall_s'] and result['total_states_per_s']==n/result['total_wall_s']
 return {'case':case,'execution_mode':mode,'strategy':strategy,'concurrent_states_or_contexts':workers,'cpu_threads_per_state':threads,
  'requested_annual_hours':plan['requested'],'evaluated_daylight_states':n,'omitted_nighttime_states':plan['nighttime'],
  'daylight_zero_dni_states':sum(p['dni']==0 for p in plan['states']),'grid_nx':plan['grid']['nx'],'grid_ny':plan['grid']['ny'],
  'total_wall_s':result['total_wall_s'],'total_wall_min':result['total_wall_s']/60.,'evaluation_wall_s':result['evaluation_wall_s'],
  'evaluation_states_per_s':result['states_per_s'],'total_wall_states_per_s':result['total_states_per_s'],
  'standard_output_npz_bytes':result['output_bytes'],'flushed_state_metadata_bytes':metadata_bytes,'complete_standard_output_bytes':result['output_bytes']+metadata_bytes,
  'all_expected_outputs_produced':True,'persisted_full_outputs_verified':n,
  'cross_mode_validation':('accepted complete annual CPU/CUDA validation' if reused else ('full annual bitwise CPU reference comparison' if mode in ('original','refactored') else 'full annual CPU reference within existing tolerances' if gpu else 'full annual persisted outputs; independently cross-checked by serial annual runs')),
  'no_temporal_interpolation':True,'first_call_included':True,'warmups_removed':0,'validation_outside_timing':True,
  'cpu_window_qualified':True,'reused_accepted_campaign':reused,'campaign_id':result['identifier'],
  'library_sha256':result['library_sha256'],'benchmark_source_revisions':result['commits'],
  'core_campaign_harness_sha256':result['harness_sha256'],'source_reference':source_reference,'source_result_sha256':source_sha256}

def timed_metadata_bytes(folder):
 files=list(folder.glob('worker-*.jsonl'))
 if not files:files=[folder/'states.jsonl']
 return sum(f.stat().st_size for f in files)

def publish(destination):
 assert load(OUT/'runner.json')['status']=='measurements_complete','All six missing runs must finish first'
 plans={case:load(OUT/'cpu'/(case+'-plan.json')) for case in ['cesa','commercial']};rows=[];proof=[]
 for case in ['cesa','commercial']:
  for mode in ['original','refactored','cpu','gpu']:
   reused=case=='commercial' and mode in ('cpu','gpu')
   if reused:
    folder=(CPU_REFERENCE/'artifacts/phase5a/campaigns/Y2-commercial-24x1') if mode=='cpu' else (GPU_REFERENCE/'artifacts/phase5b/runs/F-commercial-K24')
    vfile=folder/('storage-validation.json' if mode=='cpu' else 'validation.json')
    assert load(folder/'plan.json')['points']==plans[case]['states'],'Reused annual workload mismatch'
   else:
    identifier=f'A-{case}-'+({'original':'original-1x1','refactored':'refactored-1x1','cpu':'cpu-12x2','gpu':'gpu-K24'}[mode])
    folder=OUT/('gpu/runs' if mode=='gpu' else 'cpu/campaigns')/identifier;vfile=folder/'annual-validation.json'
   rfile=folder/'result.json';result=load(rfile);validation=load(vfile)
   rows.append(public_row(case,mode,result,validation,plans[case],reused=reused,source_reference=result['identifier']+'/result.json',source_sha256=digest(rfile),metadata_bytes=timed_metadata_bytes(folder)))
   proof.append({'campaign_id':result['identifier'],'source_result_sha256':digest(rfile),'validation_sha256':digest(vfile),'reused':reused})
 # Authoritative full coverage: CPU1T and Original independently validate every CESA CPU reference state.
 for mode in ['original','refactored']:
  validation=load(OUT/'cpu/campaigns'/f'A-cesa-{mode}-1x1'/'annual-validation.json')
  assert validation['cross_mode_reference_states']==len(plans['cesa']['states']) and validation['cross_mode_bitwise']
 speeds={case:{'total_wall':ratios([r for r in rows if r['case']==case],'total_wall_s'),
               'evaluation_wall':ratios([r for r in rows if r['case']==case],'evaluation_wall_s')} for case in plans}
 value={'passed':True,'scope':'Eight complete directly evaluated annual optical campaigns; aggregate CESA data only','rows':rows,'speedups_by_case':speeds,
  'timing_boundary':'Evaluation: state updates + ordinary eager simulation + complete outputs/metrics + NPZ write + per-worker JSONL flush; total wall adds existing worker/context setup and teardown; verification excluded',
  'rate_definitions':{'evaluation_states_per_s':'evaluated daylight states / evaluation wall seconds','total_wall_states_per_s':'evaluated daylight states / total scheduler wall seconds'},
  'output_size_definition':'NPZ complete standard payloads and flushed per-state JSONL metadata reported separately and summed; auxiliary indices/plans/telemetry excluded; no fsync durability claim',
  'original_definition':'Retained original/legacy SolarPILOT Hermite execution path with documented safety and restoration fixes; not an untouched historical upstream binary',
  'cesa_annual_definition':'Existing authoritative private hourly EPW DNI; 8760 midpoint-hour evaluations on API non-leap calendar, retain elevation >0 including zero-DNI; prior four-day constant-DNI sweep is separate',
  'commercial_annual_definition':'Exact accepted 8760 Daggett TMY2 hourly rows and same midpoint calendar; 4403 daylight states; 4357 nighttime omitted',
  'strategy_selection':{'cesa_cpu':'12x2, selected best previous seasonal throughput, directly applied without claiming universal annual optimum','cesa_gpu':'24 rolling contexts, selected best previous seasonal evaluation throughput, final validated GPU binary, static residency off','commercial_cpu':'Accepted full annual Y2-commercial-24x1; dynamic_lpt','commercial_gpu':'Accepted final full annual F-commercial-K24; 24 rolling contexts, bounded FIFO, default stream, residency off'},
  'binary_provenance':{'545775e26ca3588c9a65c56c93e6f3f93d480446e4a04272497fad27acb5e017':{'ssc_source':'0fd069b30343a08787f76247c4b1bb637e83bbe0','role':'Accepted Phase4S CPU'},'d71dd38579fe9ea9038474371e233b2d7abc931f4770ea209e5b49275cdf98d8':{'ssc_source':'1233c8eb99f2650071b4386e918844d67709178b','role':'Accepted final Phase5B GPU'}},
  'hardware':{'machine':'canonical-gpu-server','cpu':'Intel Xeon w5-3423','physical_cores':12,'logical_cpus':24,'gpu':'NVIDIA RTX 6000 Ada Generation'},
  'toolchain':{'image':'sha256:8e6e3752946ff2dde451b313cbaec2ea8e7b52221b21bfbcf53fb68dd4f4c42e','compiler':'GCC13.3','precision':'double','fast_math':False},
  'new_annual_campaigns':6,'reused_annual_campaigns':2,'failed_or_incomplete_campaign_ids':load(OUT/'runner.json')['failed_or_incomplete'],
  'no_interpolation':True,'no_extrapolated_annual_results':True,'no_manuscript_changes':True,'no_numerical_code_changes':True,
  'proof_references':proof,'publication_harness_sha256':digest(__file__),'annual_wrapper_sha256':digest(ROOT/'benchmarks/annual_matrix.py'),
  'private_inputs_and_per_state_data':'Retained only in ignored server artifacts; no CESA site/calendar/aims/maps copied to public outputs'}
 destination.mkdir(parents=True,exist_ok=True);save(destination/'annual-benchmark-matrix.json',value)
 with (destination/'annual-benchmark-matrix.csv').open('w',newline='') as stream:
  table=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');table.writeheader()
  for r in rows:table.writerow({k:(json.dumps(v,sort_keys=True) if isinstance(v,dict) else v) for k,v in r.items()})
 print('Published authoritative eight-row annual matrix',flush=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=OUT/'public');args=p.parse_args();publish(args.output)
if __name__=='__main__':main()
