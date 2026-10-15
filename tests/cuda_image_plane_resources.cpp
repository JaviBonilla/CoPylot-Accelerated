#include "ComputeBackend.h"
#include <iostream>
#include <iomanip>
int main() {
    try {
        auto context=solarpilot::make_image_plane_gpu_context(0);
        const auto r=context->resources();
        std::cout<<std::setprecision(17)<<"{\"block_size\":"<<r.block_size<<",\"registers_per_thread\":"<<r.registers
            <<",\"local_bytes_per_thread\":"<<r.local_bytes<<",\"static_shared_bytes\":"<<r.static_shared_bytes
            <<",\"constant_bytes\":"<<r.constant_bytes<<",\"max_threads_per_block\":"<<r.max_threads
            <<",\"active_blocks_per_sm\":"<<r.active_blocks_per_sm<<",\"theoretical_occupancy\":"<<r.theoretical_occupancy
            <<",\"launch_feasible\":"<<(r.active_blocks_per_sm>0?"true":"false")<<"}\n";
        context->close();return 0;
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
