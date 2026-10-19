/* SPDX-License-Identifier: BSD-3-Clause */
#include "ImagePlaneInterceptCuda.h"
#include <cstring>
#include <iostream>
int main() {
    const image_plane::Input base={};
    for (std::size_t offset=0;offset<sizeof(base);++offset) {
        auto changed=base;
        reinterpret_cast<unsigned char*>(&changed)[offset]^=0xa5;
        auto reconstructed=base;
        solarpilot::apply_temporal_image_update(reconstructed,solarpilot::temporal_image_update(changed));
        const bool exact=std::memcmp(&reconstructed,&changed,sizeof(base))==0;
        if (solarpilot::same_temporal_image_base(base,changed)!=exact) {
            std::cerr<<"A byte is neither safely updated nor guarded at offset "<<offset<<'\n';return 1;
        }
    }
    std::cout<<"PASS: all "<<sizeof(base)<<" input bytes are either guarded or reconstructed exactly\n";
}
