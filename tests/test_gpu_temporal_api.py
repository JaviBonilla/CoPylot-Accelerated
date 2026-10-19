"""Temporal API lifecycle, rejected batches and independent observable states."""
import ctypes,os,sys,unittest
from pathlib import Path
import numpy as np
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'benchmarks')]
from cases import api,configure,layout
from cpu_multicore import state,equal
from project_grid_campaign import PLAIN

class TemporalApi(unittest.TestCase):
    def setUp(self):
        self.cp=api();self.contexts=[];self.affinity=os.sched_getaffinity(0)
        for k in list(os.environ):
            if k.startswith('SOLARPILOT_'):os.environ.pop(k)
        os.environ.update({**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'flat'})
        self.batch=self.cp.pdll.sp_simulate_batch
        self.batch.argtypes=[ctypes.POINTER(ctypes.c_void_p),ctypes.c_int,ctypes.c_int];self.batch.restype=ctypes.c_bool
        self.resident=self.cp.pdll.sp_set_temporal_residency
        self.resident.argtypes=[ctypes.c_void_p,ctypes.c_bool];self.resident.restype=ctypes.c_bool
    def tearDown(self):
        os.sched_setaffinity(0,self.affinity)
        for r in self.contexts:self.cp.data_free(r)
    def context(self,cuda=False):
        r=self.cp.data_create();self.contexts.append(r)
        configure(self.cp,r,'small');self.assertTrue(self.cp.assign_layout(r,layout(7),nthreads=1))
        self.assertTrue(self.cp.data_set_number(r,'fluxsim.0.x_res',7));self.assertTrue(self.cp.data_set_number(r,'fluxsim.0.y_res',5))
        if cuda:
            self.assertTrue(self.cp.set_compute_backend(r,'cuda'));os.environ['SOLARPILOT_INTERCEPT_PATH']='cuda'
        return r
    def test_invalid_arguments_and_cpu_rejection_preserve_ordinary_cpu(self):
        r=self.context();self.assertTrue(self.cp.simulate(r,nthreads=1));expected=state(self.cp,r)
        handles=(ctypes.c_void_p*1)(r)
        self.assertFalse(self.resident(None,True));self.assertFalse(self.resident(r,True))
        for count,workers in [(0,1),(33,1),(1,0),(1,25)]:self.assertFalse(self.batch(handles,count,workers))
        self.assertFalse(self.batch(handles,1,1));self.assertTrue(self.cp.simulate(r,nthreads=1));equal(expected,state(self.cp,r))
    def test_cuda_batch_context_isolation_rejection_and_affinity_restoration(self):
        if not self.cp.cuda_available():self.skipTest('CUDA unavailable')
        r=self.context(True);q=self.context(True);refs=[]
        for i,c in enumerate([r,q]):
            self.assertTrue(self.cp.data_set_number(c,'fluxsim.0.flux_solar_el_in',25.+i*30.))
            self.assertTrue(self.cp.simulate(c,nthreads=1));refs.append(state(self.cp,c));self.assertTrue(self.resident(c,True))
        timing=self.cp.pdll.sp_set_temporal_timing;timing.argtypes=[ctypes.c_void_p,ctypes.c_bool];timing.restype=ctypes.c_bool
        metrics=self.cp.pdll.sp_get_temporal_statistics;metrics.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_double),ctypes.c_int];metrics.restype=ctypes.c_bool
        values=(ctypes.c_double*24)()
        self.assertFalse(metrics(r,values,24));self.assertTrue(timing(r,True));self.assertFalse(metrics(r,values,24))
        self.assertTrue(self.cp.simulate(r,nthreads=1));self.assertTrue(metrics(r,values,24));self.assertTrue(np.isfinite(values).all())
        self.assertFalse(metrics(r,values,23));self.assertTrue(timing(r,False));self.assertFalse(metrics(r,values,24))
        self.assertFalse(self.batch((ctypes.c_void_p*2)(r,r),2,1))
        self.assertFalse(self.batch((ctypes.c_void_p*2)(r,None),2,1))
        for workers in [1,min(2,len(self.affinity)),1]:
            self.assertTrue(self.batch((ctypes.c_void_p*2)(r,q),2,workers))
            self.assertEqual(os.sched_getaffinity(0),self.affinity)
            for c,expected in zip([r,q],refs):equal(expected,state(self.cp,c))
        os.sched_setaffinity(0,{min(self.affinity)})
        self.assertFalse(self.batch((ctypes.c_void_p*2)(r,q),2,2))
        self.assertTrue(self.cp.simulate(r,nthreads=1));equal(refs[0],state(self.cp,r))
if __name__=='__main__':unittest.main()
