"""Audit retained CPU sample statistics and matched CPU/CUDA speedups."""
from .common import need, close, timing_statistics


def audit(cpu,gpu,summary):
    for row in cpu['rows']:
        observed=timing_statistics(row['samples_s'])
        for key,value in observed.items():close(row['statistics_s'][key],value,'CPU sample statistics')
        need(row['bitwise_maps_details_summary'] and row['all215_bitwise'],'CPU numerical compatibility')
    for row in gpu['rows']:
        observed=timing_statistics(row['samples_s'])
        for key,value in observed.items():close(row['statistics_s'][key],value,'GPU sample statistics')
    for row in summary['rows']:
        for field,a,b in [('flat_1t_over_best_cpu_mt','flat_1t_median_s','best_cpu_mt_median_s'),
                          ('flat_1t_over_cuda','flat_1t_median_s','cuda_median_s'),
                          ('best_cpu_mt_over_cuda','best_cpu_mt_median_s','cuda_median_s')]:
            close(row[field],row[a]/row[b],'matched CPU/CUDA ratio')
        close(row['cuda_median_s'],timing_statistics(row['cuda_samples_s'])['median'],'retained CUDA sample population')
    return summary['rows']
