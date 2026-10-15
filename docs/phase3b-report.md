# Phase 3B: serialized fields and flat rectangular receivers

Phase 3B establishes physical/backend compatibility, without a performance or
receiver-grid convergence campaign. All results use double precision and the
unchanged `rtol=1e-9`, `atol=1e-10` criterion. Phase 3C has not started.

## Audited revisions and reconstruction

Initial clean revisions:

| Repository | Initial revision | Final code revision |
| --- | --- | --- |
| ROOT | `c504e24501ad2658d68c01c19323ae19a73428b2` | See the Phase 3B ROOT commit series |
| SSC | `cb3c0371884a2cf69aded43c20dd5081a56cf96d` | `c3ccd7db4d112c5787a5cfdea9df868208810893` |
| SolarPILOT | `0b56acb4e80a5206ec8196d21eac38af5c93e405` | `84f00a1a9212900aba09806bdf9878a0dd47b505` |
| SolTrace | `699263f12b2de1c6f12e211e3e8906a80054cc1b` | Unchanged |

SSC commits were exported before ROOT pin updates; the Python wrapper was committed
and pinned separately. Original upstream bases are unchanged. Fresh reconstruction
from each original base plus its complete mailbox reproduced the exact final SHAs;
bootstrap verified all three. Fresh CPU build, native and Python tests passed.
Historical cases, commercial assets, Phase 2/3A results and SolTrace patch were
checked against their initial SHA-256 values and remain unchanged. Nothing was pushed.

## Restoration and weather semantics

The old loader restores variables and serialized layout text, clears old runtime
objects and leaves zero instantiated heliostats. Create parses a layout shell;
managed layout subsequently constructs objects. Both generation and geometry
update unconditionally read external weather; embedded weather does not replace
that dependency. Even refresh applies exclusions and runs a design-point simulation.

The new explicit C/Python `restore_loaded_layout` operation instantiates the saved
geometry using a narrow mode in existing field preparation. It validates saved
rows and template references, preserves positions, template IDs, focal lengths,
cant vectors, flags and aims, bypasses position filtering and layout simulation,
and initializes the normal neighbor/ID infrastructure. Simulation remains a
separate call. Malformed input leaves no partly prepared runtime field. The
inherited single-row/trailing-semicolon and skipped-row indexing defects were
corrected without changing the SPT representation.

Weather resolution occurs only in memory during load: existing stored path;
otherwise project-relative reference; otherwise the same stored basename beside
the SPT. No arbitrary EPW selection or private-file rewrite occurs. Missing files
still fail weather-dependent operations. See [SPT API](spt-files.md) and
[design trace](phase3b-design.md) for the dependency matrix and API contract.

## Numerical architecture and public gates

Legacy remains the independent oracle. The Flat host/device implementation adds
the existing planar normalized slant-range branch and rectangular aperture
projection/quadrature, retaining arithmetic order. Seventy-two independent public
optical fixtures cover four sun models, three supported canting modes, errors,
facets, off-center aims, receiver rotation, clipping and invisible apertures.
Every one of the 215 doubles is bitwise identical on CPU (15,480 comparisons).
The adapter is explicitly required to accept each fixture, so Legacy fallback
cannot create a false pass.

CUDA uses that shared flat aperture branch, unchanged 64-thread image launch,
256-thread density launch, FMA policy and strict math settings. Input is now 1,664
bytes with explicit flat geometry/projection angles; output remains 1,728 bytes,
tables 3,256 bytes, resident density metadata 56 bytes. Host/device layout probes
cover all added fields. Existing receiver cells, offsets and normals supply the
physical density projection; density arithmetic/reduction was not changed.

CUDA all-215 fixture comparison: max absolute error `1.1368683772161603e-12`, RMS
`1.8752863106505544e-14`, no nonfinite values, all tolerances passed. Relative error
can reach 4 for coefficients near floating-point zero; ten exactly-zero reference
entries become tiny nonzero values. The absolute tolerance handles these entries;
no threshold was relaxed. Per-family diagnostics and zero-reference counts remain
in the public machine-readable receipt.

Edges include 0, 1, 63, 64, 65, nonmultiples and larger batches, disabled/invisible
heliostats, error recovery, repeated contexts, allocation reuse and smaller-after-
larger calls. Full-output and resident output agree bitwise with each other on
CUDA; repeated maps are deterministic. Public synthetic map tests cover rotated
flat apertures, three Hour/Day hours, saved aims, disabled fields and unsupported
snout recovery. Keep existing reuses existing aim projection and preserves the
saved global aims. Hour/Day reuses PerformanceSimulationPrep and Ambient; no new
solar-position algorithm was introduced. CPU preparation remains single-threaded.

Selected cylindrical numerical/regression gates passed, including the original
60 optical fixtures and fixed field baselines. The unchanged 8,790-heliostat
commercial case was checked at its existing 222x87 control grid, with no refinement
study. Legacy, Flat and CUDA maps and summary/integral/peak comparisons passed.

## Private integration: public-safe findings only

The private SPT and reference EPW remain ignored, untracked and byte-identical.
Detailed private outputs and maps remain only in ignored areas. Public fixtures
were independently constructed before private integration and contain no private
configuration or coordinates.

The stored weather reference is an unavailable absolute historical path. The real
reference EPW now resolves by its exact basename beside the SPT. Direct restoration
instantiates all 300 saved heliostats and preserves receiver configuration,
positions, templates, focals, canting, flags and aims. Generation and update were
also exercised using the real EPW. For this project, both reproduce those geometry
and aim attributes exactly; this is not a general guarantee about regeneration.

Reading the EPW updates latitude and longitude. The resulting Hour/Day solar state
therefore differs from the serialized-site state, and so do the flux maps. Update
and generation resolve the same solar state and produce the same map. These are
physical input changes, not backend errors. The canonical **geometry/state
restoration** is direct deserialization, which preserves serialized site inputs;
the weather-aware generation/update results are reported separately. Applications
that intentionally refresh site metadata can use the existing update path after
restoration, recognizing its general regeneration/geometry semantics. No input
was silently replaced to force cross-path numerical equality.

Legacy, Flat and CUDA pass for each of the three preparation paths at the actual
project Hour/Day state. No manual azimuth/elevation injection or synthetic weather
is used. Within each path the resolved azimuth/elevation and sun vector agree
across backends; aims, focus and geometry remain unchanged through simulation.
The project-native 25x25 grid is used only for compatibility.

| Error metric | Direct restoration | Weather-aware generation/update |
| --- | ---: | ---: |
| Legacy/Flat map max abs / RMS | 0 / 0 | 0 / 0 |
| Legacy/CUDA map max abs (kW/m2) | 1.5916157281026244e-12 | 2.0463630789890885e-12 |
| Legacy/CUDA map max relative | 1.7893277637008627e-15 | 2.2100777600840186e-15 |
| Legacy/CUDA map RMS (kW/m2) | 3.7080518029619427e-13 | 5.024742809269406e-13 |
| Peak difference (kW/m2) | 2.2737367544323206e-13 | 1.1368683772161603e-12 |
| Integrated incident power difference (kW) | 0 | 1.3642420526593924e-12 |
| Summary absorbed power difference (kW) | 0 | 0 |
| All-215 max abs / RMS | 3.637978807091713e-12 / 6.565696765560206e-14 | 2.7284841053187847e-12 / 5.741510789649661e-14 |

Private all-215 checks cover 64,500 doubles per path. Relative maxima on tiny
coefficients are 4 and 3, respectively; 92/104 zero-reference entries become tiny
nonzero values. All pass the original absolute/relative criterion. Flat/CUDA and
Legacy/CUDA maps agree; resident/full paths agree and repeat deterministically.
Summary exports retain upstream rounding, so zero summary difference is interpreted
at that exported precision. Map integration and peak comparisons use raw doubles.

## Builds, tests and limits

| Configuration | Python methods | Expected skips | Native tests |
| --- | ---: | ---: | ---: |
| CPU Release, diagnostics/profile ON | 54 | 11 | 4/4 |
| CPU Release, diagnostics/profile OFF | 54 | 13 | 4/4 |
| CUDA Release sm89, diagnostics/profile ON | 54 | 1 | 8/8 |
| CUDA Release sm89, diagnostics/profile OFF | 54 | 5 | 7/7 |
| Fresh mailbox reconstruction, CPU diagnostics | 54 | 11 | 4/4 |

Skips reflect unavailable CUDA in CPU builds, disabled diagnostics/profiling,
and the existing opt-in GPU timing gate. CUDA production also passed the
private compatibility paths. Legacy/Flat differential controls require diagnostic
builds; production checks exercise default Flat CPU against CUDA. CPU ASan/UBSan native tests passed with LeakSanitizer
(4/4); the nine project Python methods passed with two CUDA skips and CPython
leak detection disabled. Separate native private restoration/generation/update
checks passed with leak detection enabled. LeakSanitizer must run outside the
sandbox's ptrace environment. Compute Sanitizer and Nsight Compute are unavailable
in the pinned CUDA image; no installation was attempted.

Remaining CUDA scope: one configured/enabled external cylindrical or rectangular
flat receiver, Hermite seven-term optics, simple or Keep existing aims, specified
sun or Hour/Day, supported no/on-axis canting, at most 64 facets. Unsupported
receivers, snouts, aim modes, cant modes, multiple receivers and preparation thread
counts fail explicitly. Direct restoration requires one enabled receiver. SPT
serialization precision/escaping and the inherited summary formatter limitation
for nonpositive net HTF power remain unchanged.

No performance timings or speedup claims were collected. No private grid
convergence, annual simulation, batching, CPU multicore, multi-GPU, launch tuning,
shading/blocking optimization, SolTrace modification or OptiX work was performed.
Phase 3C may next study CESA-I receiver-grid convergence and resolution selection;
the native compatibility grid is not a scientific resolution recommendation.


Repeated lifecycle tests replace project A with B and back in the same context,
including warmed CUDA buffers, different receiver geometry, weather references,
field sizes and time modes. No stale field, receiver, aims or weather survives.
Backend agreement establishes model/software compatibility; it does not establish
experimental agreement with measured data, thermal validity or annual accuracy.

## Changed files

* SSC: `CoPilot_API.cpp/.h`, `SolarField.cpp/.h`, `FluxDensityCuda.cpp`,
  `ImagePlaneIntercept.h`, `ImagePlaneInterceptAdapter.cpp`,
  `ImagePlaneInterceptCuda.cpp/.h`, `ImagePlaneInterceptKernels.cu`,
  `ImagePlaneInterceptNumerics.h` (all under `solarpilot/`).
* SolarPILOT: `deploy/api/copylot.py`. SolTrace: no changes.
* ROOT: `CMakeLists.txt`, `README.md`, `repos.lock.json`, both updated SSC and
  SolarPILOT mailboxes; `benchmarks/flat_compatibility.py`; the five new
  `benchmarks/results/phase3b-*.json` receipts; `docs/phase3b-design.md`, this report
  and `docs/spt-files.md`.
* Tests: `test_flat_project.py`, `test_cuda_flux.py`, `project_state_check.cpp`,
  `flat_image_plane_fixtures.h`, `flat_image_plane_numerics.cpp`,
  `cuda_flat_image_plane_numerics.cpp` (all under `tests/`).
