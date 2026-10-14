"""Opt-in same-state comparison; production builds have no diagnostic selector."""
import csv
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
from cases import api, configure, layout


class FluxDensity(unittest.TestCase):
    def test_same_state_raw_map(self):
        cp = api()
        context = cp.data_create()
        self.assertTrue(context)
        try:
            configure(cp, context, 'small')
            # A rectangular map also checks packing/scattering without a square stride assumption.
            self.assertTrue(cp.data_set_number(context, 'fluxsim.0.x_res', 20))
            self.assertTrue(cp.data_set_number(context, 'fluxsim.0.y_res', 30))
            self.assertTrue(cp.assign_layout(context, layout(1000), nthreads=1))
            with tempfile.TemporaryDirectory() as directory:
                result = Path(directory) / 'comparison.csv'
                with patch.dict(os.environ, {'SOLARPILOT_FLUX_PATH': 'verify',
                                             'SOLARPILOT_FLUX_COMPARE_FILE': str(result)}):
                    self.assertTrue(cp.simulate(context, nthreads=1))
                if not result.exists():
                    self.skipTest('SOLARPILOT_ENABLE_FLUX_DIAGNOSTICS is OFF')
                rows = list(csv.reader(result.read_text().splitlines()))
                self.assertEqual(len(rows), 1)
                cells, absolute, relative, *_ = map(float, rows[0])
                self.assertEqual(cells, 600)
                self.assertLessEqual(absolute, 1.e-10)
                self.assertLessEqual(relative, 1.e-9)
        finally:
            self.assertTrue(cp.data_free(context))
