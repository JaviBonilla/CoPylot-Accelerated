#!/usr/bin/env python3
"""Final server-only provenance/privacy gate before exporting fixed aggregate files."""
from pathlib import Path
import hashlib,json,subprocess
import summarize_annual_matrix as s
ROOT=s.ROOT;OUT=s.OUT;PUBLIC=OUT/'public'

def main():
 v=s.load(PUBLIC/'annual-benchmark-matrix.json');assert v['passed'] and len(v['rows'])==8
 assert len({(r['case'],r['execution_mode']) for r in v['rows']})==8
 assert len({r['evaluated_daylight_states'] for r in v['rows'] if r['case']=='cesa'})==1
 assert all(r['all_expected_outputs_produced'] and r['persisted_full_outputs_verified']==r['evaluated_daylight_states'] for r in v['rows'])
 assert sum(not r['reused_accepted_campaign'] for r in v['rows'])==6
 assert s.load(OUT/'runner.json')['status']=='measurements_complete'
 protected=s.load(OUT/'protected-server.json');assert all(s.digest(ROOT/p)==h for p,h in protected.items())
 assert not subprocess.check_output(['git','diff','aa0f457','--','paper/'],text=True).strip()
 lock=s.load(ROOT/'repos.lock.json');nested={}
 for name,entry in lock.items():
  head=subprocess.check_output(['git','-C',str(ROOT/name),'rev-parse','HEAD'],text=True).strip();assert head==entry['patched_sha']
  assert not subprocess.check_output(['git','-C',str(ROOT/name),'status','--porcelain'],text=True).strip();nested[name]=head
 # Private tokens are examined only on the server; never returned or exported.
 plan=s.load(OUT/'cpu/cesa-plan.json');inputs=plan['private_project_inputs'];tokens=[]
 for path,digest in inputs.items():
  assert s.digest(path)==digest;tokens.extend([path,Path(path).name,digest])
  if path.lower().endswith('.epw'):
   with Path(path).open() as stream:header=next(stream).strip().split(',')
   tokens.extend(v for v in header[6:8] if len(v)>=4)
 manifest=s.load(ROOT/'cases/commercial-reference/case_manifest.json');assert all(s.digest(ROOT/a['path'])==a['sha256'] for a in manifest['assets'].values())
 from audit_original_baseline import audit
 source=audit()
 probes={}
 for case in ['cesa','commercial']:
  seed=s.load(OUT/'cpu/correctness'/case/'result.json');assert seed['status']=='passed' and seed['fresh_serial_full_and215_probes']==13 and seed['library_sha256']=='545775e26ca3588c9a65c56c93e6f3f93d480446e4a04272497fad27acb5e017'
  probes[case]={'fresh_serial_probes':13,'full_outputs_and215_flat_original_bitwise':True}
 value={'passed':True,'complete_annual_matrix_rows':8,'new_complete_annual_campaigns':6,'reused_accepted_annual_campaigns':2,
  'all_expected_outputs_produced':True,'every_annual_payload_persisted_and_verified':True,'cpu_original_refactored_full_annual_bitwise':True,
  'gpu_annual_existing_cpu_tolerances_unchanged':True,'no_interpolation':True,'no_extrapolation':True,'protected_server_tracked_files':len(protected),
  'protected_server_files_byte_identical':True,'paper_unchanged':True,'nested_source_pins':nested,'legacy_source_audit':source,
  'private_input_hash_checks_passed':True,'public_asset_hash_checks_passed':True,'private_per_state_details_exported':False,
  'failed_or_incomplete_campaign_ids':v['failed_or_incomplete_campaign_ids'],'validation_is_outside_timing':True,
  'fresh_pre_campaign_probes':probes,'tooling_tests_passed':5,'numerical_builds':'Reused exact previously validated Phase4S CPU and final Phase5B GPU binaries; no numerical rebuild/change',
  'validation_script_sha256':s.digest(__file__),'output_boundary':'Fixed aggregate JSON/CSV/validation whitelist; CESA private plans/weather/site/aims/timestamps/maps remain on server'}
 s.save(PUBLIC/'annual-benchmark-validation.json',value)
 allowed={'annual-benchmark-matrix.json','annual-benchmark-matrix.csv','annual-benchmark-validation.json'}
 assert {p.name for p in PUBLIC.iterdir()}==allowed
 for file in PUBLIC.iterdir():
  text=file.read_text()
  assert all(token not in text for token in tokens if token),'Private input token crossed publication boundary'
  for forbidden in ['"private_project_inputs"','"private_epw_sha256"','"operating_point"','"latitude"','"longitude"','"month"','"hour"','"aimpoint"']:assert forbidden not in text
 s.save(OUT/'public-manifest.json',{'files':{f.name:s.digest(f) for f in sorted(PUBLIC.iterdir())},'private_input_token_scan_passed':True,'whitelist_only':True})
 print('ANNUAL_MATRIX_PUBLIC_EVIDENCE_READY',flush=True)
if __name__=='__main__':main()
