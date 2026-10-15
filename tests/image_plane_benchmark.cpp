// Internal single-thread optical benchmark and complete image-state snapshot.
extern "C" {
void* sp_data_create();
bool sp_data_free(void*);
bool sp_set_string(void*,const char*,const char*);
bool sp_set_number(void*,const char*,double);
bool sp_assign_layout(void*,double*,int,int,int);
bool sp_simulate(void*,int,bool);
}
#include "SolarField.h"
#include "CoreProfile.h"
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
SolarField* imagePlaneDiagnosticField(void*);
static void require(bool ok) { if (!ok) throw std::runtime_error("Image-plane benchmark setup failed"); }
using Clock = std::chrono::steady_clock;
int main(int argc, char** argv) {
    try {
        const int count = argc > 1 ? std::stoi(argv[1]) : 1000;
        const int grid = argc > 2 ? std::stoi(argv[2]) : 25;
        const int repeats = argc > 3 ? std::stoi(argv[3]) : 7;
        const int warmups = 2;
        require(count > 0 && repeats > 0 && grid > 0);
        struct Context { void* data = sp_data_create(); ~Context() { sp_data_free(data); } } c;
        require(c.data != nullptr);
        require(sp_set_string(c.data, "ambient.0.weather_file", COPILOT_WEATHER));
        const char* keys[] = {"solarfield.0.q_des", "solarfield.0.des_sim_detail",
            "land.0.is_bounds_scaled", "land.0.is_bounds_fixed", "land.0.min_fixed_rad",
            "land.0.max_fixed_rad", "fluxsim.0.flux_model", "fluxsim.0.flux_time_type",
            "fluxsim.0.flux_solar_az_in", "fluxsim.0.flux_solar_el_in", "fluxsim.0.aim_method",
            "fluxsim.0.x_res", "fluxsim.0.y_res", "fluxsim.0.flux_dni"};
        const double values[] = {count/10.,0.,0.,1.,160.,5000.,0.,0.,180.,55.,0.,double(grid),double(grid),950.};
        for (int i=0; i<14; ++i) require(sp_set_number(c.data, keys[i], values[i]));
        std::vector<double> positions;
        for (int ring=0; int(positions.size()/4)<count; ++ring) {
            double radius=160.+35.*ring;
            int n=int(2.*std::acos(-1.)*radius/35.);
            double phase=(ring%2)*std::acos(-1.)/n;
            for (int j=0; j<n && int(positions.size()/4)<count; ++j) {
                double a=phase+2.*std::acos(-1.)*j/n;
                positions.insert(positions.end(), {0.,radius*std::sin(a),radius*std::cos(a),0.});
            }
        }
        require(sp_assign_layout(c.data, positions.data(), count, 4, 1));
        require(sp_simulate(c.data, 1, true));
        SolarField& field=*imagePlaneDiagnosticField(c.data);
        Flux& flux=*field.getFluxObject();
        Vect sun=Ambient::calcSunVectorFromAzZen(std::acos(-1.),35.*std::acos(-1.)/180.);
        auto evaluate=[&]() {
            for (auto h : *field.getHeliostats())
                flux.imagePlaneIntercept(*field.getVarMap(), *h, h->getWhichReceiver(), &sun);
        };
        for (int i=0; i<warmups; ++i) evaluate();
        std::vector<double> times;
        for (int i=0; i<repeats; ++i) {
            SP_PROFILE_SESSION("direct_intercept");
            auto start=Clock::now();
            evaluate();
            times.push_back(std::chrono::duration<double>(Clock::now()-start).count());
        }
        // No output retrieval or file I/O in the timed loop.
        if (argc > 4) {
            std::ofstream out(argv[4],std::ios::binary);
            for (auto h : *field.getHeliostats()) {
                const double intercept=flux.imagePlaneIntercept(*field.getVarMap(), *h, h->getWhichReceiver(), &sun);
                for (auto m : {h->getSunShapeCoefObject(),h->getErrorDistCoefObject(),h->getMirrorShapeCoefObject(),h->getFluxMomentsObject(),h->getHermiteCoefObject()})
                    for (size_t i=0; i<m->nrows()*m->ncols(); ++i) { double value=m->data()[i]; out.write(reinterpret_cast<char*>(&value),sizeof(value)); }
                out.write(reinterpret_cast<char*>(h->getImageSize()),2*sizeof(double));
                out.write(reinterpret_cast<const char*>(&intercept),sizeof(intercept));
            }
            require(bool(out));
        }
        auto hv=field.getHeliostats()->front()->getVarMap();
        std::cout << std::setprecision(17) << "{\"heliostats\":" << count << ",\"grid\":" << grid
          << ",\"warmups\":" << warmups << ",\"repetitions\":" << repeats
          << ",\"facets_x\":" << hv->n_cant_x.val << ",\"facets_y\":" << hv->n_cant_y.val
          << ",\"faceted\":" << int(hv->is_faceted.val) << ",\"cant_method\":" << hv->cant_method.mapval()
          << ",\"samples_s\":[";
        for (size_t i=0; i<times.size(); ++i) std::cout << (i ? "," : "") << times[i];
        std::cout << "]}\n";
    } catch(const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
