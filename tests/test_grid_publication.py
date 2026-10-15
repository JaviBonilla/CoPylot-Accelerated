"""Privacy boundary for project convergence publications."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from summarize_project_grid import safe_point,safe_errors,safe_comparison

class GridPublication(unittest.TestCase):
    def test_private_location_date_and_paths_are_not_operating_point_metadata(self):
        point={'id':'public-state','site':{'private':'location'},'project':'/private/input.spt',
               'inputs':{'fluxsim.0.flux_month':1,'fluxsim.0.flux_day':2,'fluxsim.0.flux_hour':3,'fluxsim.0.flux_dni':800},
               'resolved':{'fluxsim.0.flux_solar_az':150,'fluxsim.0.flux_solar_el':40}}
        out=safe_point(point)
        self.assertEqual(out['id'],'public-state');self.assertEqual(out['dni_w_m2'],800)
        self.assertNotIn('site',out);self.assertNotIn('inputs',out);self.assertNotIn('project',out)
        self.assertNotIn('/private',str(out));self.assertNotIn('flux_day',str(out))

    def test_private_error_argmax_and_unknown_fields_are_not_published(self):
        out=safe_errors({'max_abs':1e-12,'max_rel_nonzero':1e-14,'passed':True,
                         'worst_h_abs':5,'worst_row_col':[2,4],'path':'/private/map.npz','coordinates':[1,2]})
        self.assertEqual(out,{'max_abs':1e-12,'max_rel_nonzero':1e-14,'passed':True})

    def test_family_metrics_are_retained_without_private_argmax(self):
        out=safe_comparison({'global':{'count':215,'passed':True,'worst_h_abs':7},
                             'families':{'sun':{'count':49,'rms':1e-15,'worst_h_rel':3}}})
        self.assertEqual(out,{'global':{'count':215,'passed':True},'families':{'sun':{'count':49,'rms':1e-15}}})

if __name__=='__main__':unittest.main()
