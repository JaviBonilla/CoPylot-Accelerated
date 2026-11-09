"""Scientific evidence and public annual workflow regression checks."""
import copy
import csv
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'benchmarks'))
from benchmarks.analysis import annual_figure_data as annual,original_baseline_data as original
from benchmarks.analysis import performance_data as performance,temporal_data as temporal,gpu_temporal_data as gpu
from benchmarks.analysis.validate import main as validate_evidence


def read(name):return json.loads((ROOT/'benchmarks/results'/name).read_text())


class PublicEvidence(unittest.TestCase):
    def test_reviewed_evidence_hashes_and_all_scientific_audits(self):validate_evidence()

    def test_annual_rejects_rounded_time_wrong_output_size_or_rate(self):
        source=read('annual-benchmark-matrix.json');validation=read('annual-benchmark-validation.json')
        with (ROOT/'benchmarks/results/annual-benchmark-matrix.csv').open() as f:flat=list(csv.DictReader(f))
        for field in ['total_wall_s','standard_output_npz_bytes','evaluation_states_per_s']:
            changed=copy.deepcopy(source);changed['rows'][0][field]+=1
            with self.subTest(field=field),self.assertRaises(ValueError):annual.audit(changed,validation,flat)

    def test_original_rejects_changed_retained_sample(self):
        d=read('original-baseline-single-state.json');d['attempts'][0]['samples_s'][0]*=2
        with self.assertRaises(ValueError):original.audit(d,read('original-baseline-validation.json'))

    def test_cpu_gpu_ratio_must_use_matched_measured_values(self):
        summary=read('phase4s-cpu-gpu-summary.json');summary['rows'][0]['flat_1t_over_cuda']+=.1
        with self.assertRaises(ValueError):performance.audit(read('phase4s-final-cpu-baseline.json'),read('phase4s-cuda-control-timings.json'),summary)

    def test_temporal_group_population_cannot_be_trimmed(self):
        d=read('phase5a-campaign-summary.json');d['strategy_groups'][0]['campaign_ids'].pop()
        with self.assertRaises(ValueError):temporal.audit(d)

    def test_gpu_rejects_missing_persisted_outputs(self):
        d=read('phase5b-annual-summary.json');d['all_attempts'][0]['validation']['persisted_payloads_verified']-=1
        with self.assertRaises(ValueError):gpu.audit(d)

    def test_commercial_annual_prepare_reconstructs_plan_and_never_opens_private_case(self):
        import annual_matrix as a
        import tempfile
        plan={'requested':8760,'states':[{}]*4403,'nighttime':4357}
        with tempfile.TemporaryDirectory() as tmp,patch.object(a.t,'OUT',Path(tmp)),patch.object(a.t,'environment'),patch.object(a.t,'build_plan',return_value=plan) as build:
            a.prepare();build.assert_called_once_with('commercial')
            self.assertTrue((Path(tmp)/'commercial-plan.json').is_file())
            with self.assertRaises(RuntimeError):a.prepare()

    def test_runtime_verifier_rejects_self_reference_and_mismatched_calendar(self):
        import tempfile
        import numpy as np
        import verify_annual_matrix as v
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'gpu/runs/test';folder.mkdir(parents=True)
            cpu=root/'cpu';cpu.mkdir();reference=root/'reference';reference.mkdir()
            point={'id':0,'month':1,'day':1,'hour':12.5,'dni':0.,'sun':[180.,20.]}
            values={'map':np.zeros((2,3)),'detail_keys':np.array(['id']),
                    'detail_0':np.array([0.]),'summary_keys':np.array(['power']),
                    'summary_values':np.array([0.]),'resolved_sun':np.array(point['sun'])}
            for target in [folder,reference]:np.savez(target/'0.npz',**values)
            row={'id':0,'state':point,'signature':v.t.signature(values),
                 'metrics':{'incident_power_kw':0.,'absorbed_power_kw':0.}}
            for target in [folder,reference]:
                (target/'states.jsonl').write_text(json.dumps(row)+'\n')
                (target/'result.json').write_text(json.dumps({'status':'passed','case':'commercial',
                    'completed':1,'cpu_window':{'accepted':True},'output_bytes':(target/'0.npz').stat().st_size}))
            (cpu/'commercial-plan.json').write_text(json.dumps({'states':[point],'grid':{'nx':3,'ny':2}}))
            with patch.object(v.a,'OUT',root),patch.object(v.t,'OUT',cpu):
                with self.assertRaisesRegex(RuntimeError,'Independent cross-mode reference'):
                    v.verify('commercial','gpu','test',folder)
                self.assertTrue(v.verify('commercial','gpu','test',reference)['passed'])
                changed=copy.deepcopy(row);changed['state']['hour']+=1
                (reference/'states.jsonl').write_text(json.dumps(changed)+'\n')
                with self.assertRaisesRegex(RuntimeError,'calendar/weather differs'):
                    v.verify('commercial','gpu','test',reference)


if __name__=='__main__':unittest.main()
