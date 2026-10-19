// Calendar-only adapter. Uses exactly PerformanceSimulationPrep's Hour/Day path.
#include "Ambient.h"
#include "Toolbox.h"
#include <cmath>
extern "C" bool phase5a_sun(double latitude, double longitude, double timezone,
                            int month, int day, double hour, double* output) {
    if (!output || month<1 || month>12 || day<1 || day>31 ||
        !std::isfinite(hour) || hour<0 || hour>=24) return false;
    try {
        DateTime dt;
        Ambient::setDateTime(dt, hour, dt.GetDayOfYear(2011, month, day));
        double az, zen;
        Ambient::calcSunPosition(latitude, longitude, timezone, 0., dt, &az, &zen);
        output[0]=az; output[1]=90.-zen;
        return std::isfinite(az) && std::isfinite(zen);
    } catch (...) { return false; }
}
