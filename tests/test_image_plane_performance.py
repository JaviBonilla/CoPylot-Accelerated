"""Reject contaminated image-plane performance windows without querying hardware."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from image_plane_cuda_performance import PipelineWindow


class ImagePlanePerformance(unittest.TestCase):
    def snapshot(self):
        return {'_pids':[42],'memory.used':'1854','utilization.gpu':'80','temperature.gpu':'45',
            'clocks_throttle_reasons.hw_thermal_slowdown':'Not Active',
            'clocks_throttle_reasons.sw_thermal_slowdown':'Not Active'}
    def test_owned_large_private_state_is_allowed_but_external_work_is_not(self):
        window=PipelineWindow(1);window.allowed={42}
        with patch('image_plane_cuda_performance.gpu_snapshot',return_value=self.snapshot()):
            window.sample()
        for mutation in [{'_pids':[42,99]},{'memory.used':'4200'},{'temperature.gpu':'80'},
                         {'clocks_throttle_reasons.hw_thermal_slowdown':'Active'}]:
            with self.subTest(mutation=mutation),patch('image_plane_cuda_performance.gpu_snapshot',
                    return_value={**self.snapshot(),**mutation}):
                with self.assertRaises(RuntimeError):window.sample()
    def test_initial_window_requires_zero_utilization_and_low_memory(self):
        window=PipelineWindow(1)
        quiet={**self.snapshot(),'_pids':[],'memory.used':'2','utilization.gpu':'0'}
        with patch('image_plane_cuda_performance.gpu_snapshot',return_value=quiet):window.sample(initial=True)
        with patch('image_plane_cuda_performance.gpu_snapshot',return_value={**quiet,'utilization.gpu':'32'}):
            with self.assertRaises(RuntimeError):window.sample(initial=True)
