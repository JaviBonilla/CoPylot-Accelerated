"""Image-plane snapshot statistics must cover every heliostat and family."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from image_plane import errors,FAMILIES,statistics_s

class ImagePlaneHarness(unittest.TestCase):
    def test_family_metrics_find_last_heliostat(self):
        expected=np.ones((3,215)); actual=expected.copy()
        actual[2,198]+=5.e-11
        report=errors(expected,actual)
        self.assertEqual(set(report),set(FAMILIES))
        self.assertEqual(report['coefficients']['heliostat_index'],2)
        self.assertFalse(report['coefficients']['bitwise'])
        self.assertGreater(report['coefficients']['rms'],0)
        self.assertTrue(report['sun']['bitwise'])
        with self.assertRaises(AssertionError): errors(expected,actual+1.e-4)

    def test_statistics_keep_outliers(self):
        report=statistics_s([1.,2.,3.,100.])
        self.assertEqual(report['samples_s'],[1.,2.,3.,100.])
        self.assertEqual(report['median_s'],2.5)
        self.assertEqual(report['max_s'],100.)
