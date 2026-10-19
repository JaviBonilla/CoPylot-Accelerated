#!/usr/bin/env python3
"""Publish positive-schema GPU aggregates; never copy private raw temporal data."""
import argparse,csv,json,statistics
from pathlib import Path
from gpu_temporal import OUT,ROOT,write


def median(rows,key):return statistics.median(r[key] for r in rows)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'benchmarks/results');a=p.parse_args()
    runs=[];incomplete=[]
    for directory in sorted((OUT/'runs').iterdir()):
        if not (directory/'result.json').exists():incomplete.append(directory.name);continue
        r=json.loads((directory/'result.json').read_text());validation=directory/'validation.json'
        # No plans, state rows, private site, calendars or input hashes copied.
        fields=('identifier','case','series','mode','batch_size','active_states','completed','control_grid','contract',
                'runtime_probe_s','context_setup_s','setup_wall_s','evaluation_wall_s','total_wall_s',
                'states_per_s','total_states_per_s','simulate_batch_wall_s','batch_complete_wall_s',
                'simulation_only_states_per_s','materialize_analysis_s','serialize_write_s','output_bytes',
                'first_batch_wall_s','first_simulate_batch_s','first_call_included','warmups_excluded',
                'state_batch_completion_latency_s','cpu_window','peak_device_used_mib_sampled',
                'gpu_utilization_percent_sampled_mean','cpu_affinity','library_sha256','harness_sha256','commits','utc')
        row={k:r[k] for k in fields}
        row['cpu_window']={k:r['cpu_window'][k] for k in ('accepted','average_owned_cores','external_average_cores','thermal_throttle_increased','frequency_policy_unchanged')}
        row['state_slots']=r.get('state_slots',min(r['batch_size'],r['completed']))
        row['maximum_cpu_preparations']=r.get('maximum_cpu_preparations',r['active_states'])
        row['loaded_library']=r.get('loaded_library')
        row['gpu_execution']=r.get('gpu_execution','Ordinary sequential default-stream CUDA')
        row['instrumented']=r.get('instrumented',False)
        row['static_residency_enabled']=r.get('static_residency_enabled',r['mode']!='sequential')
        row['output_cost_includes_jsonl_flush']=r.get('output_cost_includes_jsonl_flush',False)
        row['commits']={k:r['commits'][k] for k in ('.','ssc','SolarPILOT','SolTrace')}
        validation_fields=('passed','persisted_payloads_verified','cpu_agreement_existing_tolerance','maximum_absolute_observable_error','direct_cuda_bitwise_states','stored_bytes','timing_excludes_verification')
        observed=json.loads(validation.read_text()) if validation.exists() else None
        row['validation']={k:observed[k] for k in validation_fields} if observed else None
        row['qualified']=r['cpu_window']['accepted'] and bool(row['validation'] and row['validation']['passed'])
        runs.append(row)
    a.output.mkdir(parents=True,exist_ok=True)
    for run in runs:
        if run['case']!='commercial' or run['series']!='states' or not run['qualified']:continue
        source=OUT/'runs'/run['identifier'];rows=[]
        for line in (source/'states.jsonl').read_text().splitlines():
            raw=json.loads(line);point=raw['state']
            rows.append({'weather_row_id':point['id'],'month':point['month'],'day':point['day'],
                'hour_local_standard':point['hour'],'dni_w_m2':point['dni'],'solar_azimuth_deg':point['sun'][0],
                'solar_elevation_deg':point['sun'][1],**raw['metrics'],'batch_slot':raw['slot'],
                'simulate_batch_s':raw['simulate_batch_s'],'materialize_analysis_s':raw['materialize_analysis_s'],
                'npz_serialize_write_s':raw.get('npz_serialize_write_s',raw.get('serialize_write_s')),
                'batch_completion_latency_s':raw['state_batch_completion_latency_s'],'array_payload_sha256':raw['signature']})
        assert len(rows)==run['completed']==len({r['weather_row_id'] for r in rows})
        rows.sort(key=lambda r:r['weather_row_id'])
        name='phase5b-commercial-annual-states-'+run['identifier']+'.csv'
        with (a.output/name).open('w',newline='') as stream:
            table=csv.DictWriter(stream,fieldnames=list(rows[0]));table.writeheader();table.writerows(rows)
        run['public_state_table']=name
    groups=[]
    keys=sorted({(r['case'],r['series'],r['mode'],r['batch_size'],r['active_states'],r['static_residency_enabled'],r['library_sha256']) for r in runs if not r['instrumented']})
    for case,series,mode,batch,active,residency,library in keys:
        rows=[r for r in runs if (r['case'],r['series'],r['mode'],r['batch_size'],r['active_states'],r['static_residency_enabled'],r['library_sha256'])==(case,series,mode,batch,active,residency,library) and not r['instrumented'] and r['qualified']]
        if not rows:continue
        rates=[r['states_per_s'] for r in rows]
        groups.append({'case':case,'series':series,'mode':mode,'batch_size':batch,'active_states':active,'static_residency_enabled':residency,'library_sha256':library,
            'clean_repetitions':len(rows),'campaign_ids':[r['identifier'] for r in rows],'completed':rows[0]['completed'],
            **{k:median(rows,k) for k in ('states_per_s','total_states_per_s','total_wall_s','evaluation_wall_s','setup_wall_s','materialize_analysis_s','serialize_write_s','peak_device_used_mib_sampled')},
            'throughput_cv':statistics.stdev(rates)/statistics.mean(rates) if len(rows)>1 else None,
            'all_outputs_verified':True,'output_bytes':rows[0]['output_bytes']})
    a.output.mkdir(parents=True,exist_ok=True)
    baseline=[r for r in groups if r['mode']=='sequential']
    write(a.output/'phase5b-sequential-baseline.json',{'phase':'5B','groups':baseline,'attempts':[r for r in runs if r['mode']=='sequential']})
    write(a.output/'phase5b-residency.json',{'phase':'5B','groups':[r for r in groups if r['mode'] in ('sequential','resident')],
          'note':'Sequential already reuses allocations; residency opt-in checks actual table/cell bytes before skipping uploads',
          'attempts':[r for r in runs if r['mode']=='resident']})
    batches=[r for r in groups if r['mode'] in ('batch','pipeline')]
    if batches:
        with (a.output/'phase5b-batch-scaling.csv').open('w',newline='') as stream:
            table=csv.DictWriter(stream,fieldnames=list(batches[0]));table.writeheader();table.writerows(batches)
    cpu=json.loads((ROOT/'benchmarks/results/phase5a-campaign-summary.json').read_text())
    cpu_year=next(r for r in cpu['annual'] if r['completed']==4403 and r['cpu_window']['accepted'])
    years=[r for r in groups if r['case']=='commercial' and r['series']=='states']
    best=max(years,key=lambda r:r['total_states_per_s']) if years else None
    comparison={'phase':'5B','all_groups':groups,'all_attempts':runs,'incomplete_attempt_ids_retained':incomplete,
                'cpu_annual':{k:cpu_year[k] for k in ('completed','states_in_parallel','threads_per_state','states_per_s','total_wall_s','output_bytes')},
                'gpu_annual_groups':years,'best_measured_annual':best,
                'annual_gpu_over_cpu_evaluation_throughput':best['states_per_s']/cpu_year['states_per_s'] if best else None,
                'annual_total_wall_speedup':cpu_year['total_wall_s']/best['total_wall_s'] if best else None,
                'annual_wall_reduction_fraction':1-best['total_wall_s']/cpu_year['total_wall_s'] if best else None,
                'no_temporal_approximation':True,'no_kernel_arithmetic_retuning':True,'no_multi_gpu':True,
                'raw_private_data_retained_only_on_server':True,'full_output_contract':cpu['output_contract']}
    write(a.output/'phase5b-annual-summary.json',comparison)
    profiles=OUT/'temporal-gpu-profiles.json'
    if profiles.exists():
        values=json.loads(profiles.read_text())
        allowed={'case','solar_class','mode','call','repeat','api_wall_s','full_getter_optical_check_s','stages','host_scopes','full_outputs_bitwise_equal_direct_cuda'}
        for row in values['rows']:
            if row['case']=='cesa':assert set(row)==allowed,'Private profile schema changed'
        write(a.output/'phase5b-solar-profiles.json',values)
    environment=[]
    for library in sorted({r['library_sha256'] for r in runs}):
        raw=next(json.loads((OUT/'runs'/r['identifier']/'result.json').read_text()) for r in runs if r['library_sha256']==library)
        environment.append({'library_sha256':library,'measurement_commits':sorted({r['commits']['.'] for r in runs if r['library_sha256']==library}),
            'gpu':{k:raw['gpu_telemetry'][0][k] for k in ('name','driver_version','memory.total')},
            'toolchain_image':'sha256:8e6e3752946ff2dde451b313cbaec2ea8e7b52221b21bfbcf53fb68dd4f4c42e',
            'kernel_image_block':64,'kernel_density_block':256,'precision':'double','fast_math':False})
    write(a.output/'phase5b-environment.json',{'phase':'5B','libraries':environment})
    print('Public aggregate publication:',len(runs),'attempts;',len(groups),'groups;',len(years),'annual groups')


if __name__=='__main__':main()
