"""Hybrid backend capability errors, rectangular maps and timing plumbing."""
import csv
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'benchmarks'))
from cases import api, configure, layout


class CudaFlux(unittest.TestCase):
    def setUp(self):
        self.cp=api()
        if not self.cp.cuda_available(): self.skipTest('No CUDA device in this build/run')
        library=Path(os.environ.get('COPILOT_LIB_DIR',Path(__file__).resolve().parents[1]/'build/cpu/lib'))
        cache=library.parent/'CMakeCache.txt'
        self.diagnostics=cache.exists() and 'SOLARPILOT_ENABLE_FLUX_DIAGNOSTICS:BOOL=ON' in cache.read_text()
        self.context=self.cp.data_create(); self.assertTrue(self.context)
        configure(self.cp,self.context,'small')
        self.assertTrue(self.cp.assign_layout(self.context,layout(257),nthreads=1))
        self.assertTrue(self.cp.set_compute_backend(self.context,'cuda'))

    def tearDown(self):
        if hasattr(self,'context'): self.assertTrue(self.cp.data_free(self.context))

    def test_explicit_capability_errors(self):
        for key,value,original in [('fluxsim.0.flux_model',1,0),('receiver.0.rec_type',2,0),('fluxsim.0.aim_method',1,0),('fluxsim.0.flux_time_type',1,0)]:
            with self.subTest(key=key):
                self.assertTrue(self.cp.data_set_number(self.context,key,value))
                self.assertFalse(self.cp.simulate(self.context,nthreads=1))
                self.assertIn('supports only',self.cp.get_last_backend_error(self.context))
                self.assertEqual(self.cp.get_compute_backend(self.context),'cuda')
                self.assertTrue(self.cp.data_set_number(self.context,key,original))
        self.assertFalse(self.cp.simulate(self.context,nthreads=2))
        self.assertFalse(self.cp.simulate(self.context,nthreads=1,update_aimpoints=False))
        with patch.dict(os.environ, {'SOLARPILOT_CUDA_BLOCK_SIZE':'127'}):
            if self.diagnostics:
                self.assertFalse(self.cp.simulate(self.context,nthreads=1))
                self.assertIn('block size',self.cp.get_last_backend_error(self.context))
            else:
                self.assertTrue(self.cp.simulate(self.context,nthreads=1),self.cp.get_last_backend_error(self.context))
        self.assertTrue(self.cp.simulate(self.context,nthreads=1))
        self.assertEqual(self.cp.get_last_backend_error(self.context),'')
        self.assertGreaterEqual(self.cp.add_receiver(self.context,'Second receiver'),0)
        self.assertFalse(self.cp.simulate(self.context,nthreads=1))
        self.assertIn('supports only',self.cp.get_last_backend_error(self.context))

    def test_rectangular_map(self):
        for key,value in [('x_res',20),('y_res',30)]:
            self.assertTrue(self.cp.data_set_number(self.context,'fluxsim.0.'+key,value))
        with tempfile.TemporaryDirectory() as directory:
            compare=Path(directory)/'compare.csv'
            with patch.dict(os.environ, {'SOLARPILOT_FLUX_PATH':'verify_cuda','SOLARPILOT_CUDA_COMPARE_FILE':str(compare)}):
                self.assertTrue(self.cp.simulate(self.context,nthreads=1),self.cp.get_last_backend_error(self.context))
            if self.diagnostics:
                self.assertTrue(compare.exists())
                rows=list(csv.reader(compare.read_text().splitlines()))
                self.assertEqual(len(rows),1)
                self.assertEqual(list(map(int,rows[0][1:4])),[20,30,256])
            else:self.assertFalse(compare.exists())
            cuda=np.asarray(self.cp.get_fluxmap(self.context))
            self.assertTrue(self.cp.set_compute_backend(self.context,'cpu'))
            with patch.dict(os.environ,{'SOLARPILOT_FLUX_PATH':'flat'}):
                self.assertTrue(self.cp.simulate(self.context,nthreads=1))
            np.testing.assert_allclose(cuda,self.cp.get_fluxmap(self.context),rtol=1e-9,atol=1e-10)
    def test_timing_semantics_on_idle_gpu(self):
        if os.environ.get('COPILOT_GPU_TIMING_ALLOWED') != '1':
            self.skipTest('Timing validation requires an explicitly idle GPU')
        for key,value in [('x_res',20),('y_res',30)]:
            self.assertTrue(self.cp.data_set_number(self.context,'fluxsim.0.'+key,value))
        with tempfile.TemporaryDirectory() as directory:
            timing=Path(directory)/'timing.csv'
            with patch.dict(os.environ,{'SOLARPILOT_FLUX_PATH':'flat','SOLARPILOT_CUDA_TIMING_FILE':str(timing)}):
                self.assertTrue(self.cp.simulate(self.context,nthreads=1),self.cp.get_last_backend_error(self.context))
            values=list(map(float,next(csv.reader(timing.read_text().splitlines()))))
            self.assertEqual(values[:2],[257.,600.])
            self.assertEqual(len(values),10)
            self.assertTrue(all(np.isfinite(v) and v>=0 for v in values))
            self.assertGreater(values[5],0.)
            self.assertGreater(values[7],0.)
            self.assertGreater(values[9],values[8])
            # Functional timing validation only; these values are not a speedup benchmark.
