// Read-only process floating-point environment probe for Phase 4R tooling.
#include <cstdint>
#include <xmmintrin.h>
extern "C" std::uint32_t phase4r_mxcsr() { return _mm_getcsr(); }
extern "C" std::uint16_t phase4r_x87_control() {
    std::uint16_t result;
    asm volatile("fnstcw %0" : "=m"(result));
    return result;
}
