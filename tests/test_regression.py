"""Each scalar, flux cell and per-heliostat result is checked explicitly."""
import json
import math
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
from cases import ROOT, SIZES, api, configure, collect, layout, run_case

# Strict double precision. Summary is rounded upstream, details are full precision.
RTOL = 1e-9
ATOL = 1e-10


def compare(actual, reference):
    for key in ['case', 'heliostats', 'layout_sha256', 'weather_sha256', 'parameters']:
        if actual[key] != reference[key]:
            raise AssertionError(f'Case metadata differs: {key}')
    for group in ['metrics', 'summary', 'details']:
        if actual[group].keys() != reference[group].keys():
            raise AssertionError(f'Result schema differs: {group}')
        for key, expected in reference[group].items():
            np.testing.assert_allclose(actual[group][key], expected, rtol=RTOL, atol=ATOL,
                                       equal_nan=False, err_msg=f'{group}.{key}')
    np.testing.assert_allclose(actual['flux'], reference['flux'], rtol=RTOL, atol=ATOL, equal_nan=False)


class Regression(unittest.TestCase):
    def test_all_baselines(self):
        for size in SIZES:
            with self.subTest(size=size):
                reference = json.loads((ROOT / 'tests/baselines' / f'{size}.json').read_text())
                actual, _ = run_case(size, repeats=2, measure_generation=False)
                compare(actual, reference)

    def test_dni_scaling_and_sun_restore(self):
        cp = api()
        r = cp.data_create()
        self.assertTrue(r)
        try:
            configure(cp, r, 'small')
            self.assertTrue(cp.assign_layout(r, layout(1000), nthreads=1))
            self.assertTrue(cp.simulate(r, nthreads=1))
            base, _ = collect(cp, r)
            self.assertTrue(cp.data_set_number(r, 'fluxsim.0.flux_dni', 475.))
            self.assertTrue(cp.simulate(r, nthreads=1))
            half, _ = collect(cp, r)
            np.testing.assert_allclose(half['flux'], np.asarray(base['flux']) * .5, rtol=RTOL, atol=ATOL)
            # Summary power is rounded to ~4 significant digits by upstream API.
            self.assertTrue(math.isclose(half['metrics']['receiver_power_kw'], base['metrics']['receiver_power_kw'] * .5, rel_tol=2e-4))
            self.assertTrue(cp.data_set_number(r, 'fluxsim.0.flux_solar_el_in', 25.))
            self.assertTrue(cp.simulate(r, nthreads=1))
            moved, _ = collect(cp, r)
            self.assertFalse(np.allclose(moved['flux'], half['flux'], rtol=.001))
            self.assertTrue(cp.data_set_number(r, 'fluxsim.0.flux_solar_el_in', 55.))
            self.assertTrue(cp.data_set_number(r, 'fluxsim.0.flux_dni', 950.))
            self.assertTrue(cp.simulate(r, nthreads=1))
            restored, _ = collect(cp, r)
            np.testing.assert_allclose(restored['flux'], base['flux'], rtol=RTOL, atol=ATOL)
        finally:
            self.assertTrue(cp.data_free(r))

    def test_comparator_rejects_drift(self):
        reference = json.loads((ROOT / 'tests/baselines/small.json').read_text())
        actual = json.loads(json.dumps(reference))
        actual['flux'][0][0] += .01
        with self.assertRaises(AssertionError):
            compare(actual, reference)


if __name__ == '__main__':
    unittest.main()
