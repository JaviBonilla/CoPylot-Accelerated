#!/usr/bin/env python3
"""Serial controlled GPU campaigns: isolate residency, then bound batch scaling."""
import argparse,json,subprocess,sys
from gpu_temporal import OUT,ROOT,require
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prefix',required=True)
p.add_argument('--stage',choices=['residency','batch'],required=True);p.add_argument('--library-sha256',required=True)
p.add_argument('--repetitions',type=int,default=3);p.add_argument('--batches',type=int,nargs='+',default=[1,2,4,8,16,32])
a=p.parse_args();require(a.prefix.isalnum(),'Unique alphanumeric prefix required');require(a.repetitions>=1,'Positive repetitions required')
workloads=[('cesa','seasonal'),('commercial','seasonal'),('commercial','long')]
configs=[('sequential',1),('resident',1)] if a.stage=='residency' else [('batch',b) for b in a.batches]
for repetition in range(a.repetitions):
    order=configs if repetition%2==0 else list(reversed(configs))
    cases=workloads if repetition%2==0 else list(reversed(workloads))
    for case,series in cases:
        for mode,batch in order:
            for supplement in range(4):
                identifier=f'{a.prefix}-R{repetition+1}-{case}-{series}-{mode}-B{batch}'+(f'-S{supplement}' if supplement else '')
                command=[sys.executable,'-u','benchmarks/gpu_temporal.py','campaign','--case',case,'--series',series,'--mode',mode,
                         '--batch-size',str(batch),'--library-sha256',a.library_sha256,'--id',identifier]
                with (OUT/(identifier+'.log')).open('x') as log:subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
                subprocess.run([sys.executable,'benchmarks/gpu_temporal.py','verify','--id',identifier,'--direct-reference','S1-'+case+'-'+series],cwd=ROOT,check=True)
                r=json.loads((OUT/'runs'/identifier/'result.json').read_text())
                print(identifier,'states/s',round(r['states_per_s'],5),'total wall',round(r['total_wall_s'],3),'clean',r['cpu_window']['accepted'],flush=True)
                if r['cpu_window']['accepted']:break
            else:raise RuntimeError('No clean complete GPU campaign; all attempts retained')
print('GPU matrix complete',a.prefix,flush=True)
