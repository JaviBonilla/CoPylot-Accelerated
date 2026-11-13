from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
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
        self.assertEqual(zero["signed_zero_mismatches"], 1)
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
            with self.assertRaisesRegex(RuntimeError, "failed numerical validation"):
                example.compare_cpu_modes(Path("synthetic.csv"), apple_silicon=False)
        self.assertEqual([call.args[1] for call in simulate.call_args_list], list(example.CPU_MODES))
        metadata, *pairs = [json.loads(line) for line in log.getvalue().splitlines()]
        self.assertEqual(metadata["invalid_flux_modes"], [])
        self.assertEqual([(p["actual_mode"], p["reference_mode"], p["cpu_outputs_bitwise"]) for p in pairs],
                         [("original", "refactored", False), ("original", "multicore", False),
                          ("refactored", "multicore", True)])
        self.assertEqual(pairs[0]["flux_kw_m2"]["samples"][0]["index"], [4, 9])
        self.assertEqual(pairs[0]["summary_differences"]["receiver"]["power"]["max_abs_difference"], 1.0)


class CpuAcceptance(unittest.TestCase):
    @staticmethod
    def state(flux):
        return flux, {"receiver": {"power": 1.0}}, {"id": [1.0], "power": [1.0]}

    def test_package_and_host_must_both_be_native_macos_arm64(self):
        for os_name, arch, system, machine, cuda, expected in (
            ("linux", "x86_64", "Linux", "x86_64", "", False),
            ("linux", "x86_64", "Linux", "x86_64", "89", False),
            ("linux", "arm64", "Linux", "aarch64", "", False),
            ("windows", "x86_64", "Windows", "AMD64", "", False),
            ("macos", "x86_64", "Darwin", "x86_64", "", False),
            ("macos", "x86_64", "Darwin", "arm64", "", False),
            ("macos", "arm64", "Darwin", "x86_64", "", False),
            ("macos", "arm64", "Linux", "aarch64", "", False),
            ("macos", "arm64", "Darwin", "arm64", "", True),
        ):
            with (self.subTest(os_name=os_name, arch=arch, host=(system, machine), cuda=cuda),
                  patch.object(example.platform, "system", return_value=system),
                  patch.object(example.platform, "machine", return_value=machine)):
                info = {"os": os_name, "architecture": arch, "cuda_architecture": cuda}
                apple_silicon = example.is_apple_silicon_package(info)
                self.assertEqual(apple_silicon, expected)
                ref = np.ones((25, 25))
                actual = np.nextafter(ref, 2.0)
                for first, second in example.combinations(example.CPU_MODES, 2):
                    result = example.cpu_comparison(first, second, self.state(actual), self.state(ref),
                                                    apple_silicon=apple_silicon)
                    self.assertFalse(result["cpu_outputs_bitwise"])
                    self.assertEqual(result["validation_passed"], expected and first == "original")

    def test_apple_silicon_rounding_at_observed_scale(self):
        # Synthetic representative values at the observed count and error scale.
        max_absolute = 1.4210854715202004e-14
        max_relative = 4.131375826319544e-16
        ref = np.full((25, 25), max_absolute / max_relative)
        ref.flat[87] = 30.0
        actual = ref.copy()
        actual.flat[:88] = np.nextafter(np.nextafter(ref.flat[:88], np.inf), np.inf)
        actual.flat[87] = np.nextafter(actual.flat[87], np.inf)
        outputs = [self.state(actual), self.state(ref), self.state(ref.copy())]
        log = io.StringIO()
        with patch.object(example, "simulate", side_effect=outputs), redirect_stdout(log):
            example.compare_cpu_modes(Path("synthetic.csv"), apple_silicon=True)
        _, *pairs = [json.loads(line) for line in log.getvalue().splitlines()]
        self.assertEqual([p["validation_passed"] for p in pairs], [True, True, True])
        self.assertEqual([p["cpu_outputs_bitwise"] for p in pairs], [False, False, True])
        self.assertEqual([p["flux_policy"] for p in pairs], ["tolerance", "tolerance", "bitwise"])
        flux = pairs[0]["flux_kw_m2"]
        self.assertEqual(flux["differing_elements"], 88)
        self.assertEqual(flux["differing_percent"], 14.08)
        self.assertEqual(flux["max_abs_difference"], max_absolute)
        self.assertEqual(flux["max_relative_difference"], max_relative)
        self.assertEqual(flux["max_ulp_difference"], 3)
        self.assertEqual(flux["samples"][0]["index"], [0, 0])

    def test_tolerance_is_elementwise_and_includes_the_absolute_boundary(self):
        rtol, atol = example.MACOS_ARM64_FLUX_TOLERANCE
        ref = np.geomspace(1e-15, 1e5, 1200).reshape(30, 40)
        ref[0, 0] = 0.0
        actual = np.nextafter(ref, np.inf)
        actual[0, 0] = atol
        compare = example.array_comparison
        self.assertTrue(compare(actual, ref, tolerance=(rtol, atol))["within_tolerance"])
        actual[0, 0] = np.nextafter(atol, np.inf)
        self.assertFalse(compare(actual, ref, tolerance=(rtol, atol))["within_tolerance"])
        actual[0, 0] = atol
        actual[-1, -1] += 2 * (atol + rtol * ref[-1, -1])
        self.assertFalse(compare(actual, ref, tolerance=(rtol, atol))["within_tolerance"])

    def test_apple_silicon_still_rejects_invalid_flux_and_mixed_signed_zeros(self):
        ref = np.ones((25, 25))
        ref[0, 0] = 0.0
        for value in (np.nan, np.inf, -np.inf, -1e-16):
            with self.subTest(value=value):
                actual = np.nextafter(ref, np.inf)
                actual[0, 0] = value
                result = example.cpu_comparison("original", "refactored", self.state(actual),
                                                self.state(ref), apple_silicon=True)
                self.assertFalse(result["validation_passed"])
        actual = np.nextafter(ref, np.inf)
        actual[0, 0] = -0.0
        result = example.cpu_comparison("original", "refactored", self.state(actual),
                                        self.state(ref), apple_silicon=True)
        self.assertFalse(result["validation_passed"])
        flux = result["flux_kw_m2"]
        self.assertFalse(flux["signed_zero_only"])
        self.assertEqual(flux["signed_zero_mismatches"], 1)
        self.assertFalse(flux["within_tolerance"])
        for actual in (ref[:, :-1], np.zeros_like(ref)):
            result = example.cpu_comparison("original", "refactored", self.state(actual),
                                            self.state(ref), apple_silicon=True)
            self.assertFalse(result["validation_passed"])

    def test_apple_silicon_summaries_and_details_are_bitwise(self):
        ref = self.state(np.ones((25, 25)))
        for field in ("summary_differences", "detail_differences"):
            with self.subTest(field=field):
                actual = self.state(np.nextafter(ref[0], 2.0))
                if field == "summary_differences":
                    actual[1]["receiver"]["power"] = np.nextafter(1.0, 2.0)
                else:
                    actual[2]["power"][0] = np.nextafter(1.0, 2.0)
                result = example.cpu_comparison("original", "refactored", actual, ref, apple_silicon=True)
                self.assertTrue(result["flux_kw_m2"]["within_tolerance"])
                self.assertFalse(result["validation_passed"])
                self.assertTrue(result[field])

    def test_single_mode_cli_applies_policy_and_compares_two_refactored_runs(self):
        info = {"os": "macos", "architecture": "arm64", "diagnostics": True}
        loader = SimpleNamespace(build_info=lambda: info)
        ref = self.state(np.ones((25, 25)))
        actual = self.state(np.nextafter(ref[0], 2.0))
        for mode in ("original", "refactored"):
            log = io.StringIO()
            with (self.subTest(mode=mode), patch.dict(example.sys.modules, {"copylot_accelerated": loader}),
                  patch.object(example.sys, "argv", ["example.py", "--mode", mode, "--compare"]),
                  patch.object(example.sys, "path", example.sys.path.copy()),
                  patch.object(example, "is_apple_silicon_package", return_value=True),
                  patch.object(example, "synthetic_weather"),
                  patch.object(example, "simulate", side_effect=[actual, ref]), redirect_stdout(log)):
                if mode == "original":
                    example.main()
                    result = json.loads(log.getvalue())
                    self.assertTrue(result["validation_passed"])
                    self.assertFalse(result["cpu_outputs_bitwise"])
                else:
                    with self.assertRaisesRegex(RuntimeError, "failed numerical validation"):
                        example.main()
