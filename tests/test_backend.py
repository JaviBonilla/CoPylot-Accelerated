import ctypes
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
from cases import api, configure, layout, collect


class Backend(unittest.TestCase):
    def test_cpu_dispatch_and_rejected_cuda(self):
        cp = api()
        r = cp.data_create()
        self.assertTrue(r)
        try:
            self.assertEqual(cp.get_compute_backend(r), 'cpu')
            self.assertTrue(cp.set_compute_backend(r, 'CPU'))
            with self.assertRaisesRegex(RuntimeError, 'CUDA backend not implemented yet'):
                cp.set_compute_backend(r, 'cuda')
            self.assertEqual(cp.get_compute_backend(r), 'cpu')
            with self.assertRaises(ValueError):
                cp.set_compute_backend(r, 'other')
            cp.pdll.sp_set_compute_backend.restype = ctypes.c_bool
            self.assertFalse(cp.pdll.sp_set_compute_backend(r, 99))
            self.assertEqual(cp.get_last_backend_error(r), 'Invalid compute backend')
            configure(cp, r, 'small')
            self.assertTrue(cp.assign_layout(r, layout(1000), nthreads=1))
            self.assertTrue(cp.simulate(r, nthreads=1))
            self.assertEqual(cp.get_last_backend_error(r), '')
            collect(cp, r)
        finally:
            self.assertTrue(cp.data_free(r))

    def test_probe_and_device_errors(self):
        cp = api()
        count = cp.cuda_device_count()
        self.assertEqual(cp.cuda_available(), count > 0)
        r = cp.data_create()
        try:
            with self.assertRaises(ValueError):
                cp.set_cuda_device(r, -1)
            if count:
                self.assertTrue(cp.set_cuda_device(r, 0))
                with self.assertRaisesRegex(RuntimeError, 'out of range'):
                    cp.set_cuda_device(r, count)
            else:
                with self.assertRaisesRegex(RuntimeError, 'not enabled|No CUDA devices'):
                    cp.set_cuda_device(r, 0)
        finally:
            self.assertTrue(cp.data_free(r))

    def test_null_context(self):
        cp = api()
        with self.assertRaises(RuntimeError):
            cp.get_compute_backend(None)
        with self.assertRaisesRegex(RuntimeError, 'Null CoPylot context'):
            cp.set_compute_backend(None, 'cpu')
        self.assertFalse(cp.simulate(None))


if __name__ == '__main__':
    unittest.main()
