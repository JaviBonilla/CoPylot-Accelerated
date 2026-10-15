#!/usr/bin/env python3
"""Opt-in private serialized-project studies using the shared physical-grid framework."""
import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from unittest.mock import patch

import numpy as np
from cases import ROOT,api
from receiver_grid import refinement_series,map_metrics,compare_maps
from receiver_grid_convergence import analyze,backend_check,fluxmap
from image_plane_cuda_performance import PipelineWindow,wait_idle,metadata,distribution,call

CONTROL=['peak_rel','map_l1_normalized','map_l2_normalized','map_linf_normalized',
         'centroid_distance_over_diagonal','uniformity_cv_abs']
BANDS=[.001,.0025,.005,.01,.02]
SITE=['ambient.0.'+s for s in ('latitude','longitude','time_zone','elevation')]
TIME=['fluxsim.0.'+s for s in ('flux_month','flux_day','flux_hour','flux_dni')]
PLAIN={'SOLARPILOT_PROFILE_FILE':'','SOLARPILOT_CUDA_TIMING_FILE':'','SOLARPILOT_IMAGE_TIMING_FILE':'',
       'SOLARPILOT_IMAGE_COMPARE_FILE':'','SOLARPILOT_IMAGE_HANDOFF_FILE':'','SOLARPILOT_IMAGE_MATERIALIZE_FILE':'',
       'SOLARPILOT_FLUX_PATH':'flat','SOLARPILOT_IMAGE_PIPELINE':'resident'}


def digest(data):return hashlib.sha256(data).hexdigest()
def write(path,data):path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
def numbers(cp,r,keys):return {k:cp.data_get_number(r,k) for k in keys}
def require(ok,message):
    if not ok:raise RuntimeError(message)


def read_project_weather(cp,r):
    """Existing weather loader, no-filter mode: update site without any layout simulation.

    The older Python convenience method does not release its returned array.
    Call its existing C entry point with explicit ownership, including zero records.
    """
    f=cp.pdll.sp_generate_weather_simulation_data
    f.restype=ctypes.POINTER(ctypes.c_double)
    f.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_int),ctypes.POINTER(ctypes.c_int),ctypes.c_int]
    nr=ctypes.c_int();nc=ctypes.c_int();ptr=f(r,ctypes.byref(nr),ctypes.byref(nc),0)
    require(bool(ptr),'Reference weather preparation failed')
    try:require(nr.value==0,'No-filter weather preparation unexpectedly created simulation states')
    finally:
        release=cp.pdll._sp_free_var;release.argtypes=[ctypes.POINTER(ctypes.c_double)];release.restype=None;release(ptr)


def prepare(cp,project,point=None,grid=None):
    r=cp.data_create();require(bool(r),'Context allocation failed')
    try:
        cp.load_spt(r,project)
        require(Path(cp.data_get_string(r,'ambient.0.weather_file')).is_file(),'Reference weather is unavailable')
        read_project_weather(cp,r)
        require(cp.restore_loaded_layout(r),'Serialized restoration failed')
        require(cp.data_get_number(r,'fluxsim.0.aim_method')==4,'Study requires saved Keep existing aiming')
        require(cp.data_get_number(r,'fluxsim.0.flux_time_type')==1,'Study requires existing Hour/Day semantics')
        if point:
            for key,value in point['inputs'].items():require(cp.data_set_number(r,key,value),'Cannot select Hour/Day state')
        if grid:
            for name,value in [('x_res',grid['nx']),('y_res',grid['ny'])]:
                require(cp.data_set_number(r,'fluxsim.0.'+name,value),'Cannot select receiver grid')
        return r
    except Exception:cp.data_free(r);raise


def simulate(cp,r):
    start=time.perf_counter();require(cp.simulate(r,nthreads=1),'Single-state simulation failed');return time.perf_counter()-start


def input_names():
    """Read existing input declarations; computed .setup outputs are excluded."""
    names=set()
    for line in (ROOT/'ssc/solarpilot/definitions.cpp').read_text().splitlines():
        if '.set(' not in line or 'SP_DATTYPE' not in line:continue
        literals=re.findall(r'"([^"]*)"',line.split('SP_DATTYPE')[0])
        if literals and '.' in literals[0]:names.add((literals[0].split('.')[0],literals[-1].split('.')[-1]))
    require(len(names)>150,'Input declaration schema was not recognized');return names


def frozen_state(cp,r,directory):
    """Full saved input strings plus exact runtime geometry/aim/site/sun doubles.

    The serializer has inherited precision limits; critical geometry and resolved
    solar state are independently compared at full double precision.
    """
    file=directory/'runtime-input-audit.spt';cp.save_spt(r,file)
    declared=input_names();saved={}
    for node in ET.parse(file).getroot().findall('variable'):
        comp,instance,name=[node.findtext(k) for k in ('component','instance','varname')]
        if (comp,name) in declared and (comp,name) not in {('fluxsim','x_res'),('fluxsim','y_res')}:
            saved['.'.join([comp,instance,name])]=node.findtext('value') or ''
    geometry=np.asarray(cp.get_layout_info(r,get_optical_details=True,restype='matrix')[0],dtype='<f8')
    details=cp.detail_results(r,restype='dictionary')
    aims=np.column_stack([details[k+'_aimpoint'] for k in 'xyz']).astype('<f8')
    geometry=np.column_stack([geometry[:,:5],geometry[:,6:]]).astype('<f8') # Exclude computed ranking.
    state=numbers(cp,r,SITE+TIME+['fluxsim.0.flux_solar_az','fluxsim.0.flux_solar_el'])
    return {'input_hash':digest(json.dumps(saved,sort_keys=True).encode()),'runtime_geometry_hash':digest(geometry.tobytes()),
            'aim_hash':digest(aims.tobytes()),'resolved_state':state,'saved_input_count':len(saved),
            'runtime_count':len(geometry),'serialized_layout_hash':digest(cp.data_get_string(r,'solarfield.0.layout_data').encode())}


def assert_frozen(a,b):require(a==b,'Physical state changed while varying only receiver discretization')
def power(cp,r):return next(iter(cp.summary_results(r).values()))['Power absorbed by the receiver']


def plan(cp,project,output):
    r=prepare(cp,project)
    try:
        site=numbers(cp,r,SITE);time_inputs=numbers(cp,r,TIME)
        rt=cp.data_get_number(r,'receiver.0.rec_type')
        if rt==2:receiver={'type':'flat','width_m':cp.data_get_number(r,'receiver.0.rec_width'),'height_m':cp.data_get_number(r,'receiver.0.rec_height')}
        elif rt==0:receiver={'type':'cylindrical','diameter_m':cp.data_get_number(r,'receiver.0.rec_diameter'),'height_m':cp.data_get_number(r,'receiver.0.rec_height')}
        else:raise ValueError('Unsupported project receiver for this study')
        span=receiver.get('width_m',math.pi*receiver.get('diameter_m',0.));delta=max(span,receiver['height_m'])/8
        grids=refinement_series(receiver,[delta/(2**i) for i in range(8)])
        # Approximate civil solar noon only chooses four clock inputs. All actual
        # solar positions are evaluated by the existing SolarPILOT Hour/Day path.
        noon=12+site['ambient.0.time_zone']-site['ambient.0.longitude']/15
        points=[]
        for sid,offset in [('high-elevation',0),('moderate-elevation',-1.5),('morning-offdesign',-3.5),('afternoon-offdesign',3)]:
            inputs={**time_inputs,'fluxsim.0.flux_hour':round(noon+offset,6)}
            require(0<=inputs['fluxsim.0.flux_hour']<24,'Selected civil hour is invalid')
            for key,value in inputs.items():require(cp.data_set_number(r,key,value),'Cannot set selected state')
            for k,v in [('x_res',grids[0]['nx']),('y_res',grids[0]['ny'])]:cp.data_set_number(r,'fluxsim.0.'+k,v)
            with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'verify'}):simulate(cp,r)
            resolved=numbers(cp,r,['fluxsim.0.flux_solar_az','fluxsim.0.flux_solar_el'])
            require(resolved['fluxsim.0.flux_solar_el']>5 and inputs['fluxsim.0.flux_dni']>10,'Selected state is inactive or below the horizon')
            require(np.isfinite(fluxmap(cp,r)).all() and power(cp,r)>0,'Selected state has invalid field response')
            points.append({'id':sid,'inputs':inputs,'site':site,'resolved':resolved,'dni_source':'unchanged project flux_dni; EPW supplies site metadata'})
        native={'receiver_type':receiver['type'],'nx':25,'ny':25,'cells':625,'surface_width_m':span,'height_m':receiver['height_m'],
                'target_cell_m':None,'cell_width_m':span/25,'cell_height_m':receiver['height_m']/25}
        weather=Path(cp.data_get_string(r,'ambient.0.weather_file'))
        result={'case_id':'cesa-i-private-restored','phase':'3C','project':str(project.resolve()),
            'private_inputs':{str(project.resolve()):digest(project.read_bytes()),str(weather):digest(weather.read_bytes())},
            'receiver':receiver,'operating_points':points,'grids':grids,'native_grid':native,'initial_levels':7,'extra_levels_allowed':1,
            'canonical_path':'load; existing no-filter weather metadata preparation; serialized restore; Keep existing; Hour/Day',
            'study':{'control_metrics':CONTROL,'energy_metrics':['integrated_incident_power_rel'],'tolerance_bands':BANDS},
            'primary_control_tolerance':.01,'reference_extension_policy':'Add the eighth planned level if the 1% candidate changes or is unresolved under reference refinement'}
        write(output,result)
        print('Plan frozen: four valid Hour/Day states, seven initial physical levels, one optional extra; native grid separate.',flush=True)
    finally:cp.data_free(r)


def verify_inputs(plan):
    for path,value in plan['private_inputs'].items():require(digest(Path(path).read_bytes())==value,'Private input integrity changed')


def correctness(cp,plan,output,levels,previous=None):
    verify_inputs(plan);directory=output.parent;mapdir=directory/'maps';mapdir.mkdir(exist_ok=True)
    result=json.loads(Path(previous).read_text()) if previous else {'case_id':plan['case_id'],'phase':'3C','rows':[],'native_rows':[],'status':'running','physics_checks':{}}
    maps={}
    for row in result['rows']+result['native_rows']:
        data=np.load(directory/row['map_file']);maps[(row['operating_point'],row['level'])]=data['flat']
    existing={(r['operating_point'],r['level']) for r in result['rows']+result['native_rows']}
    for point in plan['operating_points']:
        for level,grid in [(-1,plan['native_grid'])]+list(enumerate(plan['grids'][:levels])):
            if (point['id'],level) in existing:continue
            r=prepare(cp,Path(plan['project']),point,grid)
            try:
                with tempfile.TemporaryDirectory(dir=directory) as td:
                    td=Path(td)
                    with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'verify'}):simulate(cp,r)
                    flat=fluxmap(cp,r);flat_power=power(cp,r);frozen=frozen_state(cp,r,td)
                    expected=result['physics_checks'].setdefault(point['id'],frozen);assert_frozen(expected,frozen)
                    row={'case_id':plan['case_id'],'operating_point':point['id'],'level':level,'grid':grid,
                         'metrics':map_metrics(flat,grid),'physical_state_frozen':True}
                    if level in (-1,0,3,levels-1):
                        with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'legacy','SOLARPILOT_FLUX_PATH':'legacy'}):simulate(cp,r)
                        require(np.array_equal(flat.view(np.uint64),fluxmap(cp,r).view(np.uint64)),'Legacy/Flat anchor is not bitwise equal')
                        assert_frozen(expected,frozen_state(cp,r,td));row['legacy_anchor_bitwise']=True
                    require(cp.set_compute_backend(r,'cuda'),'CUDA unavailable for correctness campaign')
                    optics=td/'optics.jsonl'
                    with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'verify_cuda' if level in (-1,0,3,levels-1) else 'cuda',
                         'SOLARPILOT_IMAGE_COMPARE_FILE':str(optics) if level in (-1,0,3,levels-1) else ''}):simulate(cp,r)
                    cuda=fluxmap(cp,r);row['backend_errors']=backend_check(flat,cuda,grid)
                    row['backend_errors']['summary_power_difference_kw']=power(cp,r)-flat_power
                    np.testing.assert_allclose(power(cp,r),flat_power,rtol=1e-9,atol=1e-10)
                    for _ in range(2):
                        with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'cuda'}):simulate(cp,r)
                        require(np.array_equal(cuda.view(np.uint64),fluxmap(cp,r).view(np.uint64)),'CUDA map repeat is not bitwise deterministic')
                    row['deterministic']=True;assert_frozen(expected,frozen_state(cp,r,td))
                    if optics.exists():row['all215']=json.loads(optics.read_text().splitlines()[-1])['errors']
                    filename=point['id']+f'-level-{level}.npz';np.savez_compressed(mapdir/filename,flat=flat,cuda=cuda)
                    row['map_file']='maps/'+filename;maps[(point['id'],level)]=flat
                    (result['native_rows'] if level==-1 else result['rows']).append(row)
                    write(output,result)
                    print(point['id'],'level',level,grid['nx'],grid['ny'],'correctness PASS',flush=True)
            finally:cp.data_free(r)
    analyze(result,maps,plan)
    last=levels-1
    for row in result['native_rows']:
        row['convergence']=compare_maps(maps[(row['operating_point'],-1)],maps[(row['operating_point'],last)],row['grid'],plan['grids'][last])
    current=next(b['control_minimum_tested_level'] for b in result['recommendations']['bands'] if b['tolerance']==.01)
    prior=next(b['minimum_tested_level'] for b in result['previous_reference_recommendations'] if b['tolerance']==.01)
    result['primary_candidate']=current;result['previous_reference_primary_candidate']=prior
    result['reference_extension_required']=current is None or current!=prior
    result['status']='passed';verify_inputs(plan);write(output,result)
    print('Convergence PASS; 1% candidate:',current,'previous reference:',prior,'extra refinement needed:',result['reference_extension_required'],flush=True)


def performance(cp,plan,correct,output):
    verify_inputs(plan);cpus=sorted(os.sched_getaffinity(0));require(len(cpus)>1,'Monitoring needs a separate logical CPU')
    os.sched_setaffinity(0,{cpus[0]});wait_idle();window=PipelineWindow(cpus[-1])
    result={'case_id':plan['case_id'],'phase':'3C','status':'running','rows':[],'metadata':metadata(cpus[0],cpus[-1])}
    for k in ('weather_sha256','parameters'):result['metadata'].pop(k,None)
    result['metadata']['simulate_wall_definition']='Plain public simulate wall time; no diagnostic files/events. First call and all warmups excluded.'
    result['runtime_probe_s']=window.initialize(cp)
    try:
        byid={p['id']:p for p in plan['operating_points']}
        for source in correct['native_rows']+correct['rows']:
            point=byid[source['operating_point']];grid=source['grid'];r=prepare(cp,Path(plan['project']),point,grid)
            row={k:source[k] for k in ('case_id','operating_point','level','grid')};row['pipelines']={}
            try:
                arrays={}
                for name in ['flat','cuda']+(['legacy'] if source['level'] in (-1,correct['primary_candidate']) else []):
                    cp.set_compute_backend(r,'cuda' if name=='cuda' else 'cpu')
                    with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'cuda' if name=='cuda' else name,
                                                'SOLARPILOT_FLUX_PATH':'legacy' if name=='legacy' else 'flat'}):
                        first=simulate(cp,r)
                        warmups=3 if name=='cuda' else 2;repeats=10 if name=='cuda' else 5
                        for _ in range(warmups):simulate(cp,r)
                        samples=[simulate(cp,r) for _ in range(repeats)]
                        arrays[name]=fluxmap(cp,r)
                    row['pipelines'][name]={'first_call_s':first,'warmups_excluded_after_first':warmups,'samples_s':samples,'statistics_s':distribution(samples)}
                row['backend_errors']=backend_check(arrays['flat'],arrays['cuda'],grid)
                if 'legacy' in arrays:require(np.array_equal(arrays['legacy'].view(np.uint64),arrays['flat'].view(np.uint64)),'Timed Legacy anchor drift')
                with tempfile.TemporaryDirectory(dir=output.parent) as td:assert_frozen(correct['physics_checks'][point['id']],frozen_state(cp,r,Path(td)))
                row['flat_cuda_speedup']=row['pipelines']['flat']['statistics_s']['median']/row['pipelines']['cuda']['statistics_s']['median']
                window.validate();result['rows'].append(row);write(output,result)
                print(point['id'],'level',source['level'],grid['nx'],grid['ny'],'Flat ms',round(row['pipelines']['flat']['statistics_s']['median']*1000,3),
                      'CUDA ms',round(row['pipelines']['cuda']['statistics_s']['median']*1000,3),'speedup',round(row['flat_cuda_speedup'],3),flush=True)
            finally:cp.data_free(r)
        window.close();result.update(status='passed',gpu_telemetry=window.samples);verify_inputs(plan);write(output,result)
    except Exception:
        window.stop.set();result.update(status='invalid',gpu_telemetry=window.samples);write(output,result);raise


def profile(cp,plan,correct,output):
    level=correct['primary_candidate'];require(level is not None,'No primary candidate available to profile')
    cpus=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpus[0]});wait_idle();window=PipelineWindow(cpus[-1]);window.initialize(cp)
    result={'case_id':plan['case_id'],'level':level,'grid':plan['grids'][level],'profiles':{},'status':'running'}
    point=plan['operating_points'][0];r=prepare(cp,Path(plan['project']),point,plan['grids'][level])
    try:
        with tempfile.TemporaryDirectory(dir=output.parent) as td:
            for name in ('flat','cuda'):
                cp.set_compute_backend(r,'cuda' if name=='cuda' else 'cpu')
                with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':name}):
                    for _ in range(3):call(cp,r,Path(td),name=='cuda',name=='cuda',True)
                    result['profiles'][name]=call(cp,r,Path(td),name=='cuda',name=='cuda',True)
            assert_frozen(correct['physics_checks'][point['id']],frozen_state(cp,r,Path(td)))
        window.close();result.update(status='passed',gpu_telemetry=window.samples);verify_inputs(plan);write(output,result)
    finally:window.stop.set();cp.data_free(r)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['plan','correctness','performance','profile'],required=True)
    p.add_argument('--project',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--correctness',type=Path)
    p.add_argument('--previous',type=Path);p.add_argument('--levels',type=int,default=7);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    try:args.output.resolve().relative_to(ROOT/'local-cases')
    except ValueError:p.error('Detailed project evidence must stay under the ignored local-cases directory')
    if args.output.exists():p.error('Refusing to overwrite study evidence')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for key in list(os.environ):
        if key.startswith('SOLARPILOT_'):os.environ.pop(key)
    cp=api()
    if args.stage=='plan':require(args.project is not None,'Project required');plan(cp,args.project,args.output);return
    data=json.loads(args.plan.read_text());require(5<=args.levels<=8,'Use five to eight planned levels')
    if args.stage=='correctness':correctness(cp,data,args.output,args.levels,args.previous)
    else:
        correct=json.loads(args.correctness.read_text());require(correct['status']=='passed','Correctness must pass before characterization')
        if args.stage=='performance':performance(cp,data,correct,args.output)
        else:profile(cp,data,correct,args.output)

if __name__=='__main__':main()
