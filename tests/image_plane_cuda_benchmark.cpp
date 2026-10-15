#include "SolarField.h"
#include "image_plane_access.h"
#include "ImagePlaneInterceptComparison.h"
#include "ComputeBackend.h"
#include "image_plane_gpu_window.h"
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <vector>
extern "C" {
void* sp_data_create();bool sp_data_free(void*);
bool sp_set_string(void*,const char*,const char*);bool sp_set_number(void*,const char*,double);
bool sp_assign_layout(void*,double*,int,int,int);bool sp_simulate(void*,int,bool);
}
SolarField* imagePlaneDiagnosticField(void*);
static void require(bool ok,const char* why) { if (!ok) throw std::runtime_error(why); }
using Clock=std::chrono::steady_clock;
int main(int argc,char** argv) {
    try {
        const int count=argc>1?std::stoi(argv[1]):1000;
        const int repetitions=argc>2?std::stoi(argv[2]):5;
        const bool timing=argc>3 && std::string(argv[3])=="timing";
        require(count>0 && repetitions>0,"Invalid image-plane benchmark size/repeats");
        // Reject timing before creating any device context; correctness needs no idle window.
        ImagePlaneGpuWindow window;if (timing) window.begin();
        struct Context { void* data=sp_data_create();~Context() { if (data) sp_data_free(data); } } api;
        require(api.data!=nullptr,"CoPylot context failed");
        require(sp_set_string(api.data,"ambient.0.weather_file",COPILOT_WEATHER),"Weather setup failed");
        const char* keys[]={"solarfield.0.q_des","solarfield.0.des_sim_detail","land.0.is_bounds_scaled","land.0.is_bounds_fixed",
            "land.0.min_fixed_rad","land.0.max_fixed_rad","fluxsim.0.flux_model","fluxsim.0.flux_time_type",
            "fluxsim.0.flux_solar_az_in","fluxsim.0.flux_solar_el_in","fluxsim.0.aim_method","fluxsim.0.x_res","fluxsim.0.y_res","fluxsim.0.flux_dni"};
        const double values[]={count/10.,0.,0.,1.,160.,5000.,0.,0.,180.,55.,0.,25.,25.,950.};
        for (int i=0;i<14;++i) require(sp_set_number(api.data,keys[i],values[i]),"Case setup failed");
        std::vector<double> positions;
        for (int ring=0;int(positions.size()/4)<count;++ring) {
            const double radius=160.+35.*ring;const int n=int(2.*std::acos(-1.)*radius/35.);
            const double phase=(ring%2)*std::acos(-1.)/n;
            for (int j=0;j<n && int(positions.size()/4)<count;++j) {
                const double a=phase+2.*std::acos(-1.)*j/n;
                positions.insert(positions.end(),{0.,radius*std::sin(a),radius*std::cos(a),0.});
            }
        }
        require(sp_assign_layout(api.data,positions.data(),count,4,1),"Assigned layout failed");
        require(sp_simulate(api.data,1,true),"CPU field preparation failed");
        SolarField& field=*imagePlaneDiagnosticField(api.data);Flux& flux=*field.getFluxObject();
        require(field.getHeliostats()->size()==std::size_t(count),"Assigned field count differs from requested coverage");
        Vect sun=Ambient::calcSunVectorFromAzZen(std::acos(-1.),35.*std::acos(-1.)/180.);
        auto context=solarpilot::make_gpu_context(0);
        context->image_plane=solarpilot::make_image_plane_gpu_context(0);
        struct Selected {
            Flux& f;Selected(Flux& flux,solarpilot::GpuContext* c):f(flux) { f.setImagePlaneGpuContext(c); }
            ~Selected() { f.setImagePlaneGpuContext(nullptr); }
        } selected(flux,context.get());
        auto cpu=[&]() { for (auto h:*field.getHeliostats()) ImagePlaneTestAccess::flat(flux,*field.getVarMap(),*h,h->getWhichReceiver(),&sun); };
        auto gpu=[&]() { flux.imagePlaneInterceptCudaBatch(*field.getVarMap(),*field.getHeliostats(),&sun,timing);flux.clearImagePlaneBatch(); };
        for (int i=0;i<2;++i) { cpu();gpu();if (timing) window.check(); }
        const auto allocations=context->image_plane->statistics.allocations;
        std::vector<double> cpu_samples;std::vector<solarpilot::ImagePlaneGpuStatistics> gpu_samples;
        for (int i=0;i<repetitions;++i) {
            if (timing) window.check();
            const auto start=timing?Clock::now():Clock::time_point();cpu();
            if (timing) cpu_samples.push_back(std::chrono::duration<double>(Clock::now()-start).count());
            gpu();
            require(context->image_plane->statistics.allocations==allocations,"Repeated field evaluation allocated device memory");
            gpu_samples.push_back(context->image_plane->statistics);
            if (timing) window.check();
        }
        // Compare every heliostat and every output outside the preliminary timed intervals.
        image_plane::Comparison comparison;
        std::vector<image_plane::Output> previous=ImagePlaneTestAccess::gpu_outputs(flux);
        gpu();
        require(std::memcmp(previous.data(),ImagePlaneTestAccess::gpu_outputs(flux).data(),previous.size()*sizeof(image_plane::Output))==0,"Repeated field output was not bitwise deterministic");
        for (std::size_t h=0;h<previous.size();++h) {
            image_plane::Output expected;
            image_plane::evaluate(ImagePlaneTestAccess::gpu_inputs(flux)[h],ImagePlaneTestAccess::tables(flux),expected);
            comparison.add(expected,previous[h],h);
        }
        if (timing) window.check();
        const auto& stats=context->image_plane->statistics;
        std::cout<<std::setprecision(17)<<"{\"heliostats\":"<<count<<",\"grid\":[25,25],\"warmups\":2,\"repetitions\":"<<repetitions
            <<",\"gpu_timings_collected\":"<<(timing?"true":"false")<<",\"stage\":\"Phase 2D-B preliminary baseline\",\"errors\":";
        comparison.json(std::cout);
        std::cout<<",\"deterministic\":true,\"allocation_reuse\":true,\"allocations\":"<<stats.allocations
            <<",\"input_capacity\":"<<stats.input_capacity<<",\"output_capacity\":"<<stats.output_capacity
            <<",\"input_h2d_bytes\":"<<stats.input_h2d_bytes<<",\"tables_h2d_bytes\":"<<stats.tables_h2d_bytes<<",\"output_d2h_bytes\":"<<stats.output_d2h_bytes
            <<",\"cpu_flat_total_samples_s\":[";
        for (std::size_t i=0;i<cpu_samples.size();++i) std::cout<<(i?",":"")<<cpu_samples[i];
        std::cout<<"],\"cuda_samples\":[";
        if (timing) for (std::size_t i=0;i<gpu_samples.size();++i) {
            const auto& s=gpu_samples[i];std::cout<<(i?",":"")<<"{\"preparation_s\":"<<s.preparation_s<<",\"input_h2d_ms\":"<<s.input_h2d_ms
                <<",\"tables_h2d_ms\":"<<s.tables_h2d_ms<<",\"kernel_ms\":"<<s.kernel_ms<<",\"d2h_ms\":"<<s.d2h_ms
                <<",\"writeback_s\":"<<s.writeback_s<<",\"hybrid_total_s\":"<<s.total_s<<'}';
        }
        std::cout<<"],\"gpu_window\":{\"checks\":"<<window.checks<<",\"max_memory_mib\":"<<window.maximum_memory_mib
            <<",\"max_temperature_c\":"<<window.maximum_temperature_c<<",\"external_processes\":"<<(timing?"0":"null")<<"}}\n";
        context->close_all();
        require(comparison.global.passed,"Field CUDA image-plane output exceeded tolerance");
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
