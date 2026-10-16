// Read-only allocation-layout trace for diagnostic runs; no numerical changes.
#include <atomic>
#include <cstddef>
#include <cstdint>
extern "C" void* __libc_malloc(std::size_t);
namespace {
struct Record { std::uint64_t size, address, caller; };
Record records[4096];
std::atomic<bool> ready[4096]{};
std::atomic<unsigned> count{0};
bool selected(std::size_t size) {
    return size==2666496 || size==444416 || size==60000
        || size==927072 || size==154512 || size==1758000;
}
}
extern "C" void* malloc(std::size_t size) {
    void* pointer=__libc_malloc(size);
    if (selected(size)) {
        const unsigned slot=count.fetch_add(1,std::memory_order_relaxed);
        if (slot<4096) {
            records[slot]={size,reinterpret_cast<std::uintptr_t>(pointer),
                           reinterpret_cast<std::uintptr_t>(__builtin_return_address(0))};
            ready[slot].store(true,std::memory_order_release);
        }
    }
    return pointer;
}
extern "C" unsigned phase4r_allocation_count() { return count.load(std::memory_order_relaxed); }
extern "C" std::uint64_t phase4r_allocation_value(unsigned index,unsigned field) {
    if (index>=4096 || !ready[index].load(std::memory_order_acquire)) return 0;
    const auto& row=records[index];
    if (field==0)return row.size;
    if (field==1)return row.address;
    return row.caller;
}
