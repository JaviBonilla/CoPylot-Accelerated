# GPU data model derived from the current Hermite core

Design only. No Heliostat, Receiver, matrix_t, std::vector, unordered_map or host pointer is copied to the device. Device allocations/streams will belong to the per-CoPylot GpuContext; host views use stable integer IDs and explicit lengths/strides. All numerical columns are double precision initially.

## Measured first candidate: fluxDensity

At 25×25 resolution fluxDensity consumes ~84–86% of simulate; imagePlaneIntercept ~9%. Start by extracting fluxDensity's per-(heliostat, receiver point) contribution as a pure numerical CPU function, followed by a separately tested reduction/normalization. Existing CPU imagePlaneIntercept can initially produce the coefficients; the GPU then consumes those coefficients. This gives a smaller first migration with a larger measured potential than starting with imagePlaneIntercept.

The current calculation projects receiver points into the heliostat image plane, rotates/normalizes using sig_x/sig_y and tower height, evaluates the packed Hermite series and exponential, then accumulates `f_dot_t * hfe * cnorm`. `cnorm` uses heliostat area and total optical efficiency. The later CalcDimensionalFluxProfiles rescales dimensionless profiles by delivered power/area. That normalization and incident-versus-absorbed convention must remain intact; do not scale by DNI twice.

Minimum SoA inputs for the first cylindrical-receiver kernel:

| Scope | Device columns/data | Why |
|---|---|---|
| Per heliostat | stable id, enabled, receiver/surface id | Mask/association and result mapping |
| Static heliostat | pos_x/y/z, area | Receiver-to-heliostat vector and normalization |
| Per call / aim | aim_x/y/z | Image plane origin |
| Per call / optical | sigma_x/y, total_efficiency, packed hcoef[term][heliostat] | Series and normalization; CPU produces initially |
| Per receiver | global offset xyz, optical height, tower normalization height, geometry tag | Exact coordinate and normalization conventions |
| Per flux cell | surface-local position xyz, normal xyz, equal-area/area weights, surface offsets | Projection, visibility, sum and integration |
| Constant | Hermite index ordering/order, polynomial recurrence tables | Avoid host class/matrix access |
| Output | partial contribution tiles, dimensionless map, dimensional map, peak/integral reductions | Separate deterministic reduction from evaluation |

Flux::Setup fixes n_order=6, n_terms=7. The parity/triangular JMN/JMX sequence yields 16 packed Hermite coefficients. Carry n_terms and packing metadata explicitly, validating the 16-entry specialization; do not assume a generic 49-entry matrix or make kernel behavior depend on raw host layout. Constant tables use read-only device storage.

Widths, heights, focal lengths, cant panel geometry and tracking vectors are not direct inputs to fluxDensity once its image/coefficient state is supplied. Avoid uploading them for this first isolated kernel. Cache normalized receiver-to-heliostat vectors/rotation terms only when their dependencies permit it. Aimpoint optimization changes the image origin and generally tracking/intercept/efficiency too: keeping hcoef fixed while moving aimpoints is not automatically valid.

For cavity/falling-particle kernels, add receiver aperture dimensions/type/azimuth/elevation and snout depth/vertices/visibility predicates used by checkApertureSnout. Unsupported geometry must be rejected explicitly or handled by a clearly selected CPU path; do not silently apply a cylindrical approximation. Initial GPU support can be deliberately restricted to the tested cylinder case.

Candidate execution: tile heliostats × cells, then double precision reductions per cell, optionally a block per cell iterating over heliostat chunks. Benchmark coalescing, register/shared memory pressure and temporary storage before selecting the mapping. Avoid one global floating-point atomic per contribution as the initial reference; fixed reduction order helps reproducibility. The CPU per-pair extraction must first match CPU-old exactly within existing tolerances. GPU reduction order may differ but must still pass explicit numerical tolerances.

## Later imagePlaneIntercept inputs

This routine is not just a scalar intercept computation. It writes sun/error/mirror/convolved moments, image sigmas and Hermite coefficients, then calls hermiteIntEval → hermiteIntegralSetup → hermiteIntegral. Flux-map generation depends on those side effects. The GPU implementation must reproduce them as well as intercept efficiency.

Required inputs identified in Flux.cpp:

* Position/radial distance, tower/slant vectors, tracking vectors and focal_x/y.
* Receiver association, normal/apparent diameter from heliostat view, optical height, geometry/aperture type, dimensions, aimpoint in flux-plane coordinates, azimuth/elevation and relevant snout fields.
* Heliostat/template angular, surface and reflected errors; cant method, cant day/hour/radius, facet flag and cant rows/columns.
* Normalized mirror moments, panel positions/orientation for faceted mirrors. Use panel_offsets[heliostat+1] plus packed numeric panel arrays; variable panel counts cannot be represented by just width/height.
* Ambient latitude for off-axis canting, sun direction, normalized sun moments and error distribution constants.
* Read-only factorial, binomial and quadrature tables; seven-term scratch matrices in thread-local registers/local memory initially, measuring spills before attempting fusion.

Outputs: intercept, sigma_x/y, 16 hcoef terms and any moment arrays still consumed by CPU diagnostics/subsequent calculations. First scope can support one tested canting/receiver configuration, with explicit capability checks for others. User-vector canting is already not fully implemented upstream; GPU must not claim support absent from CPU.

## Neighbor and batch representation

Shading/blocking later uses CSR neighbor_offsets[N+1], neighbor_indices[n_edges], stable heliostat IDs, corner geometry/tracking and sun vector. Storage may remain allocated across calls, but adjacency/geometry validity depends on sun/tracking epochs. Device receiver IDs refer to a numeric receiver table, never Receiver pointers. Pack canonical C++ geometry after layout assignment: sp_assign_layout serializes supplied positions through a stringstream, so packing original Python coordinates at greater precision could diverge from the CPU geometry.

For evaluate_batch, distinguish static N-heliostat arrays from candidate-dependent state. Prefer candidate tiles and bounded buffers, explicit strides [candidate][term][heliostat] or [term][candidate][heliostat] chosen by kernel access. Keep objective, peak flux and constraint reductions on device. Return objectives/flags to Python; download full flux or heliostat details only when requested. Memory costs scale with candidate_count × heliostats × coefficients/cells; tile candidates rather than duplicating the complete field for every candidate.

## Flux density data model

Phase 2A implemented host PODs in `ssc/solarpilot/FluxDensityNumerics.h`. Ownership is by the CPU adapter/caller, not by Heliostat or Receiver pointers inside the numerical function. Records are immutable during evaluation. The CPU adapter currently packs **one** heliostat record on the stack and owns vectors of cells and accumulators for one surface; it does not allocate a full packed field. The future device estimate assumes packing all enabled records in their original order. No device buffers exist.

| Field | Exact source / units | C++ type and extent | Scope | Changes with sun / aim / layout / receiver | Residency and invalidation |
|---|---|---|---|---|---|
| `HeliostatData.direction` | unitvect(location − receiver global offsets − (0,0,tht)); receiver-to-h, not getTowerVector | double[3] | h × surface receiver | no / no / yes / offsets or tower height | May persist until location, receiver assignment/offset or tower height changes |
| `HeliostatData.aim` | getAimPoint, global metres | double[3] | h | aiming-dependent / yes / yes / yes | Persist only under aimpoint epoch; reassess even if simple aim is unchanged |
| `sigma_x`, `sigma_y` | getImageSize, hermiteIntEval sqrt(mu_F(2,0)), sqrt(mu_F(0,2)); tower-normalized | double each | h | yes / tracking-dependent / yes / yes | CPU optics output; replace after optical preparation changes |
| `normalization` | getArea × getEfficiencyTotal / (tht×tht) | double | h | yes / yes / yes / yes | Total efficiency includes current optical/shading/intercept state; invalidate with optics, reflectivity, neighbors or geometry |
| `coefficients` | getHermiteCoefObject, packed by hermiteIntEval after imagePlaneIntercept | double[16] | h | yes / yes / yes / yes | Persist under optical epoch, including sunshape, errors, canting/focal/tracking changes; moment matrices need not be uploaded |
| `CellData.position` | FluxPoint.location + surface offset + receiver offset + tower height, exactly left-associated | double[3] | cell × surface | no / no / only if receiver/tower moves / yes | Geometry cache; invalidate offsets, tower height, geometry or grid resolution |
| `CellData.normal` | FluxPoint.normal | double[3] | cell × surface | no / no / only if receiver geometry changes / yes | Same geometry cache epoch; not heliostat tracking normal |
| `Parameters.tower_height` | sf.tht passed to fluxDensity | double | call/field | no / no / tower changes / height changes | Read-only scalar, invalidate height changes |
| `Parameters.pi` | Flux::Setup: 4×atan(1) | double | algorithm | no / no / no / no | Constant; packing is fixed n_terms=7, parity/triangular 16 coefficients |
| Accumulator | initial FluxPoint.flux; each contribution added in h order | double[C] | surface | yes / yes / yes / yes | Mutable output, initialize from current map (usually cleared to zero), invalidate/recompute every simulation |

Adapter-only fields: enabled flags choose records in original vector order; compact index→heliostat identity stays on host. NX/NY and selected record counts are launch dimensions, not repeated numerical payload. Surface IDs identify independent launches. No new association filter is applied: the legacy supplied vector is preserved. Aperture type/parameters and original h.location are required by host checkApertureSnout for cavities/particles; they are intentionally outside the cylinder-only device model and memory estimate. A first device capability check must fall back for those types and missing seven-term/16-coefficient packing.

The source may return from intercept preparation before creating coefficients for invisible heliostats. The adapter detects missing/non-16 packing and retains the original route for that surface rather than reading past a matrix. This is not an optical approximation. Nonzero receiver-to-h direction and finite prepared optical data are validity assumptions; a zero vector exposes undefined projection data in the original implementation.

Numerical bytes: direction+aim+sigmas+normalization = 9 doubles = 72 B/h; coefficients = 128 B/h; whole HeliostatData = 200 B/h. CellData = 48 B/cell; Parameters = 16 B/call; accumulator = 8 B/cell. No moments, area, efficiency or source positions need duplicate residency after packing; cnorm/direction already contain their effects. AoS is the tested CPU layout; a later SoA device layout can retain these values and original index order without copying class representations.

Residency means reusable capacity and immutable values under explicit epochs, not that optics remain valid indefinitely. Preserve allocation across simulation calls eventually, but recompute/upload h optics when sun/aim/shading changes and clear output every call. Static receiver cells can persist across sun sweeps. Layout/enable changes rebuild record mapping; receiver geometry and resolution rebuild cells. DNI alone is applied by unchanged host post-processing; no DNI or absorptance is consumed by the contribution helper. Multiple receivers/surfaces need separate cell tables and receiver-dependent direction/aim data; future batching multiplies optical records/outputs by active candidate tiles, not the complete field indefinitely.
