#!/usr/bin/env python3
"""Correctness-only Phase 2D-B matrix, isolating optical and density errors."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
import numpy as np
from cases import ROOT,SIZES,api,configure,layout
from cuda_flux_correctness import collect,errors,metadata as cuda_metadata,COLUMNS


def compare(expected,actual):
    flux=errors(expected[0],actual[0])
    flux['bitwise']=bool(np.array_equal(expected[0].view(np.uint64),actual[0].view(np.uint64)))
    metric={}
    for name in ['peak_flux_kw_m2','integrated_incident_flux_kw','receiver_power_kw']:
        e,a=expected[1][name],actual[1][name]
        np.testing.assert_allclose(a,e,rtol=1e-9,atol=1e-10)
        metric[name]={'expected':e,'actual':a,'difference':a-e,'absolute_difference':abs(a-e)}
    detail={}
    for k in expected[2]: detail[k]=errors(expected[2][k],actual[2][k])
    return {'map':flux,'metrics':metric,'details':detail}


def snapshot(cp,r):
    flux,metrics=collect(cp,r)
    detail={k:np.asarray(v,dtype=np.float64) for k,v in cp.detail_results(r,restype='dictionary').items()}
    assert all(np.isfinite(v).all() for v in detail.values())
    return flux,metrics,detail


def run_case(size,grid,include_resident=False,image_block=128):
    cp=api();r=cp.data_create();assert r
    try:
        configure(cp,r,size)
        for axis in ['x_res','y_res']: assert cp.data_set_number(r,'fluxsim.0.'+axis,grid)
        assert cp.assign_layout(r,layout(SIZES[size]),nthreads=1)
        outputs={};intermediate={};density_diagnostics={};handoff={};materialization={}
        with tempfile.TemporaryDirectory() as temp:
            pipelines=[('legacy_cpu','legacy','cpu'),('flat_cpu','flat','cpu'),
                ('flat_cuda','flat','cuda'),('cuda_cpu','verify_cuda','cpu'),('cuda_cuda','verify_cuda','cuda')]
            if include_resident:pipelines.append(('cuda_resident','cuda','cuda'))
            for name,intercept,density in pipelines:
                assert cp.set_compute_backend(r,density)
                image_file=Path(temp)/(name+'-image.jsonl');density_file=Path(temp)/(name+'-density.csv')
                handoff_file=Path(temp)/(name+'-handoff.csv');materialize_file=Path(temp)/(name+'-materialize.csv')
                env={'SOLARPILOT_INTERCEPT_PATH':intercept,'SOLARPILOT_FLUX_PATH':'verify_cuda' if density=='cuda' and name!='cuda_resident' else 'flat',
                    'SOLARPILOT_IMAGE_PIPELINE':'resident' if name=='cuda_resident' else 'v1','SOLARPILOT_IMAGE_BLOCK_SIZE':str(image_block),
                    'SOLARPILOT_IMAGE_HANDOFF_FILE':str(handoff_file) if include_resident else '',
                    'SOLARPILOT_IMAGE_MATERIALIZE_FILE':str(materialize_file) if include_resident else '',
                    'SOLARPILOT_IMAGE_COMPARE_FILE':str(image_file) if intercept=='verify_cuda' else '',
                    'SOLARPILOT_CUDA_COMPARE_FILE':str(density_file),'SOLARPILOT_CUDA_BLOCK_SIZE':'256'}
                with patch.dict(os.environ,env):
                    assert cp.simulate(r,nthreads=1),cp.get_last_backend_error(r)
                    outputs[name]=snapshot(cp,r)
                    if intercept in ['verify_cuda','cuda']:
                        assert cp.simulate(r,nthreads=1),cp.get_last_backend_error(r)
                        repeated=snapshot(cp,r)
                        assert np.array_equal(outputs[name][0],repeated[0])
                if image_file.exists():
                    rows=[json.loads(x) for x in image_file.read_text().splitlines()]
                    assert len(rows)==2 and all(x['heliostats']==SIZES[size] and x['errors']['global']['passed'] for x in rows)
                    assert rows[0]['allocations']==rows[1]['allocations']
                    intermediate[name]=rows
                if density_file.exists():
                    rows=[dict(zip(COLUMNS,map(float,x))) for x in csv.reader(density_file.read_text().splitlines())]
                    assert all(x['block']==256 for x in rows)
                    for row in rows:
                        for k,v in row.items():
                            if not np.isfinite(v): row[k]=None
                    density_diagnostics[name]=rows
                if handoff_file.exists():
                    rows=[list(map(float,row)) for row in csv.reader(handoff_file.read_text().splitlines())]
                    handoff[name]=rows
                    if name=='cuda_resident':
                        assert len(rows)==2 and all(r[1]==1 and r[2]==56*SIZES[size] for r in rows)
                        assert rows[0][5]==rows[1][5]
                if materialize_file.exists():
                    rows=[list(map(float,row)) for row in csv.reader(materialize_file.read_text().splitlines())]
                    materialization[name]=rows
                    if name=='cuda_resident':assert len(rows)==2 and all(r[4]==1728*SIZES[size] and r[7]==16*SIZES[size] for r in rows)
            checks={
                'legacy_vs_flat':compare(outputs['legacy_cpu'],outputs['flat_cpu']),
                'intercept_only':compare(outputs['flat_cpu'],outputs['cuda_cpu']),
                'historical_density_only':compare(outputs['flat_cpu'],outputs['flat_cuda']),
                'density_with_same_cuda_optics':compare(outputs['cuda_cpu'],outputs['cuda_cuda']),
                'full_cuda':compare(outputs['flat_cpu'],outputs['cuda_cuda']),
                'intercept_effect_with_cuda_density':compare(outputs['flat_cuda'],outputs['cuda_cuda'])}
            if include_resident:
                checks['resident_full_cuda']=compare(outputs['flat_cpu'],outputs['cuda_resident'])
                checks['resident_vs_full_output_cuda']=compare(outputs['cuda_cuda'],outputs['cuda_resident'])
                assert checks['resident_vs_full_output_cuda']['map']['bitwise']
            assert checks['legacy_vs_flat']['map']['bitwise']
        return {'heliostats':SIZES[size],'grid':[grid,grid],'checks':checks,'intermediate':intermediate,
            'density_same_state_diagnostics':density_diagnostics,'repeated_cuda_maps_bitwise':True,
            'resident_handoff_receipts':handoff,'materialization_receipts':materialization,
            'layout_sha256':hashlib.sha256(json.dumps(layout(SIZES[size])).encode()).hexdigest()}
    finally: assert cp.data_free(r)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    for key in ['SOLARPILOT_IMAGE_TIMING_FILE','SOLARPILOT_CUDA_TIMING_FILE','SOLARPILOT_PROFILE_FILE','COPILOT_GPU_TIMING_ALLOWED']:
        os.environ.pop(key,None)
    metadata=cuda_metadata();metadata['execution_hostname']='pinned-cuda-container';metadata['hostname']='canonical-gpu-server'
    metadata.update({'phase':'2D-B','image_plane_block_size':128,'input_bytes':1640,'output_bytes':1728,'tables_bytes':3256,
        'historical_density_map_error_kw_m2':1.1141310096718371e-11,'gpu_timings_collected':False})
    result={'metadata':metadata,'cases':[]}
    for size in SIZES:
        for grid in [25,50,100]:
            row=run_case(size,grid);result['cases'].append(row)
            args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
            print(size,grid,'PASS; intercept map abs',row['checks']['intercept_only']['map']['max_abs'],
                'full CUDA abs',row['checks']['full_cuda']['map']['max_abs'],flush=True)

if __name__=='__main__': main()
