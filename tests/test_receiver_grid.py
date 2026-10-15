"""Independent physical-grid and conservative-rebin regression tests."""
import math
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from receiver_grid import physical_grid,refinement_series,conservative_rebin,map_metrics,compare_maps,minimum_converged
from commercial_reference import load_manifest,coordinates


class ReceiverGrid(unittest.TestCase):
    def test_flat_physical_aspect_ratio(self):
        g=physical_grid({'type':'flat','width_m':12.,'height_m':5.},.5)
        self.assertEqual((g['nx'],g['ny']),(24,10));self.assertEqual(g['cell_width_m'],.5);self.assertEqual(g['cell_height_m'],.5)
    def test_cylinder_uses_full_circumference(self):
        g=physical_grid({'type':'cylindrical','diameter_m':10.,'height_m':8.},1.)
        self.assertEqual((g['nx'],g['ny']),(32,8));self.assertAlmostEqual(g['cell_width_m'],math.pi*10/32)
    def test_deterministic_refinement_and_maximum_cell_size(self):
        receiver={'type':'cylindrical','diameter_m':17.65,'height_m':21.6029}
        a=refinement_series(receiver,[8,4,2,1,.5,.25,.125]);self.assertEqual(a,refinement_series(receiver,[8,4,2,1,.5,.25,.125]))
        self.assertEqual((a[-1]['nx'],a[-1]['ny']),(444,173))
        for g in a:self.assertLessEqual(max(g['cell_width_m'],g['cell_height_m']),g['target_cell_m'])
    def test_constant_noncommensurate_maps_conserve_integral(self):
        for shape in [(2,9),(11,3),(17,19)]:
            actual=conservative_rebin(np.full((7,5),3.),shape)
            np.testing.assert_allclose(actual,3.,rtol=0,atol=3e-14)
    def test_nonconstant_random_map_preserves_power(self):
        values=np.random.default_rng(812).uniform(.1,100,(13,17))
        for shape in [(3,7),(19,31),(13,17)]:
            mapped=conservative_rebin(values,shape)
            self.assertAlmostEqual(float(mapped.mean()),float(values.mean()),places=11)
    def test_known_coarse_fine_cell_average_map(self):
        fine=np.array([[1.,3.,5.,7.],[1.,3.,5.,7.]])
        coarse=conservative_rebin(fine,(1,2));np.testing.assert_allclose(coarse,[[2.,6.]])
        np.testing.assert_allclose(conservative_rebin(coarse,(2,4)),[[2,2,6,6],[2,2,6,6]])
    def test_known_noninteger_overlap(self):
        np.testing.assert_allclose(conservative_rebin([[0.,3.]],(1,3)),[[0.,1.5,3.]],atol=1e-15)
    def test_identical_map_errors_are_zero(self):
        for nx,ny in [(4,2),(7,3),(19,13)]:
            g=physical_grid({'type':'flat','width_m':float(nx),'height_m':float(ny)},1.)
            f=np.arange(1.,nx*ny+1).reshape(ny,nx);e=compare_maps(f,f,g,g)
            for key in ['map_l1_normalized','map_l2_normalized','map_linf_kw_m2','peak_rel','integrated_incident_power_rel','centroid_distance_over_diagonal','uniformity_cv_abs']:self.assertEqual(e[key],0.)
    def test_metrics_have_physical_units_and_weighted_centroid(self):
        g=physical_grid({'type':'flat','width_m':2.,'height_m':2.},1.);m=map_metrics([[1,3],[1,3]],g)
        self.assertEqual(m['integrated_incident_power_kw'],8.);self.assertEqual(m['centroid_surface_s_m'],1.25);self.assertEqual(m['centroid_z_from_bottom_m'],1.)
    def test_cylinder_centroid_across_seam_and_uniform_undefined(self):
        g=physical_grid({'type':'cylindrical','diameter_m':4/math.pi,'height_m':2.},1.)
        self.assertIsNone(map_metrics(np.ones((2,4)),g)['circular_centroid_s_m'])
        m=map_metrics([[2.,0.,0.,2.],[2.,0.,0.,2.]],g)
        self.assertLess(min(m['circular_centroid_s_m'],4-m['circular_centroid_s_m']),1e-12)
    def test_selection_requires_all_states_and_finer_levels(self):
        rows=[{'level':l,'operating_point':p,'convergence':{'error':.1/(l+1) if p=='worst' else .001}} for l in range(4) for p in ['easy','worst']]
        self.assertEqual(minimum_converged(rows,['easy','worst'],['error'],.04,4),2)
        rows[6]['convergence']['error']=.08
        self.assertIsNone(minimum_converged(rows,['easy','worst'],['error'],.04,4))
        self.assertIsNone(minimum_converged(rows[:-1],['easy','worst'],['error'],.04,4))
    def test_malformed_inputs_are_rejected(self):
        for value in [0,-1,float('nan'),float('inf'),True]:
            with self.assertRaises(ValueError):physical_grid({'type':'flat','width_m':4.,'height_m':2.},value)
        for values in [[],[[float('nan')]],[[1,-1]],[[0,0]]]:
            with self.assertRaises(ValueError):map_metrics(values,physical_grid({'type':'flat','width_m':2.,'height_m':2.},1.))
        for shape in [(0,3),(2,2.5),(True,3),(True,1),(1.,1.)]:
            with self.assertRaises(ValueError):conservative_rebin([[1.]],shape)
        with self.assertRaises(ValueError):refinement_series({'type':'flat','width_m':4.,'height_m':2.},[1,2,3,4])
        with self.assertRaises(ValueError):physical_grid({'type':'sphere','height_m':1},1)
    def test_public_case_coordinates_and_provenance(self):
        m=load_manifest();a=coordinates(m);self.assertEqual(a.shape,(8790,4));self.assertTrue(np.array_equal(a,coordinates(m)))
        self.assertFalse(m['exact_real_plant_reproduction'])
        for p in m['parameters'].values():self.assertIn(p['classification'],['published','derived','assumed'])


if __name__=='__main__':unittest.main()
