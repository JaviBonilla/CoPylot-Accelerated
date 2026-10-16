#!/usr/bin/env python3
"""Publish observed old/new pointer ownership and frozen-ELF cache-line evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def layout_records(data):
    result=[]
    for record in data['records']:
        parameters=record['parameters_address'];worker=record['worker_parameters_address']
        scratch=record['sincos_output_addresses'];line=parameters//64
        result.append({'c_api_callsite_mod64':record['c_api_callsite_mod64'],
                       'flat_frame_rsp_mod64':record['flat_frame_rsp']%64,
                       'parameters_address':hex(parameters),'worker_parameters_address':hex(worker),
                       'parameters_line_base':hex(line*64),'parameters_offset_in_line':parameters%64,
                       'sincos_output_addresses':[hex(v) for v in scratch],
                       'sincos_offsets_in_line':[v%64 for v in scratch],
                       'sincos_offsets_from_parameters':[v-parameters for v in scratch],
                       'sincos_line_indices_from_parameters':[v//64-line for v in scratch],
                       'worker_reads_same_object':parameters==worker,
                       'caller_scratch_shares_parameters_line':any(v//64==line for v in scratch)})
    return result


def elf_sections(path):
    data=path.read_bytes()
    if data[:6]!=b'\x7fELF\x02\x01':raise ValueError('Require ELF64 little-endian evidence')
    header=struct.unpack_from('<16sHHIQQQIHHHHHH',data)
    offset,width,count,names=header[6],header[11],header[12],header[13]
    if width!=64 or count==0:raise ValueError('Unsupported ELF section table')
    raw=[struct.unpack_from('<IIQQQQIIQQ',data,offset+i*width) for i in range(count)]
    names_section=raw[names];strings=data[names_section[4]:names_section[4]+names_section[5]];result={}
    for section in raw:
        name=strings[section[0]:].split(b'\0',1)[0].decode()
        payload=data[section[4]:section[4]+section[5]] if section[1]!=8 else bytes(section[5])
        result[name]={'bytes':section[5],'flags':section[2],'vma':section[3],
                      'sha256':hashlib.sha256(payload).hexdigest()}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input-dir',type=Path,required=True)
    parser.add_argument('--old-library',type=Path,required=True);parser.add_argument('--new-library',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();rows={}
    for name,library in [('old',args.old_library),('new',args.new_library)]:
        path=args.input_dir/(name+'-layout-addresses.json');raw=json.loads(path.read_text())
        if raw['library_sha256']!=sha(library):raise ValueError('Pointer evidence uses another binary')
        records=layout_records(raw)
        if {r['c_api_callsite_mod64'] for r in records}!={0,16,32,48}:raise ValueError('Missing actual callsite phase')
        if not all(r['worker_reads_same_object'] for r in records):raise ValueError('Worker pointer was not observed')
        if any(r['caller_scratch_shares_parameters_line']!=(name=='old' and r['c_api_callsite_mod64']==48) for r in records):
            raise ValueError('Observed layout does not match the mechanism')
        rows[name]={'library_sha256':sha(library),'raw_debugger_evidence_sha256':sha(path),'records':records}
    old_sections=elf_sections(args.old_library);new_sections=elf_sections(args.new_library)
    old_fatbin=old_sections['.nv_fatbin'];new_fatbin=new_sections['.nv_fatbin']
    if old_fatbin['sha256']!=new_fatbin['sha256']:raise ValueError('CUDA machine-code fatbin changed')
    assembly=subprocess.check_output(['objdump','-d','-C','--no-show-raw-insn',str(args.new_library)],text=True)
    selected={}
    for address in ('125039','12616f','1264ad','126910','126917','12692c','11849b','118521','1185d1'):
        line=next(l for l in assembly.splitlines() if l.lstrip().startswith(address+':'))
        selected['0x'+address]=line.split(':',1)[1].strip()
    ordinary=[]
    for path in sorted(args.input_dir.glob('ordinary-*-addresses.json')):
        data=json.loads(path.read_text())
        if data['library_sha256']!=sha(args.new_library):raise ValueError('Ordinary probe uses another library')
        ordinary.append({'id':path.stem,'records':layout_records(data),'raw_trace_sha256':sha(path)})
    result={'phase':'4S','cache_line_bytes':64,'measurement_kind':'Untimed existing-gdb register reads; target processes have exited',
            'forced_callsite_observations':rows,'ordinary_callsite_observations':ordinary,
            'new_ownership':{'object':'SharedParameters::value','object_size_bytes':64,'object_alignment_bytes':64,
                             'lifetime':'Const local holder in multicore branch; alive through all worker joins',
                             'serial_branch_unchanged':True,'public_api_stack_contract_changed':False},
            'corrected_instruction_evidence':selected,
            'cuda_fatbin':{'bytes':new_fatbin['bytes'],'sha256':new_fatbin['sha256'],'identical_to_phase4r':True},
            'interpretation':'Causal old stack-position intervention, actual shared read/write line, and an ownership-layout change that removes that line interaction. No direct HITM/coherence-event measurement is claimed.'}
    args.output.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
