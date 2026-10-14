"""Preserve public result forms and release native arrays on conversion failure."""
import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
from cases import api, configure, layout


class ResultExports(unittest.TestCase):
    def test_legacy_forms_and_exception_ownership(self):
        cp = api()
        r = cp.data_create()
        self.assertTrue(r)
        original_free = cp._free_result_array
        freed = []
        def record_free(ptr):
            original_free(ptr)
            freed.append(True)
        cp._free_result_array = record_free
        try:
            configure(cp, r, 'small')
            self.assertTrue(cp.assign_layout(r, layout(1000), nthreads=1))
            self.assertTrue(cp.simulate(r, nthreads=1))
            for method in [cp.get_layout_info, cp.detail_results]:
                df = method(r)  # Public default remains pandas.DataFrame.
                matrix, columns = method(r, restype='matrix')
                dictionary = method(r, restype='dictionary')
                self.assertEqual(len(df), 1000)
                self.assertEqual(list(df.columns), columns)
                self.assertEqual(list(dictionary), columns)
                np.testing.assert_array_equal(df.to_numpy(), matrix)
                np.testing.assert_array_equal(np.asarray([dictionary[k] for k in columns]).T, matrix)
            self.assertEqual(np.asarray(cp.get_fluxmap(r)).shape, (25, 25))
            self.assertEqual(len(freed), 7)
            with patch('copylot.pd.DataFrame', side_effect=RuntimeError('conversion failure')):
                with self.assertRaisesRegex(RuntimeError, 'conversion failure'):
                    cp.get_layout_info(r)
                # Upstream detail_results catches conversion exceptions and returns None.
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertIsNone(cp.detail_results(r))
            self.assertEqual(len(freed), 9, 'Failed conversion must also release its C array')
        finally:
            self.assertTrue(cp.data_free(r))


if __name__ == '__main__':
    unittest.main()
