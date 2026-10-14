#include "FluxDensityNumerics.h"
#include "Flux.h"
#include "Heliostat.h"
#include <cmath>
#include <iostream>
#include <cstring>
#include <stdexcept>

static double oracle(Flux& flux, Heliostat& source, const flux_density::HeliostatData& h,
                     const flux_density::CellData& c, const flux_density::Parameters& p) {
    Vect direction(h.direction[0], h.direction[1], h.direction[2]);
    Vect normal(c.normal[0], c.normal[1], c.normal[2]);
    const double cosine = Toolbox::dotprod(normal, direction);
    if (cosine < 0. || cosine > 1.) return 0.;
    sp_point aim(h.aim[0], h.aim[1], h.aim[2]);
    sp_point point(c.position[0], c.position[1], c.position[2]), intersection;
    Toolbox::plane_intersect(aim, direction, point, direction, intersection);
    intersection.Subtract(aim);
    Toolbox::rotation(p.pi-std::atan2(direction.i, direction.j), 2, intersection);
    Toolbox::rotation(std::acos(direction.k), 0, intersection);
    const double x = -intersection.x/p.tower_height/h.sigma_x;
    const double y = intersection.y/p.tower_height/h.sigma_y;
    const double hfe = flux.hermiteFluxEval(&source, x, y)*std::exp(-0.5*(x*x+y*y));
    return cosine*hfe*h.normalization;
}

int main() {
    Flux flux; flux.Setup();
    Heliostat source;
    source.getHermiteCoefObject()->resize(1, 16);
    const flux_density::Parameters p = {90., std::acos(-1.)};
    unsigned tested = 0;
    bool saw_positive = false, saw_clamp = false;
    for (int fixture = 0; fixture < 4; ++fixture) {
        flux_density::HeliostatData h = {};
        Vect direction(0.25+0.1*fixture, 0.65, -0.7); Toolbox::unitvect(direction);
        h.direction[0] = direction.i; h.direction[1] = direction.j; h.direction[2] = direction.k;
        h.aim[0] = 0.3; h.aim[1] = -0.7; h.aim[2] = 92.;
        h.sigma_x = 0.02; h.sigma_y = 0.03; h.normalization = 0.013;
        for (int term = 0; term < 16; ++term) {
            h.coefficients[term] = fixture == 3 ? (term == 0 ? -1. : 0.) : (term == 0 ? 1. : 0.0001*(term-7));
            source.getHermiteCoefObject()->at(term) = h.coefficients[term];
        }
        for (int point = 0; point < 6; ++point) {
            flux_density::CellData c = {{0.4*point-0.6, 0.2*point, 91.+point},
                                        {direction.i, direction.j, direction.k}};
            if (point == 3) for (int k = 0; k < 3; ++k) c.normal[k] *= -1.;
            if (point == 4) for (int k = 0; k < 3; ++k) c.normal[k] = 0.;
            if (point == 5) for (int k = 0; k < 3; ++k) c.normal[k] *= 2.;
            const double expected = oracle(flux, source, h, c, p);
            const double actual = flux_density::evaluate_contribution(h, c, p);
            if (!std::isfinite(actual) || std::abs(actual-expected) > 1.e-10+1.e-9*std::abs(expected))
                throw std::runtime_error("Flux numerical contribution differs from legacy calculation");
            saw_positive = saw_positive || actual > 0.;
            saw_clamp = saw_clamp || (fixture == 3 && point < 3 && actual == 0.);
            ++tested;
        }
    }
    if (!saw_positive || !saw_clamp) throw std::runtime_error("Fixtures did not exercise positive flux and negative-series clamp");
    std::cout << tested << " legacy/flat contribution fixtures passed; POD sizes "
              << sizeof(flux_density::HeliostatData) << '/' << sizeof(flux_density::CellData)
              << '/' << sizeof(flux_density::Parameters) << " bytes\n";
}
