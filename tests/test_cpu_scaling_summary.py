"""Keep measured optima, all samples and single-core versus best-CPU attribution distinct."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from summarize_cpu_multicore import annotate,compare


def campaign():
    rows=[]
    for sid in ('a','b','c','d'):
        for n,elapsed in ((1,12.),(2,6.2),(4,3.4),(8,2.),(12,1.6),(24,1.9)):
            rows.append({'case_id':'synthetic','state_id':sid,'path':'flat','requested_threads':n,
                         'samples_s':[elapsed-.01,elapsed,elapsed+.01],
                         'statistics_s':{'median':elapsed}})
    return {'status':'passed','rows':rows}


class CpuScalingSummary(unittest.TestCase):
    def test_efficiency_and_samples_preserved(self):
        source=campaign();result=annotate(source)
        row=next(r for r in result['rows'] if r['requested_threads']==12)
        self.assertEqual(row['scaling_speedup'],7.5)
        self.assertEqual(row['parallel_efficiency'],.625)
        self.assertEqual(row['samples_s'],source['rows'][4]['samples_s'])
        self.assertEqual(row['effective_numerical_participants'],12)
        self.assertEqual(row['spawned_numerical_workers'],11)
        self.assertNotIn('scaling_speedup',source['rows'][0])

    def test_preexisting_request_does_not_imply_workers(self):
        source=campaign()
        for row in source['rows']:
            row.update(physical_cores_used=min(row['requested_threads'],12),smt=row['requested_threads']==24)
        result=annotate(source,True)
        self.assertTrue(all(r['effective_numerical_participants']==1 and r['spawned_numerical_workers']==0 for r in result['rows']))
        self.assertTrue(all(r['physical_cores_used']==1 and not r['smt'] for r in result['rows']))
        twentyfour=next(r for r in result['rows'] if r['requested_threads']==24)
        self.assertEqual(twentyfour['physical_cores_in_affinity'],12)
        self.assertTrue(twentyfour['affinity_includes_smt'])

    def test_best_measured_count_and_gpu_comparison(self):
        flat=annotate(campaign())
        gpu={'rows':[{'case_id':'synthetic','state_id':sid,'statistics_s':{'median':.2}} for sid in ('a','b','c','d')]}
        result=compare(flat,gpu)['synthetic']
        self.assertEqual(result['common_best_thread_count'],12)
        for state in result['states']:
            self.assertEqual(state['best_cpu_threads'],12)
            self.assertEqual(state['flat_1t_to_cuda'],60.)
            self.assertEqual(state['best_cpu_to_cuda'],8.)
            self.assertLess(state['smt_gain_t12_over_t24'],1.)


if __name__=='__main__':unittest.main()
