#!/usr/bin/env python3
"""Untimed direct-CUDA optical oracle and temporal transition/invalidation checks."""
import argparse,ctypes,json,os
from pathlib import Path
import numpy as np
import gpu_temporal as g
import temporal_campaign as t
from temporal_campaign import require,write,set_state,payload


def optical_capture():
    lib=ctypes.CDLL(str(Path(os.environ['COPILOT_LIB_DIR']).parent/'libcpu_optical_state_bridge.so'))
    lib.phase4_optical_capture.argtypes=[ctypes.c_void_p];lib.phase4_optical_capture.restype=ctypes.c_void_p
    lib.phase4_optical_size.argtypes=[ctypes.c_void_p];lib.phase4_optical_size.restype=ctypes.c_size_t
    lib.phase4_optical_copy.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t];lib.phase4_optical_copy.restype=ctypes.c_bool
    lib.phase4_optical_free.argtypes=[ctypes.c_void_p]
    def capture(r):
        p=lib.phase4_optical_capture(r);require(bool(p),'Incomplete optical state')
        try:
            n=lib.phase4_optical_size(p);a=np.empty(n,dtype=np.float64)
            require(lib.phase4_optical_copy(p,a.ctypes.data,n),'Optical capture failed');return a
        finally:lib.phase4_optical_free(p)
    return capture


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',choices=['cesa','commercial'],required=True)
    p.add_argument('--mode',choices=['reference','sequential','resident','batch'],required=True);p.add_argument('--batch-size',type=int,default=1)
    a=p.parse_args();g.configure_environment();cp=t.api();capture=optical_capture()
    plan=json.loads((t.OUT/(a.case+'-plan.json')).read_text());points=plan['diagnostic']
    folder=g.OUT/'correctness'/a.case;folder.mkdir(parents=True,exist_ok=True)
    checked=0;mode='sequential' if a.mode=='reference' else a.mode
    if a.mode=='reference':
        for point in points:
            file=folder/(str(point['id'])+'.npz');require(not file.exists(),'Refuse oracle overwrite')
            r,grid=g.open_context(cp,a.case,'sequential')
            try:
                set_state(cp,r,point);require(cp.simulate(r,nthreads=1),cp.get_last_backend_error(r));v,_=payload(cp,r,point,grid)
                v['optical']=capture(r);np.savez(file,**v);checked+=1
            finally:cp.data_free(r)
    else:
        contexts=[]
        try:
            for _ in range(a.batch_size):
                r,grid=g.open_context(cp,a.case,mode);contexts.append(r)
            sequences=[('forward',points),('reverse',list(reversed(points))),('repeated',[points[0],points[4],points[0],points[-1],points[0]])]
            if mode=='batch':sequences.append(('full_batch',[points[i%len(points)] for i in range(a.batch_size)]))
            for order,seq in sequences:
                for first in range(0,len(seq),a.batch_size):
                    selected=seq[first:first+a.batch_size]
                    for r,point in zip(contexts,selected):set_state(cp,r,point)
                    if mode=='batch':
                        f=cp.pdll.sp_simulate_batch;f.argtypes=[ctypes.POINTER(ctypes.c_void_p),ctypes.c_int,ctypes.c_int];f.restype=ctypes.c_bool
                        require(f((ctypes.c_void_p*len(selected))(*contexts[:len(selected)]),len(selected),min(len(selected),24)),'Batch correctness failed')
                    else:require(cp.simulate(contexts[0],nthreads=1),cp.get_last_backend_error(contexts[0]))
                    for r,point in zip(contexts,selected):
                        v,_=payload(cp,r,point,grid);v['optical']=capture(r)
                        with np.load(folder/(str(point['id'])+'.npz'),allow_pickle=False) as ref:g.compare({k:ref[k] for k in ref.files},v,bitwise=True)
                        checked+=1
            # Fresh new temporal context compared to ordinary fresh CUDA as well.
            r,grid=g.open_context(cp,a.case,mode)
            try:
                point=max(points,key=lambda p:p['sun'][1]);set_state(cp,r,point);require(cp.simulate(r,nthreads=1),'Fresh simulation failed')
                v,_=payload(cp,r,point,grid);v['optical']=capture(r)
                with np.load(folder/(str(point['id'])+'.npz'),allow_pickle=False) as ref:g.compare({k:ref[k] for k in ref.files},v,bitwise=True)
                checked+=1
            finally:cp.data_free(r)
        finally:
            for r in contexts:cp.data_free(r)
    result={'phase':'5B','case':a.case,'mode':a.mode,'batch_size':a.batch_size,'checked':checked,
            'all215_optical_and_full_outputs_bitwise':True,'library_sha256':t.digest(Path(os.environ['COPILOT_LIB_DIR'])/'solarpilot.so'),
            'fresh_context_reference':a.mode=='reference'}
    file=folder/(a.mode+'-'+result['library_sha256'][:12]+'-'+str(a.batch_size)+'.json');require(not file.exists(),'Refuse correctness evidence overwrite');write(file,result)
    print(a.case,a.mode,a.batch_size,checked,'full-state bitwise checks passed',flush=True)


if __name__=='__main__':main()
