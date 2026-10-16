#!/usr/bin/env python3
"""Compare old/new full optical, map, detail and summary bytes in separate processes."""
import argparse
import ctypes
import json
import os
import hashlib
import subprocess
from pathlib import Path
from unittest.mock import patch
import numpy as np
import cpu_multicore as c


def arrays(state,optical):
    flux,detail,summary=state;keys=sorted(detail);summary_keys=sorted(summary)
    result={'map':flux,'optical':optical,'detail_keys':np.asarray(keys),
            'summary_keys':np.asarray(summary_keys),'summary_values':np.asarray([summary[k] for k in summary_keys],dtype=np.float64)}
    result.update({'detail_'+str(i):detail[key] for i,key in enumerate(keys)})
    return result


def main():
    from cpu_hardening import LIBRARIES,OUT
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--library',choices=['old','new'],required=True)
    args=parser.parse_args();directory,expected=LIBRARIES[args.library]
    os.environ['COPILOT_LIB_DIR']=str(c.ROOT/'build'/directory/'lib')
    for key in list(os.environ):
        if key.startswith('SOLARPILOT_'):os.environ.pop(key)
    c.topology_cache=c.topology();os.sched_setaffinity(0,set(c.topology_cache['affinity_sets']['24']))
    cp=c.api();metadata=c.metadata();c.require(metadata['library_sha256']==expected,'Wrong numerical binary')
    metadata['source_pin_for_library']=metadata['commits']['ssc'] if args.library=='new' else '581a006ec4afb0f0d1f34b1d0d8382736e83d865'
    source=(c.ROOT/'ssc/solarpilot/Flux.cpp').read_bytes() if args.library=='new' else subprocess.check_output(['git','-C',str(c.ROOT/'ssc'),'show','581a006ec4afb0f0d1f34b1d0d8382736e83d865:solarpilot/Flux.cpp'])
    metadata['density_source_sha256']=hashlib.sha256(source).hexdigest()
    metadata['source_worktree_dirty']=bool(subprocess.check_output(['git','-C',str(c.ROOT/'ssc'),'status','--porcelain'],text=True).strip())
    plan=json.loads((c.ROOT/'local-cases/example/phase3c-results/plan.json').read_text())
    bridge_path=OUT/'libold_optical_export.so' if args.library=='old' else c.ROOT/'build'/directory/'libcpu_optical_state_bridge.so'
    bridge=ctypes.CDLL(str(bridge_path))
    bridge.phase4_optical_capture.argtypes=[ctypes.c_void_p];bridge.phase4_optical_capture.restype=ctypes.c_void_p
    bridge.phase4_optical_size.argtypes=[ctypes.c_void_p];bridge.phase4_optical_size.restype=ctypes.c_size_t
    bridge.phase4_optical_copy.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t];bridge.phase4_optical_copy.restype=ctypes.c_bool
    bridge.phase4_optical_free.argtypes=[ctypes.c_void_p]
    raw=OUT/'cross-binary-arrays';raw.mkdir(exist_ok=True)
    result={'phase':'4S','kind':'cross_binary_bitwise','library':args.library,'metadata':metadata,'rows':[]}
    for case in ('cesa-i-private-restored','ssc-mspt-8790-optical-reference'):
        for sid,grid,point,context in c.contexts(cp,case,plan,True):
            try:
                expected_state=None
                with patch.dict(os.environ,{**c.PLAIN,'SOLARPILOT_INTERCEPT_PATH':'flat'}):
                    for count in (1,12,24):
                        c.simulate(cp,context,count);state=c.state(cp,context)
                        if expected_state is None:expected_state=state
                        else:c.equal(expected_state,state)
                        snapshot=bridge.phase4_optical_capture(context);c.require(bool(snapshot),'Snapshot failed')
                        try:
                            size=bridge.phase4_optical_size(snapshot);optical=np.empty(size,dtype=np.float64)
                            c.require(bridge.phase4_optical_copy(snapshot,optical.ctypes.data,size),'Export failed')
                        finally:bridge.phase4_optical_free(snapshot)
                        current=arrays(state,optical);reference=raw/f'{case}-{sid}.npz'
                        if args.library=='old' and count==1:
                            if reference.exists():raise RuntimeError('Refuse to overwrite old binary oracle')
                            np.savez(reference,**current)
                        with np.load(reference,allow_pickle=False) as saved:
                            c.require(set(saved.files)==set(current),'Cross-binary schema differs')
                            c.require(all(saved[k].dtype==v.dtype and saved[k].shape==v.shape and saved[k].tobytes()==v.tobytes() for k,v in current.items()),'Cross-binary numerical bytes differ')
                        result['rows'].append({'case_id':case,'state_id':sid,'threads':count,'grid':grid,
                                               'optical_values':size,'all215_bitwise':True,'map_details_summary_bitwise':True})
                        print(args.library,case,sid,count,'cross-binary bitwise PASS',flush=True)
            finally:cp.data_free(context)
    result['status']='passed';(OUT/f'{args.library}-equivalence.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
