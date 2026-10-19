"""Allocation, calendar and output equivalence gates for temporal campaigns."""
from pathlib import Path
import sys
import unittest
import json
import tempfile
import queue
import threading
import multiprocessing as mp
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from temporal_campaign import partitions, signature, STRATEGIES, payload, assigned_points, receive_workers, equal_metrics, load_references, LIB_SHA
from summarize_temporal import summarize
from verify_temporal_outputs import verify


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

    def test_serial_and_physical_core_controls_use_one_sibling(self):
        self.assertEqual(partitions(self.topology(),1,1),[[0]])
        self.assertEqual(partitions(self.topology(),1,12),[list(range(12))])

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
                    'zero_dni_probe':True,'private_input':'SECRET-input','reference_rows':[{'site':'SECRET-site','id':0,'metrics':{'peak_kw_m2':0,'incident_power_kw':0,'absorbed_power_kw':0}}]}
                (directory/'result.json').write_text(json.dumps(value))
                plan={'grid':{'nx':217,'ny':256},'requested':2,'states':[{'dni':0,'site':'SECRET-site'}],
                      'nighttime':1,'seasonal':[{'date':'SECRET-date'}],'dni_policy':'explicit saved DNI',
                      'aim_method':4,'solar_year':2011,'sun_derivation':'core SOLPOS','output_contract':'full',
                      'public_weather_asset':{},'diagnostic':[{'id':0}],'project':'SECRET-path','input_hash':'SECRET-hash'}
                (source/(case+'-plan.json')).write_text(json.dumps(plan))
            (source/'campaigns').mkdir()
            summarize(source,dest)
            self.assertTrue(list(dest.glob('*.json')))
            for file in dest.glob('*'):
                self.assertNotIn('SECRET',file.read_text())
            value=json.loads((dest/'phase5a-campaign-summary.json').read_text())
            self.assertFalse(value['matrix_complete'])
            self.assertFalse(value['annual_direct_complete'])

    def test_persisted_payload_verification_rejects_changed_map(self):
        class CP:
            def data_get_number(self,r,key):return 180. if key.endswith('az') else 20.
        grid={'nx':3,'ny':2,'surface_width_m':3.,'height_m':2.}
        point={'id':1,'sun':[180.,20.],'dni':0.}
        state=(np.zeros((2,3)),{'id':np.arange(4.)},{'Power absorbed by the receiver':0.})
        with patch('cpu_multicore.state',return_value=state):values,metrics=payload(CP(),None,point,grid)
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);file=directory/'1.npz';np.savez(file,**values)
            row={'id':1,'state':point,'metrics':metrics,'signature':signature(values)}
            (directory/'worker-test.jsonl').write_text(json.dumps(row)+'\n')
            (directory/'plan.json').write_text(json.dumps({'points':[point]}))
            (directory/'result.json').write_text(json.dumps({'status':'passed','identifier':'test',
                'case':'commercial','completed':1,'output_bytes':file.stat().st_size}))
            result=verify(directory,{'grid':grid})
            self.assertEqual(result['persisted_full_payloads_verified'],1)
            self.assertEqual(result['zero_dni_maps_verified_zero'],1)
            values['map'][0,0]=1.;np.savez(file,**values)
            with self.assertRaises(AssertionError):verify(directory,{'grid':grid})

    def test_dynamic_dispatch_delivers_every_job_and_honors_cancellation(self):
        jobs=queue.Queue(maxsize=2);stop=threading.Event()
        jobs.put({'id':1});jobs.put(None)
        self.assertEqual(list(assigned_points([],jobs,stop)),[{'id':1}])
        stop.set()
        self.assertEqual(list(assigned_points([],jobs,stop)),[])
        self.assertEqual(list(assigned_points([{'id':2}],None,stop)),[])

    def test_worker_errors_do_not_wait_for_an_earlier_busy_worker(self):
        first,send_first=mp.Pipe(duplex=False);second,send_second=mp.Pipe(duplex=False)
        try:
            send_second.send({'kind':'error','pid':2,'traceback':'test failure'})
            with self.assertRaises(RuntimeError):receive_workers([first,second],[SimpleNamespace(pid=1),SimpleNamespace(pid=2)],'done')
        finally:
            for pipe in (first,send_first,second,send_second):pipe.close()

    def test_derived_metrics_use_the_existing_numerical_tolerance(self):
        equal_metrics({'peak':1.,'cv':None},{'peak':1.+1e-11,'cv':None})
        with self.assertRaises(RuntimeError):equal_metrics({'peak':1.},{'peak':1.1})
        with self.assertRaises(RuntimeError):equal_metrics({'cv':None},{'cv':0.})

    def test_cross_dispatch_observations_are_not_labeled_fresh_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);reference=directory/'references.json'
            reference.write_text(json.dumps({'1':'fresh-hash'}))
            (directory/'result.json').write_text(json.dumps({'reference_rows':[{'id':1,'metrics':{'peak':1.},'simulate_s':2.}]}))
            extra={'case':'commercial','library_sha256':LIB_SHA,'rows':[
                {'id':1,'signature':'fresh-hash','metrics':{'peak':1.},'simulate_s':3.},
                {'id':2,'signature':'observed-hash','metrics':{'peak':2.},'simulate_s':4.}]}
            (directory/'extra-references.json').write_text(json.dumps(extra))
            refs,metrics,costs,fresh=load_references(reference,'commercial')
            self.assertEqual(fresh,{'1'})
            self.assertEqual(set(refs),{'1','2'})
            self.assertEqual(costs['1'],2.)
            extra['rows'][0]['signature']='conflicting-hash'
            (directory/'extra-references.json').write_text(json.dumps(extra))
            with self.assertRaises(RuntimeError):load_references(reference,'commercial')


if __name__=='__main__':unittest.main()
