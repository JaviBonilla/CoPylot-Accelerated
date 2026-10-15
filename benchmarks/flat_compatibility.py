#!/usr/bin/env python3
"""Single-state correctness receipts; no timing, convergence, or private geometry output."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import numpy as np
from cases import ROOT, api
sys.path.insert(0,str(ROOT/'tests'))
from test_flat_project import configure_flat


def errors(expected,actual):
    a=np.asarray(expected,dtype=float);b=np.asarray(actual,dtype=float)
    np.testing.assert_allclose(b,a,rtol=1e-9,atol=1e-10,equal_nan=False)
    diff=np.abs(a-b);nonzero=a!=0
    return {'max_abs':float(diff.max(initial=0)),
            'max_rel_nonzero_reference':float((diff[nonzero]/np.abs(a[nonzero])).max(initial=0)),
            'zero_reference_nonzero':int(np.count_nonzero(b[~nonzero])),
            'rms':float(np.sqrt(np.mean(diff*diff))) if a.size else 0.,'passed':True}


def read(cp,r,area):
    flux=np.asarray(cp.get_fluxmap(r),dtype=float)
    if not np.isfinite(flux).all() or flux.max()<=0: raise AssertionError('Invalid map')
    summary=next(iter(cp.summary_results(r).values()))
    power=float(summary['Power absorbed by the receiver'])
    if not np.isfinite(power) or power<=0: raise AssertionError('Invalid summary power')
    details=cp.detail_results(r,restype='dictionary')
    aims=np.column_stack([details[k+'_aimpoint'] for k in 'xyz'])
    sun=np.array([cp.data_get_number(r,'fluxsim.0.flux_solar_az'),cp.data_get_number(r,'fluxsim.0.flux_solar_el')])
    az,zen=sun[0]*np.pi/180,(90-sun[1])*np.pi/180
    sun=np.r_[sun,[np.sin(zen)*np.sin(az),np.sin(zen)*np.cos(az),np.cos(zen)]]
    return {'flux':flux,'metrics':np.array([flux.max(),flux.sum()*area/flux.size,power]),'aims':aims,'sun':sun}


def check(cp,r,directory,area):
    records={};receipt=directory/'optics.jsonl';handoff=directory/'handoff.csv'
    for name,backend,intercept,density in [('legacy','cpu','legacy','legacy'),('flat','cpu','verify','verify'),
                ('cuda_full','cuda','verify_cuda','flat'),('cuda_resident','cuda','cuda','flat'),
                ('cuda_repeat','cuda','cuda','flat')]:
        if backend=='cuda' and not cp.cuda_available(): continue
        cp.set_compute_backend(r,backend)
        with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':intercept,'SOLARPILOT_FLUX_PATH':density,
                'SOLARPILOT_IMAGE_COMPARE_FILE':str(receipt) if name=='cuda_full' else '',
                'SOLARPILOT_IMAGE_HANDOFF_FILE':str(handoff) if name=='cuda_resident' else '',
                'SOLARPILOT_IMAGE_PIPELINE':'resident','SOLARPILOT_CUDA_TIMING_FILE':'',
                'SOLARPILOT_IMAGE_TIMING_FILE':'','SOLARPILOT_PROFILE_FILE':''}):
            if not cp.simulate(r,nthreads=1): raise RuntimeError('Simulation correctness gate failed: '+name)
            records[name]=read(cp,r,area)
    reference=records['legacy'];out={}
    for name,record in records.items():
        np.testing.assert_array_equal(record['aims'],reference['aims'])
        np.testing.assert_array_equal(record['sun'],reference['sun'])
        out[name]={'map_errors':errors(reference['flux'],record['flux']),
                   'peak_integrated_summary_errors':errors(reference['metrics'],record['metrics']),
                   'aims_equal':True,'resolved_sun_equal':True}
    if 'cuda_repeat' in records:
        np.testing.assert_array_equal(records['cuda_repeat']['flux'],records['cuda_resident']['flux'])
        out['deterministic']=True
    if receipt.exists():
        rows=[json.loads(line) for line in receipt.read_text().splitlines()]
        out['all215']=rows[-1]['errors'];assert out['all215']['global']['passed']
    if handoff.exists():
        import csv
        rows=list(csv.reader(handoff.read_text().splitlines()));out['resident_handoff']=bool(rows and int(rows[-1][1])==1)
        assert out['resident_handoff']
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--project',type=Path)
    p.add_argument('--commercial',action='store_true');args=p.parse_args()
    if args.project:
        try: args.output.resolve().relative_to(ROOT/'local-cases')
        except ValueError: p.error('Private integration receipts must stay under the ignored local-cases area')
    if args.project and args.commercial: p.error('Choose one input mode')
    cp=api();r=cp.data_create()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    result={'status':'running','rtol':1e-9,'atol':1e-10,'timing_collected':False,'states':[]}
    try:
        if args.project:
            if not cp.load_spt(r,args.project): raise RuntimeError('Private project load failed')
            if not cp.restore_loaded_layout(r): raise RuntimeError('Private serialized restoration failed')
            area=cp.data_get_number(r,'receiver.0.rec_width')*cp.data_get_number(r,'receiver.0.rec_height')
            states=[None] # Preserve the project's actual single-state Hour/Day inputs.
        elif args.commercial:
            from commercial_reference import load_manifest,configure
            m=load_manifest();configure(cp,r,m,222,87,m['operating_points'][0])
            area=np.pi*cp.data_get_number(r,'receiver.0.rec_diameter')*cp.data_get_number(r,'receiver.0.rec_height')
            states=[None]
        else:
            configure_flat(cp,r,count=65,rotated=True,hour_day=True)
            with tempfile.TemporaryDirectory() as td:
                name=Path(td)/'synthetic.spt'
                assert cp.save_spt(r,name) and cp.load_spt(r,name) and cp.restore_loaded_layout(r)
            area=48.;states=[10,12,14]
        with tempfile.TemporaryDirectory(dir=args.output.parent) as td:
            for hour in states:
                if hour is not None: assert cp.data_set_number(r,'fluxsim.0.flux_hour',hour)
                result['states'].append(check(cp,r,Path(td),area))
        result['status']='passed'
        args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        print('Compatibility receipt: passed')
    finally: cp.data_free(r)

if __name__=='__main__':main()
