"""Protect campaign attribution for the production API hardening regression."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from cpu_hardening import owned_target
from cpu_hardening_layout import layout_records
from summarize_cpu_hardening import group,rsp_groups,role,placement_matches


class HardeningTooling(unittest.TestCase):
    def test_observer_owns_only_the_selected_numerical_child(self):
        argv=[b'python',b'benchmarks/cpu_hardening.py',b'campaign',b'--campaign-id',b'F1']
        self.assertTrue(owned_target(argv,'F1'))
        self.assertFalse(owned_target(argv,'F2'))
        argv[2]=b'host-run';self.assertFalse(owned_target(argv,'F1'))
        argv[2]=b'campaign';argv[1]=b'benchmarks/cpu_repeatability.py'
        self.assertFalse(owned_target(argv,'F1'))

    @staticmethod
    def block(identifier,median=.125,cv=.01,accepted=True,placement=True):
        return {'campaign_id':identifier,'source_valid':True,'cpu_window':{'accepted':accepted},
                'placement_verified':placement,'samples_s':[median]*5,
                'statistics_s':{'median':median,'coefficient_of_variation':cv}}

    def test_rejected_attempts_are_retained_without_creating_a_reference(self):
        blocks=[self.block(str(i)) for i in range(4)]
        blocks.append(self.block('jitter',cv=.06))
        blocks.append(self.block('load',accepted=False))
        result=group(blocks)
        self.assertFalse(result['passed'])
        self.assertEqual(len(result['complete_protocol_campaign_ids']),4)
        self.assertEqual(result['all_retained_sample_distribution']['samples'],30)
        self.assertIn('jitter',result['within_process_cv_failures'])
        blocks.append(self.block('replacement'))
        self.assertTrue(group(blocks)['passed'])

    def test_internally_stable_slow_position_cannot_pass_regression(self):
        rows=[]
        for i in range(5):
            contrasts=[{**self.block(str(i),median=.31 if phase==48 else .125),'callsite_mod64':phase}
                       for phase in (0,16,32,48)]
            rows.append({'role':'rsp','case_id':'safe-case','campaign_id':str(i),'source_valid':True,
                         'stack_contrasts':contrasts})
        result=rsp_groups(rows)[0]
        self.assertTrue(all(p['passed'] for p in result['positions']))
        self.assertFalse(result['passed'])
        for row in rows:
            row['stack_contrasts'][-1]['statistics_s']['median']=.126
        self.assertTrue(rsp_groups(rows)[0]['passed'])

    def test_placement_and_source_identity_are_required(self):
        blocks=[self.block(str(i)) for i in range(5)]
        blocks[-1]['placement_verified']=False
        self.assertFalse(group(blocks)['passed'])
        blocks[-1]['placement_verified']=True;blocks[-1]['source_valid']=False
        self.assertFalse(group(blocks)['passed'])

    def test_actual_addresses_distinguish_adjacent_lines_and_worker_pointer(self):
        raw={'records':[{'parameters_address':0x1030,'worker_parameters_address':0x1030,
                        'sincos_output_addresses':[0x1000,0x1008],'flat_frame_rsp':0x1020,
                        'c_api_callsite_mod64':48}]}
        observed=layout_records(raw)[0]
        self.assertTrue(observed['caller_scratch_shares_parameters_line'])
        self.assertTrue(observed['worker_reads_same_object'])
        raw['records'][0]['parameters_address']=0x1040
        observed=layout_records(raw)[0]
        self.assertFalse(observed['caller_scratch_shares_parameters_line'])
        self.assertFalse(observed['worker_reads_same_object'])

    def test_pilots_and_reduced_controls_have_distinct_roles(self):
        self.assertEqual(role('pilot-rsp'),'pilot')
        self.assertEqual(role('R09'),'rsp')
        self.assertEqual(role('B12-03'),'old_12t')
        self.assertEqual(role('N12-03'),'new_12t')
        self.assertEqual(role('D12-old'),'old_12t_rsp')
        self.assertEqual(role('D12-new'),'new_12t_rsp')

    def test_observed_workers_must_keep_the_declared_cpu_mask(self):
        observation={'observed':True,'maximum_runnable_tasks':24,
                     'maximum_distinct_last_cpus_of_runnable_tasks':24,'allowed_cpu_sets':['0-23'],
                     'thermal_throttle_increased':False}
        self.assertTrue(placement_matches(observation,list(range(24))))
        observation['allowed_cpu_sets']=['0-47']
        self.assertFalse(placement_matches(observation,list(range(24))))
        observation.update(allowed_cpu_sets=['0-23'],thermal_throttle_increased=True)
        self.assertFalse(placement_matches(observation,list(range(24))))

if __name__=='__main__':unittest.main()
