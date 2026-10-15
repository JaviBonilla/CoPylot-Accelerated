#!/usr/bin/env python3
"""Query the actual sm_89 density cubin using the installed CUDA Driver API."""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def command(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    library=args.library.resolve()
    header=Path('/usr/local/cuda/include/cuda.h').read_text()
    def enum(name):
        match=re.search(r'\b'+name+r'\s*=\s*(\d+)',header)
        if not match:raise RuntimeError('Installed CUDA header lacks '+name)
        return int(match[1])
    driver=C.CDLL('libcuda.so.1')
    def call(name, types, *values):
        function=getattr(driver,name);function.argtypes=types;function.restype=C.c_int
        status=function(*values)
        if status:raise RuntimeError(f'{name} failed with CUDA status {status}')
    ip=C.POINTER(C.c_int);vp=C.POINTER(C.c_void_p)
    call('cuInit',[C.c_uint],0)
    device=C.c_int();call('cuDeviceGet',[ip,C.c_int],C.byref(device),0)
    context=C.c_void_p();call('cuCtxCreate_v2',[vp,C.c_uint,C.c_int],C.byref(context),0,device)
    try:
        with tempfile.TemporaryDirectory() as directory:
            command('cuobjdump','--extract-elf','all',str(library),cwd=directory)
            chosen=None
            for filename in Path(directory).glob('*.cubin'):
                dump=command('cuobjdump','--dump-resource-usage',str(filename))
                match=re.search(r'Function\s*:?\s*(\S*flux_density_kernel[^:\s]*)',dump)
                if match:
                    chosen=(filename,dump,match[1]);break
            if chosen is None:raise RuntimeError('No density kernel found in extracted cubins')
            filename,dump,name=chosen
            module=C.c_void_p();call('cuModuleLoad',[vp,C.c_char_p],C.byref(module),str(filename).encode())
            try:
                kernel=C.c_void_p();call('cuModuleGetFunction',[vp,C.c_void_p,C.c_char_p],C.byref(kernel),module,name.encode())
                attrs={}
                for label,suffix in [('registers_per_thread','NUM_REGS'),('static_shared_bytes','SHARED_SIZE_BYTES'),
                                     ('local_bytes_per_thread','LOCAL_SIZE_BYTES'),('constant_bytes','CONST_SIZE_BYTES'),
                                     ('max_threads_per_block','MAX_THREADS_PER_BLOCK'),('ptx_version','PTX_VERSION'),('binary_version','BINARY_VERSION')]:
                    value=C.c_int();call('cuFuncGetAttribute',[ip,C.c_int,C.c_void_p],C.byref(value),enum('CU_FUNC_ATTRIBUTE_'+suffix),kernel);attrs[label]=value.value
                hardware={}
                for label,suffix in [('max_threads_per_sm','MAX_THREADS_PER_MULTIPROCESSOR'),('sm_count','MULTIPROCESSOR_COUNT'),
                                     ('warp_size','WARP_SIZE'),('registers_per_sm','MAX_REGISTERS_PER_MULTIPROCESSOR'),('max_blocks_per_sm','MAX_BLOCKS_PER_MULTIPROCESSOR')]:
                    value=C.c_int();call('cuDeviceGetAttribute',[ip,C.c_int,C.c_int],C.byref(value),enum('CU_DEVICE_ATTRIBUTE_'+suffix),device);hardware[label]=value.value
                blocks=[]
                for block in (64,128,256,512):
                    active=C.c_int();call('cuOccupancyMaxActiveBlocksPerMultiprocessor',[ip,C.c_void_p,C.c_int,C.c_size_t],C.byref(active),kernel,block,block*8)
                    blocks.append(dict(block_size=block,dynamic_shared_bytes=8*block,active_blocks_per_sm=active.value,
                                       active_warps_per_sm=active.value*block//hardware['warp_size'],theoretical_occupancy=active.value*block/hardware['max_threads_per_sm']))
                output=dict(library_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),kernel_symbol=name,
                            attributes=attrs,hardware=hardware,block_sizes=blocks,cuobjdump_resource_usage=dump.replace(str(filename), '<density-cubin>'),
                            definition='Theoretical resource occupancy from the actual compiled kernel; not measured achieved occupancy.',
                            occupancy_api='cuOccupancyMaxActiveBlocksPerMultiprocessor',ncu_available=bool(shutil.which('ncu')))
            finally:call('cuModuleUnload',[C.c_void_p],module)
    finally:call('cuCtxDestroy_v2',[C.c_void_p],context)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({key:output[key] for key in ('attributes','hardware','block_sizes')},indent=2))


if __name__=='__main__':main()
