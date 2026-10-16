#!/usr/bin/env python3
"""Publish aggregate single-state scaling and explicitly attributed CPU/GPU comparisons."""
import argparse
import copy
import csv
import json
from pathlib import Path
import statistics


def load(path):return json.loads(path.read_text())
def save(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def annotate(source, preexisting=False):
    if source['status']!='passed':raise ValueError('Unvalidated timing campaign')
    result=copy.deepcopy(source)
    for row in result['rows']:
        n=row['requested_threads']
        participants=1 if preexisting or row['path']=='legacy' else n
        row['effective_numerical_participants']=participants
        row['spawned_numerical_workers']=participants-1
        row['caller_participates']=True
        one=next(r for r in result['rows'] if r['case_id']==row['case_id'] and r['state_id']==row['state_id']
                 and r['path']==row['path'] and r['requested_threads']==1)
        row['scaling_speedup']=one['statistics_s']['median']/row['statistics_s']['median']
        row['parallel_efficiency']=row['scaling_speedup']/n
    return result


def compare(flat,gpu):
    result={}
    for case in sorted({r['case_id'] for r in flat['rows']}):
        rows=[r for r in flat['rows'] if r['case_id']==case]
        counts=sorted({r['requested_threads'] for r in rows})
        overall=min(counts,key=lambda n:statistics.median(r['statistics_s']['median'] for r in rows if r['requested_threads']==n))
        states=[]
        for sid in sorted({r['state_id'] for r in rows}):
            selected=[r for r in rows if r['state_id']==sid]
            best=min(selected,key=lambda r:r['statistics_s']['median'])
            one=next(r for r in selected if r['requested_threads']==1)
            twelve=next(r for r in selected if r['requested_threads']==12)
            twentyfour=next(r for r in selected if r['requested_threads']==24)
            shared=next(r for r in selected if r['requested_threads']==overall)
            cuda=next(r for r in gpu['rows'] if r['case_id']==case and r['state_id']==sid)
            t1=one['statistics_s']['median'];tb=best['statistics_s']['median'];tg=cuda['statistics_s']['median']
            states.append({'state_id':sid,'best_cpu_threads':best['requested_threads'],'flat_1t_median_s':t1,
                           'best_cpu_median_s':tb,'cuda_median_s':tg,'flat_1t_to_best_cpu':t1/tb,
                           'flat_1t_to_cuda':t1/tg,'best_cpu_to_cuda':tb/tg,
                           'common_case_count_median_s':shared['statistics_s']['median'],
                           'common_case_count_to_cuda':shared['statistics_s']['median']/tg,
                           'smt_gain_t12_over_t24':twelve['statistics_s']['median']/twentyfour['statistics_s']['median']})
        result[case]={'common_best_thread_count':overall,
                      'common_count_selection':'Lowest median of the four state-specific steady-state medians; per-state optima also retained',
                      'states':states,'scaling_ranges':[
                          {'threads':n,'median_s_range':[min(r['statistics_s']['median'] for r in rows if r['requested_threads']==n),
                                                        max(r['statistics_s']['median'] for r in rows if r['requested_threads']==n)],
                           'speedup_range':[min(r['scaling_speedup'] for r in rows if r['requested_threads']==n),
                                            max(r['scaling_speedup'] for r in rows if r['requested_threads']==n)],
                           'efficiency_range':[min(r['parallel_efficiency'] for r in rows if r['requested_threads']==n),
                                               max(r['parallel_efficiency'] for r in rows if r['requested_threads']==n)]}
                          for n in counts]}
    return result


def timing_csv(path,source):
    fields=['case_id','state_id','path','requested_threads','effective_numerical_participants','spawned_numerical_workers',
            'caller_participates','cpu_affinity','physical_cores_used','smt','first_call_s','warmups','repetitions','samples_s',
            'median_s','mean_s','minimum_s','maximum_s','stdev_s','cv','scaling_speedup','parallel_efficiency',
            'root_sha','ssc_sha','solarpilot_sha','soltrace_sha','library_sha256','metadata_json']
    with path.open('w',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for row in source['rows']:
            item={k:row[k] for k in fields if k in row}
            item.update(cpu_affinity=json.dumps(row['cpu_affinity']),samples_s=json.dumps(row['samples_s']),
                        warmups=row['warmups_excluded_after_first'],library_sha256=source['metadata']['library_sha256'])
            for key in ('median','mean','minimum','maximum','stdev'):item[key+'_s']=row['statistics_s'][key]
            item['cv']=row['statistics_s']['coefficient_of_variation']
            for label,repo in [('root','.'),('ssc','ssc'),('solarpilot','SolarPILOT'),('soltrace','SolTrace')]:
                item[label+'_sha']=source['metadata']['commits'][repo]
            item['metadata_json']='phase4-preexisting-nthreads-scaling.json' if source['stage']=='preexisting' else 'phase4-flat-multicore-scaling.json'
            writer.writerow(item)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('preexisting','flat','cuda','profile'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('correctness','pilot','startup','historical'):p.add_argument('--'+name,type=Path)
    p.add_argument('--output-dir',type=Path,required=True);args=p.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    pre=annotate(load(args.preexisting),True);flat=annotate(load(args.flat));gpu=load(args.cuda);profile=load(args.profile)
    if gpu['status']!='passed' or profile['status']!='passed':raise ValueError('Unvalidated GPU/profile evidence')
    if flat['metadata']['library_sha256']!=gpu['metadata']['library_sha256']:raise ValueError('CPU/GPU binary differs')
    for stem,source in [('phase4-preexisting-nthreads-scaling',pre),('phase4-flat-multicore-scaling',flat)]:
        save(args.output_dir/(stem+'.json'),source);timing_csv(args.output_dir/(stem+'.csv'),source)
    save(args.output_dir/'phase4-cuda-control-timings.json',gpu)
    save(args.output_dir/'phase4-stage-scaling.json',profile)
    if args.correctness:
        correctness=load(args.correctness)
        if correctness['status']!='passed':raise ValueError('Scientific full-optical anchors failed')
        save(args.output_dir/'phase4-scientific-correctness.json',correctness)
    if args.startup:save(args.output_dir/'phase4-thread-startup.json',load(args.startup))
    if args.historical:
        historical=load(args.historical)
        if historical['status']!='passed':raise ValueError('Historical CONTROL maps changed')
        save(args.output_dir/'phase4-historical-control-maps.json',historical)
    if args.pilot:
        pilot=load(args.pilot)
        pilot.update(status='stopped_implementation_evaluation',included_in_final_formal_statistics=False,
            reason='Cell-first traversal made two-thread CESA-I slower than original 1T; final workers retain heliostat-outer traversal within independent cell ranges',
            completeness='All 24 completed CESA-I configurations retained; the subsequent incomplete commercial configuration was interrupted and produced no retained timing record')
        save(args.output_dir/'phase4-initial-traversal-evaluation.json',pilot)
    save(args.output_dir/'phase4-cpu-gpu-summary.json',{
        'phase':'4','status':'passed','cpu_metadata':flat['metadata'],'cuda_metadata':gpu['metadata'],
        'cuda_provenance':'Remeasured final Phase 4 library, unchanged numerical CUDA kernels, same pinned toolchain',
        'cases':compare(flat,gpu), 'scope':'Single-state latency on fixed Phase 3 CONTROL grids; no temporal parallelism',
        'limitations':['Thread-count optima are measured sample optima, not confidence intervals',
                       'Existing powersave/turbo policy retained; frequencies may vary with active cores',
                       'Sampled runnable threads are supplementary observations; bounded executor defines exact participant count',
                       'Per-stage inclusive wall scopes overlap; worker CPU-time sums are not wall-time components']})
    print('Aggregate scaling, stage profiles and CPU/GPU comparisons published.')


if __name__=='__main__':main()
