// Read-only process floating-point environment probe for Phase 4R tooling.
#include <cstdint>
#include <xmmintrin.h>
extern "C" std::uint32_t phase4r_mxcsr() { return _mm_getcsr(); }
extern "C" std::uint16_t phase4r_x87_control() {
    std::uint16_t result;
    asm volatile("fnstcw %0" : "=m"(result));
    return result;
}
extern "C" std::uint32_t phase4r_stack_mod64() {
    volatile unsigned char marker=0;
    return reinterpret_cast<std::uintptr_t>(&marker)%64;
}
namespace { std::uint32_t last_callsite=0; }
extern "C" std::uint32_t phase4r_last_callsite_mod64() { return last_callsite; }
extern "C" bool phase4r_call_with_stack_phase(void* function,void* context,int threads,unsigned phase) {
    if (phase>48 || phase%16) return false;
    auto* space=static_cast<volatile unsigned char*>(__builtin_alloca(128+phase));
    space[0]=0;
    std::uintptr_t stack;
    asm volatile("mov %%rsp,%0" : "=r"(stack) : "r"(space) : "memory");
    last_callsite=stack%64;
    using Function=bool(*)(void*,int,bool);
    const bool result=reinterpret_cast<Function>(function)(context,threads,true);
    asm volatile("" : : "r"(space) : "memory");
    return result;
}
