#!/usr/bin/env python3
"""Untimed stage diagnostics for public high-sun and slow temporal states."""
import csv
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch
from temporal_campaign import OUT, environment, api, context, set_state, payload, signature, loaded_library, write
from cpu_multicore import simulate,topology


def main():
    environment();os.sched_setaffinity(0,set(topology()['affinity_sets']['24']))
    rows=[json.loads(line) for file in (OUT/'campaigns').glob('D1-M*-commercial-1x24/worker-*.jsonl')
          for line in file.read_text().splitlines()]
    points={'slow_selected':max(rows,key=lambda r:r['simulate_s'])['state'],
            'high_sun_selected':max(rows,key=lambda r:r['state']['sun'][1])['state']}
    output=OUT/'profiles';output.mkdir(exist_ok=True);cp=api();results=[]
    for label,point in points.items():
        r,grid=context(cp,'commercial')
        try:
            set_state(cp,r,point);simulate(cp,r,24);before=signature(payload(cp,r,point,grid)[0])
            file=output/(label+'.csv')
            if file.exists():raise RuntimeError('Refuse to overwrite diagnostic evidence')
            with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PROFILE':'1','SOLARPILOT_PROFILE_FILE':str(file)}):
                elapsed=simulate(cp,r,24)
            assert before==signature(payload(cp,r,point,grid)[0])
            scopes={row[1]:{'calls':int(row[2]),'inclusive_s':float(row[3]),'exclusive_s':float(row[4])}
                    for row in csv.reader(file.read_text().splitlines())}
            results.append({'selection':label,'case':'commercial','state':point,'threads_per_state':24,
                            'profiled_api_wall_s':elapsed,'scopes':scopes,'outputs_bitwise_unchanged':True})
        finally:cp.data_free(r)
    write(OUT/'temporal-profiles.json',{'phase':'5A','kind':'diagnostic_only','rows':results,
          'not_in_formal_throughput':True,'scope_interpretation':'Caller inclusive wall scopes overlap; do not sum nested scopes',
          'loaded_library':loaded_library(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})


if __name__=='__main__':main()
