# SolTrace compatibility and OptiX status

Analysis only; no OptiX integration. Inspected current develop at `c33d9792d2e15408ddf1e3da963b3b0223f90d2c`, not an unspecified latest branch. Build uses legacy release v3.4.0 (`79b2ca3dfec496506d24ae56055c0d7e240ba368`) plus explicit `<limits>` inclusion. Coretrace links successfully with SSC solarpilot-develop and Hermite tests pass. This proves the dependency/ABI closure exercised by Hermite; it does not establish statistical equivalence of a new ray-tracing backend. No Monte Carlo or OptiX simulation has been validated here.

## Current runner architecture

NativeRunner and EmbreeRunner share the newer SimulationData/native system infrastructure; Embree support is conditional and README requests Embree 4.x. OptixRunner adapts SimulationData into the tracked OptixCSP source under simulation_runner/optix_runner/OptixCSP. It has real initialize/setup/run/output code, including explicit surface/aperture mappings, not just a named placeholder. Current APIs include `st_sim_run_SolTrace20` with runner enum and legacy conversion.

Existing SSC `interop.cpp` and STSimulateThread.cpp call `st_sim_run`, which current SolTrace still routes through legacy st_sim_run_data with refactor=false. Merely relinking a newer SolTrace does not select OptiX. CoPylot's Hermite compute backend enum is also independent of SolTrace's runner enum; they must not be conflated.

## Concrete bridge gaps at the inspected SHA

[simdata_bridge.cpp](https://github.com/NLR-SolTrace/SolTrace/blob/c33d9792d2e15408ddf1e3da963b3b0223f90d2c/coretrace/simdata_bridge.cpp):

* Conversion rejects point-source suns. Surfaces are constructed with only VertexCurvX/Y, with a TODO to validate more surface arguments; file/general spline surfaces therefore cannot be assumed supported by this bridge.
* Native/Embree adapters copy global native hits back to legacy stage coordinates, include ray event/sign handling and sun statistics. They are more complete in this respect than the OptiX hitpoint adapter, but still require ray-tracing validation.
* run_optix_runner obtains float4 hitpoints, ray numbers and element_id_vec, but calls assign_raydata_from_hitpoints without the element IDs.
* assign_raydata_from_hitpoints sets cosines to {0,0,0}, hard-codes element_number=1, and uses bounce depth as the legacy stage number; its comment explicitly distinguishes depth from SolTrace stages. Ray IDs are narrowed to int. Stage data is not cleared symmetrically like the native adapter. The inspected OptiX adapter also does not copy sun statistics like the native path.
* The bridge overwrites runner status at initialize/setup/run and returns 0 without checking those statuses. st_sim_run_SolTrace20 ignores helper return codes in its runner switch. These paths need reliable error propagation before production integration.

These are direct code observations, not measured OptiX numerical errors. CoPylot's results processing consumes element/stage/ray data and normalization; inference: blindly enabling this bridge could corrupt receiver assignment, per-heliostat results and flux accounting. Do not claim result preservation.

[optix_runner.cpp](https://github.com/NLR-SolTrace/SolTrace/blob/c33d9792d2e15408ddf1e3da963b3b0223f90d2c/coretrace/simulation_runner/optix_runner/optix_runner.cpp) supports flat/parabola/cylinder/sphere in its surface switch; other surfaces throw. Cylinder mapping requires a rectangular aperture whose width equals 2×radius within 1e-6. Unsupported apertures throw. Cancellation has a TODO. Newer hit-record facilities exist, but this legacy adapter is still using the limited float4 path.

## Build and requirements

At current develop, coretrace/CMakeLists links native_runner, simdata, simresult, optix_runner and embree_runner unconditionally; simdata_bridge includes OptiX/Embree headers and calls their functions unconditionally. Disabling support flags alone therefore does not provide a clean independently linked legacy coretrace. Also coretrace_api is STATIC at this SHA, while the legacy Python API expects a shared library. Those issues are avoided by pinning the published legacy core for Phase 0/1, rather than mixing newer bridge repairs with CPU validation.

The [current README](https://github.com/NLR-SolTrace/SolTrace/blob/c33d9792d2e15408ddf1e3da963b3b0223f90d2c/README.md) specifies CUDA >=12, OptiX SDK >=8, Turing/compute capability >=7.5, compatible NVIDIA driver, C++17 and CMake >=3.19. The SDK supplies headers; the driver supplies the OptiX runtime. Reported development configurations include Ubuntu 22.04/GCC 11.4/CUDA 12.8/OptiX 9 and Red Hat 8/GCC 11–12/CUDA 12.3/OptiX 8. These are upstream reports, not configurations validated in this workspace.

Future evaluation should independently build GUI OFF/coretrace ON/tests ON, repair support guards and preserve full hit attributes, then compare identical seeded geometries statistically: flat/cylindrical/cavity/falling-particle receivers, multiple receivers, facets/canting, virtual stages, stage reuse, sunshape and normalization. Verify device precision and hit-record conversion; our double precision Hermite requirement does not imply that this existing float4 bridge meets it. Do not implement a new CUDA ray tracer.
