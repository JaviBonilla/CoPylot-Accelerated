# Phase 3A: scientific reference and physical receiver-grid convergence

The selected commercial-scale case is a public optical reference adapted from
the pinned SSC molten-salt tower test. It is not an exact model of a named plant.
No nested source, CUDA mathematics, launch setting or public API was changed.
The 25²/50²/100² Phase 2 fixtures remain computational scaling benchmarks.

## Initial state, preservation and reconstruction

Initial clean root: 48bf782e7832ab8c17e85ea57f943b1ce8ccf8e4.
SSC: cb3c0371884a2cf69aded43c20dd5081a56cf96d.
SolarPILOT: 0b56acb4e80a5206ec8196d21eac38af5c93e405.
SolTrace: 699263f12b2de1c6f12e211e3e8906a80054cc1b.
All branches, statuses and protected-file hashes are in the initial-state JSON.
Forty previous-evidence/pin/patch files are checked byte-for-byte unchanged.
The private experimental input passes an internal before/after integrity check;
no additional private parameters, weather/path data or file contents are published.

The three full mailboxes were replayed in a fresh local tree from the original
upstream bases, reproducing all exact patched SHAs. A fresh CPU build, CTest and
Python suite pass. Existing pins and patches remain unchanged. Root reporting
commits are fast-forwarded into the final server/reconstruction trees; they do
not relabel the SHA at which measurements actually ran. No push.

## Public reference inventory and selection

Public SolarPILOT SPT samples are multi-receiver flat demonstrations outside the
current single-cylinder CUDA scope. Its Python optical/SolTrace demonstration is
a smaller generated example without a fixed commercial layout. The SSC regression
includes complete coordinates and explicit geometry, so it is selected before
inventing any synthetic commercial field.

The candidate inventory compares this case with Crescent Dunes (suitable field
scale, incomplete consulted public optical geometry/layout) and Gemasolar
(documented public SAM study, smaller field and another case-format reconstruction).
See [commercial-reference-case.md](commercial-reference-case.md) for primary
citations and the full published/derived/assumed parameter table. No plant-name
reproduction or independent physical-validation claim follows from regression
inputs alone.

## Commercial geometry and reproduction

Site: Daggett public reference location. 8790 original heliostat positions,
12.2×12.2 m structures, 2×8 facets, on-axis slant canting and slant focusing.
Physical mirror area is 144.3748 m²/H and 1269054.492 m² total; effective available
aperture is 142.931052 m²/H and 1256363.94708 m² total. Tower optical height is
193.458 m relative to the common pivot plane; receiver is a continuous external
cylinder, diameter 17.65 m and height 21.6029 m. Design DNI is 950 W/m².

The optical mapping follows SSC where available. Simple center aiming, specified
sun, the common z=0 pivot plane and other declared study assumptions are explicit.
This is an industrial-scale optical workload, not a commercial flux-limited
operating design. No geometry/aiming/count tuning was performed to increase GPU
speedup or force a target power. All original coordinate rows remain unfiltered.

The manifest/script plus pinned public assets reconstruct the case, with hash,
count and actual API geometry checks. Optional generated SPT files remain local
because they may contain runtime absolute weather paths; they are not canonical
public inputs. All source licenses/notices remain with their pinned assets.

Sanity: field bounds x=[−1569.56,1558.23] m and y=[−1201.84,1816.87] m;
radii 145.093–1816.874 m; nearest center separation 17.223 m. No duplicate or
obviously overlapping structures/tower-interior centers were accepted. All maps
and powers are finite and positive. These checks are not a full mechanical or
thermal engineering validation.

## Representative conditions

All points use already-supported Hermite, specified sun and updated simple aiming.
They are declared study conditions, not calendar-derived or measured plant states.

| Point | Azimuth degrees | Elevation degrees | DNI W/m² |
|---|---:|---:|---:|
| high | 180 | 70 | 950 |
| moderate | 180 | 40 | 850 |
| morning | 110 | 25 | 700 |
| afternoon | 250 | 35 | 800 |

## Physical grids, reference and comparison

Ntheta=ceil(πD/Δ), Nz=ceil(H/Δ); physical sizes ds=πD/Ntheta and dz=H/Nz.
The generic rectangular implementation instead uses Nx=ceil(W/Δ), Ny=ceil(H/Δ).
Flat geometry is unit tested without private experimental execution.

Six initial levels use target cells 8→0.25 m. The additional 0.125 m refinement
checks the former finest grid and becomes the final numerical reference. This
is a finite computational comparator, not physical truth or an exact solution.

| Level | Target m | Ntheta×Nz | Cells | ds m | dz m |
|---:|---:|---|---:|---:|---:|
| 0 | 8.0 | 7×3 | 21 | 7.921301 | 7.200967 |
| 1 | 4.0 | 14×6 | 84 | 3.960651 | 3.600483 |
| 2 | 2.0 | 28×11 | 308 | 1.980325 | 1.963900 |
| 3 | 1.0 | 56×22 | 1232 | 0.990163 | 0.981950 |
| 4 | 0.5 | 111×44 | 4884 | 0.499542 | 0.490975 |
| 5 | 0.25 | 222×87 | 19314 | 0.249771 | 0.248309 |
| 6 | 0.125 | 444×173 | 76812 | 0.124885 | 0.124872 |

Maps are compared on the common unwrapped surface by conservative interval-area
overlap. Source cell values are piecewise constant, not nearest-neighbor samples.
The C API top-first rows are reversed into bottom-first z; angular seam/direction
is consistent. The native Hermite model evaluates and normalizes midpoint samples,
so peak “cell average” is explicitly a representation proxy rather than an exact
subcell integral. Fine-reference-to-coarse averaging is additionally recorded.

The normalized public map integral is constrained to the heliostat delivered
power. Consequently, apparent integrated-power convergence is largely imposed
by the existing model. It cannot independently determine ENERGY/ANNUAL spatial
resolution. No core mathematics was changed to remove that constraint.

Conservation of remapping is separately checked; maximum relative integral
residual is 3.331e-16.

Conservation does not remove representation error: piecewise-constant projection
has finite spatial error even for smooth fields. Constant, known coarse/fine ramp
and noncommensurate synthetic tests independently check that distinction.

## Convergence measured across all four states

Worst errors over the four states; fractions shown as percentages except absolute
L-infinity (kW/m²) and absolute CV change. The final row is reference self-comparison
and is excluded from minimum-resolution selection.

| Level | Power % | Peak % | L1 % | L2 % | L-infinity kW/m² | L-infinity / peak % | Centroid / diagonal % | CV absolute change |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 2.12053e-12 | 15.0631 | 34.1048 | 34.1846 | 998.537 | 47.6823 | 1.18007 | 0.141412 |
| 1 | 2.12053e-12 | 22.1755 | 24.6145 | 25.6153 | 754.592 | 35.4919 | 0.0175522 | 0.0323418 |
| 2 | 2.09832e-12 | 0.376463 | 12.3516 | 13.2038 | 424.37 | 20.1364 | 0.0107544 | 0.000868796 |
| 3 | 2.12053e-12 | 1.55769 | 5.90208 | 6.23793 | 189.107 | 9.01157 | 0.00266905 | 0.000209389 |
| 4 | 2.24265e-12 | 0.256349 | 2.61291 | 2.75907 | 78.6754 | 3.73489 | 0.000646135 | 4.9888e-05 |
| 5 | 1.68754e-12 | 0.0514181 | 0.60152 | 0.494455 | 8.26406 | 0.410899 | 0.000129134 | 1.02042e-05 |
| 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

At 28×11, worst peak error is only 0.376%, but map L1 is 12.35% and
normalized L-infinity is 20.14%. Peak-only selection would therefore be misleading.
Changing midpoint alignment also makes native peak convergence nonmonotonic.

Finest-grid native metrics (center-sample cell-average proxy):

| Point | Incident kW | Peak kW/m² | Mean kW/m² | Std kW/m² | CV | Surface centroid s m | Centroid z m |
|---|---:|---:|---:|---:|---:|---:|---:|
| high | 747725.166326 | 2216.803411 | 624.216667 | 601.114055 | 0.962989 | 27.772858 | 10.909629 |
| moderate | 643271.646182 | 2147.603332 | 537.016675 | 545.444717 | 1.015694 | 27.767110 | 10.924080 |
| morning | 476099.545716 | 1627.399298 | 397.457896 | 406.602015 | 1.023007 | 30.720693 | 10.934562 |
| afternoon | 580553.012342 | 1937.617696 | 484.657843 | 492.459211 | 1.016097 | 25.176103 | 10.927044 |

### Conditional recommendations and controlling cases

The configurable bands below are study criteria, not CSP standards. CONTROL
requires peak, normalized L1/L2/L-infinity, normalized centroid distance and
absolute CV change to pass at every representative point and every tested finer
nonreference level. A grid never qualifies through reference self-error.

| Band | Minimum tested CONTROL grid | Previous-reference selection | Energy/annual recommendation |
|---:|---|---|---|
| 0.1% | Not established | Not established | Not independently identifiable from normalized integral |
| 0.25% | Not established | Not established | Not independently identifiable from normalized integral |
| 0.5% | Not established | Not established | Not independently identifiable from normalized integral |
| 1% | Level 5: 222×87 | Not established | Not independently identifiable from normalized integral |
| 2% | Level 5: 222×87 | Level 4: 111×44 | Not independently identifiable from normalized integral |

At 1%, level 5 is controlled by morning/map_l1_normalized (0.60152% threshold units).

At 2%, level 5 is controlled by morning/map_l1_normalized (0.60152% threshold units).

Compare the two reference columns when assessing sensitivity to the added
refinement. Bands marked not established must not be represented as converged.
The final 444×173 grid is a numerical reference only; it has not been independently
validated against another finer level, measured plant data or stochastic optics.
Supported minimum-grid claims are conditional on that computed reference, not
continuum accuracy or a universal receiver resolution. Strict unresolved bands
require further measured refinement before their use in a paper.

## CPU/GPU correctness and cost

At all 28 state/grid combinations, Flat CPU and the unchanged resident CUDA
pipeline pass rtol=1e-9 and atol=1e-10. Worst map errors: absolute 1.205080e-11, relative 1.274077e-14, RMS 1.389288e-12 kW/m².

Integrated-power/peak differences and worst cells are retained per row. All GPU
and Flat repeated maps are bitwise deterministic on this build. Legacy/Flat
bitwise anchors pass at levels 0 and 3 for all four states; expensive finer Legacy
runs are deliberately omitted. Fine-grid CPU baseline remains Flat 1T.

The exact Phase 2D-C diagnostic/profile-enabled library is reused without a build:
SHA-256 0484808fda73a358c8d1409375b3367098a42f430f7fc0ce6d611fc4d10e3260.
Actual measurement root is b32ccd79a98b82386fe97ddd646f5020199bced5.
The immutable capture retains that executed SHA. Spatial analysis is reproducible
from the retained maps and separately records its analysis SHA and capture hash.
Identity rebinning avoids roundoff-only self-comparison errors without changing
any map or timing.
Its SSC/SolarPILOT/SolTrace SHAs match the initial state. Later root documentation
and smoke-grid derivation do not alter the library or measured configuration.

Existing canonical Docker image, RTX 6000 Ada, Xeon w5-3423, CUDA 13.0,
nvcc 13.0.88, GCC 13.3, Release -O3, sm_89; double/FMA, no fast math. Optical CPU
work is 1T on CPU0; telemetry uses CPU23. No packages, services, clocks, power
limits or governor were changed. OPENBLAS/OMP/MKL threads are limited to one.
Formal GPU preflight/owned-process/temperature monitoring passes; all telemetry
is retained. No simultaneous server compilation/test campaign was run.

Plain public simulate timings exclude diagnostic CSVs/events; compiled coarse
profiling probes remain in the common binary, as in Phase 2D-C. CPU first call
and one further warmup are excluded, then three samples retained. CUDA first call
and two further warmups are excluded, then ten samples retained. First calls are
fresh prepared-context observations in an initialized process, not cold-process
startup comparisons. All means/medians/extremes/stdev/CV are published. Three CPU
samples limit statistical precision; these results do not claim a best-multicore
baseline or production-profile-OFF speedup.

| Grid | Cells | Flat median range ms | CUDA median range ms | Speedup range |
|---|---:|---:|---:|---:|
| 7×3 | 21 | 111.896–115.257 | 60.267–65.428 | 1.762–1.873× |
| 14×6 | 84 | 132.111–137.403 | 60.225–67.121 | 1.998–2.214× |
| 28×11 | 308 | 207.658–221.462 | 61.809–65.428 | 3.223–3.512× |
| 56×22 | 1232 | 516.043–519.593 | 64.729–69.002 | 7.517–7.972× |
| 111×44 | 4884 | 1724.371–1732.044 | 80.492–84.947 | 20.380–21.423× |
| 222×87 | 19314 | 6691.741–6722.254 | 135.065–139.955 | 47.984–49.566× |
| 444×173 | 76812 | 25694.120–25753.279 | 357.708–361.855 | 71.170–71.917× |

Ranges above span the four operating states; they are not confidence intervals.
The maximum retained CV is 7.11% for CPU and 8.23% for CUDA, occurring in
coarser cases; samples are not trimmed.

The speedup increases with grid cells because per-cell density work grows while
fixed CPU preparation/integration costs are amortized. This is observed on the
same field/conditions; the commercial case also differs from the synthetic Phase 2
field, so field and grid effects must not be conflated across studies. No new
hotspot tuning or target-speedup calibration was performed. Physical convergence
criteria, not acceleration, determine retained scientific candidates.

## Experimental reference and future stochastic study

The experimental-scale flat-receiver reference retains its internal scientific
role only: future controls/annual/PSA comparison target. No private parameters
were extracted, no convergence simulation executed and no compatibility changes
made. The reusable rectangular utility accepts eventual public/authorized W,H
and generates Nx×Ny with the same conservative comparison framework. Flat CUDA,
existing aiming, Hour/Day, weather resolution and annual work remain deferred.

[soltrace-convergence-plan.md](soltrace-convergence-plan.md) designs a future
spatial grid × ray budget × independent-seed study. Pilot-derived logarithmic ray
levels, recorded launched/hit counts and stop rules, seed-level uncertainty and
common physical surface comparison separate discretization from Monte Carlo
noise. The current unsigned-seed/wrapper c_uint16 mismatch is documented to avoid
seed aliases. No SolTrace experiment or source change is part of Phase 3A.

A following phase may address experimental physical compatibility after reviewing
whether these conditional commercial resolution bands meet the intended paper
criteria. If stricter unresolved spatial bands are required, extend this study
first. Neither choice has been implemented.

## Validation, artifacts and limits

Utility tests: 13/13 (flat/cylinder dimensions, deterministic grids, cell sizes,
conservation, zero error, synthetic remap, centroid/seam, malformed inputs and
public provenance). Existing CPU CTest 3/3; production and diagnostic Python each
45 methods, with 10/9 expected GPU-related skips. Fresh reconstructed CPU CTest
3/3 and Python 45 methods pass. CUDA native CTest passes 6/6 and diagnostic Python passes 44 methods with one
expected gated timing skip. The final utility changes are independently retested
on CPU; the CUDA library is unchanged. Results are retained in the validation
JSON/logs. No new sanitizer claim is made because no core source
changed; prior Phase 2D-C sanitizer evidence remains immutable.

Machine-readable outputs include case sanity/provenance, 28 full rows, per-grid
worst/best/median errors, recommendations/reference sensitivity, separate cost
CSV, every timing sample, hardware/commit metadata, hashes and compressed public
Flat/CUDA maps. The summary script validates the original library identity,
map hashes, CPU/GPU tolerance and remap conservation before publication. Relative
paths only; no private file contents, usernames, IPs or private paths are included.

Limits: one public optical reference, four specified-sun states, one GPU/build,
CPU1T baseline, normalized midpoint maps, finite numerical reference and no field
measurement validation. ENERGY/ANNUAL spatial resolution is not independently
identified by a normalization invariant. No universal optimum, subcell peak,
annual-energy accuracy, confidence-qualified multicore advantage or exact
named-plant reproduction is claimed.

No shading/blocking optimization, additional Hermite CUDA tuning, experimental
CUDA compatibility, annual/batch API, CPU multithreading, multi-GPU, SolTrace
source changes, OptiX or push. All final active/reconstructed Git trees are audited
clean. Phase 3A stops here; no next implementation phase has started.
