#!/usr/bin/env python3
"""Untimed verification of persisted full temporal payloads against runtime hashes."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from temporal_campaign import OUT, signature, write


def verify(directory, plan):
    result=json.loads((directory/'result.json').read_text())
    assert result['status']=='passed'
    states=json.loads((directory/'plan.json').read_text())['points']
    rows=[json.loads(line) for file in directory.glob('worker-*.jsonl') for line in file.read_text().splitlines()]
    assert len(rows)==len(states)==result['completed']
    assert sorted(v['id'] for v in rows)==sorted(s['id'] for s in states)
    assert len({v['id'] for v in rows})==len(rows)
    grid=plan['grid'];total_bytes=0;zero_dni=0;begin=time.perf_counter()
    for row in rows:
        file=directory/(str(row['id'])+'.npz')
        with np.load(file,allow_pickle=False) as saved:values={k:saved[k] for k in saved.files}
        assert signature(values)==row['signature'],'Persisted payload differs from runtime output'
        assert values['map'].shape==(grid['ny'],grid['nx'])
        assert values['summary_keys'].shape==values['summary_values'].shape
        assert set(values)=={'map','detail_keys','summary_keys','summary_values','resolved_sun'}|{'detail_'+str(i) for i in range(len(values['detail_keys']))}
        assert all(np.isfinite(v).all() for v in values.values() if v.dtype.kind in 'fiu')
        assert values['resolved_sun'].tolist()==row['state']['sun']
        if row['state']['dni']==0:
            zero_dni+=1
            assert np.count_nonzero(values['map'])==0 and row['metrics']['incident_power_kw']==0 and row['metrics']['absorbed_power_kw']==0
        total_bytes+=file.stat().st_size
    assert total_bytes==result['output_bytes']
    evidence={'campaign_id':result['identifier'],'case':result['case'],'persisted_full_payloads_verified':len(rows),
        'all_arrays_bitwise_equal_to_runtime':True,'all_numeric_arrays_finite':True,'complete_schema':True,
        'zero_dni_maps_verified_zero':zero_dni,'stored_bytes':total_bytes,'verification_s':time.perf_counter()-begin,
        'verification_outside_benchmark_window':True}
    write(directory/'storage-validation.json',evidence)
    return evidence


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--id',required=True);args=p.parse_args()
    directory=OUT/'campaigns'/args.id
    result=json.loads((directory/'result.json').read_text())
    plan=json.loads((OUT/(result['case']+'-plan.json')).read_text())
    print(json.dumps(verify(directory,plan),indent=2))


if __name__=='__main__':main()
