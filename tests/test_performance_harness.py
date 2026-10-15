"""Scientific timing summaries and GPU-window rejection rules."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
from cuda_flux_performance import distribution, check_gpu, public_snapshot, GPU_FIELDS


class PerformanceHarness(unittest.TestCase):
    def snapshot(self):
        result = {key: 'Not Active' for key in GPU_FIELDS}
        result.update({'_pids': [], 'memory.used': '2', 'utilization.gpu': '0', 'temperature.gpu': '38'})
        return result

    def test_statistics_use_every_sample(self):
        summary = distribution([1., 2., 3., 4., 100.])
        self.assertEqual(summary['median'], 3.)
        self.assertEqual(summary['minimum'], 1.)
        self.assertEqual(summary['maximum'], 100.)
        self.assertEqual(summary['mean'], 22.)
        self.assertGreater(summary['coefficient_of_variation'], 1.)

    def test_window_rejects_external_load_and_thermal_slowdown(self):
        quiet = self.snapshot()
        check_gpu(quiet, initial=True)
        for changed in ({'_pids':[42]}, {'memory.used':'42648'}, {'utilization.gpu':'30'},
                        {'temperature.gpu':'90'}, {GPU_FIELDS[-1]:'Active'}):
            with self.subTest(changed=changed), self.assertRaises(RuntimeError):
                check_gpu({**quiet, **changed}, initial=True)
        own = {**quiet, '_pids':[42], 'memory.used':'350', 'utilization.gpu':'100'}
        check_gpu(own, allowed_pids={42})
        with self.assertRaises(RuntimeError):
            check_gpu({**own, '_pids':[42,43]}, allowed_pids={42})
        self.assertNotIn('_pids', public_snapshot(own))
        self.assertEqual(public_snapshot(own)['compute_process_count'], 1)
