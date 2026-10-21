from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from audit_original_baseline import body,normalized,audit
from original_baseline import owned_target,check_values
from summarize_original_baseline import populations,public_attempt
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
if __name__=='__main__':unittest.main()
