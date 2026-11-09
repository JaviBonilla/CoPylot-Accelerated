#!/usr/bin/env python3
"""Direct public commercial annual campaigns, reconstructed from pinned upstream assets."""
import argparse,csv,json,os,subprocess,time
from datetime import datetime,timedelta
from pathlib import Path
import numpy as np
import temporal_campaign as t
import cpu_multicore as cpu
import gpu_temporal as g
import gpu_temporal_pipeline as pipeline
from check_gpu_temporal import optical_capture

OUT=Path(os.environ.get('COPILOT_ANNUAL_OUTPUT',t.ROOT/'artifacts/annual-matrix')).resolve()
t.OUT=OUT/'cpu';g.OUT=OUT/'gpu'
BASE_ENVIRONMENT=t.environment

def annual_environment():
    BASE_ENVIRONMENT()
    if os.environ.get('COPILOT_ANNUAL_PATH')=='legacy':
        os.environ.update(SOLARPILOT_INTERCEPT_PATH='legacy',SOLARPILOT_FLUX_PATH='legacy')
t.environment=annual_environment

def epw_candidates(rows):
    """EPW hour 1..24 denotes an hour ending; evaluate its midpoint, as Daggett."""
    t.require(len(rows)==8760,'Annual EPW must have 8760 hourly rows')
    result=[];begin=datetime(2011,1,1)
    for i,row in enumerate(rows):
        t.require(len(row)==35,'Invalid EPW schema')
        month,day,hour,minute=map(int,row[1:5]);dni=float(row[14]);expected=begin+timedelta(hours=i)
        t.require((month,day,hour)==(expected.month,expected.day,expected.hour+1),'EPW calendar incomplete or reordered')
        t.require(minute in (0,60) and np.isfinite(dni) and 0<=dni<9999,'Invalid EPW minute/DNI')
        result.append({'month':month,'day':day,'hour':hour-.5,'dni':dni})
    return result

def retained(candidates,sun,site):
    states=[];night=0
    for i,p in enumerate(candidates):
        p={'id':i,**p,'sun':sun(site,p['month'],p['day'],p['hour'])}
        t.require(np.isfinite(p['sun']).all(),'Invalid derived sun')
        if p['sun'][1]<=0:night+=1
        else:states.append(p)
    return states,night

def prepare():
    """Reconstruct the accepted public commercial sequence from pinned assets."""
    t.environment()
    commercial=t.build_plan('commercial')
    t.require(commercial['requested']==8760 and len(commercial['states'])==4403 and commercial['nighttime']==4357,
              'Regenerated commercial workload differs from accepted annual counts')
    path=t.OUT/'commercial-plan.json'
    t.require(not path.exists(),'Refuse plan overwrite')
    t.write(path,commercial)
    print('Public commercial plan: 8760 requested, 4403 daylight, 4357 omitted',flush=True)


def seed(case):
    """Fresh serial optical probes before timing; complete annual cross-checks later."""
    t.environment();cp=t.api();plan=json.loads((t.OUT/(case+'-plan.json')).read_text());folder=t.OUT/'correctness'/case
    folder.mkdir(parents=True,exist_ok=False);capture=optical_capture();rows=[];references={}
    for point in plan['diagnostic']:
        r,grid=t.context(cp,case)
        try:
            t.set_state(cp,r,point);sim=cpu.simulate(cp,r,1);values,metrics=t.payload(cp,r,point,grid)
            np.savez(folder/(str(point['id'])+'.npz'),**values);optics=capture(r);np.save(folder/(str(point['id'])+'-optics.npy'),optics)
            references[str(point['id'])]=t.signature(values);rows.append({'id':point['id'],'signature':t.signature(values),'simulate_s':sim,'metrics':metrics})
            with __import__('unittest.mock',fromlist=['patch']).patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'legacy','SOLARPILOT_FLUX_PATH':'legacy'}):
                cpu.simulate(cp,r,1);other,other_metrics=t.payload(cp,r,point,grid);g.compare(values,other,bitwise=True);t.equal_metrics(other_metrics,metrics)
                t.require(optics.tobytes()==capture(r).tobytes(),'Fresh Legacy optical mismatch')
        finally:cp.data_free(r)
    t.write(folder/'references.json',references);t.write(folder/'result.json',{'status':'passed','reference_rows':rows,'fresh_serial_full_and215_probes':len(rows),'library_sha256':t.LIB_SHA})
    print(case,'fresh Flat/Legacy full-output and215 probes passed',len(rows),flush=True)

def run(case,mode,identifier,workers=None,threads=None):
    cpu.topology_cache=cpu.topology()
    if mode=='gpu':
        args=argparse.Namespace(case=case,workers=workers or 24,residency=False,series='states',id=identifier,library_sha256=t.LIB_SHA)
        pipeline.campaign(args)
    else:
        os.environ['COPILOT_ANNUAL_PATH']='legacy' if mode=='original' else 'flat';t.environment()
        workers,threads=(workers or 24,threads or 1) if mode=='cpu' else (1,1)
        t.campaign(case,workers,threads,'states',identifier,'dynamic_lpt')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['prepare','seed','run'])
    p.add_argument('--case',choices=['commercial'],default='commercial')
    p.add_argument('--mode',choices=['original','refactored','cpu','gpu'])
    p.add_argument('--id');p.add_argument('--workers',type=int);p.add_argument('--threads',type=int)
    p.add_argument('--library-sha256',default=os.environ.get('COPILOT_EXPECTED_LIBRARY_SHA256'))
    a=p.parse_args()
    if not a.library_sha256:p.error('Declare the exact rebuilt library identity with --library-sha256 or COPILOT_EXPECTED_LIBRARY_SHA256')
    t.LIB_SHA=a.library_sha256
    os.environ['COPILOT_EXPECTED_LIBRARY_SHA256']=a.library_sha256
    t.OUT.mkdir(parents=True,exist_ok=True);g.OUT.mkdir(parents=True,exist_ok=True)
    if a.command=='prepare':prepare()
    elif a.command=='seed':seed(a.case)
    else:
        t.require(a.mode and a.id and all(c.isalnum() or c=='-' for c in a.id),'Safe mode/run required')
        run(a.case,a.mode,a.id,a.workers,a.threads)
if __name__=='__main__':main()
