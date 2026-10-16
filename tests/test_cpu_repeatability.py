"""Check forensic identity and process attribution without optical workloads."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from cpu_repeatability import proc_stat,activity,identity_signature,target_argv

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

    def test_identity_uses_library_bytes_and_not_map_address_or_order(self):
        a=[{'name':'libm.so','sha256':'x','mapped_path':'/one'},{'name':'core.so','sha256':'y'}]
        b=[{'name':'core.so','sha256':'y'},{'name':'libm.so','sha256':'x','mapped_path':'/two'}]
        self.assertEqual(identity_signature(a),identity_signature(b))
        b[0]['sha256']='changed'
        self.assertNotEqual(identity_signature(a),identity_signature(b))

if __name__=='__main__':unittest.main()
