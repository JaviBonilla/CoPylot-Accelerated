"""Verify that the diagnostic stack-phase trampoline preserves the C API ABI."""
import ctypes
from pathlib import Path
import unittest

class FloatingPointProbe(unittest.TestCase):
    def test_arguments_stack_phases_and_floating_controls(self):
        path=Path('artifacts/phase4r/libcpu_fp_probe.so').resolve()
        if not path.exists():self.skipTest('Optional diagnostic probe is not built')
        probe=ctypes.CDLL(str(path))
        if not hasattr(probe,'phase4r_call_with_stack_phase'):self.skipTest('Older read-only probe')
        probe.phase4r_mxcsr.restype=ctypes.c_uint32;probe.phase4r_x87_control.restype=ctypes.c_uint16
        probe.phase4r_last_callsite_mod64.restype=ctypes.c_uint32
        probe.phase4r_call_with_stack_phase.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_uint]
        probe.phase4r_call_with_stack_phase.restype=ctypes.c_bool
        signature=ctypes.CFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_int,ctypes.c_bool)
        seen=[]
        @signature
        def callback(context,threads,aim):seen.append((context,threads,aim));return True
        controls=(probe.phase4r_mxcsr() & 0xffc0,probe.phase4r_x87_control())
        phases=[]
        for phase in (0,16,32,48):
            self.assertTrue(probe.phase4r_call_with_stack_phase(callback,123,24,phase))
            phases.append(probe.phase4r_last_callsite_mod64())
        self.assertEqual(set(phases),{0,16,32,48})
        self.assertEqual(seen,[(123,24,True)]*4)
        self.assertEqual(controls,(probe.phase4r_mxcsr() & 0xffc0,probe.phase4r_x87_control()))
        self.assertFalse(probe.phase4r_call_with_stack_phase(callback,123,24,1))

if __name__=='__main__':unittest.main()
