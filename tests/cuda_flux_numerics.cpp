#include "ComputeBackend.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <vector>

static void require(bool ok, const char* message) { if (!ok) throw std::runtime_error(message); }
static flux_density::HeliostatData fixture(int index) {
    flux_density::HeliostatData h = {};
    const double x = 0.25+0.01*(index%4), y = 0.65, z = -0.7;
    const double length = std::sqrt(x*x+y*y+z*z);
    h.direction[0]=x/length; h.direction[1]=y/length; h.direction[2]=z/length;
    h.aim[0]=0.3; h.aim[1]=-0.7; h.aim[2]=92.;
    h.sigma_x=0.02; h.sigma_y=0.03; h.normalization=0.013;
    for (int term=0; term<16; ++term) h.coefficients[term] = term==0 ? 1. : 0.0001*(term-7);
    return h;
}
struct Errors {
    double absolute=0., relative=0., squares=0.;
    std::size_t count=0;
    void add(double expected, double actual) {
        const double error=std::abs(actual-expected);
        absolute=std::max(absolute,error);
        if (expected!=0.) relative=std::max(relative,error/std::abs(expected));
        squares+=error*error; ++count;
        require(std::isfinite(expected) && std::isfinite(actual) && error<=1.e-10+1.e-9*std::abs(expected), "CUDA numerical tolerance exceeded");
    }
};
int main(int argc, char** argv) {
    try {
        require(solarpilot::cuda_device_count()>0,"A CUDA device is required for CUDA numerical tests");
        auto context=solarpilot::make_gpu_context(0);
        const flux_density::Parameters parameters={90.,4.*std::atan(1.)};
        std::vector<flux_density::HeliostatData> h;
        std::vector<flux_density::CellData> points;
        for (int i=0;i<24;++i) {
            h.push_back(fixture(i));
            const flux_density::CellData cell={{0.4*(i%6)-0.6,0.2*(i%6),91.+(i%6)},
                {h.back().direction[0]*0.8,h.back().direction[1]*0.8,h.back().direction[2]*0.8}};
            points.push_back(cell);
            if (i%6==3) for (int k=0;k<3;++k) points.back().normal[k]*=-1.;
            if (i%6==4) for (int k=0;k<3;++k) points.back().normal[k]=0.;
            if (i%6==5) for (int k=0;k<3;++k) points.back().normal[k]*=2.;
            if (i>=18) { for (double& coefficient:h.back().coefficients) coefficient=0.; h.back().coefficients[0]=-1.; }
        }
        std::vector<double> actual(24);
        context->evaluate_pairs(h.data(),points.data(),24,parameters,actual.data());
        Errors contribution, map, reduction;
        for (std::size_t i=0;i<h.size();++i) contribution.add(flux_density::evaluate_contribution(h[i],points[i],parameters),actual[i]);
        bool saw_positive=false;
        for (double value:actual) saw_positive=saw_positive || value>0.;
        require(saw_positive,"Contribution fixtures must include positive output");
        for (int i=18;i<24;++i) require(actual[i]==0.,"Negative Hermite series must clamp to zero");
        const flux_density::CellData cell={{0.,0.,92.},{0.,0.7,-0.7}};
        std::size_t edge_cases=0;
        for (std::size_t count: {std::size_t(0),std::size_t(1),std::size_t(255),std::size_t(256),std::size_t(257),std::size_t(513)}) {
            h.clear(); for (std::size_t i=0;i<count;++i) h.push_back(fixture(static_cast<int>(i)));
            std::vector<flux_density::CellData> cells(6,cell);
            cells[1].normal[0]=0.; cells[1].normal[1]=-0.7; cells[1].normal[2]=0.7;
            for (int k=0;k<3;++k) cells[2].normal[k]=0.;
            std::vector<double> first(6),second(6),expected(6,0.);
            for (const auto& helio:h) for (std::size_t c=0;c<cells.size();++c) expected[c]+=flux_density::evaluate_contribution(helio,cells[c],parameters);
            context->evaluate_flux(h.data(),count,cells.data(),cells.size(),parameters,first.data());
            const auto allocations=context->statistics.allocations;
            context->evaluate_flux(h.data(),count,cells.data(),cells.size(),parameters,second.data());
            require(allocations==context->statistics.allocations,"Repeated input must reuse GPU allocation capacity");
            require(std::memcmp(first.data(),second.data(),6*sizeof(double))==0,"CUDA reduction must be bitwise reproducible");
            for (std::size_t c=0;c<cells.size();++c) map.add(expected[c],first[c]);
            require(first[1]==0. && first[2]==0.,"Invisible and zero-cosine cells must contribute zero");
            context->evaluate_flux(h.data(),count,&cell,1,parameters,second.data());
            map.add(expected[0],second[0]); // one cell, including H=0
            if (count) {
                std::vector<flux_density::CellData> pair_cells(count,cell);
                std::vector<double> values(count);
                context->evaluate_pairs(h.data(),pair_cells.data(),count,parameters,values.data());
                double sequential=0.; for (double value:values) sequential+=value;
                reduction.add(sequential,first[0]);
            }
            ++edge_cases;
        }
        bool rejected=false;
        try { context->evaluate_flux(h.data(),h.size(),&cell,1,parameters,actual.data(),127); }
        catch (const std::exception&) { rejected=true; }
        require(rejected,"Unsupported block size must be rejected");
        context->close();
        if (argc>1) {
            std::ofstream out(argv[1]); require(bool(out),"Unable to write CUDA numerical results");
            out<<std::setprecision(17)<<"{\n  \"block_size\": 256,\n  \"contribution_cases\": 24,\n  \"edge_counts\": [0, 1, 255, 256, 257, 513],\n  \"contribution_max_abs\": "<<contribution.absolute
               <<",\n  \"contribution_max_rel\": "<<contribution.relative<<",\n  \"map_max_abs\": "<<map.absolute<<",\n  \"map_max_rel\": "<<map.relative
               <<",\n  \"reduction_only_max_abs\": "<<reduction.absolute<<",\n  \"reduction_only_max_rel\": "<<reduction.relative
               <<",\n  \"deterministic\": true,\n  \"allocation_reuse\": true,\n  \"precision\": \"double\",\n  \"rtol\": 1e-9,\n  \"atol\": 1e-10,\n  \"gpu_timings_collected\": false\n}\n";
            require(bool(out),"Unable to finish CUDA numerical results");
        }
        std::cout<<"PASS: 24 CUDA contributions; "<<edge_cases<<" edge counts; fixed double reduction, deterministic repeats and allocation reuse\n";
        return 0;
    } catch (const std::exception& error) { std::cerr<<error.what()<<'\n'; return 1; }
}
