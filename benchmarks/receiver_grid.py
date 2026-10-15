"""Physical receiver grids and conservative piecewise-constant surface comparison."""
import math
import numpy as np


def _positive(value,name):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
        raise ValueError(name+' must be finite and positive')
    return float(value)


def physical_grid(receiver,target_cell_m):
    delta=_positive(target_cell_m,'target cell size');height=_positive(receiver['height_m'],'height')
    if receiver['type']=='cylindrical':width=math.pi*_positive(receiver['diameter_m'],'diameter')
    elif receiver['type']=='flat':width=_positive(receiver['width_m'],'width')
    else:raise ValueError('Unsupported receiver surface')
    nx=max(2,math.ceil(width/delta));ny=max(2,math.ceil(height/delta))
    if nx*ny>4_000_000:raise ValueError('Grid exceeds explicit safety limit')
    return {'receiver_type':receiver['type'],'nx':nx,'ny':ny,'cells':nx*ny,'surface_width_m':width,'height_m':height,
            'target_cell_m':delta,'cell_width_m':width/nx,'cell_height_m':height/ny}


def refinement_series(receiver,target_sizes):
    if len(target_sizes)<4:raise ValueError('At least four target levels are required')
    if any(a<=b for a,b in zip(target_sizes,target_sizes[1:])):raise ValueError('Targets must strictly decrease')
    grids=[physical_grid(receiver,v) for v in target_sizes]
    if len({(g['nx'],g['ny']) for g in grids})!=len(grids):raise ValueError('Duplicate physical grids')
    return grids


def checked_map(values):
    values=np.asarray(values,dtype=float)
    if values.ndim!=2 or 0 in values.shape or not np.isfinite(values).all():raise ValueError('Map must be a finite nonempty matrix')
    if values.min()<0:raise ValueError('Flux density must be nonnegative')
    return values


def overlap_weights(source_count,target_count):
    if any(isinstance(v,bool) or not isinstance(v,(int,np.integer)) or v<1 for v in [source_count,target_count]):
        raise ValueError('Grid counts must be positive integers')
    edges_s=np.linspace(0,1,source_count+1);edges_t=np.linspace(0,1,target_count+1)
    weights=np.zeros((target_count,source_count));i=j=0
    while i<target_count and j<source_count:
        left=max(edges_t[i],edges_s[j]);right=min(edges_t[i+1],edges_s[j+1])
        if right>left:weights[i,j]=(right-left)*target_count
        if edges_t[i+1]<edges_s[j+1]-1e-15:i+=1
        elif edges_s[j+1]<edges_t[i+1]-1e-15:j+=1
        else:i+=1;j+=1
    return weights


def conservative_rebin(values,target_shape):
    """Same rectangular physical extent and seam/origin; target cell averages."""
    values=checked_map(values)
    if len(target_shape)!=2:raise ValueError('Expected rows, columns')
    if any(isinstance(v,bool) or not isinstance(v,(int,np.integer)) or v<1 for v in target_shape):
        raise ValueError('Grid counts must be positive integers')
    if tuple(target_shape)==values.shape:
        # An identical partition requires no projection or floating-point weights.
        return values.copy()
    wy=overlap_weights(values.shape[0],target_shape[0]);wx=overlap_weights(values.shape[1],target_shape[1])
    # Explicit einsum loops avoid introducing BLAS worker threads.
    tmp=np.einsum('ij,jk->ik',wy,values)
    return np.einsum('ij,kj->ik',tmp,wx)


def map_metrics(values,grid):
    values=checked_map(values)
    if values.shape!=(grid['ny'],grid['nx']):raise ValueError('Grid/map shape mismatch')
    area=grid['surface_width_m']*grid['height_m'];mean=float(values.mean());mass=float(values.sum())
    if mass<=0:raise ValueError('Positive incident power is required')
    x=(np.arange(grid['nx'])+.5)*grid['cell_width_m'];z=(np.arange(grid['ny'])+.5)*grid['cell_height_m']
    cx=float(np.einsum('ij,j->',values,x)/mass);cz=float(np.einsum('ij,i->',values,z)/mass)
    result={'integrated_incident_power_kw':mean*area,'peak_cell_average_proxy_kw_m2':float(values.max()),
            'mean_kw_m2':mean,'std_kw_m2':float(values.std()),'uniformity_cv':float(values.std()/mean),
            'centroid_surface_s_m':cx,'centroid_z_from_bottom_m':cz}
    if grid['receiver_type']=='cylindrical':
        angle=2*np.pi*x/grid['surface_width_m']
        sine=float(np.einsum('ij,j->',values,np.sin(angle))/mass);cosine=float(np.einsum('ij,j->',values,np.cos(angle))/mass)
        resultant=math.hypot(sine,cosine)
        result['circular_centroid_s_m']=None if resultant<1e-12 else float((math.atan2(sine,cosine)%(2*np.pi))*grid['surface_width_m']/(2*np.pi))
        result['circular_resultant']=resultant
    return result


def compare_maps(coarse,reference,grid,reference_grid):
    coarse=checked_map(coarse);reference=checked_map(reference)
    a=map_metrics(coarse,grid);b=map_metrics(reference,reference_grid)
    if grid['receiver_type']!=reference_grid['receiver_type']:
        raise ValueError('Receiver surface types must agree')
    if any(not np.isclose(grid[k],reference_grid[k],rtol=1e-13,atol=1e-13) for k in ['surface_width_m','height_m']):
        raise ValueError('Physical receiver extents must agree')
    mapped=conservative_rebin(coarse,reference.shape);diff=mapped-reference
    rms=float(np.sqrt(np.mean(diff**2)));ref_rms=float(np.sqrt(np.mean(reference**2)))
    ref_on_coarse=conservative_rebin(reference,coarse.shape)
    centroid=math.hypot(a['centroid_surface_s_m']-b['centroid_surface_s_m'],a['centroid_z_from_bottom_m']-b['centroid_z_from_bottom_m'])
    result={'integrated_incident_power_rel':abs(a['integrated_incident_power_kw']/b['integrated_incident_power_kw']-1),
        'peak_rel':abs(a['peak_cell_average_proxy_kw_m2']/b['peak_cell_average_proxy_kw_m2']-1),
        'map_l1_normalized':float(np.abs(diff).mean()/reference.mean()),'map_l2_normalized':rms/ref_rms,
        'map_rms_kw_m2':rms,'map_linf_kw_m2':float(np.abs(diff).max()),
        'map_linf_normalized':float(np.abs(diff).max()/reference.max()),
        'centroid_distance_over_diagonal':centroid/math.hypot(grid['surface_width_m'],grid['height_m']),
        'uniformity_cv_abs':abs(a['uniformity_cv']-b['uniformity_cv']),
        'reference_averaged_to_coarse_peak_kw_m2':float(ref_on_coarse.max()),
        'native_vs_rebinned_reference_peak_rel':abs(float(coarse.max()/ref_on_coarse.max())-1),
        'remap_relative_integral_error':abs(float(mapped.mean()/coarse.mean())-1)}
    if grid['receiver_type']=='cylindrical':
        ca,cb=a['circular_centroid_s_m'],b['circular_centroid_s_m'];span=grid['surface_width_m']
        result['circular_centroid_distance_m']=None if ca is None or cb is None else min(abs(ca-cb),span-abs(ca-cb))
    return result


def minimum_converged(rows,point_ids,metrics,tolerance,reference_level):
    """Require all states and every tested finer non-reference level to pass."""
    _positive(tolerance,'tolerance')
    if not rows or not point_ids or not metrics:
        raise ValueError('Rows, operating points and criteria are required')
    levels=sorted({r['level'] for r in rows if r['level']<reference_level})
    for level in levels:
        selected=[r for r in rows if level<=r['level']<reference_level]
        complete=all(any(r['level']==lev and r['operating_point']==point for r in selected) for lev in levels if lev>=level for point in point_ids)
        if complete and all(all(math.isfinite(r['convergence'][m]) and r['convergence'][m]<=tolerance for m in metrics) for r in selected):return level
    return None
