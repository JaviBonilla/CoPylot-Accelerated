"""Deterministic CPU single-state threading and lifecycle regression."""
import os
import csv
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'benchmarks'),str(Path(__file__).parent)]
from cases import api, configure, layout
from test_flat_project import configure_flat
from cpu_multicore import state, equal
from project_grid_campaign import PLAIN


class CpuMulticore(unittest.TestCase):
    def test_readonly_optical_export_checks_capacity_and_preserves_snapshot(self):
        import ctypes
        import math
        library=Path(os.environ.get('COPILOT_LIB_DIR',Path(__file__).resolve().parents[1]/'build/cpu/lib')).resolve().parent/'libcpu_optical_state_bridge.so'
        if not library.exists():self.skipTest('Diagnostic optical bridge unavailable')
        bridge=ctypes.CDLL(str(library))
        if not hasattr(bridge,'phase4_optical_copy'):self.skipTest('Cross-binary optical export unavailable')
        bridge.phase4_optical_capture.argtypes=[ctypes.c_void_p];bridge.phase4_optical_capture.restype=ctypes.c_void_p
        bridge.phase4_optical_size.argtypes=[ctypes.c_void_p];bridge.phase4_optical_size.restype=ctypes.c_size_t
        bridge.phase4_optical_copy.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t];bridge.phase4_optical_copy.restype=ctypes.c_bool
        bridge.phase4_optical_equal.argtypes=[ctypes.c_void_p,ctypes.c_void_p];bridge.phase4_optical_equal.restype=ctypes.c_bool
        bridge.phase4_optical_free.argtypes=[ctypes.c_void_p]
        cp=api();context=cp.data_create();snapshot=None
        try:
            configure(cp,context,'small');self.assertTrue(cp.assign_layout(context,layout(7),nthreads=1))
            with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'flat'}):
                self.assertTrue(cp.simulate(context,nthreads=1));snapshot=bridge.phase4_optical_capture(context)
                self.assertTrue(snapshot);size=bridge.phase4_optical_size(snapshot);self.assertEqual(size,7*215)
                output=(ctypes.c_double*size)()
                self.assertFalse(bridge.phase4_optical_copy(snapshot,output,size-1))
                self.assertFalse(bridge.phase4_optical_copy(None,output,size))
                self.assertFalse(bridge.phase4_optical_copy(snapshot,None,size))
                self.assertTrue(bridge.phase4_optical_copy(snapshot,output,size));self.assertTrue(all(math.isfinite(v) for v in output))
                self.assertTrue(cp.simulate(context,nthreads=12));self.assertTrue(bridge.phase4_optical_equal(snapshot,context))
        finally:
            if snapshot:bridge.phase4_optical_free(snapshot)
            cp.data_free(context)

    def run_case(self, flat, count, grid):
        cp=api();r=cp.data_create()
        try:
            if flat:
                configure_flat(cp,r,count=count,hour_day=True)
                with tempfile.TemporaryDirectory() as td:
                    file=Path(td)/'initial.spt';self.assertTrue(cp.save_spt(r,file))
                    self.assertTrue(cp.load_spt(r,file));self.assertTrue(cp.restore_loaded_layout(r))
            else:
                configure(cp,r,'small');self.assertTrue(cp.assign_layout(r,layout(count),nthreads=1))
            for name,value in zip(('x_res','y_res'),grid):self.assertTrue(cp.data_set_number(r,'fluxsim.0.'+name,value))
            with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'flat'}):
                self.assertTrue(cp.simulate(r,nthreads=1));expected=state(cp,r)
                for n in (2,4,8,12,24,1,12,1,12,24,4):
                    for _ in range(2):
                        self.assertTrue(cp.simulate(r,nthreads=n));equal(expected,state(cp,r))
                # Preserve inherited clamping of nonpositive and oversized requests.
                for n in (0,-3,10000,1):
                    self.assertTrue(cp.simulate(r,nthreads=n));equal(expected,state(cp,r))
                with tempfile.TemporaryDirectory() as td:
                    file=Path(td)/'synthetic.spt';self.assertTrue(cp.save_spt(r,file))
                    self.assertTrue(cp.load_spt(r,file));self.assertTrue(cp.restore_loaded_layout(r))
                    self.assertTrue(cp.simulate(r,nthreads=1));expected=state(cp,r)
                    self.assertTrue(cp.simulate(r,nthreads=12));equal(expected,state(cp,r))
                # A failed backend selection must not poison subsequent CPU simulation.
                self.assertFalse(cp.pdll.sp_set_compute_backend(__import__('ctypes').c_void_p(r),-123))
                self.assertTrue(cp.simulate(r,nthreads=4));equal(expected,state(cp,r))
        finally:self.assertTrue(cp.data_free(r))

    def test_one_flat_heliostat_and_fewer_cells_than_threads(self):self.run_case(True,1,(2,1))
    def test_flat_nondivisible_heliostats_and_rectangular_grid(self):self.run_case(True,7,(9,5))
    def test_one_cylindrical_heliostat(self):self.run_case(False,1,(3,2))
    def test_cylindrical_nondivisible_work(self):self.run_case(False,17,(7,3))

    def test_optical_batch_profile_is_a_caller_wall_scope(self):
        cp=api();r=cp.data_create()
        try:
            configure(cp,r,'small');self.assertTrue(cp.assign_layout(r,layout(7),nthreads=1))
            with tempfile.TemporaryDirectory() as td:
                file=Path(td)/'profile.csv'
                with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'flat',
                                           'SOLARPILOT_INTERCEPT_PROFILE':'1','SOLARPILOT_PROFILE_FILE':str(file)}):
                    self.assertTrue(cp.simulate(r,nthreads=12))
                if not file.exists():self.skipTest('Core profiling disabled in this build')
                rows={row[1]:row for row in csv.reader(file.read_text().splitlines())}
                self.assertEqual(int(rows['CPUImagePlane.batch'][2]),1)
                self.assertGreater(float(rows['CPUImagePlane.batch'][3]),0)
                self.assertGreaterEqual(float(rows['PerformanceSimulationPrep'][3]),float(rows['CPUImagePlane.batch'][3]))
        finally:self.assertTrue(cp.data_free(r))

    def test_cuda_rejects_multicore_requests_and_recovers_without_stale_results(self):
        cp=api()
        if not cp.cuda_available():self.skipTest('CUDA unavailable')
        r=cp.data_create()
        try:
            configure(cp,r,'small');self.assertTrue(cp.assign_layout(r,layout(7),nthreads=1))
            self.assertTrue(cp.set_compute_backend(r,'cuda'))
            with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'cuda'}):
                self.assertTrue(cp.simulate(r,nthreads=1));expected=state(cp,r)
                for n in (2,12,24):
                    self.assertFalse(cp.simulate(r,nthreads=n))
                    self.assertIn('one CPU preparation thread',cp.get_last_backend_error(r))
                    equal(expected,state(cp,r))
                    self.assertTrue(cp.simulate(r,nthreads=1));equal(expected,state(cp,r))
        finally:self.assertTrue(cp.data_free(r))


if __name__=='__main__':unittest.main()
