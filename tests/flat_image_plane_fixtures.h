#ifndef COPILOT_FLAT_IMAGE_PLANE_FIXTURES_H
#define COPILOT_FLAT_IMAGE_PLANE_FIXTURES_H
#include "image_plane_access.h"
#include "Ambient.h"
#include <cmath>
// Independent public flat apertures, rotations, optical errors and off-center aims.
template<class Callback> unsigned for_each_flat_image_plane_fixture(Callback callback) {
    unsigned index=0;
    for (int sun_model : {0,1,2,4}) for (int cant : {0,-1,1})
    for (int geometry=0; geometry<6; ++geometry) {
            var_map v; v.reset();
            v.flux.aim_method.combo_select_by_mapval(geometry%2?4:0);
            v.recs.front().rec_type.combo_select_by_mapval(2);
            v.recs.front().rec_width.val=geometry==1?55.:8.;
            v.recs.front().rec_height.val=geometry==1?40.:6.;
            v.recs.front().rec_azimuth.val=geometry==5?23.:0.;
            v.recs.front().rec_elevation.val=geometry==5?11.:0.;
            v.flux.flux_time_type.combo_select_by_mapval(0);
            v.amb.sun_type.combo_select_by_mapval(sun_model);
            auto& hv=v.hels.front();
            hv.cant_method.combo_select_by_mapval(cant);
            hv.is_faceted.val=geometry!=0;
            hv.is_enabled.val=geometry!=4; // Direct intercept has no enabled-state guard.
            hv.n_cant_x.val=geometry==4?8:2; hv.n_cant_y.val=geometry==4?8:8;
            const double error=geometry==1?1.e-8:(geometry==3?0.008:0.001);
            hv.err_azimuth.val=error; hv.err_elevation.val=1.3*error;
            hv.err_surface_x.val=0.7*error; hv.err_surface_y.val=1.2*error;
            hv.err_reflect_x.val=0.4*error; hv.err_reflect_y.val=0.9*error;
            Ambient ambient; ambient.Create(v);
            Flux f; f.Setup(); f.initHermiteCoefs(v,ambient);
            Receiver rec; rec.Create(v.recs.front(),v.sf.tht.val);
            Heliostat h; h.Create(v,0);
            const double x=geometry==0?0.:(geometry==3?-950.:150.);
            const double y=geometry==2?2200.:250.;
            h.setLocation(x,y,0.);
            const double ax=geometry==2?0.45*v.recs.front().rec_width.val:0.;
            const double ay=geometry==3?0.45*v.recs.front().rec_height.val:0.;
            h.setAimPointFluxPlane(ax,ay,0.);
            Vect tower(-x,-y,v.recs.front().optical_height.Val()+ay);
            const double range=std::sqrt(tower.i*tower.i+tower.j*tower.j+tower.k*tower.k);
            Toolbox::unitvect(tower); h.setTowerVector(tower); h.setSlantRange(range);
            h.setFocalLengthX(range*(geometry==2?1.2:1.));
            h.setFocalLengthY(range*(geometry==3?0.85:1.));
            Vect sun=Ambient::calcSunVectorFromAzZen(geometry==0?0.:2.8,geometry==1?0.:0.6);
            Vect tracking(sun.i+tower.i,sun.j+tower.j,sun.k+tower.k);
            Toolbox::unitvect(tracking); h.setTrackVector(tracking);
            f.hermiteMirrorCoefs(h,v.sf.tht.val);
        callback(index,v,f,h,rec,sun);
        ++index;
    }
    return index;
}
#endif
