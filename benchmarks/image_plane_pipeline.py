#!/usr/bin/env python3
"""Phase 2D-A downstream correctness and single-thread CPU simulate measurements."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from unittest.mock import patch

import numpy as np
from cases import ROOT,SIZES,api,configure,layout
from cuda_flux_correctness import collect,errors
from image_plane import metadata,statistics_s


def snapshot(cp,r):
    flux,metrics=collect(cp,r)
    details={k:np.asarray(v,dtype=np.float64) for k,v in cp.detail_results(r,restype='dictionary').items()}
    summary={k:v for k,v in next(iter(cp.summary_results(r).values())).items() if isinstance(v,(float,int))}
    assert np.isfinite(flux).all() and flux.max()>0
    assert all(np.isfinite(v).all() for v in details.values())
    return flux,metrics,details,summary


def compare(expected,actual):
    flux=errors(expected[0],actual[0])
    flux['bitwise']=bool(np.array_equal(expected[0].view(np.uint64),actual[0].view(np.uint64)))
    checks={}
    for k in expected[2]:
        checks[k]=errors(expected[2][k],actual[2][k])
        checks[k]['bitwise']=bool(np.array_equal(expected[2][k].view(np.uint64),actual[2][k].view(np.uint64)))
    assert expected[1]==actual[1] and expected[3]==actual[3]
    return {'flux':flux,'detail_columns':checks,'metrics':actual[1],'summary_equal':True}


def run(performance):
    result={'metadata':metadata(),'cases':[]}
    if performance:
        configurations=[('small',25),('medium',25),('large',25),('large',100)]
    else:
        configurations=[(s,g) for s in SIZES for g in [25,50,100]]
    for size,grid in configurations:
        cp=api();r=cp.data_create();assert r
        try:
            configure(cp,r,size)
            for axis in ['x_res','y_res']: assert cp.data_set_number(r,'fluxsim.0.'+axis,grid)
            assert cp.assign_layout(r,layout(SIZES[size]),nthreads=1)
            row={'heliostats':SIZES[size],'grid':grid,'paths':{}}
            snapshots={}
            paths=[('legacy','flat'),('flat','flat')]
            if not performance: paths+=[('legacy','legacy')]
            for intercept,density in paths:
                name=intercept+'_intercept_'+density+'_density'
                with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':intercept,'SOLARPILOT_FLUX_PATH':density}):
                    if performance:
                        for _ in range(2): assert cp.simulate(r,nthreads=1),cp.get_last_backend_error(r)
                        samples=[]
                        for _ in range(7):
                            start=time.perf_counter();assert cp.simulate(r,nthreads=1),cp.get_last_backend_error(r)
                            samples.append(time.perf_counter()-start)
                        row['paths'][name]=statistics_s(samples)
                    else:
                        assert cp.simulate(r,nthreads=1),cp.get_last_backend_error(r)
                        snapshots[name]=snapshot(cp,r)
            if performance:
                row['speedup']=row['paths']['legacy_intercept_flat_density']['median_s']/row['paths']['flat_intercept_flat_density']['median_s']
            else:
                reference=snapshots['legacy_intercept_flat_density']
                row['paths']={name:compare(reference,values) for name,values in snapshots.items()}
                with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'verify','SOLARPILOT_FLUX_PATH':'verify'}):
                    assert cp.simulate(r,nthreads=1),cp.get_last_backend_error(r)
                row['same_state_verification_passed']=True
            result['cases'].append(row)
            print(size,grid,'PASS',flush=True)
        finally: assert cp.data_free(r)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--performance',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    for key in ['SOLARPILOT_PROFILE_FILE','SOLARPILOT_INTERCEPT_PROFILE','SOLARPILOT_CUDA_TIMING_FILE']:
        os.environ.pop(key,None)
    args.output.write_text(json.dumps(run(args.performance),indent=2,allow_nan=False)+'\n')
