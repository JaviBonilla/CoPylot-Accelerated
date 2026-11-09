#!/usr/bin/env python3
"""Publish only approved aggregate grid, correctness and timing evidence."""
import argparse
import csv
import json
from pathlib import Path

ERROR_KEYS={'count','max_abs','max_rel','max_rel_nonzero','rms','zero_reference_nonzero','nonfinite','bitwise','passed',
            'max_abs_kw_m2','rms_kw_m2','integrated_power_difference_kw','peak_difference_kw_m2','summary_power_difference_kw'}


def safe_point(point):
    # Public evidence contains opaque state labels only. Private solar/weather
    # metadata belongs to local input plans, never aggregate publication files.
    return {'id':point['id']}


METADATA_KEYS={'commits','cpu_model','cpu_affinity','monitor_cpu','cpu_governor','cpu_threads',
 'precision','fma','fast_math','nvcc','compiler','cmake','build_settings','kernel_source_sha256','library_sha256',
 'rtol','atol','ncu_available','first_call_definition','monitoring','simulate_wall_definition'}

def safe_metadata(data):return {k:v for k,v in data.items() if k in METADATA_KEYS}

def safe_errors(data):return {key:value for key,value in data.items() if key in ERROR_KEYS}

def safe_comparison(data):
    return {'global':safe_errors(data['global']),
            'families':{name:safe_errors(value) for name,value in data['families'].items()}}
def save(path,data):path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def summarize(plan,correct,performances,profile):
    if correct['status']!='passed' or any(p['status']!='passed' for p in performances):raise ValueError('Unvalidated evidence')
    metadata=performances[0]['metadata'];timings={};segments=[]
    for segment,p in enumerate(performances):
        for key in ('library_sha256','kernel_source_sha256','cpu_model','build_settings','cpu_affinity'):
            if p['metadata'][key]!=metadata[key]:raise ValueError('Measurement segments changed build or hardware configuration')
        for name in ('ssc','SolarPILOT','SolTrace'):
            if p['metadata']['commits'][name]!=metadata['commits'][name]:raise ValueError('Numerical core changed between measurements')
        segments.append({'segment':segment,'metadata':safe_metadata(p['metadata']),'runtime_probe_s':p['runtime_probe_s'],'gpu_telemetry':p['gpu_telemetry']})
        for row in p['rows']:
            key=(row['operating_point'],row['level'])
            if key in timings:raise ValueError('Duplicated timing evidence')
            timings[key]=(segment,row)
    result={'phase':'3C','case_id':plan['case_id'],'status':'passed','receiver':plan['receiver'],
        'heliostats':next(iter(correct['physics_checks'].values()))['runtime_count'],
        'operating_points':[safe_point(p) for p in plan['operating_points']],
        'canonical_path':plan['canonical_path'],'location_semantics':'reference EPW site metadata frozen before serialized restoration',
        'map_representation':'Normalized Hermite midpoint samples represented as piecewise constant cells; not true integrated cell averages',
        'map_coordinates':'Local receiver columns increasing x and rows increasing y from lower edge after C API vertical reversal',
        'rtol':1e-9,'atol':1e-10,'primary_control_tolerance':plan['primary_control_tolerance'],
        'primary_candidate_level':correct['primary_candidate'],'reference_level':correct['recommendations']['reference_level'],
        'recommendations':correct['recommendations'],'previous_reference_recommendations':correct['previous_reference_recommendations'],
        'reference_refinement_check':correct['reference_refinement_check'],
        'measurement_segments':segments,'rows':[],'independent_energy_resolution':None,
        'energy_reason':'Normalized integrated receiver power is not an independent spatial accuracy criterion',
        'physical_state_checks':{'saved_inputs_equal_excluding_x_res_y_res':True,'runtime_geometry_and_aims_exact':True,
                                 'resolved_sun_site_and_dni_exact':True,'private_input_hashes_published':False},
        'profile':None,'limitations':['Four representative single states on one project date; no annual or low-horizon validation',
           'Finite numerical reference; no physical truth or experimental/thermal validation claim',
           'Piecewise constant remapping measures the represented sampled map, not the unknown within-cell optical field',
           'Uniformity tolerance is absolute CV change and centroid tolerance is displacement over receiver diagonal',
           'Same profile-enabled binary for both backends; profile files/events disabled in formal samples',
           'CPU baseline is one thread; no best-multicore performance claim']}
    candidate_rows=[r for r in correct['rows'] if r['level']==correct['primary_candidate']]
    candidate_worst={metric:max(r['convergence'][metric] for r in candidate_rows) for metric in plan['study']['control_metrics']}
    reference_step={metric:max(r['convergence'][metric] for r in correct['reference_refinement_check']) for metric in plan['study']['control_metrics']}
    previous=next(b['minimum_tested_level'] for b in correct['previous_reference_recommendations'] if b['tolerance']==plan['primary_control_tolerance'])
    result['reference_validation']={'previous_reference_minimum_level':previous,'final_reference_minimum_level':correct['primary_candidate'],
        'minimum_changed_with_last_refinement':previous!=correct['primary_candidate'],
        'candidate_worst_metrics':candidate_worst,'last_reference_step_worst_metrics':reference_step,
        'candidate_plus_observed_step_within_primary_band':all(candidate_worst[m]+reference_step[m]<plan['primary_control_tolerance'] for m in candidate_worst),
        'interpretation':'Finite-reference sensitivity check, not a certified error bound or proof of the continuum solution; recommendation is conditional on tested states and references'}
    result['centroid_coordinates']={'centroid_surface_s_m':'receiver local x from left edge',
                                    'centroid_z_from_bottom_m':'receiver local y from lower edge (legacy generic metric key)'}
    for source in correct['native_rows']+correct['rows']:
        key=(source['operating_point'],source['level']);segment,timing=timings.pop(key)
        row={k:source[k] for k in ('case_id','operating_point','level','grid','metrics','convergence','deterministic','physical_state_frozen')}
        row['role']='historical_native' if source['level']==-1 else ('numerical_reference' if source['level']==result['reference_level'] else 'physical_level')
        row['backend_errors']=safe_errors(source['backend_errors']);row['legacy_anchor_bitwise']=source.get('legacy_anchor_bitwise')
        if 'all215' in source:
            row['all215']=safe_comparison(source['all215'])
        row['measurement_segment']=segment;row['pipelines']=timing['pipelines'];row['flat_cuda_speedup']=timing['flat_cuda_speedup']
        result['rows'].append(row)
    if timings:raise ValueError('Timing levels do not match scientific rows')
    if profile:
        if profile['status']!='passed' or profile['level']!=result['primary_candidate_level']:raise ValueError('Profile does not match selected grid')
        result['profile']={'case_id':plan['case_id'],'operating_point':plan['operating_points'][0]['id'],
            'grid':profile['grid'],'level':profile['level'],'profiles':profile['profiles'],
            'build_metadata':safe_metadata(performances[-1]['metadata']),
            'gpu_model':performances[-1]['gpu_telemetry'][0]['name'],
            'interpretation':'Instrumented diagnostic observation after separate event warmups; inclusive scopes overlap and are not additive; excluded from formal timings'}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--correctness',type=Path,required=True);p.add_argument('--performance',type=Path,action='append',required=True)
    p.add_argument('--profile',type=Path);p.add_argument('--output-dir',type=Path,required=True);args=p.parse_args()
    load=lambda path:json.loads(path.read_text())
    result=summarize(load(args.plan),load(args.correctness),[load(x) for x in args.performance],load(args.profile) if args.profile else None)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    save(args.output_dir/'phase3c-cesa1-grid-convergence-summary.json',result)
    correctness={'phase':'3C','case_id':result['case_id'],'rtol':1e-9,'atol':1e-10,'status':'passed',
        'core_revisions':result['measurement_segments'][0]['metadata']['commits'],
        'build_metadata':result['measurement_segments'][0]['metadata'],
        'gpu_model':result['measurement_segments'][0]['gpu_telemetry'][0]['name'],
        'rows':[{k:r[k] for k in ('operating_point','level','grid','backend_errors','legacy_anchor_bitwise','deterministic')}
                |({'all215':r['all215']} if 'all215' in r else {}) for r in result['rows']]}
    save(args.output_dir/'phase3c-cesa1-backend-correctness.json',correctness)
    if result['profile']:save(args.output_dir/'phase3c-cesa1-profile.json',result['profile'])
    fields=['case_id','state_id','level','role','nx','ny','cells','dx_m','dy_m','target_cell_m','measurement_segment',
        'flat_cuda_speedup','legacy_first_s','flat_first_s','cuda_first_s']
    for backend in ('flat','cuda'):
        fields += [backend+'_'+key+'_s' for key in ('median','minimum','maximum','mean','stdev')]+[backend+'_cv']
    conv=['peak_rel','map_l1_normalized','map_l2_normalized','map_linf_normalized','map_linf_kw_m2',
          'map_rms_kw_m2','centroid_distance_over_diagonal','uniformity_cv_abs','integrated_incident_power_rel']
    fields+=['peak_cell_average_proxy_kw_m2','mean_kw_m2','uniformity_cv','integrated_incident_power_kw',
             'centroid_surface_s_m','centroid_z_from_bottom_m']
    fields+=['cpu_model','gpu_model','cpu_threads','precision','fma','fast_math','build_type','cuda_arch','library_sha256']
    fields+=conv+['backend_max_abs_kw_m2','backend_max_rel_nonzero','backend_rms_kw_m2','root_sha','ssc_sha','solarpilot_sha','soltrace_sha']
    with (args.output_dir/'phase3c-cesa1-grid-performance.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for r in result['rows']:
            g=r['grid'];item={'case_id':r['case_id'],'state_id':r['operating_point'],'level':r['level'],'role':r['role'],
                'nx':g['nx'],'ny':g['ny'],'cells':g['cells'],'dx_m':g['cell_width_m'],'dy_m':g['cell_height_m'],
                'target_cell_m':g['target_cell_m'],'measurement_segment':r['measurement_segment'],'flat_cuda_speedup':r['flat_cuda_speedup'],
                **{key:r['convergence'][key] for key in conv}}
            for backend in ('legacy','flat','cuda'):
                if backend in r['pipelines']:item[backend+'_first_s']=r['pipelines'][backend]['first_call_s']
            for backend in ('flat','cuda'):
                stats=r['pipelines'][backend]['statistics_s']
                item.update({backend+'_'+key+'_s':stats[key] for key in ('median','minimum','maximum','mean','stdev')})
                item[backend+'_cv']=stats['coefficient_of_variation']
            for key in ('max_abs_kw_m2','max_rel_nonzero','rms_kw_m2'):item['backend_'+key]=r['backend_errors'][key]
            item.update({k:r['metrics'][k] for k in ('peak_cell_average_proxy_kw_m2','mean_kw_m2','uniformity_cv',
                         'integrated_incident_power_kw','centroid_surface_s_m','centroid_z_from_bottom_m')})
            segment=result['measurement_segments'][r['measurement_segment']];meta=segment['metadata']
            item.update({k:meta[k] for k in ('cpu_model','cpu_threads','precision','fma','fast_math','library_sha256')})
            item.update(gpu_model=segment['gpu_telemetry'][0]['name'],build_type=meta['build_settings']['CMAKE_BUILD_TYPE'],
                        cuda_arch=meta['build_settings']['CMAKE_CUDA_ARCHITECTURES'])
            commits=meta['commits']
            for key,repo in [('root','.'),('ssc','ssc'),('solarpilot','SolarPILOT'),('soltrace','SolTrace')]:item[key+'_sha']=commits[repo]
            writer.writerow(item)
    print('Approved aggregate study, correctness, timing CSV and profile published.')

if __name__=='__main__':main()
