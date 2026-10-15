#include "image_plane_access.h"
#include "Ambient.h"
#include <cmath>
#include <cstring>
#include <iostream>
#include <stdexcept>
static void require(bool ok,const char* why) { if (!ok) throw std::runtime_error(why); }
int main() {
    try {
        unsigned fixtures=0;
        // Independent optical fixtures: no simulate(), density map or benchmark bridge.
        for (int sun_model : {0,1,2,4}) for (int cant : {0,-1,1})
        for (int geometry=0; geometry<5; ++geometry) {
            var_map v; v.reset();
            v.flux.aim_method.combo_select_by_mapval(0);
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
            const double ax=geometry==2?0.45*v.recs.front().rec_diameter.val:0.;
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
            const double efficiency=ImagePlaneTestAccess::legacy(f,v,h,&rec,&sun);
            double expected[215],actual[215]; ImagePlaneTestAccess::capture(h,efficiency,expected);
            image_plane::Input input;
            require(ImagePlaneTestAccess::prepare(f,v,h,&rec,&sun,input),"Fixture unexpectedly outside Flat dispatch");
            image_plane::Output output;
            image_plane::evaluate(input,ImagePlaneTestAccess::tables(f),output);
            require(output.updated,"Visible fixture did not update image");
            ImagePlaneTestAccess::write(f,h,output);
            ImagePlaneTestAccess::capture(h,output.intercept,actual);
            for (int i=0; i<215; ++i) require(std::isfinite(actual[i]),"Nonfinite direct optical fixture");
            if (std::memcmp(expected,actual,sizeof(expected))!=0) {
                for (int i=0; i<215; ++i) if (std::memcmp(expected+i,actual+i,8)!=0)
                    std::cerr << "difference fixture " << fixtures << " value " << i << " expected " << expected[i] << " actual " << actual[i] << '\n';
                throw std::runtime_error("Direct Legacy/Flat image state is not bitwise equal");
            }
            // Repeated independent evaluation does not consume old optical outputs.
            image_plane::Output again;
            image_plane::evaluate(input,ImagePlaneTestAccess::tables(f),again);
            require(std::memcmp(again.flux.values,output.flux.values,sizeof(output.flux))==0,"Core consumed hidden mutable state");
            // A back-facing aperture returns zero and leaves H state untouched in both paths.
            input.visible=false;
            image_plane::evaluate(input,ImagePlaneTestAccess::tables(f),again);
            require(!again.updated && again.intercept==0.,"Invisible core behavior");
            ImagePlaneTestAccess::write(f,h,again);
            ImagePlaneTestAccess::capture(h,output.intercept,actual);
            require(std::memcmp(expected,actual,sizeof(expected))==0,"Invisible writeback changed old state");
            Vect away(-tower.i,-tower.j,-tower.k); h.setTowerVector(away);
            require(ImagePlaneTestAccess::legacy(f,v,h,&rec,&sun)==0.,"Back-facing legacy intercept");
            require(ImagePlaneTestAccess::prepare(f,v,h,&rec,&sun,input) && !input.visible,"Back-facing adapter visibility");
            image_plane::evaluate(input,ImagePlaneTestAccess::tables(f),again);
            ImagePlaneTestAccess::write(f,h,again);
            ImagePlaneTestAccess::capture(h,output.intercept,actual);
            require(std::memcmp(expected,actual,sizeof(expected))==0,"Back-facing legacy/flat changed old state");
            ++fixtures;
        }
        std::cout << "{\"fixtures\":" << fixtures << ",\"values_per_fixture\":215,\"bitwise\":true,\"max_abs\":0,\"max_rel\":0,\"rms\":0,\"input_bytes\":"
          << sizeof(image_plane::Input) << ",\"output_bytes\":" << sizeof(image_plane::Output)
          << ",\"tables_bytes\":" << sizeof(image_plane::Tables) << ",\"facet_capacity\":64}\n";
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
