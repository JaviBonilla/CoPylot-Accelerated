"""Public synthetic project integration for the generic convergence harness."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'benchmarks'),str(Path(__file__).parent)]
from test_flat_project import configure_flat
from project_grid_campaign import api,read_project_weather,prepare,frozen_state,assert_frozen,simulate,PLAIN,input_names


class ProjectGridCampaign(unittest.TestCase):
    def test_existing_weather_path_without_layout_generation(self):
        cp=api();source=cp.data_create()
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/'public.spt'
            try:
                configure_flat(cp,source,count=3,hour_day=True)
                self.assertTrue(cp.data_set_number(source,'ambient.0.latitude',0))
                self.assertTrue(cp.save_spt(source,file));self.assertTrue(cp.load_spt(source,file))
                self.assertEqual(cp.get_layout_info(source,restype='matrix')[0],[])
                read_project_weather(cp,source)
                self.assertGreater(cp.data_get_number(source,'ambient.0.latitude'),0)
                self.assertEqual(cp.get_layout_info(source,restype='matrix')[0],[])
                self.assertTrue(cp.restore_loaded_layout(source))
                self.assertEqual(len(cp.get_layout_info(source,restype='dictionary')['id']),3)
            finally:self.assertTrue(cp.data_free(source))

    def test_freeze_excludes_grid_and_detects_physical_change(self):
        cp=api();source=cp.data_create()
        with tempfile.TemporaryDirectory() as td:
            td=Path(td);file=td/'public.spt'
            try:
                configure_flat(cp,source,count=3,hour_day=True);self.assertTrue(cp.save_spt(source,file))
                states=[]
                for nx,ny in ((9,7),(18,14)):
                    r=prepare(cp,file,grid={'nx':nx,'ny':ny})
                    try:
                        with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'verify'}):simulate(cp,r)
                        states.append(frozen_state(cp,r,td))
                        self.assertTrue(cp.data_set_number(r,'fluxsim.0.flux_dni',800))
                        with patch.dict(os.environ,{**PLAIN,'SOLARPILOT_INTERCEPT_PATH':'verify'}):simulate(cp,r)
                        with self.assertRaises(RuntimeError):assert_frozen(states[-1],frozen_state(cp,r,td))
                    finally:self.assertTrue(cp.data_free(r))
                assert_frozen(*states)
                self.assertIn(('heliostat','err_surface_x'),input_names())
                self.assertNotIn(('fluxsim','flux_solar_az'),input_names())
            finally:self.assertTrue(cp.data_free(source))

if __name__=='__main__':unittest.main()
