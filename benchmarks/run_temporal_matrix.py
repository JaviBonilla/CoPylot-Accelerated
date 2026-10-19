"""Run serial clean-window matrix; all failed attempts remain immutable."""
from pathlib import Path
import argparse,json,subprocess,sys
from cases import ROOT
from temporal_campaign import OUT
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--prefix',required=True,help='Unique immutable campaign family, e.g. R1')
p.add_argument('--scheduler',choices=['dynamic','round_robin'],default='dynamic')
p.add_argument('--skip-controls',action='store_true',help='Reuse the retained long serial/physical-core controls')
a=p.parse_args()
if not a.prefix.isalnum():p.error('prefix must be alphanumeric')
root=ROOT;out=OUT
strategies=[(1,24),(2,12),(4,6),(6,4),(12,2),(24,1)]
for rep in range(3):
    order=strategies if rep%2==0 else list(reversed(strategies))
    cases=('cesa','commercial') if rep%2==0 else ('commercial','cesa')
    for case in cases:
        for workers,threads in order:
            identifier=f'{a.prefix}-M{rep+1}-{case}-{workers}x{threads}'
            command=[sys.executable,'-u','benchmarks/temporal_campaign.py','campaign','--case',case,'--workers',str(workers),'--threads',str(threads),'--id',identifier,'--scheduler',a.scheduler]
            with (out/(identifier+'.log')).open('x') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
            r=json.loads((out/'campaigns'/identifier/'result.json').read_text())
            print(identifier,'states/s',round(r['states_per_s'],5),'wall',round(r['total_wall_s'],3),'accepted',r['cpu_window']['accepted'],flush=True)
# Retain and supplement whole rejected campaigns, never individual samples.
for case in ('cesa','commercial'):
    for workers,threads in strategies:
        def rows():
            values=[json.loads(p.read_text()) for p in (out/'campaigns').glob('*/result.json')]
            return [r for r in values if r['identifier'].startswith(a.prefix+'-') and r['case']==case and r['states_in_parallel']==workers and r['threads_per_state']==threads and r['series']=='seasonal' and r['cpu_window']['accepted']]
        for attempt in range(1,4):
            if len(rows())>=3:break
            identifier=f'{a.prefix}-S{attempt}-{case}-{workers}x{threads}'
            command=[sys.executable,'-u','benchmarks/temporal_campaign.py','campaign','--case',case,'--workers',str(workers),'--threads',str(threads),'--id',identifier,'--scheduler',a.scheduler]
            with (out/(identifier+'.log')).open('x') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
            r=json.loads((out/'campaigns'/identifier/'result.json').read_text())
            print(identifier,'states/s',round(r['states_per_s'],5),'accepted',r['cpu_window']['accepted'],flush=True)
        assert len(rows())>=3,(case,workers,'Insufficient clean campaigns')
print('CPU strategy matrix completed',flush=True)
for case in (() if a.skip_controls else ('cesa','commercial')):
    for threads in (1,12):
        for attempt in range(1,4):
            identifier=f'{a.prefix}-B{attempt}-{case}-1x{threads}'
            command=[sys.executable,'-u','benchmarks/temporal_campaign.py','campaign','--case',case,'--workers','1','--threads',str(threads),'--id',identifier,'--scheduler',a.scheduler]
            with (out/(identifier+'.log')).open('x') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
            r=json.loads((out/'campaigns'/identifier/'result.json').read_text())
            print(identifier,'states/s',round(r['states_per_s'],5),'wall',round(r['total_wall_s'],3),'accepted',r['cpu_window']['accepted'],flush=True)
            if r['cpu_window']['accepted']:break
        assert r['cpu_window']['accepted'],(case,threads,'No clean serial/physical-core control')
print('CPU matrix and serial/physical-core controls completed',flush=True)
