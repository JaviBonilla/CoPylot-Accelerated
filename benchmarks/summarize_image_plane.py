#!/usr/bin/env python3
"""Summarize complete Phase 2D-A datasets without selecting individual runs."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RESULTS=ROOT/'benchmarks/results'
def read(name): return json.loads((RESULTS/name).read_text())
def main():
    before=read('phase2da-legacy-profile.json')
    final=read('phase2da-cpu-performance.json')
    pipeline=read('phase2da-correctness.json')
    gpu=read('phase2da-cuda-correctness.json')
    direct=read('phase2da-direct-tests.json')
    report={'phase':'2D-A','status':'CPU extraction and characterization complete; Phase 2D-B not started',
        'performance_source_repositories':final['repositories'],
        'compiler':final['compiler'],'cpu':final['cpu'],'threads':1,'affinity':final['cpu_affinity'],
        'warmups':2,'repetitions':7,'rtol':1e-9,'atol':1e-10,
        'library_sha256':final['library_sha256'],
        'final_formatting_commit_library_identical':True,
        'direct_fixtures':direct,'memory':{},'direct_cpu':[],
        'intermediate':{'configurations':len(final['grid_snapshots']),
            'heliostat_evaluations':sum(x['heliostats'] for x in final['grid_snapshots']),
            'values_compared':sum(x['heliostats']*215 for x in final['grid_snapshots']),
            'bitwise_against_pre_extraction':all(all(v['bitwise'] for v in x['vs_pre_extraction_legacy'].values()) for x in final['grid_snapshots']),
            'max_abs':max(v['max_abs'] for x in final['grid_snapshots'] for v in x['vs_pre_extraction_legacy'].values()),
            'max_rel':max(v['max_rel'] for x in final['grid_snapshots'] for v in x['vs_pre_extraction_legacy'].values()),
            'rms_max':max(v['rms'] for x in final['grid_snapshots'] for v in x['vs_pre_extraction_legacy'].values())},
        'downstream_cpu':{'configurations':len(pipeline['cases']),
            'all_maps_and_details_bitwise':all(all(p['flux']['bitwise'] and all(v['bitwise'] for v in p['detail_columns'].values()) for p in c['paths'].values()) for c in pipeline['cases'])},
        'cuda_density':{'configurations':len(gpu['cases']),'block_size':256,'gpu_timings_collected':False,
            'worst_dimensional_map_max_abs':max(c['dimensional_errors']['max_abs'] for c in gpu['cases']),
            'repeat_maps_bitwise':all(c['repeated_cuda_bitwise'] for c in gpu['cases'])},
        'end_to_end_cpu':read('phase2da-end-to-end.json')['cases'],
        'profile_note':'Detailed scope measurements include additional clock overhead; primary direct samples have detailed scopes disabled.',
        'limitations':['Seven repetitions are descriptive; small CPU timing differences are not an established global speedup.',
            'CUDA timing-semantics functional test skipped after automatic review rejected timing enablement; correctness-only CUDA regression passed.',
            'No allocator sampling percentage; allocation overhead is included in mathematical stage timings.',
            'Validated single cylinder/simple aim/specified sun/one CPU thread; other paths retain legacy.',
            'Host stack/vectorization evidence does not establish CUDA register use or GPU speed.']}
    for n in [1000,5000,10000]:
        a=next(x for x in final['direct'] if x['heliostats']==n and x['path']=='legacy')
        b=next(x for x in final['direct'] if x['heliostats']==n and x['path']=='flat')
        original=next(x for x in before['direct'] if x['heliostats']==n)
        report['direct_cpu'].append({'heliostats':n,'pre_extraction_legacy_median_ms':original['median_s']*1000,
            'same_binary_legacy_median_ms':a['median_s']*1000,'flat_median_ms':b['median_s']*1000,'speedup':a['median_s']/b['median_s']})
        report['memory'][str(n)]={'input_bytes':1640*n,'output_bytes':1728*n,'all_records_plus_tables_bytes':3368*n+3256}
    report['memory'].update({'input_bytes_per_heliostat':1640,'output_bytes_per_heliostat':1728,'tables_bytes':3256,
        'host_evaluate_stack_bytes':8128,'facet_capacity':64,'core_dynamic_allocations':0,
        'runtime_note':'The current CPU adapter streams one input/output on the stack; field-sized record totals are future storage estimates, not allocated buffers.'})
    (RESULTS/'phase2da-summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
if __name__=='__main__': main()
