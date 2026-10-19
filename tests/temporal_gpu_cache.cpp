/* SPDX-License-Identifier: BSD-3-Clause */
#include "image_plane_fixtures.h"
#include "ComputeBackend.h"
#include "TemporalUploadCache.h"
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <vector>
static void require(bool ok,const char* why) { if (!ok) throw std::runtime_error(why); }
int main() {
 try {
    solarpilot::TemporalUploadCache<flux_density::CellData> host;
    flux_density::CellData point={{1.,2.,100.},{0.,1.,0.}};
    require(!host.matches(&point,1),"Empty cache hit");host.commit(&point,1);
    auto copy=point;require(host.matches(&copy,1),"Content equality needs no stable address");
    copy.position[2]+=1.;require(!host.matches(&copy,1),"Same shape hid geometry change");
    require(!host.matches(&point,0),"Count change hit");host.invalidate();require(!host.matches(&point,1),"Invalidated cache hit");
    if (!solarpilot::cuda_device_count()) return 77;
    auto cached=solarpilot::make_image_plane_gpu_context(0),direct=solarpilot::make_image_plane_gpu_context(0);
    cached->temporal_residency=true;
    image_plane::Input input={};image_plane::Tables tables={};
    for_each_image_plane_fixture([&](unsigned index,var_map& v,Flux& f,Heliostat& h,Receiver& r,Vect& sun) {
      if (!index) { require(ImagePlaneTestAccess::prepare(f,v,h,&r,&sun,input),"Fixture preparation");tables=ImagePlaneTestAccess::tables(f); }
    });
    image_plane::Output expected,actual;
    for (int step=0;step<6;++step) {
      if (step==2) tables.sun.values[0]*=1.01;
      if (step==3) cached->temporal_residency=false;
      if (step==4) cached->temporal_residency=true;
      if (step==5) cached->close();
      direct->evaluate(&input,1,tables,&expected);cached->evaluate(&input,1,tables,&actual);
      require(std::memcmp(&expected,&actual,sizeof(actual))==0,"Cached table output differs");
      require(cached->statistics.tables_h2d_bytes==(step==1?0:sizeof(tables)),"Table invalidation/transfer counter incorrect");
    }
    auto density=solarpilot::make_gpu_context(0),reference=solarpilot::make_gpu_context(0);
    density->temporal_residency=true;
    flux_density::HeliostatData h={};h.direction[1]=1.;h.aim[2]=100.;h.sigma_x=.02;h.sigma_y=.03;h.normalization=.1;h.coefficients[0]=1.;
    std::vector<flux_density::CellData> cells(3,point);double a[8],b[8];
    const flux_density::Parameters parameters={100.,std::acos(-1.)};
    for (int step=0;step<7;++step) {
      if (step==2) cells[0].position[2]+=1.;
      if (step==3) cells.resize(5,point);
      if (step==4) density->temporal_residency=false;
      if (step==5) density->temporal_residency=true;
      if (step==6) density->close();
      reference->evaluate_flux(&h,1,cells.data(),cells.size(),parameters,a);
      density->evaluate_flux(&h,1,cells.data(),cells.size(),parameters,b);
      require(std::memcmp(a,b,cells.size()*sizeof(double))==0,"Cached receiver cells differ");
      require(density->statistics.cell_h2d_bytes==(step==1?0:cells.size()*sizeof(point)),"Cell invalidation/transfer counter incorrect");
    }
    std::cout<<"PASS: content/shape mutations, toggles, close/reallocation and direct CUDA equality\n";return 0;
 } catch (const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
