"""Public CUDA intercept dispatch, mixed diagnostic paths and explicit scope errors."""
import json
import csv
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from cases import api,configure,layout

class CudaImagePlane(unittest.TestCase):
    def setUp(self):
        self.cp=api()
        if not self.cp.cuda_available(): self.skipTest('CUDA build/device required')
        self.r=self.cp.data_create();self.assertTrue(self.r)
        configure(self.cp,self.r,'small')
        self.assertTrue(self.cp.assign_layout(self.r,layout(257),nthreads=1))
        self.assertTrue(self.cp.set_compute_backend(self.r,'cuda'))

    def tearDown(self):
        if hasattr(self,'r'): self.assertTrue(self.cp.data_free(self.r))

    def test_public_and_mixed_image_plane_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            comparison=Path(directory)/'optics.jsonl'
            with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'verify_cuda','SOLARPILOT_IMAGE_COMPARE_FILE':str(comparison)}):
                self.assertTrue(self.cp.simulate(self.r,nthreads=1),self.cp.get_last_backend_error(self.r))
                full=np.asarray(self.cp.get_fluxmap(self.r))
            if not comparison.exists(): self.skipTest('Flux diagnostics disabled')
            rows=[json.loads(x) for x in comparison.read_text().splitlines()]
            self.assertEqual(rows[0]['heliostats'],257)
            self.assertEqual(rows[0]['errors']['global']['count'],257*215)
            self.assertTrue(rows[0]['errors']['global']['passed'])
            self.assertTrue(self.cp.set_compute_backend(self.r,'cpu'))
            with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'verify_cuda','SOLARPILOT_IMAGE_COMPARE_FILE':str(comparison)}):
                self.assertTrue(self.cp.simulate(self.r,nthreads=1),self.cp.get_last_backend_error(self.r))
                image_only=np.asarray(self.cp.get_fluxmap(self.r))
            with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'flat','SOLARPILOT_IMAGE_COMPARE_FILE':''}):
                self.assertTrue(self.cp.simulate(self.r,nthreads=1),self.cp.get_last_backend_error(self.r))
                reference=np.asarray(self.cp.get_fluxmap(self.r))
            np.testing.assert_allclose(image_only,reference,rtol=1e-9,atol=1e-10)
            np.testing.assert_allclose(full,reference,rtol=1e-9,atol=1e-10)

    def test_unsupported_facet_capacity_and_recovery(self):
        self.assertTrue(self.cp.data_set_number(self.r,'heliostat.0.n_cant_x',9))
        self.assertFalse(self.cp.simulate(self.r,nthreads=1))
        self.assertIn('64-facet',self.cp.get_last_backend_error(self.r))
        self.assertEqual(self.cp.get_compute_backend(self.r),'cuda')
        self.assertTrue(self.cp.data_set_number(self.r,'heliostat.0.n_cant_x',2))
        self.assertTrue(self.cp.simulate(self.r,nthreads=1),self.cp.get_last_backend_error(self.r))
        self.assertEqual(self.cp.get_last_backend_error(self.r),'')

    def test_disabled_heliostat_is_excluded_from_cuda_batch(self):
        ids=self.cp.get_layout_info(self.r,restype='dictionary')['id']
        self.assertTrue(self.cp.modify_heliostats(self.r,{'id':[ids[0]],'enabled':[0]}))
        with tempfile.TemporaryDirectory() as directory:
            comparison=Path(directory)/'disabled.jsonl'
            with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'verify_cuda','SOLARPILOT_IMAGE_COMPARE_FILE':str(comparison)}):
                self.assertTrue(self.cp.simulate(self.r,nthreads=1),self.cp.get_last_backend_error(self.r))
                actual=np.asarray(self.cp.get_fluxmap(self.r))
            if not comparison.exists(): self.skipTest('Flux diagnostics disabled')
            rows=[json.loads(x) for x in comparison.read_text().splitlines()]
            self.assertEqual(rows[0]['heliostats'],256)
            self.assertTrue(self.cp.set_compute_backend(self.r,'cpu'))
            with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'flat','SOLARPILOT_IMAGE_COMPARE_FILE':''}):
                self.assertTrue(self.cp.simulate(self.r,nthreads=1))
                expected=np.asarray(self.cp.get_fluxmap(self.r))
            np.testing.assert_allclose(actual,expected,rtol=1e-9,atol=1e-10)

    def test_resident_reuploads_mutations_and_enabled_subset(self):
        ids=self.cp.get_layout_info(self.r,restype='dictionary')['id']
        with tempfile.TemporaryDirectory() as directory:
            for elevation,enabled in [(55,1),(40,0),(55,1)]:
                self.assertTrue(self.cp.data_set_number(self.r,'fluxsim.0.flux_solar_el_in',elevation))
                self.assertTrue(self.cp.data_set_number(self.r,'fluxsim.0.flux_dni',700 if enabled==0 else 950))
                self.assertTrue(self.cp.modify_heliostats(self.r,{'id':[ids[0]],'enabled':[enabled]}))
                receipt=Path(directory)/'handoff.csv';receipt.write_text('')
                self.assertTrue(self.cp.set_compute_backend(self.r,'cuda'))
                with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'cuda','SOLARPILOT_FLUX_PATH':'flat',
                        'SOLARPILOT_IMAGE_PIPELINE':'resident','SOLARPILOT_IMAGE_HANDOFF_FILE':str(receipt)}):
                    self.assertTrue(self.cp.simulate(self.r,nthreads=1),self.cp.get_last_backend_error(self.r))
                    actual=np.asarray(self.cp.get_fluxmap(self.r))
                rows=list(csv.reader(receipt.read_text().splitlines()))
                self.assertEqual(len(rows),1);self.assertEqual(int(rows[0][1]),1)
                self.assertEqual(int(rows[0][0]),256+enabled);self.assertEqual(int(rows[0][2]),56*(256+enabled))
                self.assertTrue(self.cp.set_compute_backend(self.r,'cpu'))
                with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'flat','SOLARPILOT_IMAGE_HANDOFF_FILE':''}):
                    self.assertTrue(self.cp.simulate(self.r,nthreads=1))
                    expected=np.asarray(self.cp.get_fluxmap(self.r))
                np.testing.assert_allclose(actual,expected,rtol=1e-9,atol=1e-10)

    def test_resident_recovers_after_invalid_device(self):
        with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'cuda','SOLARPILOT_IMAGE_PIPELINE':'resident'}):
            self.assertTrue(self.cp.simulate(self.r,nthreads=1),self.cp.get_last_backend_error(self.r))
            expected=np.asarray(self.cp.get_fluxmap(self.r))
            with self.assertRaises(RuntimeError):self.cp.set_cuda_device(self.r,9999)
            self.assertTrue(self.cp.simulate(self.r,nthreads=1),self.cp.get_last_backend_error(self.r))
            self.assertTrue(np.array_equal(expected,np.asarray(self.cp.get_fluxmap(self.r))))
