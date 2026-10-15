#include "image_plane_fixtures.h"
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
        fixtures=for_each_image_plane_fixture([&](unsigned fixture_index,var_map& v,Flux& f,Heliostat& h,Receiver& rec,Vect& sun) {
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
                    std::cerr << "difference fixture " << fixture_index << " value " << i << " expected " << expected[i] << " actual " << actual[i] << '\n';
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
            const Vect tower=*h.getTowerVector();
            Vect away(-tower.i,-tower.j,-tower.k); h.setTowerVector(away);
            require(ImagePlaneTestAccess::legacy(f,v,h,&rec,&sun)==0.,"Back-facing legacy intercept");
            require(ImagePlaneTestAccess::prepare(f,v,h,&rec,&sun,input) && !input.visible,"Back-facing adapter visibility");
            image_plane::evaluate(input,ImagePlaneTestAccess::tables(f),again);
            ImagePlaneTestAccess::write(f,h,again);
            ImagePlaneTestAccess::capture(h,output.intercept,actual);
            require(std::memcmp(expected,actual,sizeof(expected))==0,"Back-facing legacy/flat changed old state");
        });
        std::cout << "{\"fixtures\":" << fixtures << ",\"values_per_fixture\":215,\"bitwise\":true,\"max_abs\":0,\"max_rel\":0,\"rms\":0,\"input_bytes\":"
          << sizeof(image_plane::Input) << ",\"output_bytes\":" << sizeof(image_plane::Output)
          << ",\"tables_bytes\":" << sizeof(image_plane::Tables) << ",\"facet_capacity\":64}\n";
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
