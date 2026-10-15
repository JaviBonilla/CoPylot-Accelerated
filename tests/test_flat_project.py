"""Independent synthetic serialized fields; never reads local/private cases."""
import ctypes
import os
from pathlib import Path
import shutil
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'benchmarks'))
from cases import api, configure, WEATHER


def configure_flat(cp, r, count=5, rotated=False, hour_day=False):
    configure(cp, r, 'small')
    assert cp.data_set_string(r, 'solarfield.0.temp_which', cp.data_get_string(r, 'heliostat.0.helio_name'))
    params = {'solarfield.0.tht': 80, 'solarfield.0.layout_method': 3, 'receiver.0.rec_type': 2,
              'receiver.0.rec_width': 8, 'receiver.0.rec_height': 6,
              'receiver.0.rec_azimuth': 17 if rotated else 0,
              'receiver.0.rec_elevation': 9 if rotated else 0,
              'receiver.0.therm_loss_base': .01, 'receiver.0.piping_loss_coef': .001,
              'heliostat.0.width': 4, 'heliostat.0.height': 5,
              'heliostat.0.cant_method': 0, 'fluxsim.0.x_res': 13,
              'fluxsim.0.y_res': 11, 'fluxsim.0.aim_method': 4,
              'fluxsim.0.flux_time_type': 1 if hour_day else 0,
              'fluxsim.0.flux_month': 6, 'fluxsim.0.flux_day': 15,
              'fluxsim.0.flux_hour': 12}
    for key, value in params.items():
        assert cp.data_set_number(r, key, value), key
    # Explicit positions/focus/cant/aims, independent of any private project.
    rows = [[0, 1, 1, -40+20*(i%5), 180+22*(i//5), 0,
             215+i, 225+i, 0, 0, 1, .3*(i%3-1), 0, 80+.2*(i%2)] for i in range(count)]
    assert cp.data_set_string(r, 'solarfield.0.layout_data',
                              ';'.join(','.join(map(str, row)) for row in rows)+';')
    return rows


class FlatProject(unittest.TestCase):
    def setUp(self):
        self.cp=api(); self.contexts=[]
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)

    def tearDown(self):
        for r in reversed(self.contexts): self.assertTrue(self.cp.data_free(r))

    def context(self):
        r=self.cp.data_create();self.assertTrue(r);self.contexts.append(r);return r

    def loaded(self, count=5, rotated=False, hour_day=False):
        r=self.context();rows=configure_flat(self.cp,r,count,rotated,hour_day)
        name=self.base/'synthetic.spt'
        self.assertTrue(self.cp.save_spt(r,name));self.assertTrue(self.cp.load_spt(r,name))
        return r,rows

    def test_restore_without_weather_preserves_serialized_geometry(self):
        cp=self.cp;r,rows=self.loaded()
        self.assertTrue(cp.data_set_string(r,'ambient.0.weather_file','missing-synthetic-weather.epw'))
        original=cp.data_get_string(r,'solarfield.0.layout_data')
        self.assertFalse(cp.simulate(r,nthreads=1))
        self.assertTrue(cp.restore_loaded_layout(r),cp.get_last_backend_error(r))
        layout=np.asarray(cp.get_layout_info(r,get_optical_details=True,restype='matrix')[0])
        np.testing.assert_array_equal(layout[:,1:4],np.asarray(rows)[:,3:6])
        np.testing.assert_array_equal(layout[:,4],np.asarray(rows)[:,0])
        np.testing.assert_array_equal(layout[:,6:8],np.asarray(rows)[:,6:8])
        self.assertEqual(cp.data_get_string(r,'solarfield.0.layout_data'),original)
        self.assertFalse(cp.restore_loaded_layout(r))
        self.assertIn('newly loaded',cp.get_last_backend_error(r))
        for intercept in ('legacy','verify'):
            with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':intercept,'SOLARPILOT_FLUX_PATH':'verify'}):
                self.assertTrue(cp.simulate(r,nthreads=1,update_aimpoints=False),cp.get_last_backend_error(r))
            details=cp.detail_results(r,restype='dictionary')
            for axis,index in zip('xyz',range(11,14)):
                np.testing.assert_array_equal(details[axis+'_aimpoint'],np.asarray(rows)[:,index])

    def test_native_geometry_flags_and_templates(self):
        binary=Path(os.environ.get('COPILOT_LIB_DIR','build/cpu/lib')).resolve().parent/'project_state_check'
        if not binary.exists(): self.skipTest('Diagnostic native bridge required')
        cp=self.cp; r=self.context();rows=configure_flat(cp,r)
        self.assertEqual(cp.add_heliostat_template(r,'Independent second template'),1)
        rows[1][0]=1;rows[2][1]=0;rows[3][2]=0
        rows[0][8:11]=[.1,.2,.97]
        self.assertTrue(cp.data_set_string(r,'solarfield.0.layout_data',
                        ';'.join(','.join(map(str,row)) for row in rows)+';'))
        self.assertTrue(cp.data_set_number(r,'solarfield.0.layout_method',1))
        # Restoration ignores generation-only angular/land filtering.
        self.assertTrue(cp.data_set_number(r,'solarfield.0.accept_min',150))
        name=self.base/'flags.spt';self.assertTrue(cp.save_spt(r,name))
        result=subprocess.run([str(binary),str(name),'restore'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        state=json.loads(result.stdout)
        for key in ('positions','templates','focus','cant','aims','flags'):
            self.assertTrue(state[key+'_preserved'],key)

    def test_repeated_load_restore_simulate_and_project_replacement(self):
        cp=self.cp;projects=[]
        for index,count in enumerate((3,7)):
            source=self.context();rows=configure_flat(cp,source,count=count,rotated=bool(index),hour_day=bool(index))
            weather='unavailable-public-'+str(index)+'.epw'
            self.assertTrue(cp.data_set_string(source,'ambient.0.weather_file',weather))
            self.assertTrue(cp.data_set_number(source,'receiver.0.rec_width',8+3*index))
            name=self.base/('project-'+str(index)+'.spt');self.assertTrue(cp.save_spt(source,name))
            projects.append((name,rows,weather,8+3*index))
        target=self.context()
        for backend in ('cpu','cuda') if cp.cuda_available() else ('cpu',):
            self.assertTrue(cp.set_compute_backend(target,backend))
            for name,rows,weather,width in projects+projects[::-1]:
                self.assertTrue(cp.load_spt(target,name))
                self.assertEqual(cp.get_layout_info(target,restype='matrix')[0],[])
                self.assertFalse(cp.simulate(target,nthreads=1))
                self.assertTrue(cp.restore_loaded_layout(target),cp.get_last_backend_error(target))
                self.assertEqual(cp.data_get_string(target,'ambient.0.weather_file'),weather)
                self.assertEqual(cp.data_get_number(target,'receiver.0.rec_width'),width)
                self.assertEqual(cp.get_compute_backend(target),backend)
                geometry=np.asarray(cp.get_layout_info(target,get_optical_details=True,restype='matrix')[0])
                np.testing.assert_array_equal(geometry[:,1:4],np.asarray(rows)[:,3:6])
                np.testing.assert_array_equal(geometry[:,6:8],np.asarray(rows)[:,6:8])
                with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'verify_cuda' if backend=='cuda' else 'verify'}):
                    self.assertTrue(cp.simulate(target,nthreads=1),cp.get_last_backend_error(target))
                details=cp.detail_results(target,restype='dictionary')
                for axis,index in zip('xyz',range(11,14)):
                    np.testing.assert_array_equal(details[axis+'_aimpoint'],np.asarray(rows)[:,index])

    def test_single_row_and_zero_rows(self):
        cp=self.cp;r,rows=self.loaded(count=1)
        self.assertTrue(cp.restore_loaded_layout(r),cp.get_last_backend_error(r))
        self.assertEqual(len(cp.get_layout_info(r,restype='dictionary')['id']),1)
        empty,_=self.loaded(count=0)
        self.assertFalse(cp.restore_loaded_layout(empty))
        self.assertIn('empty',cp.get_last_backend_error(empty))

    def test_restore_errors_and_recovery(self):
        cp=self.cp;r,_=self.loaded()
        good=cp.data_get_string(r,'solarfield.0.layout_data')
        for bad in ('','0,1,1,5,6,7;',good.replace('215','NaN',1),
                    good.replace('215,225','215,NULL',1),good.replace('0,1,1,','99,1,1,',1)):
            self.assertTrue(cp.data_set_string(r,'solarfield.0.layout_data',bad))
            self.assertFalse(cp.restore_loaded_layout(r));self.assertTrue(cp.get_last_backend_error(r))
            self.assertEqual(cp.get_layout_info(r,restype='matrix')[0],[])
        self.assertTrue(cp.data_set_string(r,'solarfield.0.layout_data',good))
        self.assertTrue(cp.restore_loaded_layout(r),cp.get_last_backend_error(r))
        self.assertFalse(cp.pdll.sp_restore_loaded_layout(None))
        self.assertEqual(cp.pdll.sp_restore_loaded_layout.argtypes,[ctypes.c_void_p])

    def test_hour_day_legacy_flat_keep_existing(self):
        cp=self.cp
        for rotated in (False,True):
            r,rows=self.loaded(rotated=rotated,hour_day=True)
            self.assertTrue(cp.restore_loaded_layout(r),cp.get_last_backend_error(r))
            for hour in (10,12,14):
                self.assertTrue(cp.data_set_number(r,'fluxsim.0.flux_hour',hour))
                outputs=[]
                for intercept,density in (('legacy','legacy'),('verify','verify')):
                    with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':intercept,'SOLARPILOT_FLUX_PATH':density}):
                        self.assertTrue(cp.simulate(r,nthreads=1),cp.get_last_backend_error(r))
                        outputs.append(np.asarray(cp.get_fluxmap(r)))
                    details=cp.detail_results(r,restype='dictionary')
                    for axis,index in zip('xyz',range(11,14)):
                        np.testing.assert_array_equal(details[axis+'_aimpoint'],np.asarray(rows)[:,index])
                np.testing.assert_allclose(*outputs,rtol=1e-9,atol=1e-10)

    def test_cuda_flat_maps_resident_time_and_aims(self):
        cp=self.cp
        if not cp.cuda_available(): self.skipTest('CUDA build/device required')
        for count in (1,63,64,65,129):
            r,rows=self.loaded(count=count,rotated=count%2==1,hour_day=True)
            self.assertTrue(cp.restore_loaded_layout(r),cp.get_last_backend_error(r))
            for hour in (10,12,14):
                self.assertTrue(cp.data_set_number(r,'fluxsim.0.flux_hour',hour))
                self.assertTrue(cp.set_compute_backend(r,'cpu'))
                with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'verify','SOLARPILOT_FLUX_PATH':'verify'}):
                    self.assertTrue(cp.simulate(r,nthreads=1),cp.get_last_backend_error(r))
                    expected=np.asarray(cp.get_fluxmap(r))
                self.assertTrue(cp.set_compute_backend(r,'cuda'))
                actual=[]
                for mode in ('verify_cuda','cuda','cuda'):
                    with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':mode,'SOLARPILOT_IMAGE_PIPELINE':'resident'}):
                        self.assertTrue(cp.simulate(r,nthreads=1,update_aimpoints=False),cp.get_last_backend_error(r))
                        actual.append(np.asarray(cp.get_fluxmap(r)))
                    np.testing.assert_allclose(actual[-1],expected,rtol=1e-9,atol=1e-10)
                np.testing.assert_array_equal(actual[-1],actual[-2])
                details=cp.detail_results(r,restype='dictionary')
                for axis,index in zip('xyz',range(11,14)):
                    np.testing.assert_array_equal(details[axis+'_aimpoint'],np.asarray(rows)[:,index])

    def test_cuda_disabled_flat_and_unsupported_recovery(self):
        cp=self.cp
        if not cp.cuda_available(): self.skipTest('CUDA build/device required')
        source=self.context();rows=configure_flat(cp,source,count=65,hour_day=True)
        rows[0][1]=0
        self.assertTrue(cp.data_set_string(source,'solarfield.0.layout_data',
                        ';'.join(','.join(map(str,row)) for row in rows)+';'))
        name=self.base/'disabled.spt';self.assertTrue(cp.save_spt(source,name))
        self.assertTrue(cp.load_spt(source,name));self.assertTrue(cp.restore_loaded_layout(source))
        with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'verify'}):
            self.assertTrue(cp.simulate(source,nthreads=1),cp.get_last_backend_error(source))
        expected=np.asarray(cp.get_fluxmap(source))
        self.assertTrue(cp.set_compute_backend(source,'cuda'))
        self.assertTrue(cp.data_set_number(source,'receiver.0.is_snout',1))
        self.assertFalse(cp.simulate(source,nthreads=1));self.assertIn('supports only',cp.get_last_backend_error(source))
        self.assertTrue(cp.data_set_number(source,'receiver.0.is_snout',0))
        with patch.dict(os.environ,{'SOLARPILOT_INTERCEPT_PATH':'verify_cuda'}):
            self.assertTrue(cp.simulate(source,nthreads=1),cp.get_last_backend_error(source))
        np.testing.assert_allclose(cp.get_fluxmap(source),expected,rtol=1e-9,atol=1e-10)

    def test_portable_weather_resolution(self):
        cp=self.cp
        for stored in ('nested/public.csv','/obsolete/public.csv'):
            source=self.context();configure_flat(cp,source)
            self.assertTrue(cp.data_set_string(source,'ambient.0.weather_file',stored))
            f=self.base/'portable.spt';self.assertTrue(cp.save_spt(source,f))
            weather=self.base/('nested/public.csv' if stored.startswith('nested') else 'public.csv')
            weather.parent.mkdir(exist_ok=True);shutil.copyfile(WEATHER,weather)
            before=f.read_bytes();target=self.context()
            self.assertTrue(cp.load_spt(target,f))
            self.assertEqual(Path(cp.data_get_string(target,'ambient.0.weather_file')),weather)
            self.assertEqual(f.read_bytes(),before)
            self.assertTrue(cp.generate_layout(target,nthreads=1))
        self.assertTrue(cp.data_set_string(source,'ambient.0.weather_file',str(WEATHER)))
        self.assertTrue(cp.save_spt(source,f));self.assertTrue(cp.load_spt(target,f))
        self.assertEqual(cp.data_get_string(target,'ambient.0.weather_file'),str(WEATHER))

if __name__=='__main__': unittest.main()
