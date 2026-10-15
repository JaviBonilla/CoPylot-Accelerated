#!/usr/bin/env python3
"""Publish validated physical-resolution evidence without rerunning simulations."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import re
import subprocess
import numpy as np
from commercial_reference import MANIFEST,load_manifest
from receiver_grid_convergence import analyze


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--case',type=Path,required=True);parser.add_argument('--output',type=Path,default=Path('benchmarks/results'))
    args=parser.parse_args();raw=json.loads(args.input.read_text());m=load_manifest()
    assert raw['status']=='valid' and raw['gpu_performance_collected']
    assert raw['manifest_sha256']==hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    levels=len(m['study']['initial_target_cell_sizes_m'])+1;points=[p['id'] for p in m['operating_points']]
    assert len(raw['rows'])==levels*len(points)
    assert {(r['level'],r['operating_point']) for r in raw['rows']}=={(l,p) for l in range(levels) for p in points}
    previous=json.loads(Path('benchmarks/results/phase2dc-final-performance.json').read_text())
    assert raw['metadata']['library_sha256']==previous['metadata']['library_sha256']
    for name in ['ssc','SolarPILOT','SolTrace']:assert raw['metadata']['commits'][name]==previous['metadata']['commits'][name]
    cpu_counts={len(r['pipelines']['flat']['samples_s']) for r in raw['rows']}
    cuda_counts={len(r['pipelines']['cuda']['samples_s']) for r in raw['rows']}
    assert len(cpu_counts)==len(cuda_counts)==1
    raw['metadata'].update(phase='3A',image_block_size=64,density_block_size=256,
        unchanged_phase2dc_library=True,cpu_repetitions=cpu_counts.pop(),cuda_repetitions=cuda_counts.pop(),
        monitoring='Stable idle preflight; exact owned process; <=4096 MiB after context; <80 C, no thermal slowdown; no concurrent server build/test.')
    assert all(s['compute_process_count']<=1 and float(s['temperature.gpu'])<80 for s in raw['gpu_telemetry'])
    args.output.mkdir(parents=True,exist_ok=True);mapdir=args.output/'phase3a-grid-maps';mapdir.mkdir(exist_ok=True)
    maps={}
    for r in raw['rows']:
        assert r['cpu_gpu']['passed'] and r['pipelines']['cuda']['repeated_bitwise']
        assert all(np.isfinite(p['absorbed_receiver_power_kw']) and p['absorbed_receiver_power_kw']>0 for p in r['pipelines'].values())
        assert r['convergence']['remap_relative_integral_error']<1e-12
        path=args.input.parent/r['map_file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==r['map_sha256']
        arrays=np.load(path,allow_pickle=False)
        assert all(arrays[k].shape==(r['grid']['ny'],r['grid']['nx']) for k in ['flat','cuda'])
        np.testing.assert_allclose(arrays['cuda'],arrays['flat'],rtol=1e-9,atol=1e-10)
        maps[(r['operating_point'],r['level'])]=arrays['flat'].copy()
        shutil.copyfile(path,mapdir/path.name);r['map_file']='phase3a-grid-maps/'+path.name
    # Recompute only spatial analysis from retained measured maps. Numerical core,
    # timing samples and their executed commit provenance remain unchanged.
    analyze(raw,maps,m)
    raw['metadata']['analysis_root_sha']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    raw['metadata']['capture_sha256']=hashlib.sha256(args.input.read_bytes()).hexdigest()
    bylevel=[]
    for level in range(levels):
        rows=[r for r in raw['rows'] if r['level']==level];metrics=rows[0]['convergence']
        summaries={}
        for key in metrics:
            values=[r['convergence'][key] for r in rows]
            if any(v is None for v in values):continue
            worst=max(rows,key=lambda r:r['convergence'][key])
            summaries[key]={'best':min(values),'median':statistics.median(values),'worst':max(values),'worst_operating_point':worst['operating_point']}
        bylevel.append({'level':level,'grid':rows[0]['grid'],'errors_across_states':summaries,
            'flat_median_s_range':[min(r['pipelines']['flat']['statistics_s']['median'] for r in rows),max(r['pipelines']['flat']['statistics_s']['median'] for r in rows)],
            'cuda_median_s_range':[min(r['pipelines']['cuda']['statistics_s']['median'] for r in rows),max(r['pipelines']['cuda']['statistics_s']['median'] for r in rows)],
            'speedup_range':[min(r['flat_to_cuda_speedup'] for r in rows),max(r['flat_to_cuda_speedup'] for r in rows)]})
    summary={'metadata':raw['metadata'],'case_id':raw['case_id'],'receiver':raw['receiver'],'operating_points':m['operating_points'],
        'levels':bylevel,'recommendations':raw['recommendations'],'previous_reference_recommendations':raw['previous_reference_recommendations'],
        'reference_refinement_check':raw['reference_refinement_check'],
        'energy_resolution':None,'energy_reason':'Normalized dimensional power is constrained by the existing heliostat power model and cannot identify an independent spatial energy resolution.',
        'reference_limit':'Finest computed grid is a numerical reference; all conclusions are conditional on this model, these states and this computed range.',
        'worst_cpu_gpu_abs_kw_m2':max(r['cpu_gpu']['max_abs_kw_m2'] for r in raw['rows']),
        'worst_cpu_gpu_rel_nonzero':max(r['cpu_gpu']['max_rel_nonzero'] for r in raw['rows']),
        'worst_cpu_gpu_rms_kw_m2':max(r['cpu_gpu']['rms_kw_m2'] for r in raw['rows']),
        'max_remap_relative_integral_error':max(r['convergence']['remap_relative_integral_error'] for r in raw['rows'])}
    def publish(name,data):
        text=json.dumps(data,indent=2,allow_nan=False)+'\n'
        assert not re.search(r'/workspace',text),name
        (args.output/name).write_text(text)
    case=json.loads(args.case.read_text());assert case['manifest_sha256']==raw['manifest_sha256']
    case.update(metadata=raw['metadata'],case_kind=m['kind'],exact_real_plant_reproduction=False)
    publish('phase3a-commercial-case.json',case);publish('phase3a-grid-convergence.json',raw);publish('phase3a-grid-convergence-summary.json',summary)
    csvrows=[]
    for r in raw['rows']:
        g=r['grid'];row={'case_id':raw['case_id'],'operating_point':r['operating_point'],'level':r['level'],**g,
            'diameter_m':raw['receiver']['diameter_m'],'sun_azimuth_deg':r['sun']['azimuth_deg'],'sun_elevation_deg':r['sun']['elevation_deg'],'dni_w_m2':r['sun']['dni_w_m2'],
            'model':'Hermite','cpu_backend':'Flat 1T','cuda_backend':'Phase 2D-C resident64/density256',**r['pipelines']['flat']['metrics'],**r['convergence'],
            'flat_median_s':r['pipelines']['flat']['statistics_s']['median'],'cuda_median_s':r['pipelines']['cuda']['statistics_s']['median'],
            'flat_cv':r['pipelines']['flat']['statistics_s']['coefficient_of_variation'],'cuda_cv':r['pipelines']['cuda']['statistics_s']['coefficient_of_variation'],
            'speedup':r['flat_to_cuda_speedup'],'cpu_gpu_abs_kw_m2':r['cpu_gpu']['max_abs_kw_m2'],'cpu_gpu_rel_nonzero':r['cpu_gpu']['max_rel_nonzero'],
            'cpu_gpu_rms_kw_m2':r['cpu_gpu']['rms_kw_m2'],'cpu_gpu_power_difference_kw':r['cpu_gpu']['integrated_power_difference_kw'],
            'cpu_gpu_peak_difference_kw_m2':r['cpu_gpu']['peak_difference_kw_m2'],'total_level_runtime_s':r['total_level_runtime_s'],
            **{name.replace('.','root')+'_sha':sha for name,sha in raw['metadata']['commits'].items()},
            'cpu_model':raw['metadata']['cpu_model'],'gpu_model':raw['gpu_telemetry'][0]['name'],'driver':raw['gpu_telemetry'][0]['driver_version'],
            'build_type':raw['metadata']['build_settings']['CMAKE_BUILD_TYPE'],'precision':'double','fma':True,'fast_math':False,
            'library_sha256':raw['metadata']['library_sha256'],'map_file':r['map_file']}
        csvrows.append(row)
    for name,fields in [('phase3a-grid-convergence.csv',list(csvrows[0])),('phase3a-cpu-gpu-resolution-performance.csv',[
        'case_id','operating_point','level','nx','ny','cells','cell_width_m','cell_height_m','flat_median_s','cuda_median_s','flat_cv','cuda_cv','speedup','root_sha','ssc_sha','library_sha256'])]:
        with (args.output/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');writer.writeheader();writer.writerows(csvrows)
    print('Published',len(raw['rows']),'validated states/grids and',levels,'physical levels')


if __name__=='__main__':main()
