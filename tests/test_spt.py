"""Temporary, synthetic projects exercise the existing C SPT serialization."""
import ctypes
import os
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
from cases import api, configure, collect


def exported_values(filename):
    """Inspect semantic variable values in C-generated XML, without rewriting it."""
    return {'.'.join(node.findtext(key) for key in ('component', 'instance', 'varname')):
            node.findtext('value') or '' for node in ET.parse(filename).getroot().findall('variable')}


class SptFiles(unittest.TestCase):
    def setUp(self):
        self.cp = api()
        self.contexts = []
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)

    def tearDown(self):
        for context in reversed(self.contexts):
            self.assertTrue(self.cp.data_free(context))

    def context(self):
        context = self.cp.data_create()
        self.assertTrue(context)
        self.contexts.append(context)
        return context

    def test_variables_templates_receivers_and_embedded_weather(self):
        cp, source, target = self.cp, self.context(), self.context()
        configure(cp, source, 'small')
        self.assertEqual(cp.add_receiver(source, 'Secondary receiver'), 1)
        self.assertEqual(cp.add_heliostat_template(source, 'Secondary template'), 1)
        numbers = {'solarfield.0.tht': 123.5, 'receiver.0.rec_height': 14.25,
                   'receiver.1.rec_height': 11.5, 'receiver.1.is_enabled': 0,
                   'heliostat.1.width': 9.25, 'fluxsim.0.x_res': 12,
                   'fluxsim.0.y_res': 18, 'fluxsim.0.flux_dni': 850.}
        for key, value in numbers.items():
            self.assertTrue(cp.data_set_number(source, key, value))
        self.assertTrue(cp.data_set_string(source, 'solarfield.0.temp_which',
                                               cp.data_get_string(source, 'heliostat.0.helio_name')))
        positions = [[i % 2, 200. + 30. * i, 300., 0.] for i in range(8)]
        self.assertTrue(cp.assign_layout(source, positions, nthreads=1))
        filename = self.base / 'project with spaces ü.spt'
        self.assertTrue(cp.save_spt(source, filename))
        self.assertTrue(cp.load_spt(target, str(filename)))
        for key, value in numbers.items():
            self.assertEqual(cp.data_get_number(target, key), value)
        self.assertEqual(cp.data_get_string(target, 'receiver.1.rec_name'), 'Secondary receiver')
        self.assertEqual(cp.data_get_string(target, 'heliostat.1.helio_name'), 'Secondary template')
        for key in ('solarfield.0.layout_data', 'ambient.0.weather_file', 'solarfield.0.layout_method',
                    'fluxsim.0.flux_model', 'fluxsim.0.aim_method', 'fluxsim.0.flux_time_type'):
            self.assertEqual(cp.data_get_string(target, key), cp.data_get_string(source, key))
        self.assertEqual(len(cp.get_layout_info(target, restype='matrix')[0]), 0)
        reexport = self.base / 'reexport.spt'
        self.assertTrue(cp.save_spt(target, reexport))
        before, after = exported_values(filename), exported_values(reexport)
        self.assertGreater(before['ambient.0.wf_data'].count('[P]'), 8000)
        self.assertEqual(after['ambient.0.wf_data'], before['ambient.0.wf_data'])
        self.assertTrue(cp.generate_layout(target, nthreads=1))
        self.assertEqual(len(cp.get_layout_info(target, restype='matrix')[0]), len(positions))

    def test_roundtrip_cpu_simulation_and_reused_context(self):
        cp, source, target = self.cp, self.context(), self.context()
        configure(cp, source, 'small')
        # Keep net HTF power positive for a tiny synthetic field. Upstream summary
        # formatting applies log10 to net power and is undefined for nonpositive values.
        self.assertTrue(cp.data_set_number(source, 'receiver.0.therm_loss_base', 0.1))
        self.assertTrue(cp.data_set_number(source, 'receiver.0.piping_loss_coef', 0.01))
        # Integer coordinates avoid introducing layout string rounding artifacts.
        positions = [[0, x, y, 0] for x in (-200, 0, 200) for y in (200, 300, 400, 500)]
        self.assertTrue(cp.assign_layout(source, positions, nthreads=1))
        # Start from an SPT-loaded state: upstream serialization has finite decimal
        # precision. It does not promise an exact snapshot of arbitrary doubles.
        seed = self.base / 'seed.spt'
        self.assertTrue(cp.save_spt(source, seed))
        self.assertTrue(cp.load_spt(source, seed))
        self.assertTrue(cp.generate_layout(source, nthreads=1))
        with patch.dict(os.environ, {'SOLARPILOT_FLUX_PATH': 'flat'}):
            self.assertTrue(cp.simulate(source, nthreads=1))
            original, _ = collect(cp, source)
            self.assertGreater(original['summary']['Power absorbed by HTF'], 0)
            filename = self.base / 'roundtrip.spt'
            self.assertTrue(cp.save_spt(source, filename))
            self.assertTrue(cp.load_spt(target, filename))
            self.assertTrue(cp.generate_layout(target, nthreads=1))
            self.assertTrue(cp.simulate(target, nthreads=1))
            restored, _ = collect(cp, target)
        self.assertEqual(len(restored['details']['id']), len(positions))
        for key in ('flux',):
            np.testing.assert_allclose(restored[key], original[key], rtol=1e-9, atol=1e-10)
        for key in ('summary', 'metrics'):
            self.assertEqual(restored[key].keys(), original[key].keys())
            np.testing.assert_allclose(list(restored[key].values()), list(original[key].values()),
                                       rtol=1e-9, atol=1e-10)
        for key in original['details']:
            np.testing.assert_allclose(restored['details'][key], original['details'][key],
                                       rtol=1e-9, atol=1e-10)
        # Reloading a used context must not expose stale runtime objects or results.
        self.assertTrue(cp.load_spt(source, filename))
        self.assertEqual(cp.get_layout_info(source, restype='matrix')[0], [])
        self.assertTrue(cp.generate_layout(source, nthreads=1))
        self.assertTrue(cp.simulate(source, nthreads=1))
        np.testing.assert_allclose(cp.get_fluxmap(source), restored['flux'], rtol=1e-9, atol=1e-10)

    def test_error_handling_and_legacy_boolean_methods(self):
        cp, context = self.cp, self.context()
        missing = self.base / 'missing.spt'
        with self.assertRaisesRegex(RuntimeError, 'Failed to load SPT.*input file'):
            cp.load_spt(context, missing)
        self.assertFalse(cp.load_from_script(context, str(missing)))
        # All formerly unchecked required nodes, including parametric containers.
        valid_var = ('<variable><component>solarfield</component><instance>0</instance>'
                     '<varname>tht</varname><units>m</units><value>120</value></variable>')
        invalid_inputs = ['', 'not XML', '<data>', '<data></wrong>', '<data/>',
                          '<other/><data><version>x</version></data>',
                          '<data><version>x</version></data>',
                          '<data><version>x</version><variable/></data>']
        invalid_inputs.extend([f'<data><version>x</version>{valid_var}</data><other/>',
                               f'<other/><data><version>x</version>{valid_var}</data>'])
        for element in ('component', 'instance', 'varname', 'units', 'value'):
            invalid_inputs.append('<data><version>x</version>' +
                                  valid_var.replace(f'<{element}>', f'<missing_{element}>').replace(
                                      f'</{element}>', f'</missing_{element}>') + '</data>')
        invalid_inputs.append('<data><version>x</version>' + valid_var.replace('<instance>0', '<instance>bad') + '</data>')
        for section, entry in (('parametric', 'par_variable'), ('optimization', 'opt_variable')):
            invalid_inputs.append(f'<data><version>x</version>{valid_var}<{section}><{entry}/></{section}></data>')
        invalid = self.base / 'invalid.spt'
        for contents in invalid_inputs:
            with self.subTest(contents=contents):
                invalid.write_text(contents)
                with self.assertRaisesRegex(RuntimeError, 'Failed to load SPT'):
                    cp.load_spt(context, invalid)
                self.assertFalse(cp.load_from_script(context, str(invalid)))
        for output in (self.base, self.base / 'absent' / 'output.spt'):
            with self.assertRaisesRegex(RuntimeError, 'Failed to save SPT'):
                cp.save_spt(context, output)
            self.assertFalse(cp.save_from_script(context, str(output)))
        # A valid project clears stale errors; the caller can still free the context.
        valid = self.base / 'valid.spt'
        self.assertTrue(cp.save_from_script(context, str(valid)))
        self.assertTrue(cp.load_from_script(context, str(valid)))
        self.assertEqual(cp.get_last_backend_error(context), '')
        self.assertTrue(cp.load_spt(context, valid))
        self.assertTrue(cp.save_spt(context, valid))

    def test_relative_path_arguments_and_c_signatures(self):
        cp, context = self.cp, self.context()
        previous = Path.cwd()
        try:
            os.chdir(self.base)
            self.assertTrue(cp.save_spt(context, 'my_project.spt'))
            self.assertTrue(cp.load_spt(context, Path('my_project.spt')))
        finally:
            os.chdir(previous)
        for operation in (cp.load_spt, cp.save_spt):
            for value in ('', 'bad\0path'):
                with self.assertRaises(ValueError):
                    operation(context, value)
            for value in (None, 3, b'bytes.spt'):
                with self.assertRaises(TypeError):
                    operation(context, value)
            with self.assertRaises(ValueError):
                operation(None, 'my_project.spt')
        for function in (cp.pdll.sp_load_from_script, cp.pdll.sp_save_from_script):
            self.assertIs(function.restype, ctypes.c_bool)
            self.assertEqual(function.argtypes, [ctypes.c_void_p, ctypes.c_char_p])
            self.assertFalse(function(None, b'unused.spt'))
            self.assertFalse(function(context, None))

    def test_embedded_weather_does_not_replace_external_file(self):
        cp, source, target = self.cp, self.context(), self.context()
        configure(cp, source, 'small')
        self.assertTrue(cp.assign_layout(source, [[0, 200, 300, 0]], nthreads=1))
        # A synthetic missing path tests the dependency without relying on private data.
        absent = str(self.base / 'absent-weather.epw')
        self.assertTrue(cp.data_set_string(source, 'ambient.0.weather_file', absent))
        filename = self.base / 'embedded-weather.spt'
        self.assertTrue(cp.save_spt(source, filename))
        self.assertGreater(exported_values(filename)['ambient.0.wf_data'].count('[P]'), 8000)
        self.assertTrue(cp.load_spt(target, filename))
        self.assertEqual(cp.data_get_string(target, 'ambient.0.weather_file'), absent)
        self.assertFalse(cp.generate_layout(target, nthreads=1))
        self.assertEqual(cp.get_layout_info(target, restype='matrix')[0], [])

    def test_existing_serializer_does_not_preserve_arbitrary_double_precision(self):
        cp, source, target = self.cp, self.context(), self.context()
        value = 123.123456789
        self.assertTrue(cp.data_set_number(source, 'solarfield.0.tht', value))
        filename = self.base / 'precision.spt'
        self.assertTrue(cp.save_spt(source, filename))
        self.assertTrue(cp.load_spt(target, filename))
        # Record the inherited limitation; do not loosen simulation tolerances.
        self.assertNotEqual(cp.data_get_number(target, 'solarfield.0.tht'), value)
        self.assertEqual(cp.data_get_number(target, 'solarfield.0.tht'),
                         float(exported_values(filename)['solarfield.0.tht']))

    def test_cuda_correctness_after_roundtrip_and_backend_not_serialized(self):
        cp = self.cp
        if not cp.cuda_available():
            self.skipTest('CUDA build/device required')
        source, target = self.context(), self.context()
        configure(cp, source, 'small')
        self.assertTrue(cp.data_set_number(source, 'receiver.0.therm_loss_base', 0.1))
        self.assertTrue(cp.data_set_number(source, 'receiver.0.piping_loss_coef', 0.01))
        self.assertTrue(cp.assign_layout(source, [[0, x, y, 0] for x in (-200, 0, 200)
                                                 for y in (200, 300, 400, 500)], nthreads=1))
        filename = self.base / 'cuda-roundtrip.spt'
        self.assertTrue(cp.save_spt(source, filename))
        self.assertTrue(cp.load_spt(source, filename))
        self.assertTrue(cp.generate_layout(source, nthreads=1))
        with patch.dict(os.environ, {'SOLARPILOT_FLUX_PATH': 'flat', 'SOLARPILOT_CUDA_TIMING_FILE': ''}):
            self.assertTrue(cp.simulate(source, nthreads=1))
            expected, _ = collect(cp, source)
            self.assertGreater(expected['summary']['Power absorbed by HTF'], 0)
            self.assertTrue(cp.set_compute_backend(source, 'cuda'))
            self.assertTrue(cp.save_spt(source, filename))
            self.assertTrue(cp.load_spt(target, filename))
            self.assertEqual(cp.get_compute_backend(target), 'cpu')
            self.assertTrue(cp.set_compute_backend(target, 'cuda'))
            self.assertTrue(cp.load_spt(target, filename))
            self.assertEqual(cp.get_compute_backend(target), 'cuda')
            self.assertTrue(cp.generate_layout(target, nthreads=1))
            self.assertTrue(cp.simulate(target, nthreads=1))
            actual, _ = collect(cp, target)
        np.testing.assert_allclose(actual['flux'], expected['flux'], rtol=1e-9, atol=1e-10)
        np.testing.assert_allclose(list(actual['metrics'].values()), list(expected['metrics'].values()),
                                   rtol=1e-9, atol=1e-10)
