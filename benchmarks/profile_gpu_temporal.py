#!/usr/bin/env python3
"""Separate first/steady CUDA-event profiles; never used as throughput samples."""
import argparse,ctypes,json,os,time
from pathlib import Path
import numpy as np
import gpu_temporal as g
import temporal_campaign as t
from check_gpu_temporal import optical_capture


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);a=p.parse_args()
    output=g.OUT/a.output;t.require(not output.exists(),'Refuse profile overwrite')
    g.configure_environment();cpus=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpus[0]})
    g.wait_idle();cp=t.api();window=g.PipelineWindow(cpus[-1]);window.initialize(cp);capture=optical_capture();rows=[]
    try:
        for case in ('cesa','commercial'):
            plan=json.loads((t.OUT/(case+'-plan.json')).read_text());points=plan['states'] if case=='commercial' else plan['seasonal']
            selected={'high_sun':max(points,key=lambda p:p['sun'][1]),
                      'moderate_sun':min(points,key=lambda p:abs(p['sun'][1]-30.)),
                      'near_horizon':min(points,key=lambda p:p['sun'][1])}
            if case=='commercial':
                annual=[json.loads(line) for line in (g.OUT/'runs/S1-commercial-year/states.jsonl').read_text().splitlines()]
                selected['near_horizon']=max(annual,key=lambda r:r['simulate_batch_s'])['state']
                t.require(selected['near_horizon']['sun'][1]<5.,'Annual slow anchor is not a low-sun state')
            for label,point in selected.items():
                direct_anchor=None
                for mode in ('sequential','resident'):
                    r,grid=g.open_context(cp,case,mode)
                    try:
                        f=cp.pdll.sp_set_temporal_timing;f.argtypes=[ctypes.c_void_p,ctypes.c_bool];f.restype=ctypes.c_bool
                        t.require(f(r,True),'Cannot enable event diagnostics');t.set_state(cp,r,point);initial=None
                        for repeat in range(3):
                            begin=time.perf_counter();t.require(cp.simulate(r,nthreads=1),cp.get_last_backend_error(r));elapsed=time.perf_counter()-begin
                            f=cp.pdll.sp_get_temporal_statistics;f.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_double),ctypes.c_int];f.restype=ctypes.c_bool
                            measured=(ctypes.c_double*len(g.STAGE_FIELDS))();t.require(f(r,measured,len(measured)),'No stage metrics')
                            begin=time.perf_counter();v,_=t.payload(cp,r,point,grid);optics=capture(r);materialize=time.perf_counter()-begin
                            with np.load(g.OUT/'runs'/('S1-commercial-year' if case=='commercial' else 'S1-cesa-seasonal')/(str(point['id'])+'.npz'),allow_pickle=False) as ref:g.compare({k:ref[k] for k in ref.files},v,bitwise=True)
                            v['optical']=optics
                            if direct_anchor is None:direct_anchor=v
                            else:g.compare(direct_anchor,v,bitwise=True)
                            if initial is None:initial=v
                            else:g.compare(initial,v,bitwise=True)
                            row={'case':case,'solar_class':label,'mode':mode,'call':'first' if not repeat else 'steady',
                                 'repeat':repeat,'api_wall_s':elapsed,'full_getter_optical_check_s':materialize,
                                 'stages':dict(zip(g.STAGE_FIELDS,measured)),'full_outputs_bitwise_equal_direct_cuda':True}
                            if case=='commercial':row['public_state']=point
                            rows.append(row)
                        window.validate()
                    finally:cp.data_free(r)
        window.close()
    finally:window.stop.set()
    t.write(output,{'phase':'5B','diagnostic_only':True,'rows':rows,'library_sha256':t.digest(Path(os.environ['COPILOT_LIB_DIR'])/'solarpilot.so'),
                    'selection':'Commercial low-sun anchor is the slowest measured ordinary CUDA annual API state; high/moderate anchors use the complete public calendar',
                    'interpretation':'Inclusive prep wall contains image GPU work; do not sum nested/overlapping scopes. First and two steady instrumented calls are separate from plain throughput.'})
    print('High/moderate/horizon profiles and full observable checks passed:',len(rows),flush=True)


if __name__=='__main__':main()
