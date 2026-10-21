from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from audit_original_baseline import body,normalized,audit
from original_baseline import owned_target,check_values
from summarize_original_baseline import populations,public_attempt,stable_hardware
import test_cpu_hardening as hardening
import numpy as np
class OriginalBaseline(unittest.TestCase):
 def test_source_body_proof_accounts_for_comments_strings_and_instrumentation(self):
  a='void X::f(){ /* } */ const char*s="}"; SP_PROFILE_SCOPE(API);return; }'
  b='void X::g(){const char*s="}";return;}'
  self.assertEqual(normalized(body(a,'X::f')),normalized(body(b,'X::g')))
  self.assertEqual(len(audit()['legacy_body_checks']),5)
 def test_observer_cannot_claim_another_process(self):
  args=[b'python',b'benchmarks/original_baseline.py',b'campaign',b'--id',b'O-cesa-1']
  self.assertTrue(owned_target(args,'O-cesa-1'));self.assertFalse(owned_target(args,'O-cesa-2'))
  args[2]=b'host-run';self.assertFalse(owned_target(args,'O-cesa-1'))
 def test_bitwise_contract_rejects_equal_valued_different_bits(self):
  check_values({'a':np.array([1.])},{'a':np.array([1.])})
  with self.assertRaises(RuntimeError):check_values({'a':np.array([0.])},{'a':np.array([-0.])})
 def test_eight_groups_require_five_complete_processes_and_retain_jitter(self):
  rows=[dict(hardening.HardeningTooling.block(str(i)),case_id='cesa-i-private-restored',state_id='high-elevation') for i in range(5)]
  self.assertEqual(sum(g['passed'] for g in populations(rows)),1)
  rows[-1]['statistics_s']['coefficient_of_variation']=.06
  self.assertFalse(any(g['passed'] for g in populations(rows)))
  self.assertIn('4',populations(rows)[0]['within_process_cv_failures'])
 def test_publication_excludes_private_payloads_and_transient_frequency(self):
  import copy,json
  root=Path(__file__).resolve().parents[1]
  row=dict(hardening.HardeningTooling.block('O-test'),case_id='cesa-i-private-restored',state_id='high-elevation',label='High',first_call_s=1.,warmup_samples_s=[1.,1.],policy_unchanged=True,raw_campaign_sha256='a'*64,raw_host_sha256='b'*64,raw_sample_reference='O-test.json',all215_map_detail_summary_bitwise=True)
  row['statistics_s'].update(minimum=1.,maximum=1.,mean=1.,stdev=0.,private='PRIVATE_SENTINEL')
  row['operating_point']={'date':'PRIVATE_SENTINEL'};row['observation']={'path':'PRIVATE_SENTINEL'}
  self.assertNotIn('PRIVATE_SENTINEL',json.dumps(public_attempt(row)))
  meta=json.loads((root/'benchmarks/results/phase4s-cpu-gpu-summary.json').read_text())['gpu_provenance']['metadata'];other=copy.deepcopy(meta)
  for r in other['topology']['lscpu']['lscpu']:
   if r['field']=='CPU(s) scaling MHz:':r['data']='99%'
  self.assertEqual(stable_hardware(meta),stable_hardware(other))
  other['topology']['physical_cores']-=1
  self.assertNotEqual(stable_hardware(meta),stable_hardware(other))
if __name__=='__main__':unittest.main()
