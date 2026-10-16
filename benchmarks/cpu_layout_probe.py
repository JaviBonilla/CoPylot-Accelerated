#!/usr/bin/env python3
"""Untimed debugger target: forced or ordinary calls on one CONTROL state."""
import argparse
import ctypes
import json
import os
from pathlib import Path
from unittest.mock import patch
import cpu_multicore as c


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--case',choices=['cesa','commercial'],default='cesa')
    parser.add_argument('--ordinary',action='store_true',help='Use normal ctypes calls without loading the stack probe')
    args=parser.parse_args()
    for key in list(os.environ):
        if key.startswith('SOLARPILOT_'):os.environ.pop(key)
    c.topology_cache=c.topology();os.sched_setaffinity(0,set(c.topology_cache['affinity_sets']['24']))
    plan=json.loads(args.plan.read_text())
    # Host debugger uses the same ignored inputs as the /workspace container mount.
    plan['project']=str(c.ROOT/Path(plan['project']).relative_to('/workspace'))
    cp=c.api();case='cesa-i-private-restored' if args.case=='cesa' else 'ssc-mspt-8790-optical-reference'
    generator=c.contexts(cp,case,plan,False);sid,grid,point,context=next(generator)
    if not args.ordinary:
        probe=ctypes.CDLL(str(c.ROOT/'artifacts/phase4r/libcpu_fp_probe.so'))
        probe.phase4r_call_with_stack_phase.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_uint]
        probe.phase4r_call_with_stack_phase.restype=ctypes.c_bool;probe.phase4r_last_callsite_mod64.restype=ctypes.c_uint32
        signature=ctypes.CFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_int,ctypes.c_bool)
        noop=signature(lambda context,threads,aim:True);function=ctypes.cast(cp.pdll.sp_simulate,ctypes.c_void_p)
    try:
        expected=None
        with patch.dict(os.environ,{**c.PLAIN,'SOLARPILOT_INTERCEPT_PATH':'flat'}):
            for phase in (0,16,32,48):
                if args.ordinary:c.simulate(cp,context,24)
                else:
                    c.require(probe.phase4r_call_with_stack_phase(noop,None,24,0),'Calibration failed')
                    padding=(int(probe.phase4r_last_callsite_mod64())-phase)%64
                    c.require(probe.phase4r_call_with_stack_phase(function,context,24,padding),'Simulation failed')
                    c.require(probe.phase4r_last_callsite_mod64()==phase,'Actual pre-call phase differs')
                actual=c.state(cp,context)
                if expected is None:expected=actual
                else:c.equal(expected,actual)
        print('Untimed '+('ordinary API' if args.ordinary else 'actual four-phase')+' layout probe: bitwise PASS',flush=True)
    finally:cp.data_free(context)


if __name__=='__main__':main()
