from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np


spec = importlib.util.spec_from_file_location(
    "package_example", Path(__file__).resolve().parents[1] / "packaging/example.py")
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


class CpuDiagnostics(unittest.TestCase):
    def test_logical_indices_and_one_ulp_difference(self):
        reference = np.array([[1.0, 2.0], [3.0, -4.0]], dtype=">f8")
        actual = np.array(reference, dtype="<f8", order="F")
        self.assertTrue(example.array_comparison(actual, reference)["bitwise"])
        actual[1, 1] = np.nextafter(-4.0, -np.inf)
        result = example.array_comparison(actual, reference)
        self.assertFalse(result["bitwise"])
        self.assertEqual(result["differing_elements"], 1)
        self.assertEqual(result["differing_percent"], 25.0)
        self.assertEqual(result["max_abs_difference"], abs(actual[1, 1] + 4.0))
        self.assertEqual(result["max_relative_difference"], abs(actual[1, 1] + 4.0) / 4.0)
        self.assertEqual(result["max_ulp_difference"], 1)
        self.assertEqual(result["samples"][0]["index"], [1, 1])
        self.assertEqual(float(result["samples"][0]["actual"]), actual[1, 1])

    def test_signed_zero_and_nonfinite_values_fail_strictly(self):
        zero = example.array_comparison([-0.0], [0.0])
        self.assertFalse(zero["bitwise"])
        self.assertTrue(zero["signed_zero_only"])
        self.assertEqual(zero["max_ulp_difference"], 0)
        values = [np.nan, np.inf, -np.inf]
        nonfinite = example.array_comparison(values, values)
        self.assertFalse(nonfinite["bitwise"])
        self.assertEqual(nonfinite["differing_elements"], 0)
        self.assertEqual(nonfinite["nonfinite"]["actual"], {"nan": 1, "pos_inf": 1, "neg_inf": 1})
        self.assertIsNone(nonfinite["max_ulp_difference"])
        json.dumps(nonfinite, allow_nan=False)

    def test_shape_mismatch_is_rejected(self):
        result = example.array_comparison([[1.0, 2.0]], [1.0, 2.0])
        self.assertFalse(result["bitwise"])
        self.assertEqual(result["actual_shape"], [1, 2])
        self.assertEqual(result["reference_shape"], [2])

    def test_failure_reports_every_pair_and_summary_fields(self):
        reference = np.ones((25, 25))
        original = reference.copy()
        original[4, 9] = np.nextafter(1.0, 2.0)
        optimized = (reference, {"receiver": {"power": 1.0}}, {"id": [1.0]})
        outputs = [(original, {"receiver": {"power": 2.0}}, {"id": [1.0]}), optimized, optimized]
        log = io.StringIO()
        with patch.object(example, "simulate", side_effect=outputs) as simulate, redirect_stdout(log):
            with self.assertRaisesRegex(RuntimeError, "failed bitwise"):
                example.compare_cpu_modes(Path("synthetic.csv"))
        self.assertEqual([call.args[1] for call in simulate.call_args_list], list(example.CPU_MODES))
        metadata, *pairs = [json.loads(line) for line in log.getvalue().splitlines()]
        self.assertEqual(metadata["invalid_flux_modes"], [])
        self.assertEqual([(p["actual_mode"], p["reference_mode"], p["cpu_outputs_bitwise"]) for p in pairs],
                         [("original", "refactored", False), ("original", "multicore", False),
                          ("refactored", "multicore", True)])
        self.assertEqual(pairs[0]["flux_kw_m2"]["samples"][0]["index"], [4, 9])
        self.assertEqual(pairs[0]["summary_differences"]["receiver"]["power"]["max_abs_difference"], 1.0)
