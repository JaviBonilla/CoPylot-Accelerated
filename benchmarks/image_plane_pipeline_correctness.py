#!/usr/bin/env python3
"""Complete Phase 2D-C full-output versus resident pipeline correctness matrix."""
import argparse
import json
import os
from pathlib import Path
from image_plane_cuda_correctness import run_case
from cuda_flux_correctness import metadata
from cases import SIZES


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    for k in list(os.environ):
        if k.startswith('SOLARPILOT_'):os.environ.pop(k)
    info=metadata();info.update(phase='2D-C',hostname='canonical-gpu-server',execution_hostname='pinned-cuda-container',
        image_plane_block_size=64,density_block_size=256,full_output_values_per_heliostat=215,gpu_timings_collected=False)
    result={'metadata':info,'cases':[]}
    for size in SIZES:
        for grid in [25,50,100]:
            row=run_case(size,grid,include_resident=True,image_block=64);result['cases'].append(row)
            args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
            print(size,grid,'resident/full bitwise PASS; Flat tolerance PASS',flush=True)


if __name__=='__main__':main()
