"""Allocation, calendar and output equivalence gates for temporal campaigns."""
from pathlib import Path
import sys
import unittest
import json
import tempfile
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from temporal_campaign import partitions, signature, STRATEGIES, payload
from summarize_temporal import summarize


class TemporalContracts(unittest.TestCase):
    @staticmethod
    def topology():
        return {'logical_cpus':[{'cpu':i,'socket':0,'core':i%12} for i in range(24)]}

    def test_every_supported_strategy_covers_each_cpu_once(self):
        for workers,threads in STRATEGIES:
            masks=partitions(self.topology(),workers,threads)
            self.assertEqual(len(masks),workers)
            self.assertTrue(all(len(m)==threads for m in masks))
            self.assertEqual(sorted(sum(masks,[])),list(range(24)))

    def test_whole_core_assignment_avoids_cross_context_sibling_sharing(self):
        for workers,threads in STRATEGIES[:-1]:
            masks=partitions(self.topology(),workers,threads)
            for mask in masks:
                self.assertEqual({c%12 for c in mask if c<12},{c%12 for c in mask if c>=12})
        self.assertEqual(partitions(self.topology(),24,1),[[i] for i in range(24)])

    def test_incomplete_topology_and_oversubscription_fail(self):
        top=self.topology();top['logical_cpus'].pop()
        with self.assertRaises(RuntimeError):partitions(top,2,12)
        with self.assertRaises(RuntimeError):partitions(self.topology(),4,12)

    def test_full_output_signature_includes_schema_and_float_bits(self):
        original={'map':np.zeros((2,3)), 'detail':np.ones(5),'resolved_sun':np.array([180.,20.])}
        reordered=dict(reversed(list(original.items())))
        self.assertEqual(signature(original),signature(reordered))
        for key in original:
            changed={k:v.copy() for k,v in original.items()}
            changed[key].flat[0]=np.nextafter(changed[key].flat[0],np.inf)
            self.assertNotEqual(signature(original),signature(changed))
        changed={**original,'map':original['map'].reshape(3,2)}
        self.assertNotEqual(signature(original),signature(changed))
        changed={**original,'detail':original['detail'].astype(np.float32)}
        self.assertNotEqual(signature(original),signature(changed))

    def test_zero_dni_full_output_has_finite_metrics_and_explicit_undefined_cv(self):
        class CP:
            def data_get_number(self,r,key):return 180. if key.endswith('az') else 20.
        state=(np.zeros((2,3)),{'id':np.arange(4.)},{'Power absorbed by the receiver':0.})
        grid={'nx':3,'ny':2,'surface_width_m':3.,'height_m':2.}
        with patch('cpu_multicore.state',return_value=state):
            values,metrics=payload(CP(),None,{'sun':[180.,20.]},grid)
        self.assertEqual(metrics['incident_power_kw'],0.)
        self.assertIsNone(metrics['uniformity_cv'])
        self.assertIsNone(metrics['centroid_column'])
        json.dumps(metrics,allow_nan=False)
        self.assertEqual(values['map'].shape,(2,3))
        self.assertIn('detail_0',values)

    def test_publication_keeps_private_input_and_state_details_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'raw';dest=root/'public'
            for case in ('cesa','commercial'):
                directory=source/'correctness'/case;directory.mkdir(parents=True)
                value={'status':'passed','fresh_serial_states':1,'transition_checks':[{'threads':1,'order':'forward',
                    'bitwise_full_outputs':True,'bitwise_all215':True}], 'immutable_geometry_aim':True,
                    'zero_dni_probe':True,'private_input':'SECRET-input','reference_rows':[{'site':'SECRET-site'}]}
                (directory/'result.json').write_text(json.dumps(value))
                plan={'grid':{'nx':217,'ny':256},'requested':2,'states':[{'dni':0,'site':'SECRET-site'}],
                      'nighttime':1,'seasonal':[{'date':'SECRET-date'}],'dni_policy':'explicit saved DNI',
                      'aim_method':4,'solar_year':2011,'sun_derivation':'core SOLPOS','output_contract':'full',
                      'public_weather_asset':{},'project':'SECRET-path','input_hash':'SECRET-hash'}
                (source/(case+'-plan.json')).write_text(json.dumps(plan))
            (source/'campaigns').mkdir()
            summarize(source,dest)
            self.assertTrue(list(dest.glob('*.json')))
            for file in dest.glob('*'):
                self.assertNotIn('SECRET',file.read_text())
            value=json.loads((dest/'phase5a-campaign-summary.json').read_text())
            self.assertFalse(value['matrix_complete'])
            self.assertFalse(value['annual_direct_complete'])


if __name__=='__main__':unittest.main()
