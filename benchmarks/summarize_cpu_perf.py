#!/usr/bin/env python3
"""Publish the user-supplied perf supplement without changing closed CPU references."""
import argparse
import hashlib
import json
from pathlib import Path
from cpu_repeatability import EXPECTED_LIBRARY,identity_signature
from summarize_cpu_repeatability import summarize_host
from timing_counters import PERF_EVENTS,perf_rows,perf_origin_bounds,align_perf,perf_metrics


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def pooled_groups(contrasts):
    groups=[]
    for name,phases in [('fast',[0,16,32]),('slow',[48])]:
        selected=[s for s in contrasts if s['callsite_mod64'] in phases]
        totals={e:sum(s['perf']['counts'][e] for s in selected) for e in PERF_EVENTS}
        groups.append({'regime':name,'callsite_phases_mod64':phases,'contrast_blocks':len(selected),
                       'contrast_blocks_with_counter_coverage':sum(bool(s['perf']['fully_interior_intervals']) for s in selected),
                       'block_median_range_s':[min(s['statistics_s']['median'] for s in selected),max(s['statistics_s']['median'] for s in selected)],
                       'fully_interior_intervals':sum(s['perf']['fully_interior_intervals'] for s in selected),
                       'minimum_running_percent':min((s['perf']['minimum_running_percent'] for s in selected if s['perf']['minimum_running_percent'] is not None),default=None),
                       **perf_metrics(totals)})
    return groups


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();directory=args.input_dir
    campaign_path=directory/'P1-perf-stack.json';host_path=directory/'P1-perf-stack-host.json'
    capture=directory/'perf-capture.txt';clock_path=directory/'perf2-live-clock.json'
    campaign=json.loads(campaign_path.read_text());host=json.loads(host_path.read_text())
    clock=json.loads(clock_path.read_text());counters=perf_rows(capture.read_text())
    if campaign['status']!='passed' or campaign['metadata']['library_sha256']!=EXPECTED_LIBRARY:
        raise ValueError('Require the frozen library and accepted numerical windows')
    if not counters or counters[-1]['relative_end_s']<179:raise ValueError('Require completed three-minute capture')
    bounds=perf_origin_bounds(clock);comparisons=[]
    for row in campaign['rows']:
        if not(row['bitwise_repeat'] and row['historical_control_map_bitwise'] and row['loaded_set_unchanged']):
            raise ValueError('Numerical correctness or mapped identity changed')
        row['loaded_identity_group']=hashlib.sha256(json.dumps(identity_signature(row['loaded_after'])).encode()).hexdigest()
        row['perf']=align_perf(counters,row['measurement_monotonic'],bounds)
        row['host_observation']=summarize_host(host,row)
        for contrast in row['stack_contrasts']:
            if not contrast['bitwise_equal']:raise ValueError('Stack contrast changed numerical outputs')
            contrast['perf']=align_perf(counters,contrast['measurement_monotonic'],bounds)
            contrast['host_observation']=summarize_host(host,contrast)
            if not contrast['perf']['fully_interior_intervals']:raise ValueError('Stack contrast has no fully interior counters')
        wider=[bounds[0]-.05,bounds[1]+.05]
        sensitivity=[{**s,'perf':align_perf(counters,s['measurement_monotonic'],wider,margin=.1)} for s in row['stack_contrasts']]
        comparisons.append({'case_id':row['case_id'],'groups':pooled_groups(row['stack_contrasts']),
                            'wider_alignment_sensitivity':{'origin_bounds':wider,'additional_boundary_margin_s':.1,
                                                           'groups':pooled_groups(sensitivity)}})
    result={'phase':'4R','kind':'supplementary_perf_intervention','frozen_library_sha256':EXPECTED_LIBRARY,
            'provenance':{'raw_capture_sha256':sha(capture),'raw_campaign_sha256':sha(campaign_path),
                          'raw_host_sha256':sha(host_path),'clock_evidence_sha256':sha(clock_path),
                          'clock_evidence':clock,'capture_intervals':len(counters),
                          'complete_intervals':sum(r['complete'] for r in counters),
                          'capture_end_relative_s':counters[-1]['relative_end_s'],
                          'origin_monotonic_bounds':bounds,'additional_boundary_margin_s':.05,
                          'origin_assumptions':'The sole live perf process produced this file. Its start tick precedes counter setup; file writes follow interval timestamps. Conservative 10/20 ms granularity allowances and an additional 50 ms boundary margin are applied.'},
            'comparisons':comparisons,'campaign':campaign,'capture_intervals':counters,
            'local_perf_event_descriptions':{'resource_stalls.sb':'Cycles stalled due to no store buffers available; excludes draining for sync.',
                                             'ld_blocks.address_alias':'False dependencies in MOB due to partial compare on address.',
                                             'ld_blocks.store_forward':'Loads blocked due to overlap with a preceding store that cannot be forwarded.'},
            'interpretation':['Within-process stack intervention independently confirms the IPC collapse.',
                              'Branch misses are per million retired instructions, not a fraction of branches.',
                              'Address-alias, store-forward and store-buffer events do not directly measure cache-line coherence/HITM.',
                              'System-wide counters include observer/background activity; no causal stall attribution follows from event correlation alone.',
                              'Original controlled CPU references and all previous campaign samples remain unchanged.']}
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('Published',len(campaign['rows']),'case rows and',sum(len(r['stack_contrasts']) for r in campaign['rows']),'contrast blocks')


if __name__=='__main__':main()
