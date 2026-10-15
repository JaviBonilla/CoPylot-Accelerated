# Public commercial-scale optical reference

Selected case: `ssc-mspt-8790-optical-reference`, an optical adaptation of the
public, pinned SSC molten-salt tower regression case. It is a **public reference
case**, not an exact model of a named plant and not a reproduction/validation of
the entire SAM thermal, electrical or annual simulation.

## Selection and inventory

The two public SolarPILOT SPT examples are multi-receiver demonstrations outside
the present CUDA scope. The API demonstration has no fixed documented commercial
layout. SSC provides a complete 8790-coordinate field plus tested tower, receiver
and heliostat inputs; this is preferable to reconstructing unpublished geometry.
The machine-readable inventory records the inspected public files and candidates.

Crescent Dunes is a credible 10347-heliostat external-cylinder alternative, but
the consulted authoritative project record lacks receiver dimensions and a full
coordinate table. Gemasolar has a documented public SAM study, but its 2650-mirror
scale is below the preferred range and its version-specific case needs another
reconstruction. Neither is represented as an exactly reproduced plant here.

Sources: [Crescent Dunes project record](https://solarpaces.nlr.gov/project/crescent-dunes-solar-energy-project),
[Gemasolar NREL SAM case study, 2013](https://sam.nrel.gov/images/web_page_files/sam_case_csp_salt_tower_gemasolar_2013-1-15.pdf).

## Explicit parameters and provenance

PUBLISHED means directly present in the cited public input/header; DERIVED means
an explicit unit conversion/product or the existing SSC-to-SolarPILOT mapping;
ASSUMED means a declared study choice. Source years identify the pinned file's
last upstream change where applicable, not the publication date of a named plant.
The weather source has no established publication year and records null.

| Parameter | Value | Units | Classification | Source | Notes |
|---|---|---|---|---|---|
| solarfield.0.tht | 193.458 | m | published | [Pinned SSC molten-salt tower regression inputs](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/test/tcs_test/tcsmolten_salt_common_data.h) |  |
| receiver.0.rec_diameter | 17.65 | m | published | [Pinned SSC molten-salt tower regression inputs](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/test/tcs_test/tcsmolten_salt_common_data.h) |  |
| receiver.0.rec_height | 21.6029 | m | published | [Pinned SSC molten-salt tower regression inputs](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/test/tcs_test/tcsmolten_salt_common_data.h) |  |
| solarfield.0.dni_des | 950.0 | W/m2 | published | [Pinned SSC molten-salt tower regression inputs](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/test/tcs_test/tcsmolten_salt_common_data.h) |  |
| heliostat.0.width | 12.2 | m | published | [Pinned SSC molten-salt tower regression inputs](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/test/tcs_test/tcsmolten_salt_common_data.h) |  |
| heliostat.0.height | 12.2 | m | published | [Pinned SSC molten-salt tower regression inputs](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/test/tcs_test/tcsmolten_salt_common_data.h) |  |
| heliostat.0.reflectivity | 0.9 | 1 | published | [Pinned SSC molten-salt tower regression inputs](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/test/tcs_test/tcsmolten_salt_common_data.h) |  |
| receiver.0.absorptance | 0.94 | 1 | published | [Pinned SSC molten-salt tower regression inputs](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/test/tcs_test/tcsmolten_salt_common_data.h) |  |
| heliostat.0.n_cant_x | 2 | count | published | [Pinned SSC molten-salt tower regression inputs](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/test/tcs_test/tcsmolten_salt_common_data.h) |  |
| heliostat.0.n_cant_y | 8 | count | published | [Pinned SSC molten-salt tower regression inputs](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/test/tcs_test/tcsmolten_salt_common_data.h) |  |
| heliostat.0.reflect_ratio | 0.9602999999999999 | 1 | derived | [Pinned SSC mapping from tower inputs to SolarPILOT](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/tcs/csp_solver_pt_heliostatfield.cpp) | SSC available fraction 0.99 times mirror density 0.97; retain both physical mirror and effective aperture areas in metadata. |
| heliostat.0.err_surface_x | 0.00153 | rad | derived | [Pinned SSC mapping from tower inputs to SolarPILOT](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/tcs/csp_solver_pt_heliostatfield.cpp) | Published 1.53 mrad surface-normal error converted to radians. |
| heliostat.0.err_surface_y | 0.00153 | rad | derived | [Pinned SSC mapping from tower inputs to SolarPILOT](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/tcs/csp_solver_pt_heliostatfield.cpp) | Published 1.53 mrad surface-normal error converted to radians. |
| heliostat.0.err_azimuth | 0 | rad | derived | [Pinned SSC mapping from tower inputs to SolarPILOT](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/tcs/csp_solver_pt_heliostatfield.cpp) | Use the existing SSC optical mapping; on-axis slant canting and slant focusing. |
| heliostat.0.err_elevation | 0 | rad | derived | [Pinned SSC mapping from tower inputs to SolarPILOT](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/tcs/csp_solver_pt_heliostatfield.cpp) | Use the existing SSC optical mapping; on-axis slant canting and slant focusing. |
| heliostat.0.err_reflect_x | 0 | rad | derived | [Pinned SSC mapping from tower inputs to SolarPILOT](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/tcs/csp_solver_pt_heliostatfield.cpp) | Use the existing SSC optical mapping; on-axis slant canting and slant focusing. |
| heliostat.0.err_reflect_y | 0 | rad | derived | [Pinned SSC mapping from tower inputs to SolarPILOT](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/tcs/csp_solver_pt_heliostatfield.cpp) | Use the existing SSC optical mapping; on-axis slant canting and slant focusing. |
| heliostat.0.soiling | 1 | 1 | derived | [Pinned SSC mapping from tower inputs to SolarPILOT](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/tcs/csp_solver_pt_heliostatfield.cpp) | Use the existing SSC optical mapping; on-axis slant canting and slant focusing. |
| heliostat.0.cant_method | -1 | 1 | derived | [Pinned SSC mapping from tower inputs to SolarPILOT](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/tcs/csp_solver_pt_heliostatfield.cpp) | Use the existing SSC optical mapping; on-axis slant canting and slant focusing. |
| heliostat.0.focus_method | 1 | 1 | derived | [Pinned SSC mapping from tower inputs to SolarPILOT](https://github.com/NatLabRockies/ssc/blob/e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec/tcs/csp_solver_pt_heliostatfield.cpp) | Use the existing SSC optical mapping; on-axis slant canting and slant focusing. |
| receiver.0.rec_type | 0 | 1 | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| receiver.0.is_open_geom | 0 | 1 | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| receiver.0.rec_offset_x_global | 0 | m | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| receiver.0.rec_offset_y_global | 0 | m | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| receiver.0.rec_offset_z_global | 0 | m | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| heliostat.0.is_faceted | 1 | 1 | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| heliostat.0.x_gap | 0 | m | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| heliostat.0.y_gap | 0 | m | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| ambient.0.sun_type | 2 | 1 | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| ambient.0.sun_rad_limit | 4.65 | mrad | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| ambient.0.atm_model | 0 | 1 | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| fluxsim.0.flux_model | 0 | 1 | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| fluxsim.0.flux_time_type | 0 | 1 | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| fluxsim.0.aim_method | 0 | 1 | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| solarfield.0.des_sim_detail | 0 | 1 | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| solarfield.0.q_des | 670 | MWt | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| land.0.is_bounds_scaled | 0 | 1 | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| land.0.is_bounds_fixed | 1 | 1 | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| land.0.min_fixed_rad | 0 | m | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| land.0.max_fixed_rad | 5000 | m | assumed | Phase 3A explicitly chosen study configuration | Explicit benchmark optical/dispatch assumption; no layout filtering or geometry optimization. All unspecified parameters retain pinned defaults. |
| ambient.0.latitude | 34.866667 | deg | published | [Pinned public SolarPILOT Daggett TMY2 header](https://github.com/NatLabRockies/SolarPILOT/blob/c74618a70fd8e85708957b1ee57b157ba75a5045/deploy/climate_files/USA%20CA%20Daggett%20(TMY2).csv) | Public Daggett TMY2 header; specified sun avoids calendar derivation. |
| ambient.0.longitude | -116.783333 | deg | published | [Pinned public SolarPILOT Daggett TMY2 header](https://github.com/NatLabRockies/SolarPILOT/blob/c74618a70fd8e85708957b1ee57b157ba75a5045/deploy/climate_files/USA%20CA%20Daggett%20(TMY2).csv) | Public Daggett TMY2 header; specified sun avoids calendar derivation. |
| ambient.0.time_zone | -8 | h | published | [Pinned public SolarPILOT Daggett TMY2 header](https://github.com/NatLabRockies/SolarPILOT/blob/c74618a70fd8e85708957b1ee57b157ba75a5045/deploy/climate_files/USA%20CA%20Daggett%20(TMY2).csv) | Public Daggett TMY2 header; specified sun avoids calendar derivation. |

Count is 8790 (PUBLISHED). Original x/y coordinates and row order are preserved;
z=0 is an ASSUMED common pivot plane. Tower height is relative to that plane.
The public latitude/longitude/timezone come from the pinned Daggett TMY2 header.
That weather asset supplies existing preparation infrastructure; no annual or
calendar-derived operating sequence is executed. Four solar positions/DNI values
are explicitly ASSUMED study conditions, not inferred facility observations.

The 12.2×12.2 m structure gives 148.84 m² gross area; mirror density 0.97 gives
144.3748 m² physical mirror area. The 0.99 availability mapping gives
142.931052 m² effective aperture. Total physical mirror area is 1269054.492 m²;
effective aperture is 1256363.94708 m². These are DERIVED, separately labelled
quantities, not contradictory area estimates. Tower is 193.458 m and the
continuous external cylinder is 17.65 m diameter ×21.6029 m height.

On-axis slant canting, slant focusing and the source 2×8 facets are supported by
the existing CUDA path. Simple aiming is an explicit study assumption, not a
commercial flux-limited control strategy. High local flux values are retained
and reported rather than tuning aiming/geometry to obtain a desired result.
Pillbox sun, atmospheric defaults and zero extra reflected/tracking errors are
stated model choices/mappings. All unspecified defaults are frozen by the pinned
SSC definitions hash and dependency SHAs.

## Reconstruction and checks

`cases/commercial-reference/case_manifest.json` contains all parameter records,
source URLs/years, asset hashes, optical mapping, operating points and grid study
criteria. `benchmarks/commercial_reference.py` verifies hashes, reads only public
coordinate/weather assets, configures the receiver/template and assigns the
unfiltered original layout. It checks actual API count/geometry, finite positive
flux, field bounds/radii and duplicate/obvious-overlap exclusion.

```sh
COPILOT_LIB_DIR=build/cpu/lib OPENBLAS_NUM_THREADS=1 .venv/bin/python benchmarks/commercial_reference.py --output artifacts/phase3a/commercial-case.json
```

Optional `--save-spt` generates a local public SPT convenience artifact; it can
contain runtime absolute weather paths, so it is not the canonical redistributed
input and is not committed. Reconstruction depends on the manifest/script/pinned
assets rather than serializer text determinism. Existing SSC BSD-3-Clause and
SolarPILOT license/notice files remain with their assets; no proprietary input is
copied. No external case or package needs downloading to reconstruct this case.

Limitations and measured sanity/performance/convergence results are in the final
Phase 3A report. This is an industrial-scale optical workload, not an assertion
that its center-aimed receiver is an operable commercial thermal design.
