/* SPDX-License-Identifier: BSD-3-Clause */
// Interpose only this test process's cudaMalloc: fail after one successful grow.
#include "image_plane_fixtures.h"
#include "ComputeBackend.h"
#include <cuda_runtime_api.h>
#include <dlfcn.h>
#include <cstring>
#include <iostream>
#include <stdexcept>
static int fail_after=-1;
static int injected=0;
extern "C" cudaError_t cudaMalloc(void** pointer,std::size_t bytes) {
    using Allocate=cudaError_t (*)(void**,std::size_t);
    static auto allocate=reinterpret_cast<Allocate>(dlsym(RTLD_NEXT,"cudaMalloc"));
    if (!allocate) return cudaErrorUnknown;
    if (fail_after==0) { fail_after=-1;++injected;*pointer=nullptr;return cudaErrorMemoryAllocation; }
    const bool poison=fail_after>0;
    if (poison) --fail_after;
    const auto status=allocate(pointer,bytes);
    // A new allocation has no valid cached content; zeros expose accidental hits.
    if (status==cudaSuccess && poison) return cudaMemset(*pointer,0,bytes);
    return status;
}
static void require(bool ok,const char* why) { if (!ok) throw std::runtime_error(why); }
int main() {
 try {
    if (!solarpilot::cuda_device_count()) return 77;
    int failures=0;
    auto cached=solarpilot::make_image_plane_gpu_context(0),direct=solarpilot::make_image_plane_gpu_context(0);
    cached->temporal_residency=true;
    image_plane::Input input={};image_plane::Tables tables={};
    for_each_image_plane_fixture([&](unsigned index,var_map& v,Flux& f,Heliostat& h,Receiver& r,Vect& sun) {
      if (!index) { require(ImagePlaneTestAccess::prepare(f,v,h,&r,&sun,input),"Fixture preparation");tables=ImagePlaneTestAccess::tables(f); }
    });
    image_plane::Input inputs[]={input,input};image_plane::Output expected,actual,larger[2];
    direct->evaluate(&input,1,tables,&expected);cached->evaluate(&input,1,tables,&actual);
    fail_after=1;
    try { cached->evaluate(inputs,2,tables,larger); } catch (const std::exception&) { ++failures; }
    require(failures==1 && injected==1 && fail_after==-1,"Image grow must fail at second allocation");
    try {
      cached->evaluate(&input,1,tables,&actual);
      if (std::memcmp(&expected,&actual,sizeof(actual)) || cached->statistics.input_h2d_bytes!=sizeof(input)) {
        std::cerr<<"Image recovery reused cache after replacing its input buffer\n";++failures;
      }
    } catch (const std::exception& e) { std::cerr<<"Image recovery: "<<e.what()<<'\n';++failures; }
    auto density=solarpilot::make_gpu_context(0),reference=solarpilot::make_gpu_context(0);
    density->temporal_residency=true;
    flux_density::HeliostatData h={};h.direction[1]=1.;h.aim[2]=100.;h.sigma_x=.02;h.sigma_y=.03;h.normalization=.1;h.coefficients[0]=1.;
    flux_density::CellData cells[2]={{{1.,2.,100.},{0.,1.,0.}},{{1.,2.,100.},{0.,1.,0.}}};
    double a[2],b[2];const flux_density::Parameters parameters={100.,std::acos(-1.)};
    reference->evaluate_flux(&h,1,cells,1,parameters,a);density->evaluate_flux(&h,1,cells,1,parameters,b);
    fail_after=1;bool threw=false;
    try { density->evaluate_flux(&h,1,cells,2,parameters,b); } catch (const std::exception&) { threw=true; }
    require(threw && injected==2 && fail_after==-1,"Density grow must fail at second allocation");
    try {
      density->evaluate_flux(&h,1,cells,1,parameters,b);
      if (std::memcmp(a,b,sizeof(double)) || density->statistics.cell_h2d_bytes!=sizeof(cells[0])) {
        std::cerr<<"Density recovery reused cache after replacing its cell buffer\n";++failures;
      }
    } catch (const std::exception& e) { std::cerr<<"Density recovery: "<<e.what()<<'\n';++failures; }
    require(failures==1,"Recovery failed after injected allocation failures");
    std::cout<<"PASS: both caches reupload after successful buffer growth followed by injected OOM\n";return 0;
 } catch (const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
