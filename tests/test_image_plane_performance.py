"""Reject contaminated image-plane performance windows without querying hardware."""
import sys
from pathlib import Path
import unittest
import tempfile
import os
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from image_plane_cuda_performance import PipelineWindow,distribution,call


class ImagePlanePerformance(unittest.TestCase):
    def test_deferred_materialization_is_counted_once_with_correct_units(self):
        for resident in [False,True]:
            with self.subTest(resident=resident),tempfile.TemporaryDirectory() as temp:
                def measured(*args):
                    Path(os.environ['SOLARPILOT_IMAGE_TIMING_FILE']).write_text('1,.01,2,.1,3,.5,.001,.02\n')
                    Path(os.environ['SOLARPILOT_IMAGE_MATERIALIZE_FILE']).write_text(
                        '1,1.5,.004,.006,1728,.002,.25,16,1640,3256,0,.004\n' if resident else
                        '1,0,0,0,0,.002,0,0,1640,3256,.0008,.0002\n')
                    Path(os.environ['SOLARPILOT_IMAGE_HANDOFF_FILE']).write_text(
                        '1,1,56,48,.1,4,1,1,1\n' if resident else '1,0,200,48,0,3,1,1,1\n')
                    return {'profile':{}}
                with patch('image_plane_cuda_performance.simulate_once',side_effect=measured):
                    result=call(None,None,Path(temp),True,True,True)
                self.assertAlmostEqual(result['image_total_s'],.026 if resident else .02)
                self.assertAlmostEqual(result['image_d2h_s'],.002 if resident else .0005)
                self.assertAlmostEqual(result['image_writeback_s'],.005 if resident else .001)
                self.assertEqual(result['density_heliostat_h2d_bytes'],56 if resident else 200)
                self.assertAlmostEqual(result['handoff_s'],.0001 if resident else 0.)
    def test_zero_profile_scope_has_defined_statistics_without_division(self):
        result=distribution([0.,0.,0.])
        self.assertEqual(result['median'],0.)
        self.assertEqual(result['stdev'],0.)
        self.assertIsNone(result['coefficient_of_variation'])
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
