#!/usr/bin/env python3
"""Measure physical Hermite refinement using the unchanged Phase 2D-C core."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from unittest.mock import patch
import numpy as np
from cases import ROOT,api
from commercial_reference import MANIFEST,load_manifest,configure
from receiver_grid import refinement_series,map_metrics,compare_maps,minimum_converged
from image_plane_cuda_performance import PipelineWindow,wait_idle,metadata,distribution


def simulate(cp,r):
    start=time.perf_counter()
    if not cp.simulate(r,nthreads=1):raise RuntimeError(cp.get_last_backend_error(r))
    return time.perf_counter()-start


def fluxmap(cp,r):
    # C API row 0 is the top; scientific utilities use z increasing from bottom.
    return np.asarray(cp.get_fluxmap(r),dtype=np.float64)[::-1,:].copy()


def backend_check(reference,actual,grid):
    np.testing.assert_allclose(actual,reference,rtol=1e-9,atol=1e-10,equal_nan=False)
    diff=actual-reference;relative=np.divide(np.abs(diff),np.abs(reference),out=np.zeros_like(diff),where=reference!=0)
    a=map_metrics(reference,grid);b=map_metrics(actual,grid)
    result={'max_abs_kw_m2':float(np.abs(diff).max()),'max_rel_nonzero':float(relative.max()),
        'zero_reference_nonzero':int(np.count_nonzero((reference==0)&(actual!=0))),
        'rms_kw_m2':float(np.sqrt(np.mean(diff**2))),'integrated_power_difference_kw':b['integrated_incident_power_kw']-a['integrated_incident_power_kw'],
        'peak_difference_kw_m2':b['peak_cell_average_proxy_kw_m2']-a['peak_cell_average_proxy_kw_m2'],
        'worst_row_col':list(map(int,np.unravel_index(np.abs(diff).argmax(),diff.shape))),'passed':True}
    for k in ['integrated_incident_power_kw','peak_cell_average_proxy_kw_m2']:np.testing.assert_allclose(a[k],b[k],rtol=1e-9,atol=1e-10)
    return result


def analyze(result,maps,manifest):
    last=max(r['level'] for r in result['rows']);points=[p['id'] for p in manifest['operating_points']]
    for r in result['rows']:
        reference=next(q for q in result['rows'] if q['level']==last and q['operating_point']==r['operating_point'])
        r['convergence']=compare_maps(maps[(r['operating_point'],r['level'])],maps[(r['operating_point'],last)],r['grid'],reference['grid'])
        r['reference_level']=last
    criteria=manifest['study'];bands=[]
    for tolerance in criteria['tolerance_bands']:
        candidate=minimum_converged(result['rows'],points,criteria['control_metrics'],tolerance,last)
        bands.append({'tolerance':tolerance,'control_minimum_tested_level':candidate,
            'energy_normalization_only_minimum_level':minimum_converged(result['rows'],points,criteria['energy_metrics'],tolerance,last),
            'energy_scientific_recommendation':None,
            'energy_reason':'The dimensional integral is normalized to delivered heliostat power; independent spatial energy accuracy is not identified by this invariant.'})
    result['recommendations']={'bands':bands,'reference_level':last,'reference_is_physical_truth':False,
        'control_criteria':criteria['control_metrics'],'policy':'Minimum tested level passing all representative states and every tested finer nonreference level; not a universal optimum.'}
    prior=last-1
    result['reference_refinement_check']=[{'operating_point':r['operating_point'],'from_level':prior,'to_level':last,
        'convergence':r['convergence']} for r in result['rows'] if r['level']==prior]
    result['previous_reference_recommendations']=[{'tolerance':t,'minimum_tested_level':minimum_converged([
        {**r,'convergence':compare_maps(maps[(r['operating_point'],r['level'])],maps[(r['operating_point'],prior)],r['grid'],
        next(q['grid'] for q in result['rows'] if q['level']==prior and q['operating_point']==r['operating_point']))}
        for r in result['rows'] if r['level']<=prior],points,criteria['control_metrics'],t,prior)} for t in criteria['tolerance_bands']]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cpu-repetitions',type=int,default=3);parser.add_argument('--cuda-repetitions',type=int,default=10)
    parser.add_argument('--cpu-only',action='store_true');args=parser.parse_args()
    if args.output.exists():raise RuntimeError('Refusing to overwrite campaign evidence')
    if min(args.cpu_repetitions,args.cuda_repetitions)<2:raise ValueError('At least two timing samples required')
    m=load_manifest();p=m['parameters'];receiver={'type':'cylindrical','diameter_m':p['receiver.0.rec_diameter']['value'],'height_m':p['receiver.0.rec_height']['value']}
    targets=[*m['study']['initial_target_cell_sizes_m'],m['study']['validation_target_cell_size_m']]
    grids=refinement_series(receiver,targets);cpus=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpus[0]})
    for k in list(os.environ):
        if k.startswith('SOLARPILOT_'):os.environ.pop(k)
    args.output.parent.mkdir(parents=True,exist_ok=True);mapdir=args.output.parent/'maps';mapdir.mkdir(exist_ok=True)
    result={'phase':'3A','status':'running_unvalidated','case_id':m['case_id'],'receiver':receiver,'rows':[],
        'manifest_sha256':hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),'metadata':metadata(cpus[0],cpus[-1]) if not args.cpu_only else
            {'commits':{n:__import__('subprocess').check_output(['git','-C',str(ROOT/n),'rev-parse','HEAD'],text=True).strip() for n in ['.','ssc','SolarPILOT','SolTrace']},'cpu_threads':1},
        'map_representation':'Piecewise constant equal-area cells from normalized Hermite midpoint samples; not true integrated cell averages.',
        'map_orientation':'Rows increase from receiver bottom after C API vertical reversal. Columns follow native decreasing azimuth; s starts at native clockwise seam.',
        'performance_policy':'Plain public simulate wall time, no diagnostic CSV/events; compiled coarse scopes retained. CPU first + 1 warmup excluded; CUDA first + 2 warmups excluded. No concurrent server jobs.'}
    window=None;maps={};cp=api()
    try:
        if not args.cpu_only:
            wait_idle();window=PipelineWindow(cpus[-1]);result['runtime_probe_s']=window.initialize(cp)
        for point in m['operating_points']:
            for level,grid in enumerate(grids):
                started=time.perf_counter();r=cp.data_create()
                row={'case_id':m['case_id'],'operating_point':point['id'],'sun':point,'receiver':receiver,'level':level,'grid':grid,'pipelines':{}}
                try:
                    row['sanity']=configure(cp,r,m,grid['nx'],grid['ny'],point)
                    arrays={}
                    for name in ['flat']+([] if args.cpu_only else ['cuda']):
                        if not cp.set_compute_backend(r,name if name=='cuda' else 'cpu'):raise RuntimeError('Backend selection failed')
                        with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'cuda' if name=='cuda' else 'flat','SOLARPILOT_FLUX_PATH':'flat'}):
                            first=simulate(cp,r)
                            for _ in range(2 if name=='cuda' else 1):simulate(cp,r)
                            samples=[simulate(cp,r) for _ in range(args.cuda_repetitions if name=='cuda' else args.cpu_repetitions)]
                            values=fluxmap(cp,r);simulate(cp,r);repeated=fluxmap(cp,r)
                        assert np.array_equal(values.view(np.uint64),repeated.view(np.uint64))
                        arrays[name]=values
                        row['pipelines'][name]={'first_call_s':first,'warmups_excluded':3 if name=='cuda' else 2,'samples_s':samples,
                            'statistics_s':distribution(samples),'metrics':map_metrics(values,grid),'repeated_bitwise':True,
                            'absorbed_receiver_power_kw':next(iter(cp.summary_results(r).values()))['Power absorbed by the receiver']}
                    maps[(point['id'],level)]=arrays['flat']
                    if 'cuda' in arrays:
                        row['cpu_gpu']=backend_check(arrays['flat'],arrays['cuda'],grid)
                        row['flat_to_cuda_speedup']=row['pipelines']['flat']['statistics_s']['median']/row['pipelines']['cuda']['statistics_s']['median']
                    if level in [0,3]:
                        cp.set_compute_backend(r,'cpu')
                        with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'legacy','SOLARPILOT_FLUX_PATH':'legacy'}):simulate(cp,r);legacy=fluxmap(cp,r)
                        assert np.array_equal(legacy.view(np.uint64),arrays['flat'].view(np.uint64));row['legacy_anchor_bitwise']=True
                    filename=point['id']+f'-level-{level}.npz';np.savez_compressed(mapdir/filename,**arrays)
                    row['map_file']='maps/'+filename;row['map_sha256']=hashlib.sha256((mapdir/filename).read_bytes()).hexdigest()
                    row['total_level_runtime_s']=time.perf_counter()-started
                    if window:window.validate()
                    result['rows'].append(row)
                    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
                    print(point['id'],level,grid['nx'],grid['ny'],'Flat ms',round(row['pipelines']['flat']['statistics_s']['median']*1000,3),
                        'CUDA ms',round(row['pipelines'].get('cuda',{}).get('statistics_s',{}).get('median',0)*1000,3),'PASS',flush=True)
                finally:cp.data_free(r)
        analyze(result,maps,m)
        if window:window.close()
        result.update(status='valid',gpu_telemetry=window.samples if window else [],gpu_performance_collected=not args.cpu_only)
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    except Exception as error:
        if window:window.stop.set()
        result.update(status='invalid',reason=str(error),gpu_telemetry=window.samples if window else [])
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');raise


if __name__=='__main__':main()
