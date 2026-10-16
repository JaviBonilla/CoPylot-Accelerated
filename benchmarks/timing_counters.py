"""Align read-only system counter captures with monotonic benchmark windows."""
import statistics


def turbostat_rows(text):
    header=None;rows=[]
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
        if 'Time_Of_Day_Seconds' in row:rows.append(row)
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
        for r in selected:by_time.setdefault(r['Time_Of_Day_Seconds'],[]).append(r)
        weighted=[]
        for group in by_time.values():
            valid=[r for r in group if 'Bzy_MHz' in r and 'Busy%' in r];weight=sum(r['Busy%'] for r in valid)
            if weight:weighted.append(sum(r['Bzy_MHz']*r['Busy%'] for r in valid)/weight)
        if weighted:result['affinity_busy_weighted_mhz_median']=statistics.median(weighted)
    return result
