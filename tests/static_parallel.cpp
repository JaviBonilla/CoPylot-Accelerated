// Bounded range coverage, completion, exceptions and recovery without optical I/O.
#include "StaticParallel.h"
#include <atomic>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <set>
#include <stdexcept>
#include <vector>
static void require(bool ok) { if (!ok) throw std::runtime_error("Static range executor validation failed"); }
int main(int argc,char** argv) {
    try {
        if (argc==2) {
            const int requested=std::stoi(argv[1]);
            const auto call=[&]() {
                std::atomic<int> reached(0);const auto start=std::chrono::steady_clock::now();
                solarpilot::static_parallel(4096,requested,[&](std::size_t,std::size_t,std::size_t) { ++reached; });
                require(reached==solarpilot::bounded_cpu_threads(requested));
                return std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
            };
            const double first=call();call();call();
            std::cout<<std::setprecision(17)<<"{\"requested_threads\":"<<requested<<",\"first_call_s\":"<<first
                     <<",\"warmups\":2,\"samples_s\":[";
            for(int i=0;i<10;++i)std::cout<<(i?",":"")<<call();
            std::cout<<"],\"interpretation\":\"Synthetic bounded-executor launch/join cost; no optical workload\"}\n";
            return 0;
        }
        unsigned checks=0;
        for (std::size_t work:{0,1,2,7,17,257}) for (int requested:{-2,0,1,2,4,8,12,24,1000}) {
            std::vector<int> values(work,-1);
            std::atomic<int> active(0);
            solarpilot::static_parallel(work,requested,[&](std::size_t begin,std::size_t end,std::size_t range) {
                ++active;
                for (auto i=begin;i<end;++i) { require(values[i]==-1);values[i]=int(range); }
                --active;
            });
            require(active==0);
            for (auto value:values) require(value>=0);
            ++checks;
        }
        // Every range throws; deterministic lowest-range failure wins after all join.
        try {
            solarpilot::static_parallel(17,4,[](std::size_t,std::size_t,std::size_t range) {
                throw std::runtime_error(std::to_string(range));
            });
            require(false);
        } catch (const std::runtime_error& e) { require(std::string(e.what())=="0"); }
        std::vector<int> recovered(13,0);
        solarpilot::static_parallel(13,12,[&](std::size_t begin,std::size_t end,std::size_t) {
            for (auto i=begin;i<end;++i) recovered[i]=1;
        });
        for (auto value:recovered) require(value==1);
        const int participants=solarpilot::bounded_cpu_threads(4);
        std::atomic<int> arrived(0);std::mutex mutex;std::set<std::thread::id> ids;
        const auto caller=std::this_thread::get_id();
        const auto used=solarpilot::static_parallel(17,participants,[&](std::size_t,std::size_t,std::size_t) {
            { std::lock_guard<std::mutex> lock(mutex);ids.insert(std::this_thread::get_id()); }
            ++arrived;
            while (arrived<participants) std::this_thread::yield();
        });
        require(used==std::size_t(participants));require(ids.size()==used);require(ids.count(caller)==1);
        std::cout<<"{\"passed\":true,\"range_configurations\":"<<checks<<",\"exception_recovery\":true}\n";
        return 0;
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
