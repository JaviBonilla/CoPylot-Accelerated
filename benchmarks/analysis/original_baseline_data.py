"""Audit retained Original process samples and matched four-mode timing ratios."""
import statistics
from .common import need, close, timing_statistics


def audit(summary,validation):
    need(summary['passed'] and validation['passed'],'Original archive validation')
    p=summary['protocol'];need(p['intercept_path']==p['flux_path']=='legacy' and p['no_trim'],'Original execution protocol')
    rows=summary['rows'];need(len(rows)==8 and len({(r['case_id'],r['state_id']) for r in rows})==8,'eight-state coverage')
    for r in rows:
        attempts=[a for a in summary['attempts'] if (a['case_id'],a['state_id'])==(r['case_id'],r['state_id'])]
        need(len(attempts)==r['qualified_processes']>=p['minimum_qualified_processes'],'qualified process coverage')
        medians=[]
        for a in attempts:
            need(len(a['samples_s'])==p['samples_per_process'] and len(a['warmup_samples_s'])==p['warmups'],'sample coverage')
            need(all(a[k] for k in ['source_valid','placement_verified','policy_unchanged','all215_map_detail_summary_bitwise']),
                 'qualification/output compatibility')
            observed=timing_statistics(a['samples_s'])
            for k,v in observed.items():close(a['statistics_s'][k],v,'Original sample statistics')
            need(observed['coefficient_of_variation']<=p['within_process_cv_max'],'within-process stability')
            medians.append(observed['median'])
        cv=statistics.stdev(medians)/statistics.mean(medians);spread=max(medians)/min(medians)
        close(r['original_median_s'],statistics.median(medians),'Original median of process medians')
        close(r['inter_process_cv'],cv,'Original process CV');close(r['process_median_max_over_min'],spread,'Original process spread')
        need(cv<=p['inter_process_median_cv_max'] and spread<=p['process_median_max_over_min'],'between-process gates')
        for ratio,a,b in [('original_over_flat1t','original_median_s','flat_1t_median_s'),
                          ('original_over_flat24t','original_median_s','flat_24t_median_s'),
                          ('original_over_cuda','original_median_s','cuda_median_s'),
                          ('flat1t_over_flat24t','flat_1t_median_s','flat_24t_median_s'),
                          ('flat24t_over_cuda','flat_24t_median_s','cuda_median_s')]:
            close(r[ratio],r[a]/r[b],'matched Original ratio')
        need(r['correctness_bitwise_full_original_flat'] and r['samples_trimmed']==0,'full-output compatibility')
    need(validation['process_state_blocks_retained']==len(summary['attempts']) and
         validation['measured_samples_retained']==sum(len(a['samples_s']) for a in summary['attempts']),
         'validation population accounting')
    return rows
