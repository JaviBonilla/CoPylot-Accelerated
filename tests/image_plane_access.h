#ifndef COPILOT_IMAGE_PLANE_TEST_ACCESS_H
#define COPILOT_IMAGE_PLANE_TEST_ACCESS_H
#include "Flux.h"
#include "Heliostat.h"
#include "Receiver.h"
#include <algorithm>
// Friend access stays in native tests; no public SolarPILOT API is added.
struct ImagePlaneTestAccess {
    static const std::vector<image_plane::Input>& gpu_inputs(Flux& f) { return f._image_inputs; }
    static const std::vector<image_plane::Output>& gpu_outputs(Flux& f) { return f._image_outputs; }
    static double flat(Flux& f,var_map& v,Heliostat& h,Receiver* r,Vect* s) { return f.imagePlaneInterceptFlat(v,h,r,s); }
    static double legacy(Flux& f,var_map& v,Heliostat& h,Receiver* r,Vect* s) { return f.imagePlaneInterceptLegacy(v,h,r,s); }
    static bool prepare(Flux& f,var_map& v,Heliostat& h,Receiver* r,Vect* s,image_plane::Input& in) { return f.prepareImagePlane(v,h,r,s,in); }
    static const image_plane::Tables& tables(Flux& f) { return f._image_tables; }
    static void write(Flux& f,Heliostat& h,const image_plane::Output& out) { f.writeImagePlane(h,out); }
    static void capture(Heliostat& h,double intercept,double (&out)[215]) {
        int offset=0;
        for (auto m : {h.getSunShapeCoefObject(),h.getErrorDistCoefObject(),h.getMirrorShapeCoefObject(),h.getFluxMomentsObject(),h.getHermiteCoefObject()}) {
            std::copy(m->data(),m->data()+m->nrows()*m->ncols(),out+offset); offset+=m->nrows()*m->ncols();
        }
        out[212]=h.getImageSize()[0]; out[213]=h.getImageSize()[1]; out[214]=intercept;
    }
};
#endif
