#!/usr/bin/env python3
"""Publish validated Phase 2D-C samples, disjoint profiles and staged ratios."""
import argparse
import copy
import csv
import json
from pathlib import Path
import re
from image_plane_cuda_performance import distribution


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path,default=Path('artifacts/phase2dc'))
    parser.add_argument('--output',type=Path,default=Path('benchmarks/results'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    def read(name):return json.loads((args.artifacts/name).read_text())
    v1=read('v1-baseline.json');sweep=read('block-sweep.json');final=read('final-performance.json')
    profile=read('final-profile-calibration.json');core=read('resident-core-final.json')
    downstream=read('resident-downstream-final.json');tools=read('existing-tools-resources.json')
    for campaign in [v1,sweep,final,profile]:
        assert campaign['status']=='valid' and len(campaign['cases'])==9
        telemetry=campaign['gpu_telemetry'];assert telemetry
        campaign['metadata'].update(gpu_model=telemetry[0]['name'],driver=telemetry[0]['driver_version'],
            compute_capability=core['resources']['compute_capability'],cuda_runtime_version=core['resources']['runtime_version'],
            cuda_driver_api_version=core['resources']['driver_version'],density_block_size=256,
            image_source_options=['--fmad=true','--ptxas-options=-v'])
        campaign['metadata']['first_call_caveat']='Fresh prepared CoPylot context in an already initialized process; mode order can prime modules. Do not derive cold-process first-call speedups. Direct image first-use cases use independent child processes.'
        campaign['metadata']['direct_statistics_units']='Every cuda_statistics value is in seconds, including keys inherited with an _ms suffix. Raw cuda_samples retain their explicit _ms or _s units.'
        assert all(x['compute_process_count']<=1 and float(x['temperature.gpu'])<80 for x in telemetry)
    assert final['metadata']['library_sha256']==profile['metadata']['library_sha256']==tools['binary_sha256']['build/cuda/lib/solarpilot.so']
    assert read('v1-library-preservation.json')['before_sha256']==v1['metadata']['library_sha256']
    assert core['fixtures']==60 and core['fixture_errors']['global']['passed']
    assert core['resident_fixture_errors']['global']['passed'] and core['resident_edge_errors']['global']['passed']
    assert core['handoff_same_optics_bitwise'] and core['deterministic'] and core['allocation_reuse']
    assert core['layout'][:6]==[1640,8,1728,8,3256,8]
    assert core['layout'][16:]==[16,8,8,12,56,8,48]
    index=lambda campaign:{(c['heliostats'],tuple(c['grid'])):c for c in campaign['cases']}
    initial_by=index(v1);final_by=index(final);profile_by=index(profile)
    rows=[];profiles=[];transfers=[]
    for key,c in final_by.items():
        h,grid=key;g=grid[0];m={name:p['plain_statistics']['median'] for name,p in c['pipelines'].items()}
        before=initial_by[key]['pipelines'];cold_v1=before['v1']['plain_statistics']['median']
        ratios={'legacy_to_flat':m['legacy']/m['flat'],
            'phase2c_density_only_to_exact_v1':before['density_only']['plain_statistics']['median']/cold_v1,
            'exact_v1_to_final':cold_v1/m['final'],'same_campaign_v1_compat_to_final':m['v1']/m['final'],
            'flat_to_final':m['flat']/m['final'],'legacy_to_final':m['legacy']/m['final']}
        rows.append({'heliostats':h,'grid':list(grid),'median_s':{**m,'exact_v1_baseline':cold_v1},'ratios':ratios,
            'final_coefficient_of_variation':c['pipelines']['final']['plain_statistics']['coefficient_of_variation'],
            'first_calls_s':{name:p['first_call_s'] for name,p in c['pipelines'].items()}})
        p=profile_by[key]['pipelines']['final'];assert p['instrumented_warmups_excluded']==3
        assert all(s['resident_handoff'] for s in p['instrumented_samples'])
        budgets=[];fractions=[];bounds=[];host_work=[]
        for s in p['instrumented_samples']:
            wall=s['simulate_wall_s'];q=s['profile']
            shade=q['ShadingBlockingNeighbors']['inclusive_s'];neighbors=q['UpdateNeighborList']['inclusive_s']
            prep=q['PerformanceSimulationPrep']['inclusive_s']-s['image_initial_s']-shade-neighbors
            budget={'image_plane':s['image_total_s'],'flux_density':s['hybrid_density_s'],
                'shading_blocking':shade,'neighbor_list':neighbors,'other_preparation_tracking':prep,
                'projected_shadow_geometry':q['calcHeliostatShadows']['inclusive_s'],
                'normalization_dimensional_postprocessing':s['postprocessing_s'],'api_results_callbacks':q['API']['exclusive_s']}
            budget['timing_driver_other']=wall-sum(budget.values())
            assert all(x>=-1e-7 for x in budget.values()),budget
            assert abs(sum(budget.values())-wall)<1e-12
            f={k:value/wall for k,value in budget.items()}
            f['image_numerical_kernel_only']=s['image_kernel_s']/wall
            b={k:1./(1.-value) for k,value in f.items()}
            measured_host=prep+neighbors+budget['projected_shadow_geometry']+budget['normalization_dimensional_postprocessing']+budget['api_results_callbacks']+s['image_preparation_s']+s['image_host_validation_s']+s['image_writeback_s']+s['preparation_s']
            host_work.append(measured_host/wall);budgets.append(budget);fractions.append(f);bounds.append(b)
        summarize=lambda series:{k:distribution([r[k] for r in series]) for k in series[0]}
        budget_stats=summarize(budgets);fraction_stats=summarize(fractions)
        ranking=sorted(budget_stats,key=lambda k:budget_stats[k]['median'],reverse=True)
        profiles.append({'heliostats':h,'grid':list(grid),'samples_s':budgets,'fractions':fractions,
            'component_statistics_s':budget_stats,'fraction_statistics':fraction_stats,'amdahl_statistics':summarize(bounds),
            'dominant_components':ranking[:3],'measured_host_preparation_integration_fraction':distribution(host_work),
            'plain_median_s':p['plain_statistics']['median'],'instrumented_median_s':p['instrumented_statistics']['simulate_wall_s']['median'],
            'observer_ratio':p['instrumented_statistics']['simulate_wall_s']['median']/p['plain_statistics']['median'],
            'cross_campaign_flux_hash_equal':p['physical_metrics']['flux_sha256']==c['pipelines']['final']['physical_metrics']['flux_sha256']})
        cells=g*g;old_h2d=1840*h+3256+48*cells;new_h2d=1696*h+3256+48*cells
        old_d2h=1728*h+8*cells;new_d2h=1744*h+8*cells
        transfers.append({'heliostats':h,'grid':list(grid),'v1_h2d_bytes':old_h2d,'final_h2d_bytes':new_h2d,
            'h2d_saved_bytes':old_h2d-new_h2d,'h2d_saved_fraction':(old_h2d-new_h2d)/old_h2d,
            'v1_d2h_bytes':old_d2h,'final_d2h_bytes':new_d2h,'d2h_increase_fraction':(new_d2h-old_d2h)/old_d2h,
            'image_input_h2d_bytes':1640*h,'tables_h2d_bytes':3256,'density_metadata_h2d_bytes':56*h,
            'required_image_d2h_bytes':16*h,'eager_full_image_d2h_bytes':1728*h,'final_flux_d2h_bytes':8*cells})
    families=[{'name':n,'count':count,'density_consumes':n in ['coefficients','sigmas'],
        'mandatory_early_cpu':n=='intercept','c_python_direct':n=='intercept','cxx_optical_getter':True,
        'materialized_before_return':True} for n,count in [('sun',49),('errors',49),('mirror',49),('flux_moments',49),('coefficients',16),('sigmas',2),('intercept',1)]]
    assert sum(f['count'] for f in families)==215
    host_states=[read('host-state-final-'+str(h)+'.json') for h in [1000,5000,10000]]
    for s in host_states:assert s['full_resident_host_bitwise'] and s['cpu_switch_bitwise'] and s['errors']['global']['passed']
    assert len(downstream['cases'])==9 and all(c['checks']['resident_vs_full_output_cuda']['map']['bitwise'] for c in downstream['cases'])
    correctness={'metadata':downstream['metadata'],'direct':core,'canonical_host_states':host_states,'downstream':downstream['cases']}
    resources={'metadata':copy.deepcopy(final['metadata']),'initial':read('v1-resources.json')['resources'],
        'final':core['resources'],'final_layout_probe':core['layout'],'tools':tools,'kernel_body_unchanged':True,
        'private_state_study':'Two FacetPowers arrays declare 7168 bytes; compiler/PTX static evidence is recorded. No dynamic stall/traffic attribution or register/local rewrite was used.',
        'tuning_stop':'The numerical kernel is not dominant; retain bounded launch improvement without a private-state rewrite.'}
    handoff={'metadata':copy.deepcopy(final['metadata']),'output_families':families,
        'density_input':{'old_doubles':25,'old_bytes':200,'resident_optical_doubles':18,'cpu_metadata_doubles':7,'cpu_metadata_bytes':56},
        'materialization_policy':'Early intercept/update/validation status; device SoA conversion; separate density kernel; eager complete canonical C++ optical materialization before return. No lazy or cross-state cache.',
        'full_verification_preserved':True,'density_arithmetic_unchanged':True,'density_block_size':256,'transfers':transfers}
    summary={'metadata':copy.deepcopy(final['metadata']),'cases':rows,'interpretation':'Ratios of medians, Flat CPU 1T is the primary GPU baseline. Exact historical v1 and same-campaign full-output control are separate. No cold-process speedup claims.'}
    profile_result={'metadata':copy.deepcopy(profile['metadata']),'cases':profiles,
        'definitions':'Per-sample disjoint functional budgets sum to the instrumented public wall time. Component medians need not sum. Nested scopes are retained in raw calibration data, never added to parents.',
        'amdahl':'Ideal elimination upper bounds 1/(1-f), conditional on this measured instrumented workload; not predictions or an implementation plan.',
        'host_fraction':'Lower bound from explicitly timed, nonoverlapping host preparation/integration subsets; excludes shading and unassigned driver/wait time.',
        'observer':'Primary speedups use no-CSV/event runs. Reprofiling independently warms events three times, retains ten samples and a paired plain calibration.'}
    def publish(name,data):
        text=json.dumps(data,indent=2,allow_nan=False)+'\n'
        assert not re.search(r'/workspace',text,re.I),name
        (args.output/('phase2dc-'+name+'.json')).write_text(text)
    for name,data in [('v1-baseline',v1),('block-sweep',sweep),('final-performance',final),('profile-calibration',profile),
        ('final-profile',profile_result),('correctness',correctness),('resource-usage',resources),('handoff-analysis',handoff),('summary',summary)]:publish(name,data)
    with (args.output/'phase2dc-block-sweep.csv').open('w',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['heliostats','grid','block','status','kernel_median_s','image_hybrid_median_s','simulate_median_s','simulate_cv','registers','local_bytes','occupancy'])
        for c in sweep['cases']:
            for r in sweep['resources']:
                b=next((b for b in c['blocks'] if b['block_size']==r['block_size']),None)
                writer.writerow([c['heliostats'],c['grid'][0],r['block_size'],'measured' if b else 'resource_unavailable',
                    b['instrumented_statistics']['image_kernel_s']['median'] if b else '',b['instrumented_statistics']['image_total_s']['median'] if b else '',
                    b['plain_statistics']['median'] if b else '',b['plain_statistics']['coefficient_of_variation'] if b else '',r['registers_per_thread'],r['local_bytes_per_thread'],r['theoretical_occupancy']])
    print('Published valid Phase 2D-C campaigns, correctness, resources, transfers, ratios and Amdahl bounds')


if __name__=='__main__':main()
