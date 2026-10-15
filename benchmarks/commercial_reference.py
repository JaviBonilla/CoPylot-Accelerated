#!/usr/bin/env python3
"""Reconstruct the public SSC commercial-scale optical reference without core edits."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from cases import ROOT, api

MANIFEST=ROOT/'cases/commercial-reference/case_manifest.json'


def load_manifest(path=MANIFEST):
    data=json.loads(Path(path).read_text())
    for asset in data['assets'].values():
        if hashlib.sha256((ROOT/asset['path']).read_bytes()).hexdigest()!=asset['sha256']:
            raise ValueError('Pinned public asset hash changed')
    for p in data['parameters'].values():
        if p['classification'] not in ['published','derived','assumed'] or p['source'] not in data['sources']:
            raise ValueError('Incomplete parameter provenance')
    return data


def coordinates(manifest):
    xy=np.loadtxt(ROOT/manifest['assets']['layout']['path'],delimiter=',')
    if xy.shape!=(manifest['heliostats']['count'],2) or not np.isfinite(xy).all():
        raise ValueError('Invalid public coordinate table')
    return np.column_stack([np.zeros(len(xy)),xy,np.full(len(xy),manifest['heliostats']['z_m'])])


def configure(cp,context,manifest,nx,ny,point):
    if not cp.data_set_string(context,'ambient.0.weather_file',str(ROOT/manifest['assets']['weather']['path'])):
        raise RuntimeError('Cannot configure public climate asset')
    settings={k:p['value'] for k,p in manifest['parameters'].items()}
    settings.update({'fluxsim.0.x_res':nx,'fluxsim.0.y_res':ny,'fluxsim.0.flux_solar_az_in':point['azimuth_deg'],
                     'fluxsim.0.flux_solar_el_in':point['elevation_deg'],'fluxsim.0.flux_dni':point['dni_w_m2']})
    for k,value in settings.items():
        if not cp.data_set_number(context,k,value):raise RuntimeError('Cannot set '+k)
    positions=coordinates(manifest)
    if not cp.assign_layout(context,positions.tolist(),nthreads=1):raise RuntimeError('Cannot assign public layout')
    actual=len(cp.get_layout_info(context,restype='dictionary')['id'])
    if actual!=manifest['heliostats']['count']:raise RuntimeError('Unexpected filtered heliostat count')
    return sanity(cp,context,manifest,positions)


def sanity(cp,context,manifest,positions):
    xy=positions[:,1:3];radii=np.linalg.norm(xy,axis=1)
    width=cp.data_get_number(context,'heliostat.0.width');height=cp.data_get_number(context,'heliostat.0.height')
    ratio=cp.data_get_number(context,'heliostat.0.reflect_ratio')
    if radii.min()<=np.hypot(width,height)/2 or len(np.unique(xy,axis=0))!=len(xy):
        raise ValueError('Invalid tower exclusion or duplicate coordinates')
    # Spatial buckets bound nearest-neighbor checking without an H x H matrix.
    buckets={};nearest=float('inf');bucket_width=25.
    for x,y in xy:
        key=(int(x//bucket_width),int(y//bucket_width))
        for dx in [-1,0,1]:
            for dy in [-1,0,1]:
                for a,b in buckets.get((key[0]+dx,key[1]+dy),[]):nearest=min(nearest,float(np.hypot(x-a,y-b)))
        buckets.setdefault(key,[]).append((x,y))
    if nearest<max(width,height):raise ValueError('Obviously overlapping heliostat structures')
    geometry={k:cp.data_get_number(context,k) for k in ['solarfield.0.tht','receiver.0.rec_diameter','receiver.0.rec_height','solarfield.0.dni_des']}
    for k,value in geometry.items():
        if not np.isclose(value,manifest['parameters'][k]['value'],rtol=0,atol=1e-12):raise ValueError('Unexpected receiver geometry')
    return {'heliostats':len(xy),'heliostat_structure_area_m2':width*height,
        'physical_mirror_area_m2':width*height*manifest['area_definition']['mirror_density']*len(xy),
        'effective_aperture_area_m2':width*height*ratio*len(xy),'layout_bounds_m':{'x':list(map(float,[xy[:,0].min(),xy[:,0].max()])),
        'y':list(map(float,[xy[:,1].min(),xy[:,1].max()]))},'radius_range_m':[float(radii.min()),float(radii.max())],
        'nearest_separation_within_adjacent_25m_buckets_m':nearest,'geometry':geometry,
        'layout_sha256':hashlib.sha256(positions.astype('<f8').tobytes()).hexdigest(),
        'coordinate_convention':'[template_id,x_east_m,y_north_m,z_pivot_m]; original row order retained'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--save-spt',type=Path);args=parser.parse_args();m=load_manifest();cp=api();r=cp.data_create()
    try:
        info=configure(cp,r,m,14,6,m['operating_points'][0])
        if not cp.simulate(r,nthreads=1):raise RuntimeError(cp.get_last_backend_error(r))
        flux=np.asarray(cp.get_fluxmap(r));assert np.isfinite(flux).all() and flux.max()>0
        info.update(case_id=m['case_id'],flux_shape=list(flux.shape),finite_positive=True,peak_kw_m2=float(flux.max()),
                    manifest_sha256=hashlib.sha256(MANIFEST.read_bytes()).hexdigest())
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(info,indent=2,allow_nan=False)+'\n')
        if args.save_spt:
            args.save_spt.parent.mkdir(parents=True,exist_ok=True)
            if not cp.save_spt(r,str(args.save_spt)):raise RuntimeError('Cannot save public generated case')
        print(json.dumps(info,indent=2))
    finally:cp.data_free(r)


if __name__=='__main__':main()
