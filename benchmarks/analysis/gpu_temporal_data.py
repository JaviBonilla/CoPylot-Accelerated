"""Audit CUDA temporal populations, output coverage and measured annual ratios."""
import statistics
from .common import need, close


def audit(summary):
    raw=summary['all_attempts']
    for row in raw:
        need(row['qualified'] and row['first_call_included'] and row['warmups_excluded']==0,'CUDA campaign qualification')
        v=row['validation']
        need(v['passed'] and v['persisted_payloads_verified']==row['completed'] and v['stored_bytes']==row['output_bytes'] and
             v['cpu_agreement_existing_tolerance'] and v['timing_excludes_verification'],'CUDA persisted outputs')
        close(row['states_per_s'],row['completed']/row['evaluation_wall_s'],'CUDA evaluation denominator')
        close(row['total_states_per_s'],row['completed']/row['total_wall_s'],'CUDA total denominator')
    for group in summary['all_groups']:
        population=[r for r in raw if r['identifier'] in group['campaign_ids']]
        need(len(population)==group['clean_repetitions'] and group['all_outputs_verified'],'CUDA group population')
        for field in ['states_per_s','total_states_per_s','total_wall_s','evaluation_wall_s','setup_wall_s','materialize_analysis_s','serialize_write_s','output_bytes']:
            close(group[field],statistics.median(r[field] for r in population),'CUDA group '+field)
    best=summary['best_measured_annual'];cpu=summary['cpu_annual']
    need(best in summary['all_groups'] and best['library_sha256']==summary['annual_selection_library_sha256'],'annual binary selection')
    need(best['completed']==cpu['completed'] and best['output_bytes']==cpu['output_bytes'],'matched annual workload')
    close(summary['annual_total_wall_speedup'],cpu['total_wall_s']/best['total_wall_s'],'measured annual ratio')
    return best
