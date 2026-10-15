#!/usr/bin/env python3
"""Publish completed Phase 2D-B evidence without rerunning measurements."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path,default=Path('artifacts/phase2db'))
    parser.add_argument('--output',type=Path,default=Path('benchmarks/results'))
    args=parser.parse_args()
    def read(name): return json.loads((args.artifacts/name).read_text())
    core=read('direct-core-final.json');downstream=read('downstream.json');timing=read('preliminary-complete.json')
    assert core['fixtures']==60 and core['fixture_errors']['global']['count']==12900
    assert core['fixture_errors']['global']['passed'] and core['edge_errors']['global']['passed']
    assert core['host_device_layout_equal'] and core['deterministic'] and core['allocation_reuse']
    assert len(downstream['cases'])==9
    assert timing['status']=='complete' and len(timing['cases'])==3
    metadata=copy.deepcopy(downstream['metadata'])
    metadata.update(image_plane_source_options=['--fmad=true','--ptxas-options=-v'],fma_enabled=True,fast_math=False,
        compute_capability=core['resources']['compute_capability'],runtime_version=core['resources']['runtime_version'])
    full=[]
    for c in downstream['cases']:
        for rows in c['intermediate'].values():
            assert len(rows)==2
            assert all(r['errors']['global']['passed'] and r['errors']['global']['count']==215*c['heliostats'] for r in rows)
            assert rows[0]['allocations']==rows[1]['allocations']
        assert c['repeated_cuda_maps_bitwise']
        if c['grid']==[25,25]:
            full.append({'grid':c['grid'],**c['intermediate']['cuda_cpu'][0]})
    assert [r['heliostats'] for r in full]==[1000,5000,10000]
    correctness={'metadata':metadata,'direct':core,'full_heliostat_coverage':full,
        'edge_counts':[0,1,127,128,129,259,1000,5000,10000,1,0],
        'relative_error_policy':'max_rel is null when a zero reference has a nonzero output; max_rel_nonzero reports the finite-reference subset. The unchanged combined tolerance decides passing.',
        'source_artifact_sha256':{n:hashlib.sha256((args.artifacts/n).read_bytes()).hexdigest() for n in ['direct-core-final.json','downstream.json']}}
    log=(args.artifacts/'final-cuda-tests.log').read_text()
    match=re.search(r'Function properties for [^\n]*18image_plane_kernel[^\n]*\n(.*?)\nptxas info    : Compile time',log,re.S)
    assert match
    ptxas=match.group(1).strip()
    assert '7648 bytes stack frame, 0 bytes spill stores, 0 bytes spill loads' in ptxas and 'Used 156 registers' in ptxas
    resources={'metadata':metadata,'runtime':core['resources'],'ptxas':{'stack_frame_bytes':7648,'cumulative_stack_bytes':7648,
        'spill_store_bytes':0,'spill_load_bytes':0,'registers_per_thread':156,'constant_banks_bytes':{'0':384,'2':616},'raw':ptxas},
        'device_model':{'layout':'AoS','alignment_bytes':8,'input_bytes':1640,'input_padding_bytes':2,'output_bytes':1728,
            'output_doubles':215,'output_flag_bytes':1,'output_padding_bytes':7,'tables_bytes':3256,'tables_storage':'ordinary read-only device global buffer',
            'host_device_layout_equal':True,'layout_probe':core['layout']},
        'transfers':[{'heliostats':h,'input_h2d_bytes':1640*h,'tables_h2d_bytes':3256,'total_h2d_bytes':1640*h+3256,
            'output_d2h_bytes':1728*h,'owned_optical_buffer_bytes':3368*h+3256} for h in [1000,5000,10000]],
        'compute_sanitizer':{'available':False,'checked':'PATH and existing CUDA bin/compute-sanitizer directories','installed':False},
        'limitations':['CUDA local memory is device memory, not fast shared memory.',
            'Occupancy is a fixed-block theoretical query, not a profiler measurement.',
            'Runtime constSizeBytes and ptxas constant-bank values are recorded separately as reported.',
            'No tuning or profiling-based bottleneck attribution was performed.']}
    timing['metadata']['timing_guard']='Three consecutive idle native preflight samples; exact owned GPU process set and memory/temperature checks around every sample; no concurrent server jobs.'
    timing['metadata']['cpu_governor']='powersave (unchanged)'
    timing['metadata']['limits']='Preliminary five-sample batch baseline only; no end-to-end speedup, distribution study, sweep or formal performance claim.'
    for row in timing['cases']:
        assert row['gpu_window']['checks']>=16 and row['gpu_window']['external_processes']==0
        assert row['errors']['global']['passed'] and row['deterministic'] and row['allocation_reuse']
    args.output.mkdir(parents=True,exist_ok=True)
    for name,data in [('imageplane-correctness',correctness),('downstream-correctness',downstream),('resource-usage',resources),('preliminary-timing',timing)]:
        text=json.dumps(data,indent=2,allow_nan=False)+'\n'
        assert not re.search(r'/workspace',text,re.I)
        (args.output/('phase2db-'+name+'.json')).write_text(text)
        print(name,'PASS')


if __name__=='__main__': main()
