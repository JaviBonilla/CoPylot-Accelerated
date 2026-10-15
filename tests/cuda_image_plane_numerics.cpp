#include "image_plane_fixtures.h"
#include "ComputeBackend.h"
#include "ImagePlaneInterceptComparison.h"
#include <fstream>
#include <iostream>
#include <limits>
#include <vector>
static void require(bool ok,const char* message) { if (!ok) throw std::runtime_error(message); }
int main(int argc,char** argv) {
    try {
        const int devices=solarpilot::cuda_device_count();
        if (!devices) { std::cout<<"SKIP: no CUDA device\n";return 77; }
        require(devices>0,solarpilot::cuda_probe_error());
        auto context=solarpilot::make_image_plane_gpu_context(0);
        const auto layout=context->device_layout();
        require(layout==solarpilot::image_plane_host_layout(),"Host/device image-plane layout mismatch");
        image_plane::Comparison fixtures,edges,resident_fixtures,resident_edges;
        image_plane::Input representative={};image_plane::Tables tables={};
        bool deterministic=true;
        const unsigned count=for_each_image_plane_fixture([&](unsigned index,var_map& v,Flux& f,Heliostat& h,Receiver& rec,Vect& sun) {
            image_plane::Input input={};
            require(ImagePlaneTestAccess::prepare(f,v,h,&rec,&sun,input),"Unsupported fixture");
            image_plane::Output expected,actual,again;
            image_plane::evaluate(input,ImagePlaneTestAccess::tables(f),expected);
            context->evaluate(&input,1,ImagePlaneTestAccess::tables(f),&actual);
            const auto allocations=context->statistics.allocations;
            context->evaluate(&input,1,ImagePlaneTestAccess::tables(f),&again);
            deterministic=deterministic && std::memcmp(&actual,&again,sizeof(actual))==0;
            require(context->statistics.allocations==allocations,"Repeated image-plane fixture allocated device memory");
            fixtures.add(expected,actual,index);
            solarpilot::ImagePlaneRequiredOutput required;
            image_plane::Output materialized;
            context->evaluate_resident(&input,1,ImagePlaneTestAccess::tables(f),&required);
            context->download_outputs(&materialized,1);
            require(required.valid==1 && required.updated==actual.updated && required.intercept==actual.intercept,"Required output differs from complete output");
            require(std::memcmp(&actual,&materialized,sizeof(actual))==0,"Resident fixture output differs bitwise from full-output CUDA");
            resident_fixtures.add(expected,materialized,index);
            if (index==0) { representative=input;tables=ImagePlaneTestAccess::tables(f); }
        });
        std::size_t previous_allocations=0;
        for (std::size_t n:{std::size_t(0),std::size_t(1),std::size_t(63),std::size_t(64),std::size_t(65),std::size_t(127),std::size_t(128),std::size_t(129),std::size_t(255),std::size_t(256),std::size_t(257),std::size_t(259),std::size_t(1000),std::size_t(5000),std::size_t(10000),std::size_t(1),std::size_t(0)}) {
            std::vector<image_plane::Input> inputs(n,representative);
            if (n>1) inputs[1].visible=0;
            std::vector<image_plane::Output> expected(n),actual(n),again(n);
            for (std::size_t i=0;i<n;++i) image_plane::evaluate(inputs[i],tables,expected[i]);
            context->evaluate(inputs.data(),n,tables,actual.data());
            const auto stats=context->statistics;
            context->evaluate(inputs.data(),n,tables,again.data());
            require(stats.allocations==context->statistics.allocations,"Repeated image-plane buffers did not reuse capacity");
            require(n!=1 || stats.input_capacity<10000 || stats.allocations==previous_allocations,"Smaller after larger allocated image-plane buffers");
            deterministic=deterministic && (n==0 || std::memcmp(actual.data(),again.data(),n*sizeof(image_plane::Output))==0);
            for (std::size_t i=0;i<n;++i) edges.add(expected[i],actual[i],i);
            std::vector<solarpilot::ImagePlaneRequiredOutput> required(n);
            context->evaluate_resident(inputs.data(),n,tables,required.data());
            const auto resident_allocations=context->statistics.allocations;
            context->evaluate_resident(inputs.data(),n,tables,required.data());
            require(context->statistics.allocations==resident_allocations,"Resident repeat allocated device buffers");
            context->download_outputs(again.data(),n);
            require(n==0 || std::memcmp(actual.data(),again.data(),n*sizeof(image_plane::Output))==0,"Resident/full edge output differs bitwise");
            for (std::size_t i=0;i<n;++i) resident_edges.add(expected[i],again[i],i);
            previous_allocations=context->statistics.allocations;
        }
        bool rejected=false;
        auto invalid=representative;invalid.cant_method=4;image_plane::Output output;
        try { context->evaluate(&invalid,1,tables,&output); } catch (const std::exception&) { rejected=true; }
        require(rejected,"Unsupported CUDA canting silently accepted");
        rejected=false;
        try { auto bad=solarpilot::make_image_plane_gpu_context(devices); } catch (const std::exception&) { rejected=true; }
        require(rejected,"Invalid CUDA image-plane device accepted");
        auto bad_tables=tables;bad_tables.sun.values[0]=std::numeric_limits<double>::quiet_NaN();
        solarpilot::ImagePlaneRequiredOutput required;
        rejected=false;
        try { context->evaluate_resident(&representative,1,bad_tables,&required); } catch (const std::exception&) { rejected=true; }
        require(rejected,"Resident validation accepted nonfinite optical output");
        image_plane::Output expected_recovery;
        image_plane::evaluate(representative,tables,expected_recovery);
        context->evaluate(&representative,1,tables,&output);
        image_plane::Comparison recovery;recovery.add(expected_recovery,output,0);
        require(recovery.global.passed,"Valid CUDA image-plane context did not recover after rejected inputs/device");
        auto density=solarpilot::make_gpu_context(0);density->image_plane=solarpilot::make_image_plane_gpu_context(0);
        for (std::size_t n:{std::size_t(0),std::size_t(1),std::size_t(63),std::size_t(64),std::size_t(65),std::size_t(257),std::size_t(1000),std::size_t(1)}) {
            std::vector<image_plane::Input> inputs(n,representative);std::vector<image_plane::Output> optics(n);
            std::vector<solarpilot::ImagePlaneRequiredOutput> required_outputs(n);
            density->image_plane->evaluate_resident(inputs.data(),n,tables,required_outputs.data());
            std::vector<solarpilot::ResidentDensityInput> metadata(n);
            for (std::size_t h=0;h<n;++h) metadata[h]={{0.,1.,0.},{.01*double(h),0.,100.},.1+.0001*double(h)};
            std::vector<flux_density::CellData> cells(13);
            for (std::size_t c=0;c<cells.size();++c) cells[c]={{double(c),0.,100.},{0.,1.,0.}};
            const flux_density::Parameters parameters={100.,std::acos(-1.)};
            std::vector<double> resident_map(cells.size()),full_map(cells.size());
            density->evaluate_flux_resident(metadata.data(),n,cells.data(),cells.size(),parameters,resident_map.data());
            density->image_plane->download_outputs(optics.data(),n);
            std::vector<flux_density::HeliostatData> packed(n);
            for (std::size_t h=0;h<n;++h) {
                std::copy(metadata[h].direction,metadata[h].direction+3,packed[h].direction);
                std::copy(metadata[h].aim,metadata[h].aim+3,packed[h].aim);
                packed[h].normalization=metadata[h].normalization;packed[h].sigma_x=optics[h].sigma[0];packed[h].sigma_y=optics[h].sigma[1];
                std::copy(optics[h].hermite.values,optics[h].hermite.values+16,packed[h].coefficients);
            }
            density->evaluate_flux(packed.data(),n,cells.data(),cells.size(),parameters,full_map.data());
            require(std::memcmp(resident_map.data(),full_map.data(),full_map.size()*sizeof(double))==0,"Resident density handoff differs bitwise from the same optical SoA input");
        }
        density->close_all();
        const auto resources=context->resources();
        const auto stats=context->statistics;
        std::ofstream file;
        if (argc>1) file.open(argv[1]);
        std::ostream& out=argc>1?file:std::cout;
        require(bool(out),"Cannot write image-plane numerical result");
        out<<"{\"fixtures\":"<<count<<",\"fixture_errors\":";fixtures.json(out);
        out<<",\"edge_errors\":";edges.json(out);
        out<<",\"resident_fixture_errors\":";resident_fixtures.json(out);
        out<<",\"resident_edge_errors\":";resident_edges.json(out);
        out<<",\"handoff_same_optics_bitwise\":true,\"deterministic\":"<<(deterministic?"true":"false")<<",\"allocation_reuse\":true,\"input_capacity\":"<<stats.input_capacity
           <<",\"output_capacity\":"<<stats.output_capacity<<",\"allocations\":"<<stats.allocations
           <<",\"block_size\":"<<stats.block_size<<",\"host_device_layout_equal\":true,\"layout\":[";
        for (std::size_t i=0;i<layout.size();++i) out<<(i?",":"")<<layout[i];
        out<<"],\"resources\":{\"registers_per_thread\":"<<resources.registers<<",\"local_bytes_per_thread\":"<<resources.local_bytes
           <<",\"static_shared_bytes\":"<<resources.static_shared_bytes<<",\"dynamic_shared_bytes\":0,\"constant_bytes\":"<<resources.constant_bytes
           <<",\"active_blocks_per_sm\":"<<resources.active_blocks_per_sm<<",\"theoretical_occupancy\":"<<resources.theoretical_occupancy
           <<",\"sm_count\":"<<resources.sm_count<<",\"compute_capability\":["<<resources.compute_major<<','<<resources.compute_minor
           <<"],\"runtime_version\":"<<resources.runtime_version<<",\"driver_version\":"<<resources.driver_version<<"}}\n";
        require(bool(out),"Cannot finish image-plane numerical result");
        context->close();
        require(deterministic,"Repeated CUDA image-plane output is not bitwise reproducible");
        require(fixtures.global.passed && edges.global.passed,"CUDA image-plane tolerance exceeded; inspect family diagnostics");
        require(resident_fixtures.global.passed && resident_edges.global.passed,"Resident CUDA image-plane tolerance exceeded");
        return 0;
    } catch (const std::exception& error) { std::cerr<<error.what()<<'\n';return 1; }
}
