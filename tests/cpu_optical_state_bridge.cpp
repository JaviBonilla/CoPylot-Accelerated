// Diagnostic test bridge: compare live-context optical state without serializing geometry.
#include "SolarField.h"
#include "Heliostat.h"
#include <cmath>
#include <cstring>
#include <stdexcept>
#include <vector>
extern SolarField* imagePlaneDiagnosticField(void*);
static std::vector<double> capture(void* context) {
    if (!context) throw std::runtime_error("Missing test context");
    std::vector<double> values;
    const auto& heliostats=*imagePlaneDiagnosticField(context)->getHeliostats();
    values.reserve(heliostats.size()*215);
    for (auto* h:heliostats) {
        for (auto* m:{h->getSunShapeCoefObject(),h->getErrorDistCoefObject(),h->getMirrorShapeCoefObject(),
                     h->getFluxMomentsObject(),h->getHermiteCoefObject()}) {
            const auto expected=m==h->getHermiteCoefObject()?16u:49u;
            if (m->ncells()!=expected) throw std::runtime_error("Incomplete test optical state");
            values.insert(values.end(),m->data(),m->data()+m->ncells());
        }
        values.push_back(h->getImageSize()[0]);values.push_back(h->getImageSize()[1]);
        values.push_back(h->getEfficiencyIntercept());
    }
    for (auto value:values) if (!std::isfinite(value)) throw std::runtime_error("Nonfinite test optical state");
    return values;
}
extern "C" void* phase4_optical_capture(void* context) {
    try { return new std::vector<double>(capture(context)); } catch (...) { return nullptr; }
}
extern "C" bool phase4_optical_equal(void* snapshot,void* context) {
    try {
        if(!snapshot)return false;
        const auto& before=*static_cast<std::vector<double>*>(snapshot);const auto after=capture(context);
        return before.size()==after.size() && std::memcmp(before.data(),after.data(),before.size()*sizeof(double))==0;
    } catch (...) { return false; }
}
extern "C" std::size_t phase4_optical_size(void* snapshot) {
    return snapshot?static_cast<std::vector<double>*>(snapshot)->size():0;
}
// Untimed cross-binary regression export; callers keep optical arrays ignored.
extern "C" bool phase4_optical_copy(void* snapshot,double* output,std::size_t capacity) {
    if (!snapshot || !output) return false;
    const auto& values=*static_cast<std::vector<double>*>(snapshot);
    if (capacity!=values.size()) return false;
    std::memcpy(output,values.data(),values.size()*sizeof(double));
    return true;
}
extern "C" void phase4_optical_free(void* snapshot) { delete static_cast<std::vector<double>*>(snapshot); }
