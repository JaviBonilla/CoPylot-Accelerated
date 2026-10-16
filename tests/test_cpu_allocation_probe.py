"""Exercise the optional diagnostic preload in an isolated child process."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT=r'''
import ctypes
p=ctypes.CDLL(None)
p.malloc.argtypes=[ctypes.c_size_t];p.malloc.restype=ctypes.c_void_p
p.free.argtypes=[ctypes.c_void_p]
p.phase4r_allocation_value.argtypes=[ctypes.c_uint,ctypes.c_uint]
p.phase4r_allocation_value.restype=ctypes.c_uint64
p.phase4r_allocation_count.restype=ctypes.c_uint
before=p.phase4r_allocation_count();pointer=p.malloc(60000)
assert pointer
ctypes.c_ubyte.from_address(pointer).value=37
ctypes.c_ubyte.from_address(pointer+59999).value=19
assert p.phase4r_allocation_count()==before+1
assert p.phase4r_allocation_value(before,0)==60000
assert p.phase4r_allocation_value(before,1)==pointer
assert ctypes.c_ubyte.from_address(pointer).value==37
assert ctypes.c_ubyte.from_address(pointer+59999).value==19
p.free(pointer)
before=p.phase4r_allocation_count();pointer=p.malloc(123);p.free(pointer)
assert p.phase4r_allocation_count()==before
'''

class AllocationProbe(unittest.TestCase):
    def test_preload_preserves_pointer_and_writable_allocation(self):
        path=Path(os.environ.get('COPILOT_ALLOCATION_PROBE','artifacts/phase4r/libcpu_allocation_probe.so')).resolve()
        if not path.is_file():self.skipTest('Optional diagnostic preload is not built')
        result=subprocess.run([sys.executable,'-c',SCRIPT],env={**os.environ,'LD_PRELOAD':str(path)},text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
