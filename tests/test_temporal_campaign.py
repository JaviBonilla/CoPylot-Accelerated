"""Allocation, calendar and output equivalence gates for temporal campaigns."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from temporal_campaign import partitions, signature, STRATEGIES


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


if __name__=='__main__':unittest.main()
