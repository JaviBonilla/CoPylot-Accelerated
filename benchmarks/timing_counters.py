"""Align read-only system counter captures with monotonic benchmark windows."""
import statistics
import csv

PERF_EVENTS=('cycles','instructions','branch-misses','ld_blocks.address_alias',
             'ld_blocks.store_forward','resource_stalls.sb')


def perf_rows(text):
    """Read perf -I -x, integer events, including decimal-comma running percent."""
    groups={}
    for parts in csv.reader(text.splitlines()):
        if len(parts)<6 or parts[3] not in PERF_EVENTS:continue
        try:
            end=float(parts[0]);count=float(parts[1]);runtime=float(parts[4])
            percent=parts[5]
            if len(parts)>6 and parts[6].isdigit() and len(parts[6])==2 and percent.isdigit():
                percent+='.'+parts[6]
            percent=float(percent)
        except ValueError:continue
        row=groups.setdefault(end,{'relative_end_s':end,'counts':{},'runtime_ns':{},'running_percent':{}})
        row['counts'][parts[3]]=count;row['runtime_ns'][parts[3]]=runtime
        row['running_percent'][parts[3]]=percent
    previous=0.;rows=[]
    for end,row in sorted(groups.items()):
        row['relative_start_s']=previous;previous=end
        row['complete']=all(event in row['counts'] for event in PERF_EVENTS)
        rows.append(row)
    return rows


def perf_origin_bounds(clock):
    """Bound origin using the sole live perf start tick and observed write times."""
    if len(clock['processes'])!=1:raise ValueError('Perf process origin is ambiguous')
    hz=clock['clk_tck'];samples=clock['samples']
    offset=statistics.median(s['utc_epoch_s']-s['monotonic'] for s in samples)
    # Process creation precedes event setup. File writes follow interval timestamping.
    # Add conservative 10/20 ms allowances for start-tick and filesystem granularity.
    low=clock['processes'][0]['starttime_ticks']/hz-1/hz
    high=min(s['mtime_epoch_s']-s['last_relative_s']-offset for s in samples)+.02
    if not 0<=high-low<=.2:raise ValueError('Perf origin cannot be bounded within 200 ms')
    return [low,high]


def align_perf(rows,measurement_monotonic,origin_bounds,margin=.05):
    start,end=measurement_monotonic;low,high=origin_bounds
    selected=[r for r in rows if r['complete'] and low+r['relative_start_s']>=start+margin
              and high+r['relative_end_s']<=end-margin]
    totals={event:sum(r['counts'][event] for r in selected) for event in PERF_EVENTS}
    return {'fully_interior_intervals':len(selected),'origin_monotonic_bounds':origin_bounds,
            'additional_boundary_margin_s':margin,**perf_metrics(totals),
            'minimum_running_percent':min((v for r in selected for v in r['running_percent'].values()),default=None),
            'interpretation':'System-wide counters, including observer/background work. Only complete intervals wholly inside the benchmark for the entire origin bound are included; branch misses are normalized per instruction, not per branch.'}


def perf_metrics(totals):
    cycles=totals['cycles'];instructions=totals['instructions']
    return {'counts':totals,'ipc':instructions/cycles if cycles else None,
            'events_per_million_instructions':{e:totals[e]*1e6/instructions for e in PERF_EVENTS[2:]} if instructions else {},
            'store_buffer_stall_cycles_over_cycles':totals['resource_stalls.sb']/cycles if cycles else None}


def turbostat_rows(text):
    header=None;rows=[];interval=-1
    for line in text.splitlines():
        parts=line.split()
        if not parts:continue
        if parts[0]=='Time_Of_Day_Seconds':header=parts;continue
        if header is None or len(parts)<8:continue
        row={}
        for key,value in zip(header,parts):
            if key in ('CPU','Core'):row[key]=value
            else:
                try:row[key]=float(value)
                except ValueError:pass
        if 'Time_Of_Day_Seconds' in row:
            if row.get('CPU')=='-':interval+=1
            row['interval_index']=interval
            rows.append(row)
    return rows


def align_turbostat(rows,measurement_monotonic,clock_offset,threads,cadence=.2):
    start,end=[v+clock_offset for v in measurement_monotonic]
    # Omit one whole interval at either edge, independent of sampling phase.
    inside=[r for r in rows if start+cadence<=r['Time_Of_Day_Seconds']<=end-cadence]
    aggregates=[r for r in inside if r.get('CPU')=='-']
    selected=[r for r in inside if r.get('CPU','-').isdigit() and int(r['CPU'])<threads]
    result={'utc_window_epoch_s':[start,end],'boundary_exclusion_s':cadence,'aggregate_intervals':len(aggregates),
            'affinity_cpu_rows':len(selected),'interpretation':'Turbostat Bzy_MHz and IPC; whole boundary intervals excluded. System-wide aggregate includes the small observer/background load.'}
    result['aggregate_medians']={k:statistics.median(r[k] for r in aggregates if k in r) for k in
        ('Bzy_MHz','Avg_MHz','Busy%','IPC','PkgWatt','CoreThr','SMI','PKG_%') if any(k in r for r in aggregates)}
    if selected:
        by_time={}
        # Turbostat timestamps each CPU separately within one capture interval.
        for r in selected:by_time.setdefault(r['interval_index'],[]).append(r)
        weighted=[]
        for group in by_time.values():
            valid=[r for r in group if 'Bzy_MHz' in r and 'Busy%' in r];weight=sum(r['Busy%'] for r in valid)
            if weight:weighted.append(sum(r['Bzy_MHz']*r['Busy%'] for r in valid)/weight)
        if weighted:result['affinity_busy_weighted_mhz_median']=statistics.median(weighted)
    return result
