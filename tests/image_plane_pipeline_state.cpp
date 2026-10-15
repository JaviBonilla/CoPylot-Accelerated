// Verify canonical C++ optical state after every public CUDA return.
#include "image_plane_access.h"
#include "ImagePlaneInterceptComparison.h"
#include "ComputeBackend.h"
#include "SolarField.h"
#include <cstdlib>
#include <iostream>
#include <fstream>
#include <vector>
extern "C" {
void* sp_data_create();bool sp_data_free(void*);
bool sp_set_string(void*,const char*,const char*);bool sp_set_number(void*,const char*,double);
bool sp_assign_layout(void*,double*,int,int,int);bool sp_simulate(void*,int,bool);
bool sp_set_compute_backend(void*,int);const char* sp_get_last_backend_error(void*);
}
SolarField* imagePlaneDiagnosticField(void*);
static void require(bool ok,const char* why) { if (!ok) throw std::runtime_error(why); }
static void environment(const char* key,const char* value) {
#ifdef _WIN32
    _putenv_s(key,value);
#else
    setenv(key,value,1);
#endif
}
static std::vector<image_plane::Output> capture(SolarField& field) {
    std::vector<image_plane::Output> outputs(field.getHeliostats()->size());
    for (std::size_t i=0;i<outputs.size();++i) {
        auto* h=field.getHeliostats()->at(i);auto& out=outputs[i];
        matrix_t<double>* from[]={h->getSunShapeCoefObject(),h->getErrorDistCoefObject(),h->getMirrorShapeCoefObject(),h->getFluxMomentsObject()};
        image_plane::Matrix<7,7>* to[]={&out.sun,&out.errors,&out.mirror,&out.flux};
        for (int m=0;m<4;++m) { require(from[m]->ncells()==49,"Canonical moment matrix is not materialized");std::copy(from[m]->data(),from[m]->data()+49,to[m]->values); }
        require(h->getHermiteCoefObject()->ncells()==16,"Canonical coefficients are not materialized");
        std::copy(h->getHermiteCoefObject()->data(),h->getHermiteCoefObject()->data()+16,out.hermite.values);
        h->getImageSize(out.sigma[0],out.sigma[1]);out.intercept=h->getEfficiencyIntercept();out.updated=1;
    }
    return outputs;
}
int main(int argc,char** argv) {
    try {
        if (solarpilot::cuda_device_count()==0) return 77;
        const int count=argc>1?std::stoi(argv[1]):257;require(count>0,"Invalid field count");
        struct Context { void* data=sp_data_create();~Context() { if (data) sp_data_free(data); } } context;
        require(context.data!=nullptr,"Cannot create field context");
        require(sp_set_string(context.data,"ambient.0.weather_file",COPILOT_WEATHER),"Cannot set weather");
        const char* keys[]={"solarfield.0.q_des","solarfield.0.des_sim_detail","land.0.is_bounds_scaled","land.0.is_bounds_fixed",
            "land.0.min_fixed_rad","land.0.max_fixed_rad","fluxsim.0.flux_model","fluxsim.0.flux_time_type",
            "fluxsim.0.flux_solar_az_in","fluxsim.0.flux_solar_el_in","fluxsim.0.aim_method","fluxsim.0.x_res","fluxsim.0.y_res","fluxsim.0.flux_dni"};
        const double values[]={count/10.,0.,0.,1.,160.,5000.,0.,0.,180.,55.,0.,25.,25.,950.};
        for (int i=0;i<14;++i) require(sp_set_number(context.data,keys[i],values[i]),"Cannot configure field");
        std::vector<double> positions;
        for (int ring=0;int(positions.size()/4)<count;++ring) {
            const double radius=160.+35.*ring;const int n=int(2.*std::acos(-1.)*radius/35.);const double phase=(ring%2)*std::acos(-1.)/n;
            for (int j=0;j<n && int(positions.size()/4)<count;++j) {
                const double a=phase+2.*std::acos(-1.)*j/n;positions.insert(positions.end(),{0.,radius*std::sin(a),radius*std::cos(a),0.});
            }
        }
        require(sp_assign_layout(context.data,positions.data(),count,4,1),"Cannot assign field");
        environment("SOLARPILOT_INTERCEPT_PATH","flat");environment("SOLARPILOT_FLUX_PATH","flat");
        auto simulate=[&]() { if (!sp_simulate(context.data,1,true)) throw std::runtime_error(sp_get_last_backend_error(context.data)); };
        simulate();
        auto& field=*imagePlaneDiagnosticField(context.data);auto& flux=*field.getFluxObject();
        const auto cpu=capture(field);std::vector<image_plane::Output> full;
        image_plane::Comparison comparison;
        require(sp_set_compute_backend(context.data,1),sp_get_last_backend_error(context.data));
        for (const char* mode:{"v1","resident","resident"}) {
            environment("SOLARPILOT_INTERCEPT_PATH","cuda");environment("SOLARPILOT_IMAGE_PIPELINE",mode);
            environment("SOLARPILOT_IMAGE_BLOCK_SIZE",mode[0]=='v'?"128":"64");
            simulate();
            require(!ImagePlaneTestAccess::pending(flux),"Public simulate left pending optical materialization");
            const auto actual=capture(field);
            if (full.empty()) full=actual;
            else require(std::memcmp(full.data(),actual.data(),actual.size()*sizeof(image_plane::Output))==0,"Resident/full canonical state differs bitwise");
            for (std::size_t h=0;h<actual.size();++h) comparison.add(cpu[h],actual[h],h);
        }
        require(comparison.global.passed,"Canonical CUDA output differs from CPU beyond tolerance");
        require(sp_set_compute_backend(context.data,0),"Cannot switch back to CPU");environment("SOLARPILOT_INTERCEPT_PATH","flat");
        simulate();
        const auto again=capture(field);require(std::memcmp(cpu.data(),again.data(),cpu.size()*sizeof(image_plane::Output))==0,"CPU after CUDA consumed stale optical state");
        std::ofstream file;if (argc>2) file.open(argv[2]);std::ostream& out=argc>2?file:std::cout;require(bool(out),"Cannot write canonical state result");
        out<<"{\"heliostats\":"<<count<<",\"values_per_heliostat\":215,\"full_resident_host_bitwise\":true,\"cpu_switch_bitwise\":true,\"eager_materialization\":true,\"errors\":";
        comparison.json(out);out<<"}\n";
        void* released=context.data;context.data=nullptr;require(sp_data_free(released),"Cannot release field context");return 0;
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
