"""Protect campaign attribution for the production API hardening regression."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from cpu_hardening import owned_target


class HardeningTooling(unittest.TestCase):
    def test_observer_owns_only_the_selected_numerical_child(self):
        argv=[b'python',b'benchmarks/cpu_hardening.py',b'campaign',b'--campaign-id',b'F1']
        self.assertTrue(owned_target(argv,'F1'))
        self.assertFalse(owned_target(argv,'F2'))
        argv[2]=b'host-run';self.assertFalse(owned_target(argv,'F1'))
        argv[2]=b'campaign';argv[1]=b'benchmarks/cpu_repeatability.py'
        self.assertFalse(owned_target(argv,'F1'))

if __name__=='__main__':unittest.main()
