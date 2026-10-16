"""Check forensic identity and process attribution without optical workloads."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from cpu_repeatability import proc_stat,activity,identity_signature,target_argv
from summarize_cpu_repeatability import stability,replication_groups
from timing_counters import turbostat_rows,align_turbostat,perf_rows,perf_origin_bounds,align_perf,PERF_EVENTS

class RepeatabilityTooling(unittest.TestCase):
    def test_proc_name_parentheses_do_not_shift_cpu_fields(self):
        fields=['0']*50
        for index,value in {0:'R',11:'123',12:'7',15:'20',16:'0',17:'24',36:'23'}.items():fields[index]=value
        result=proc_stat('123 (worker (nested)) '+' '.join(fields))
        self.assertEqual(result,{'state':'R','cpu_ticks':130,'priority':20,'nice':0,'threads':24,'last_cpu':23})

    def test_external_activity_excludes_benchmark_and_preserves_competition(self):
        before={1:{'ticks':100,'name':'owned'},2:{'ticks':20,'name':'compiler'}}
        after={1:{'ticks':1100,'name':'owned'},2:{'ticks':220,'name':'compiler'}}
        with patch('cpu_repeatability.os.sysconf',return_value=100):result=activity(before,after,2,{1})
        self.assertEqual(result,[{'process_name':'compiler','average_cores':1.}])

    def test_observer_selects_worker_action_and_never_its_coordinator(self):
        worker=[b'python',b'benchmarks/cpu_repeatability.py',b'campaign',b'--campaign-id',b'A1']
        coordinator=worker.copy();coordinator[2]=b'host-run'
        self.assertTrue(target_argv(worker,'A1'))
        self.assertFalse(target_argv(coordinator,'A1'))
        self.assertFalse(target_argv(worker,'A2'))

    def test_independent_campaign_gate_rejects_bimodality_without_trimming(self):
        values=[.125,.126,.329,.125,.348]
        result=stability(values)
        self.assertEqual(result['campaigns'],5)
        self.assertGreater(result['maximum_over_minimum'],2.7)
        self.assertFalse(result['meets_declared_between_campaign_gates'])
        self.assertEqual(values,[.125,.126,.329,.125,.348])

    def test_stable_fresh_campaigns_require_five_replicates(self):
        self.assertTrue(stability([.675,.676,.677,.674,.678])['meets_declared_between_campaign_gates'])
        self.assertFalse(stability([.675,.676])['meets_declared_between_campaign_gates'])

    def test_replication_keeps_rejected_campaigns_separate_from_protocol_reference(self):
        rows=[{'campaign_id':f'L{i}-controlled','case_id':'case','threads':24,
               'measurement_window_accepted':i!=5,'within_campaign_cv_gate_passed':True,
               'statistics_s':{'median':.125 if i!=5 else .350}} for i in range(1,7)]
        result=replication_groups(rows)[0]
        self.assertEqual(len(result['all_declared_campaign_ids']),6)
        self.assertNotIn('L5-controlled',result['complete_protocol_campaign_ids'])
        self.assertTrue(result['complete_protocol_stability']['meets_declared_between_campaign_gates'])
        self.assertEqual(rows[4]['statistics_s']['median'],.350)
        rows[0]['within_campaign_cv_gate_passed']=False
        result=replication_groups(rows)[0]
        self.assertFalse(result['complete_protocol_stability']['meets_declared_between_campaign_gates'])

    def test_turbostat_alignment_excludes_edges_and_uses_affinity(self):
        header='Time_Of_Day_Seconds Core CPU Avg_MHz Busy% Bzy_MHz TSC_MHz IPC'
        text=header+'\n10.1 - - 3000 100 3000 2100 2.3\n10.5 - - 3000 100 3000 2100 2.3\n10.5 0 0 4000 100 4000 2100 2.3\n10.51 1 1 800 50 800 2100 1.0\n10.9 - - 3000 100 3000 2100 2.3\n'
        result=align_turbostat(turbostat_rows(text),[1,2],9,1)
        self.assertEqual(result['aggregate_intervals'],1)
        self.assertEqual(result['aggregate_medians']['Bzy_MHz'],3000)
        self.assertEqual(result['affinity_busy_weighted_mhz_median'],4000)
        pair=align_turbostat(turbostat_rows(text),[1,2],9,2)
        self.assertAlmostEqual(pair['affinity_busy_weighted_mhz_median'],(4000*100+800*50)/150)

    def test_identity_uses_library_bytes_and_not_map_address_or_order(self):
        a=[{'name':'libm.so','sha256':'x','mapped_path':'/one'},{'name':'core.so','sha256':'y'}]
        b=[{'name':'core.so','sha256':'y'},{'name':'libm.so','sha256':'x','mapped_path':'/two'}]
        self.assertEqual(identity_signature(a),identity_signature(b))
        b[0]['sha256']='changed'
        self.assertNotEqual(identity_signature(a),identity_signature(b))

    def test_perf_decimal_comma_and_complete_interior_intervals(self):
        lines=[]
        for end,cycles,instructions,pct in [(.2,100,200,'100,00'),(.4,200,300,'98.50'),(.6,100,50,'100,00')]:
            for event in PERF_EVENTS:
                count=cycles if event=='cycles' else instructions if event=='instructions' else 3
                lines.append(f'{end},{count},,{event},4800000000,{pct},,')
        rows=perf_rows('\n'.join(lines))
        self.assertEqual(rows[0]['running_percent']['cycles'],100.)
        self.assertEqual(rows[1]['running_percent']['cycles'],98.5)
        result=align_perf(rows,[100.15,100.55],[100.,100.01],margin=0)
        self.assertEqual(result['fully_interior_intervals'],1)
        self.assertEqual(result['ipc'],1.5)
        self.assertEqual(result['events_per_million_instructions']['branch-misses'],10000.)
        self.assertEqual(result['minimum_running_percent'],98.5)
        unsupported='\n'.join(lines).replace('0.4,3,,ld_blocks.address_alias','0.4,<not counted>,,ld_blocks.address_alias')
        missing=perf_rows(unsupported)
        self.assertFalse(missing[1]['complete'])
        self.assertEqual(align_perf(missing,[100.15,100.55],[100.,100.01],margin=0)['fully_interior_intervals'],0)

    def test_perf_origin_uses_live_process_and_write_bound(self):
        clock={'processes':[{'starttime_ticks':1000}],'clk_tck':100,
               'samples':[{'utc_epoch_s':1012.,'monotonic':12.,'mtime_epoch_s':1012.05,'last_relative_s':2.}]}
        low,high=perf_origin_bounds(clock)
        self.assertAlmostEqual(low,9.99);self.assertAlmostEqual(high,10.07)
        clock['processes'].append({'starttime_ticks':1000})
        with self.assertRaises(ValueError):perf_origin_bounds(clock)

if __name__=='__main__':unittest.main()
