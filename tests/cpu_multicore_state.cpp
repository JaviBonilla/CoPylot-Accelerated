// Public synthetic and opt-in restored-project bitwise CPU threading anchors.
#include "SolarField.h"
#include "Heliostat.h"
#include "Receiver.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <vector>
extern "C" {
void* sp_data_create(); bool sp_data_free(void*);
bool sp_set_string(void*,const char*,const char*); bool sp_set_number(void*,const char*,double);
bool sp_assign_layout(void*,double*,int,int,int); bool sp_simulate(void*,int,bool);
bool sp_load_from_script(void*,const char*); bool sp_restore_loaded_layout(void*);
}
extern SolarField* imagePlaneDiagnosticField(void*);
static void require(bool ok) { if (!ok) throw std::runtime_error("Multicore state validation failed"); }
static void environment(const char* key,const char* value) {
#ifdef _WIN32
    _putenv_s(key,value);
#else
    setenv(key,value,1);
#endif
}
static std::vector<double> capture(SolarField& field) {
    std::vector<double> values;
    for (auto* h:*field.getHeliostats()) {
        for (auto* m:{h->getSunShapeCoefObject(),h->getErrorDistCoefObject(),h->getMirrorShapeCoefObject(),
                     h->getFluxMomentsObject(),h->getHermiteCoefObject()}) {
            require(m->ncells()==49 || m->ncells()==16);
            values.insert(values.end(),m->data(),m->data()+m->ncells());
        }
        values.push_back(h->getImageSize()[0]); values.push_back(h->getImageSize()[1]);
        values.push_back(h->getEfficiencyIntercept());
    }
    for (auto* r:*field.getReceivers()) for (auto& surface:*r->getFluxSurfaces())
        for (auto& column:*surface.getFluxMap()) for (auto& p:column) values.push_back(p.flux);
    return values;
}
static void equal(const std::vector<double>& a,const std::vector<double>& b) {
    require(a.size()==b.size()); require(std::memcmp(a.data(),b.data(),a.size()*sizeof(double))==0);
}
int main(int argc,char** argv) {
    void* data=sp_data_create();
    try {
        require(data!=nullptr);
        const bool flat=argc==2 && std::string(argv[1])=="--flat";
        if (argc==2 && !flat) { require(sp_load_from_script(data,argv[1])); require(sp_restore_loaded_layout(data)); }
        else {
            require(sp_set_string(data,"ambient.0.weather_file",COPILOT_WEATHER));
            const char* keys[]={"solarfield.0.des_sim_detail","land.0.is_bounds_scaled","land.0.is_bounds_fixed",
                "land.0.min_fixed_rad","land.0.max_fixed_rad","fluxsim.0.flux_model","fluxsim.0.flux_time_type",
                "fluxsim.0.flux_solar_az_in","fluxsim.0.flux_solar_el_in","fluxsim.0.aim_method",
                "fluxsim.0.x_res","fluxsim.0.y_res","fluxsim.0.flux_dni"};
            const double v[]={0,0,1,160,5000,0,0,180,55,0,7,3,950};
            for (int i=0;i<13;++i) require(sp_set_number(data,keys[i],v[i]));
            if (flat) {
                require(sp_set_number(data,"receiver.0.rec_type",2));
                require(sp_set_number(data,"receiver.0.rec_width",8));
                require(sp_set_number(data,"receiver.0.rec_height",6));
                require(sp_set_number(data,"solarfield.0.tht",80));
                require(sp_set_number(data,"heliostat.0.width",4));
                require(sp_set_number(data,"heliostat.0.height",5));
            }
            std::vector<double> pos;
            for (int i=0;i<7;++i) pos.insert(pos.end(),{0.,double(i-3)*40.,220.,0.});
            require(sp_assign_layout(data,pos.data(),7,4,1));
        }
        environment("SOLARPILOT_FLUX_PATH","flat"); environment("SOLARPILOT_INTERCEPT_PATH","flat");
        require(sp_simulate(data,1,true));
        auto& field=*imagePlaneDiagnosticField(data);
        const auto expected=capture(field);
        const int counts[]={2,4,8,12,24,1,12,1,12,24,4,1};
        for (int n:counts) for (int repeat=0;repeat<2;++repeat) {
            require(sp_simulate(data,n,true)); equal(expected,capture(field));
        }
        environment("SOLARPILOT_FLUX_PATH","legacy");environment("SOLARPILOT_INTERCEPT_PATH","legacy");
        require(sp_simulate(data,24,true)); equal(expected,capture(field));
        require(sp_simulate(data,1,true)); equal(expected,capture(field));
        const auto count=field.getHeliostats()->size();
        require(sp_data_free(data));data=nullptr;
        std::cout<<"{\"passed\":true,\"heliostats\":"<<count
                 <<",\"values_per_heliostat\":215,\"maps_and_optics_bitwise\":true,\"legacy_bitwise\":true,\"repeated_thread_count_transitions\":24}\n";
        return 0;
    } catch (...) { if(data)sp_data_free(data);std::cerr<<"CPU multicore validation failed; input details suppressed\n";return 1; }
}
