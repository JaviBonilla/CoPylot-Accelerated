"""Do not weaken full-output CPU/CUDA agreement or direct-CUDA equality."""
from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from gpu_temporal import compare
class GpuTemporalContracts(unittest.TestCase):
    def test_original_tolerance_and_zero_values(self):
        ref={'map':np.array([0.,1.]),'schema':np.array(['map'])}
        compare(ref,{'map':np.array([1e-11,1.+1e-10]),'schema':ref['schema']})
        with self.assertRaises(RuntimeError):compare(ref,{'map':np.array([1e-8,1.]),'schema':ref['schema']})
    def test_direct_cuda_requires_exact_float_bits(self):
        ref={'map':np.array([1.])}
        with self.assertRaises(RuntimeError):compare(ref,{'map':np.nextafter(ref['map'],2.)},bitwise=True)
    def test_full_schema_shape_dtype_and_nonfinite_fail(self):
        ref={'map':np.zeros((2,3)),'keys':np.array(['x'])}
        candidates=[{'map':ref['map']},{'map':ref['map'].T,'keys':ref['keys']},
                    {'map':ref['map'].astype('f4'),'keys':ref['keys']},
                    {'map':np.full((2,3),np.nan),'keys':ref['keys']},
                    {'map':ref['map'],'keys':np.array(['y'])}]
        for candidate in candidates:
            with self.assertRaises(RuntimeError):compare(ref,candidate)
if __name__=='__main__':unittest.main()
