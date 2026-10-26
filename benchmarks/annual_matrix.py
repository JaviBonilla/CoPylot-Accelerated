#!/usr/bin/env python3
"""Complete direct annual optical matrix; private plans/payloads stay server-side."""
import argparse,csv,json,os,subprocess,time
from datetime import datetime,timedelta
from pathlib import Path
import numpy as np
import temporal_campaign as t
import cpu_multicore as cpu
import gpu_temporal as g
import gpu_temporal_pipeline as pipeline
from check_gpu_temporal import optical_capture

OUT=t.ROOT/'artifacts/annual-matrix'
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
    t.environment();cp=t.api();r,grid=t.context(cp,'cesa')
    try:
        project=json.loads((t.ROOT/'local-cases/example/phase3c-results/plan.json').read_text())
        t.verify_inputs(project)
        weather=[Path(p) for p in project['private_inputs'] if p.lower().endswith('.epw')]
        t.require(len(weather)==1,'Require the authoritative existing private EPW')
        with weather[0].open() as stream:
            headers=[next(stream) for _ in range(8)];rows=list(csv.reader(stream))
        candidates=epw_candidates(rows);site=[cp.data_get_number(r,k) for k in t.SITE[:3]]
        states,night=retained(candidates,t.sun_function(),site)
        # Fixed representative probes, entirely server-private. No timing selection.
        diag=[]
        for quarter in range(4):
            selected=[p for p in states if quarter*2190<=p['id']<(quarter+1)*2190]
            for key in [lambda p:p['sun'][1],lambda p:-p['sun'][1],lambda p:-abs(p['sun'][1]-30.)]:
                diag.append(max(selected,key=key))
        diag=list({p['id']:p for p in diag}.values())
        probe={**max(states,key=lambda p:p['sun'][1]),'id':8760,'dni':0.,'probe':True};diag.append(probe)
        plan={'case':'cesa','grid':grid,'requested':8760,'nighttime':night,'states':states,'seasonal':diag,'diagnostic':diag,
              'solar_year':2011,'sun_derivation':'Existing Ambient Hour/Day SOLPOS; no interval correction',
              'dni_policy':'Authoritative existing private EPW hourly DNI; evaluate hour-ending record at midpoint; retain daylight zero-DNI',
              'hour_policy':'EPW hour 1..24 -> local standard hour minus 0.5; API fixed non-leap 2011 calendar',
              'output_contract':t.CONTRACT,'aim_method':4,'private_epw_sha256':t.digest(weather[0]),
              'private_project_inputs':project['private_inputs']}
        t.require(not (t.OUT/'cesa-plan.json').exists(),'Refuse plan overwrite');t.write(t.OUT/'cesa-plan.json',plan)
    finally:cp.data_free(r)
    previous=t.ROOT/'artifacts/phase5a/commercial-plan.json';commercial=json.loads(previous.read_text())
    t.require(commercial['requested']==8760 and len(commercial['states'])==4403 and commercial['nighttime']==4357,'Commercial workload differs')
    t.require(not (t.OUT/'commercial-plan.json').exists(),'Refuse plan overwrite');t.write(t.OUT/'commercial-plan.json',commercial)
    t.write(OUT/'private-plan-audit.json',{'passed':True,'cesa':{'requested':8760,'evaluated':len(states),'nighttime':night,'daylight_zero_dni':sum(p['dni']==0 for p in states)},'commercial':{'requested':8760,'evaluated':4403,'nighttime':4357},'no_interpolation':True})
    print('Annual plans passed:',len(states),'CESA daylight states; 4403 commercial states',flush=True)

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

def run(case,mode,identifier):
    cpu.topology_cache=cpu.topology()
    if mode=='gpu':
        args=argparse.Namespace(case=case,workers=24,residency=False,series='states',id=identifier,library_sha256=os.environ['COPILOT_EXPECTED_LIBRARY_SHA256'])
        pipeline.campaign(args)
    else:
        os.environ['COPILOT_ANNUAL_PATH']='legacy' if mode=='original' else 'flat';t.environment()
        workers,threads=(12,2) if mode=='cpu' else (1,1)
        t.campaign(case,workers,threads,'states',identifier,'dynamic_lpt')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare','seed','run']);p.add_argument('--case',choices=['cesa','commercial']);p.add_argument('--mode',choices=['original','refactored','cpu','gpu']);p.add_argument('--id');a=p.parse_args()
    t.OUT.mkdir(parents=True,exist_ok=True);g.OUT.mkdir(parents=True,exist_ok=True)
    if a.command=='prepare':prepare()
    elif a.command=='seed':seed(a.case)
    else:
        t.require(a.case and a.mode and a.id and all(c.isalnum() or c=='-' for c in a.id),'Safe case/mode/run required');run(a.case,a.mode,a.id)
if __name__=='__main__':main()
