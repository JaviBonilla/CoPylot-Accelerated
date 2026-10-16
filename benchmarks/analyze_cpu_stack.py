#!/usr/bin/env python3
"""Extract the stack-placement evidence from the frozen Phase 4 ELF binary."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from cpu_repeatability import EXPECTED_LIBRARY


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if hashlib.sha256(args.library.read_bytes()).hexdigest()!=EXPECTED_LIBRARY:
        raise RuntimeError('This analysis applies only to the frozen numerical binary')
    assembly=subprocess.check_output(['objdump','-d','-C','--no-show-raw-insn',str(args.library)],text=True)
    instructions={}
    for line in assembly.splitlines():
        try:address=int(line.split(':',1)[0].strip(),16)
        except ValueError:continue
        instructions[hex(address)]=line.split(':',1)[1].strip()
    # Frame changes include the return address pushed on entry to each function.
    frames=[('sp_simulate','0xa4250',48,0x238,'0xa435a'),
            ('simulate_cpu','0xa3bf0',48,0x3d8,'0xa41ed'),
            ('HermiteFluxSimulationHandler','0x144040',48,0x498,'0x1440a7'),
            ('HermiteFluxSimulation','0x172050',32,0x38,'0x172092'),
            ('AnalyticalFluxSimulation','0x169830',48,0x78,'0x1698ea'),
            ('fluxDensity','0x1278b0',48,0x2f8,'0x127a83'),
            ('fluxDensityFlat','0x125030',48,0x388,None)]
    rows=[]
    for name,start,pushes,local,call in frames:
        rows.append({'function':name,'symbol_offset':start,'callee_save_push_bytes':pushes,
                     'local_frame_bytes':local,'including_return_address_bytes':8+pushes+local,
                     'next_call_offset':call,'next_call_instruction':instructions[call] if call else None})
    selected=['0x125041','0x12515d','0x126459','0x1268a7','0x1268af','0x1268c1',
              '0x1268fa','0x11849b','0x118521','0x1185d1']
    delta=sum(row['including_return_address_bytes'] for row in rows)%64
    placements=[]
    for phase in (0,16,32,48):
        base=(phase-delta)%64
        scratch=[base+0xe0,base+0xe8];parameters=[base+0x110,base+0x118]
        shared=bool({v//64 for v in scratch}&{v//64 for v in parameters})
        placements.append({'c_api_callsite_rsp_mod64':phase,'flat_frame_rsp_mod64':base,
                           'sincos_scratch_cacheline_indices':[v//64 for v in scratch],
                           'shared_parameters_cacheline_indices':[v//64 for v in parameters],
                           'overlapping_cacheline':shared})
    result={'phase':'4R','library_sha256':EXPECTED_LIBRARY,'cacheline_bytes':64,
            'frame_chain':rows,'total_stack_delta_mod64':delta,
            'instruction_evidence':{k:instructions[k] for k in selected},'placements':placements,
            'measured_causal_variable':'C API calling-stack position modulo 64 bytes; see K1-stack and K2-stack',
            'mechanism_assessment':'Assembly predicts false sharing between immutable parameters read by workers and mutable sincos outputs written by the caller, exactly at measured slow callsite phase 48. This is static and intervention evidence, not a direct HITM/coherence-event measurement.',
            'scope':'Frozen compiler/binary only; no numerical-core modification or production API repair'}
    args.output.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
