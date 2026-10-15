#!/usr/bin/env python3
"""Derive Phase 2C ratios, paired block comparisons, and exclusive profiles."""
import csv
import json
import hashlib
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
RESULTS=ROOT/'benchmarks/results'
from cases import layout


def keyed(data):
    return {(c['heliostats'],c['grid'][0]):c for c in data['cases']}


def interval(reference,candidate):
    # Paired rotating rounds, no best-run selection. Fixed seed makes the
    # percentile interval reproducible; n=10 remains a small-sample limitation.
    ref=np.asarray(reference);cand=np.asarray(candidate)
    indices=np.random.default_rng(20261015).integers(0,len(ref),(5000,len(ref)))
    ratios=np.median(ref[indices],axis=1)/np.median(cand[indices],axis=1)
    return [float(x) for x in np.quantile(ratios,[.025,.975])]


def main():
    baseline=json.loads((RESULTS/'phase2c-baseline.json').read_text())
    sweep=json.loads((RESULTS/'phase2c-block-sweep.json').read_text())
    plain=json.loads((RESULTS/'phase2c-end-to-end.json').read_text())
    final=json.loads((RESULTS/'phase2c-final.json').read_text())
    for dataset in (baseline,sweep,plain,final):assert dataset['status']=='valid'
    assert len({d['metadata']['library_sha256'] for d in (baseline,sweep,plain,final)})==1
    base,control,finished=map(keyed,(baseline,plain,final));rows=[];blocks=[]
    sw={(c['heliostats'],c['grid'][0],c['block_size']):c for c in sweep['cases']}
    for key,c in control.items():
        h,grid=key;b=base[key]['backends'];f=finished[key];cuda={x['block_size']:x for x in c['cuda_blocks']}
        legacy=c['backends']['legacy']['simulate_wall_s']['median'];flat=c['backends']['flat']['simulate_wall_s']['median']
        gpu=cuda[256]['simulate_wall_s']['median'];fs=f['statistics'];density=b['flat']['statistics']['density_profile_s']['median']
        fractions={name:v['exclusive_s']['median']/fs['profile']['API']['inclusive_s']['median'] for name,v in fs['profile'].items()}
        fraction=density/b['flat']['statistics']['simulate_wall_s']['median']
        rows.append(dict(heliostats=h,grid=grid,cells=grid*grid,
                         effective_parameters={**baseline['metadata']['parameters'],'fluxsim.0.x_res':grid,'fluxsim.0.y_res':grid,'solarfield.0.q_des':h/10},
                         layout_sha256=hashlib.sha256(json.dumps(layout(h)).encode()).hexdigest(),legacy_simulate_s=legacy,flat_simulate_s=flat,
                         cuda_simulate_s=gpu,final_confirmation_s=f['plain_simulate_wall_s']['median'],
                         flat_density_s=density,cuda_kernel_s=fs['kernel_s']['median'],cuda_hybrid_s=fs['hybrid_density_s']['median'],
                         speedups=dict(legacy_to_flat=legacy/flat,flat_density_to_kernel=density/fs['kernel_s']['median'],
                                       flat_density_to_hybrid=density/fs['hybrid_density_s']['median'],flat_to_cuda_simulate=flat/gpu,legacy_to_cuda=legacy/gpu),
                         transfer_bytes=base[key]['transfer_bytes'],cuda_stages_s={name:fs[name]['median'] for name in ('optical_preparation_s','preparation_s','h2d_heliostat_s','h2d_cell_s','h2d_total_s','kernel_s','d2h_s','postprocessing_s','hybrid_density_s','simulate_wall_s')},
                         transfer_fraction=(fs['h2d_total_s']['median']+fs['d2h_s']['median'])/fs['simulate_wall_s']['median'],
                         exclusive_profile_s={name:v['exclusive_s']['median'] for name,v in fs['profile'].items()},exclusive_profile_fractions=fractions,
                         flat_density_fraction=fraction,flat_zero_density_amdahl_limit=1/(1-fraction),
                         intercept_removal_amdahl_limit=1/(1-fractions['Flux::imagePlaneIntercept']),correctness=f['correctness']))
        for block in (64,128,256,512):
            sample=sw[(h,grid,block)];stats=sample['statistics'];bare=cuda[block]
            blocks.append(dict(heliostats=h,grid=grid,block_size=block,repetitions=10,
                               kernel_median_s=stats['kernel_s']['median'],kernel_min_s=stats['kernel_s']['minimum'],kernel_max_s=stats['kernel_s']['maximum'],
                               hybrid_median_s=stats['hybrid_density_s']['median'],profiled_simulate_median_s=stats['simulate_wall_s']['median'],
                               plain_simulate_median_s=bare['simulate_wall_s']['median'],plain_simulate_min_s=bare['simulate_wall_s']['minimum'],plain_simulate_max_s=bare['simulate_wall_s']['maximum'],
                               plain_speedup_vs_256=cuda[256]['simulate_wall_s']['median']/bare['simulate_wall_s']['median'],
                               paired_95pct_speedup_interval=interval(cuda[256]['samples_s'],bare['samples_s'])))
    output=dict(selected_block_size=256,ssc_modified=False,decision='Retain CUDA v1: no alternative gives a material consistent kernel and end-to-end gain; no additional optimization justified.',
                primary_speedup_source='event/file-output-free rotating plain control; final repeat reported separately',cases=rows,block_comparison=blocks,
                block_geometric_mean_speedups={str(block):float(np.exp(np.mean(np.log([r['plain_speedup_vs_256'] for r in blocks if r['block_size']==block])))) for block in (64,128,256,512)},
                next_hotspot='Flux::imagePlaneIntercept exclusive CPU time',
                new_correctness=dict(max_abs=max(c['correctness']['max_abs'] for c in sweep['cases']),max_rel=max(c['correctness']['max_rel'] for c in sweep['cases']),
                                     max_rms=max(c['correctness']['rms'] for c in sweep['cases']),
                                     max_peak_abs=max(abs(c['correctness']['peak_flux_difference_kw_m2']) for c in sweep['cases']),
                                     max_integrated_abs=max(abs(c['correctness']['integrated_flux_difference_kw']) for c in sweep['cases'])))
    (RESULTS/'phase2c-summary.json').write_text(json.dumps(output,indent=2)+'\n')
    with (RESULTS/'phase2c-block-sweep.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(blocks[0]));writer.writeheader();writer.writerows(blocks)
    print('| H | Grid | Legacy ms | Flat ms | CUDA ms | Flat/CUDA |')
    print('|---:|---:|---:|---:|---:|---:|')
    for row in rows:print(f"| {row['heliostats']} | {row['grid']}² | {row['legacy_simulate_s']*1000:.3f} | {row['flat_simulate_s']*1000:.3f} | {row['cuda_simulate_s']*1000:.3f} | {row['speedups']['flat_to_cuda_simulate']:.2f} |")


if __name__=='__main__':main()
