"""Audit measured annual rows, byte accounting, CSV agreement and unrounded ratios.
Adapted from the existing scientific annual-evidence audit; presentation code removed.
"""
import json
from .common import need, close

MODES=['original','refactored','cpu','gpu']
RATIOS=[('original','refactored'),('original','cpu'),('original','gpu'),
        ('refactored','cpu'),('refactored','gpu'),('cpu','gpu')]


def audit(matrix, validation, flat):
    need(matrix['passed'] and validation['passed'],'annual archive validation failed')
    for field in ['all_expected_outputs_produced','every_annual_payload_persisted_and_verified',
                  'cpu_original_refactored_full_annual_bitwise','gpu_annual_existing_cpu_tolerances_unchanged',
                  'no_interpolation','no_extrapolation','validation_is_outside_timing']:
        need(validation[field] is True,'annual validation '+field)
    need(not validation['private_per_state_details_exported'],'private per-state export')
    need(not matrix['failed_or_incomplete_campaign_ids'] and not validation['failed_or_incomplete_campaign_ids'],
         'incomplete annual campaigns')
    expected={(case,mode) for case in ['cesa','commercial'] for mode in MODES}
    keyed={(r['case'],r['execution_mode']):r for r in matrix['rows']}
    csv_rows={(r['case'],r['execution_mode']):r for r in flat}
    need(len(matrix['rows'])==len(keyed)==len(flat)==len(csv_rows)==len(expected) and set(keyed)==set(csv_rows)==expected,
         'complete eight-mode annual coverage')
    need(validation['complete_annual_matrix_rows']==len(expected),'validation row count')
    cases={}
    for case in ['cesa','commercial']:
        rows={m:keyed[(case,m)] for m in MODES};ref=rows['original'];cases[case]=rows
        for mode,row in rows.items():
            need(row['all_expected_outputs_produced'] and row['persisted_full_outputs_verified']==row['evaluated_daylight_states'],
                 'annual payload coverage')
            need(row['cpu_window_qualified'] and row['no_temporal_interpolation'] and row['first_call_included'] and
                 row['warmups_removed']==0 and row['validation_outside_timing'],'annual timing protocol')
            for field in ['requested_annual_hours','evaluated_daylight_states','omitted_nighttime_states',
                          'daylight_zero_dni_states','grid_nx','grid_ny','standard_output_npz_bytes']:
                need(row[field]==ref[field],'matched annual workload '+field)
            need(row['requested_annual_hours']==row['evaluated_daylight_states']+row['omitted_nighttime_states'],
                 'annual state accounting')
            need(row['complete_standard_output_bytes']==row['standard_output_npz_bytes']+row['flushed_state_metadata_bytes'],
                 'output byte accounting')
            need(row['total_wall_s']>=row['evaluation_wall_s']>0,'wall boundary')
            close(row['total_wall_min'],row['total_wall_s']/60,'minutes')
            close(row['evaluation_states_per_s'],row['evaluated_daylight_states']/row['evaluation_wall_s'],'evaluation rate')
            close(row['total_wall_states_per_s'],row['evaluated_daylight_states']/row['total_wall_s'],'total-wall rate')
            if mode in ['original','refactored']:
                need(row['concurrent_states_or_contexts']==row['cpu_threads_per_state']==1,'serial allocation')
            c=csv_rows[(case,mode)];need(c.keys()==row.keys(),'CSV schema')
            for field,value in row.items():
                if isinstance(value,bool):need(c[field]==str(value),'CSV boolean '+field)
                elif isinstance(value,(int,float)):close(float(c[field]),value,'CSV numeric '+field)
                elif isinstance(value,dict):need(json.loads(c[field])==value,'CSV provenance '+field)
                else:need(c[field]==value,'CSV field '+field)
        for a,b in RATIOS:
            for clock,field in [('total_wall','total_wall_s'),('evaluation_wall','evaluation_wall_s')]:
                close(matrix['speedups_by_case'][case][clock][a+'_over_'+b],rows[a][field]/rows[b][field],
                      'unrounded annual speedup')
    return cases
