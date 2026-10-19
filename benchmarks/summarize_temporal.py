#!/usr/bin/env python3
"""Publish only safe aggregate Phase 5A evidence; retain every timing attempt."""
import argparse
import csv
import json
from pathlib import Path
import statistics
import sys
from temporal_campaign import STRATEGIES, CONTRACT, LIB_SHA, OUT, write


def summarize(source, destination):
    destination.mkdir(parents=True,exist_ok=True)
    correctness={'phase':'5A','passed':True,'contract':'bitwise maps, every detail column, numeric summary, resolved sun, all215 optics','cases':{}}
    for case in ('cesa','commercial'):
        raw=json.loads((source/'correctness'/case/'result.json').read_text())
        plan=json.loads((source/(case+'-plan.json')).read_text())
        checks=raw['transition_checks']
        assert raw['status']=='passed' and all(r['bitwise_full_outputs'] and r['bitwise_all215'] for r in checks)
        correctness['cases'][case]={'fresh_serial_states':raw['fresh_serial_states'],'transition_checks':len(checks),
            'threads':sorted({r['threads'] for r in checks}),'orders':sorted({r['order'] for r in checks}),
            'invariant_geometry_aim':raw['immutable_geometry_aim'],'zero_dni_probe':raw['zero_dni_probe'],
            'control_grid':[plan['grid']['nx'],plan['grid']['ny']],
            'private_input_details_published':False}
    write(destination/'phase5a-temporal-correctness.json',correctness)
    campaigns=[]
    for file in sorted((source/'campaigns').glob('*/result.json')):
        raw=json.loads(file.read_text())
        assert raw['status']=='passed' and raw['library_sha256']==LIB_SHA and raw['contract']==CONTRACT
        assert raw['affinity_observation']['passed']
        selected=('identifier','case','series','contract','states_in_parallel','threads_per_state','masks','completed',
                  'evaluation_wall_s','total_wall_s','setup_wall_s','states_per_s','total_states_per_s',
                  'simulation_latency_s','state_latency_s','output_materialization_s','output_total_worker_s','output_bytes',
                  'checked_against_serial_oracle','affinity_observation','library_sha256','harness_sha256','commits','utc')
        item={k:raw[k] for k in selected}
        item['cpu_window']={k:v for k,v in raw['cpu_window'].items() if k not in ('before','after')}
        item['worker_setup_s']=[w['setup_s'] for w in raw['workers']]
        campaigns.append(item)
    groups=[]
    for case in ('cesa','commercial'):
        for workers,threads in STRATEGIES:
            all_rows=[r for r in campaigns if r['case']==case and r['series']=='seasonal' and r['states_in_parallel']==workers and r['threads_per_state']==threads]
            rows=[r for r in all_rows if r['cpu_window']['accepted']]
            if not rows:continue
            assert all(r['checked_against_serial_oracle']==r['completed'] for r in rows)
            throughput=[r['states_per_s'] for r in rows];walls=[r['total_wall_s'] for r in rows]
            groups.append({'case':case,'states_in_parallel':workers,'threads_per_state':threads,
                'attempts':len(all_rows),'clean_repetitions':len(rows),'campaign_ids':[r['identifier'] for r in rows],
                'daylight_states':rows[0]['completed'],'states_per_s':statistics.median(throughput),
                'states_per_s_cv':statistics.stdev(throughput)/statistics.mean(throughput) if len(rows)>1 else None,
                'evaluation_wall_s':statistics.median(r['evaluation_wall_s'] for r in rows),
                'total_wall_s':statistics.median(walls),'setup_wall_s':statistics.median(r['setup_wall_s'] for r in rows),
                'simulation_median_s':statistics.median(r['simulation_latency_s']['median'] for r in rows),
                'state_latency_median_s':statistics.median(r['state_latency_s']['median'] for r in rows),
                'state_latency_p95_s':statistics.median(r['state_latency_s']['p95'] for r in rows),
                'state_latency_p99_s':statistics.median(r['state_latency_s']['p99'] for r in rows),
                'output_median_s':statistics.median(r['output_materialization_s']['median'] for r in rows),
                'average_owned_cores':statistics.median(r['cpu_window']['average_owned_cores'] for r in rows),
                'output_bytes':rows[0]['output_bytes']})
    best={}
    serial_baselines={}
    for case in ('cesa','commercial'):
        serial=[r for r in campaigns if r['case']==case and r['series']=='seasonal' and r['states_in_parallel']==1 and r['threads_per_state']==1 and r['cpu_window']['accepted']]
        if serial:serial_baselines[case]=statistics.median(r['states_per_s'] for r in serial)
    for case in ('cesa','commercial'):
        rows=[r for r in groups if r['case']==case]
        if len(rows)!=6:continue
        baseline=next(r for r in rows if r['states_in_parallel']==1)
        winner=max(rows,key=lambda r:r['states_per_s'])
        for row in rows:
            row['throughput_relative_to_1x24']=row['states_per_s']/baseline['states_per_s']
            row['equal_machine_budget_relative_throughput']=row['throughput_relative_to_1x24']
            row['speedup_vs_1x1']=row['states_per_s']/serial_baselines[case] if case in serial_baselines else None
            row['efficiency_vs_24_ideal_logical_cpus']=row['speedup_vs_1x1']/24 if case in serial_baselines else None
            row['efficiency_vs_12_ideal_physical_cores']=row['speedup_vs_1x1']/12 if case in serial_baselines else None
        best[case]={k:winner[k] for k in ('states_in_parallel','threads_per_state','states_per_s','throughput_relative_to_1x24','campaign_ids')}
    fields=list(groups[0]) if groups else []
    if groups:
        with (destination/'phase5a-cpu-strategy-scaling.csv').open('w',newline='') as f:
            out=csv.DictWriter(f,fieldnames=fields);out.writeheader();out.writerows(groups)
    plans={}
    for case in ('cesa','commercial'):
        plan=json.loads((source/(case+'-plan.json')).read_text())
        public={'requested':plan['requested'],'daylight':len(plan['states']),'nighttime_skipped':plan['nighttime'],
                'daylight_zero_dni':sum(p['dni']==0 for p in plan['states']),'seasonal_daylight':len(plan['seasonal']),
                'seasonal_days':4,'diagnostic_states':len(plan['diagnostic']),'seasonal_requested':96,'seasonal_nighttime_skipped':96-len(plan['seasonal']),'dni_policy':plan['dni_policy'],'aim_method':plan['aim_method'],
                'solar_year':plan['solar_year'],'sun_derivation':plan['sun_derivation'],'output_contract':plan['output_contract']}
        if case=='commercial':
            public.update(weather_asset=plan['public_weather_asset'],seasonal_dates=[[3,21],[6,21],[9,21],[12,21]],
                          hour_policy='Each pinned hourly row evaluated at Hour + 0.5 local standard time')
        plans[case]=public
    annual=[r for r in campaigns if r['case']=='commercial' and r['series']=='states']
    complete=len(groups)==12 and len(best)==2
    write(destination/'phase5a-campaign-summary.json',{'phase':'5A','matrix_complete':complete,
        'campaigns':plans,'serial_cpu_states_per_s':serial_baselines,'best':best,'strategy_groups':groups,'raw_attempts':campaigns,'annual':annual,
        'annual_direct_complete':any(r['completed']==plans['commercial']['daylight'] and r['cpu_window']['accepted'] for r in annual),
        'no_interpolation':True,'gpu_architecture_changes':False,'numerical_changes':False,
        'output_contract':CONTRACT,'private_inputs_and_raw_maps':'ignored; no private filenames, paths, sites, dates or input hashes published',
        'efficiency_definition':'Full-output throughput / measured 1x1 throughput / 24 logical CPUs (or / 12 physical cores). SMT siblings do not promise ideal independent-core speedup. Equal-budget gain is separately relative to 1x24.'})
    print('Published',len(campaigns),'attempts;',len(groups),'strategy groups; annual',len(annual),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input-dir',type=Path,default=OUT)
    p.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'benchmarks/results')
    args=p.parse_args();summarize(args.input_dir,args.output_dir)


if __name__=='__main__':main()
