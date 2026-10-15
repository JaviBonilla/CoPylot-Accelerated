// Public synthetic and opt-in private integration bridge. Output contains status only.
extern "C" {
void* sp_data_create();bool sp_data_free(void*);
bool sp_load_from_script(void*,const char*);bool sp_generate_layout(void*,int);
bool sp_restore_loaded_layout(void*);bool sp_update_geometry(void*);
}
#include "SolarField.h"
#include "Heliostat.h"
#include "Receiver.h"
#include <iostream>
#include <stdexcept>
#include <string>
extern SolarField* imagePlaneDiagnosticField(void*);
static void require(bool ok) { if (!ok) throw std::runtime_error("Project state validation failed"); }
static bool point(const sp_point& a,const sp_point& b) { return a.x==b.x && a.y==b.y && a.z==b.z; }
int main(int argc,char** argv) {
    if (argc!=3) return 2;
    void* data=sp_data_create();
    try {
        require(sp_load_from_script(data,argv[1]));
        SolarField& sf=*imagePlaneDiagnosticField(data);
        auto& v=*sf.getVarMap();
        require(sf.getHeliostats()->empty());
        layout_shell serialized;
        SolarField::parseHeliostatXYZFile(v.sf.layout_data.val,serialized);
        auto receiver_state=[&]() {
            std::vector<double> state={v.sf.tht.val};
            for (auto& rec:v.recs) for (double value:{double(rec.rec_type.mapval()),double(rec.is_enabled.val),
                rec.rec_width.val,rec.rec_height.val,rec.rec_diameter.val,rec.rec_azimuth.val,rec.rec_elevation.val,
                rec.rec_offset_x.val,rec.rec_offset_y.val,rec.rec_offset_z.val}) state.push_back(value);
            return state;
        };
        const auto receiver_before=receiver_state();
        const bool generated=std::string(argv[2])=="generated";
        require(generated?sp_generate_layout(data,1):sp_restore_loaded_layout(data));
        const bool updated=std::string(argv[2])=="updated";
        if (updated) require(sp_update_geometry(data));
        const bool receiver_preserved=receiver_before==receiver_state();
        require(receiver_preserved);
        const auto& hs=*sf.getHeliostats();
        bool positions=hs.size()==serialized.size(),templates=positions,focus=positions,cant=positions,aims=positions,flags=positions;
        if (positions) for (unsigned i=0;i<hs.size();++i) {
            auto& row=serialized[i];auto& h=*hs[i];
            positions=positions && point(row.location,*h.getLocation());
            templates=templates && row.helio_type==h.getMasterTemplate()->getId();
            focus=focus && (!row.is_user_focus || (row.focal_x==h.getFocalX() && row.focal_y==h.getFocalY()));
            auto c=h.getCantVector();
            cant=cant && (!row.is_user_cant || (row.cant.i==c->i && row.cant.j==c->j && row.cant.k==c->k));
            aims=aims && (!row.is_user_aim || point(row.aim,*h.getAimPoint()));
            flags=flags && row.is_enabled==h.IsEnabled() && row.is_in_layout==h.IsInLayout();
        }
        if (!generated && !updated) require(positions && templates && focus && cant && aims && flags);
        std::cout<<"{\"prepared\":true,\"count\":"<<hs.size()<<",\"positions_preserved\":"<<positions
          <<",\"templates_preserved\":"<<templates<<",\"focus_preserved\":"<<focus<<",\"cant_preserved\":"<<cant
          <<",\"aims_preserved\":"<<aims<<",\"flags_preserved\":"<<flags<<",\"active_receivers\":"<<sf.getActiveReceiverCount()<<",\"receiver_configuration_preserved\":"<<receiver_preserved<<"}\n";
        require(sp_data_free(data));return 0;
    } catch (...) { sp_data_free(data);std::cerr<<"Project state check failed; private input details suppressed\n";return 1; }
}
