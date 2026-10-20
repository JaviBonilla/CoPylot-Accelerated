"""Private input/state additions must not cross the aggregate publication boundary."""
from pathlib import Path
import json,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
import summarize_gpu_temporal as publication

class PublicGpuEvidence(unittest.TestCase):
    def test_private_raw_fields_are_excluded_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/'raw';run=raw/'runs/SAFE';run.mkdir(parents=True);dest=root/'public'
            value={'identifier':'SAFE','case':'cesa','series':'seasonal','mode':'sequential','batch_size':1,
                   'active_states':1,'completed':48,'control_grid':[217,256],'contract':'full',
                   'runtime_probe_s':.1,'context_setup_s':[.1],'setup_wall_s':.1,'evaluation_wall_s':1.,
                   'total_wall_s':1.1,'states_per_s':48.,'total_states_per_s':48/1.1,
                   'simulate_batch_wall_s':{},'batch_complete_wall_s':{},'simulation_only_states_per_s':60.,
                   'materialize_analysis_s':.1,'serialize_write_s':.1,'output_bytes':100,'first_batch_wall_s':.1,
                   'first_simulate_batch_s':.1,'first_call_included':True,'warmups_excluded':0,
                   'state_batch_completion_latency_s':{},'cpu_window':{'accepted':True,'average_owned_cores':1.,
                   'external_average_cores':0.,'thermal_throttle_increased':False,'frequency_policy_unchanged':True,
                   'private_path':'SECRET-private-input'},'peak_device_used_mib_sampled':500.,
                   'gpu_utilization_percent_sampled_mean':10.,'cpu_affinity':[0],
                   'library_sha256':'a'*64,'harness_sha256':'b'*64,'commits':{'.':'c'*40,'ssc':'d'*40,
                   'SolarPILOT':'e'*40,'SolTrace':'f'*40,'private_hash':'SECRET-input-hash'},'utc':'benchmark-clock',
                   'gpu_telemetry':[{'name':'fixture','driver_version':'fixture','memory.total':'49140'}],
                   'private_inputs':'SECRET-filename','states':[{'site':'SECRET-site','calendar':'SECRET-date'}]}
            (run/'result.json').write_text(json.dumps(value))
            validation={'passed':True,'persisted_payloads_verified':48,'cpu_agreement_existing_tolerance':True,
                        'maximum_absolute_observable_error':0.,'direct_cuda_bitwise_states':48,'stored_bytes':100,
                        'timing_excludes_verification':True,'private_details':'SECRET-private-details'}
            (run/'validation.json').write_text(json.dumps(validation))
            pilot=raw/'runs/PP-fixture';pilot.mkdir()
            (pilot/'result.json').write_text(json.dumps({**value,'identifier':'PP-fixture'}))
            (pilot/'validation.json').write_text(json.dumps(validation))
            with patch.object(publication,'OUT',raw),patch.object(sys,'argv',['publish','--output',str(dest)]):publication.main()
            for file in dest.iterdir():self.assertNotIn('SECRET',file.read_text())
            result=json.loads((dest/'phase5b-annual-summary.json').read_text())
            self.assertIsNone(result['best_measured_annual']);self.assertEqual(len(result['all_groups']),1)
            self.assertTrue(result['all_attempts'][0]['qualified'])
            self.assertEqual(len(result['all_groups'][0]['campaign_ids']),1)
            self.assertEqual(sum(r['measurement_role']=='pilot' for r in result['all_attempts']),1)
if __name__=='__main__':unittest.main()
