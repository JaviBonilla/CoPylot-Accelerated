#!/usr/bin/env python3
"""Recheck all 10,320,000 Legacy/Flat optical values without performance claims."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import numpy as np
from image_plane import errors,ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    binary=args.binary.resolve()
    result={'phase':'2D-C Legacy/Flat CPU regression','gpu_timings_collected':False,'cpu_timing_samples_discarded':True,
        'rtol':1e-9,'atol':1e-10,'commits':{r:subprocess.check_output(['git','-C',str(ROOT/r),'rev-parse','HEAD'],text=True).strip() for r in ['.','ssc','SolarPILOT','SolTrace']},
        'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'cases':[]}
    with tempfile.TemporaryDirectory() as temp:
        for h in [1000,5000,10000]:
            for grid in [25,50,100]:
                data={}
                for mode in ['legacy','flat']:
                    env={k:v for k,v in os.environ.items() if not k.startswith('SOLARPILOT_')};env['SOLARPILOT_INTERCEPT_PATH']=mode
                    target=Path(temp)/(mode+'.bin')
                    subprocess.run([str(binary),str(h),str(grid),'1',str(target)],env=env,check=True,stdout=subprocess.DEVNULL)
                    data[mode]=np.fromfile(target,dtype=np.float64).reshape(h,215)
                assert np.array_equal(data['legacy'].view(np.uint64),data['flat'].view(np.uint64))
                result['cases'].append({'heliostats':h,'grid':[grid,grid],'compared_values':h*215,'bitwise':True,'families':errors(data['legacy'],data['flat'])})
                print(h,grid,'Legacy/Flat bitwise PASS',flush=True)
    result['total_compared_values']=sum(c['compared_values'] for c in result['cases']);assert result['total_compared_values']==10320000
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
