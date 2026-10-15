# Image-plane intercept: pre-extraction analysis

This analysis was written before the numerical extraction. The initial oracle is SSC
5343ddbef451549ac573ccd020f692c26ee0e222, Flux.cpp lines 711–2140.
Phase 2D-A preserves double precision and the seven-term, order-six Hermite model.

## Actual call flow and scope

`sp_simulate -> simulate_cpu -> interop::PerformanceSimulationPrep ->
SolarField::Simulate -> SimulateHeliostatEfficiency -> Flux::imagePlaneIntercept ->
hermiteIntEval -> hermiteIntegralSetup -> hermiteIntegral`.
Simple aiming runs twice (initial and final) and updates tracking, but does not
itself call intercept. The performance loop calls intercept once for each enabled,
accepted heliostat. Disabled heliostats and receiver acceptance failures return
before this call, zeroing efficiencies/power. Layout optical zoning instead calls
one representative per nonempty group and copies image state to its group; the
subsequent efficiency loop skips intercept. `RefactorHeliostatImages` is a separate
caller that processes every heliostat without setting intercept efficiency. Other
aiming paths can invoke image refactoring and are outside this validation scope.
Measured call counts and grid independence will be recorded before extraction.

The validated dispatch is analytical Hermite, one enabled continuous external
cylinder, simple aiming, specified sun position, and one CPU thread. Other paths
must keep the historical implementation. No receiver/aiming support is expanded.

## Mathematical stages and dependencies

1. Receiver normal at the heliostat location: `CalculateNormalVector`, atan2,
   sin/cos; dot with tower vector. A nonnegative dot returns zero without updating
   image state. For the cylinder the normal is radial with configured elevation.
2. Sun moments: cylinder slant = sqrt((radial distance - diameter/2)^2 + optical
   height^2)/tower height. Repeated powers multiply normalized `_mu_SN` in the
   existing parity/total-order bounds. This is not a fresh sunshape integration.
3. Error propagation: tracking, tower and sun unit vectors define zenith/azimuth
   transforms (acos, atan2, sin/cos, sqrt). Angular azimuth/elevation errors, surface
   slopes x/y and reflected-ray errors x/y define delta1/delta2/covariance.
   The covariance threshold `delta_a^2 < 1e-20` selects separable factorial moments;
   otherwise normalized `_mu_GN` coefficients form correlated moments with pow.
4. Mirror projection: normalized mirror moments, focal distances x/y, A/B
   transforms, slant and cosine efficiency produce projected moments with nested
   binomial sums. Constants including the Eij `1e-10` shifts are retained exactly.
5. Facets: no cant, on-axis at slant, user radius and historical off-axis formulas
   translate panel centers and convolve their powers with saved mirror moments.
   Panel order is row then column and must not change. User-vector cant throws.
   Only the first three cant methods will enter the new validated dispatch.
6. Convolution: S, G and M moments are combined in the existing m,n,k,l,i,j loop
   order, normalized by their zeroth-moment product. No cross-heliostat sum exists.
7. `hermiteIntEval`: sqrt of F(2,0), F(0,2) sets image sigmas. It calls the aperture
   integral then evaluates 16 packed Hermite coefficients using factorials and
   `_binomials_hxn`, accumulating intercept in packed order. The historical
   normalization constant is 6.2832, not an exact 2*pi replacement.
8. Cylinder `hermiteIntegralSetup`: optical height normalization, apparent
   diameter, receiver height, tower zenith and flux-plane aim x/y determine curved
   aperture bounds. The four-sigma combined-radius clipping branch is preserved.
9. `hermiteIntegral`: 16 fixed quadrature abscissas/weights, exp cutoffs at squared
   distance 100, nine-term recurrences, the historical four-coefficient normal-CDF
   approximation and pow(...,-4). Accumulates 16 spill terms in original order.
10. A heliostat inside the cylinder radius returns zero *after* updating state.
    The normal performance caller clamps returned intercept above one.

`Flux::Setup` fixes order=6, terms=7, factorial and binomial tables, quadrature
weights/abscissas and CDF coefficients. `initHermiteCoefs` supplies normalized
sun/error tables; mirror normalization is prepared for heliostat geometry. Neither
is recalculated by intercept. No RNG is used in this call chain.

## Exact output ownership and consumers

| State | Shape/type | Scale | Owner/lifetime | Consumer |
|---|---|---|---|---|
| Sun moments `_mu_S` | 7x7 doubles | image coordinates / tower height, moment powers | Heliostat, overwritten on next visible evaluation | convolution; diagnostics |
| Error moments `_mu_G` | 7x7 doubles | same moment powers | Heliostat | convolution; diagnostics |
| Mirror moments `_mu_M` | 7x7 doubles | normalized mirror projection; unnormalized zeroth moment includes cosine/facets | Heliostat | convolution; diagnostics |
| Flux moments `_mu_F` | 7x7 doubles | unit-flux normalized moment powers | Heliostat | hermiteIntEval; CopyImageData |
| Image size | 2 doubles | dimensionless sigma (length / tower height) | Heliostat | CPU/CUDA density packing and Hermite normalization |
| Hermite coefficients | 1x16 doubles | historical normalized polynomial density factors | Heliostat | hermiteFluxEval, Flat/CUDA fluxDensity |
| Intercept return | double | dimensionless efficiency | caller; stored separately after clamp | optical efficiency and receiver power |

All 49 entries of each matrix, including unused zero entries, need comparison.
No aim offset is produced here; density also reads independently prepared tracking,
tower direction, aim, receiver geometry, power and normalization. No additional
writeback to a receiver, sunshape table, neighbor or other heliostat occurs in the
validated cylinder chain. Cavity/snouted paths can mutate an aim point in setup;
these remain legacy and are not evidence for independence of unsupported paths.

## Independence and grid resolution

The cylinder path reads only this heliostat plus immutable Flux tables and
receiver/variable state. All numerical temporaries are local. No cache or global
accumulation is present. Reordering independently evaluated heliostats cannot
change their outputs; simultaneous writeback to the *same* heliostat is unsafe.
Setup/table mutation, diagnostic environment changes and shared CSV output must
not run concurrently with evaluation. This phase introduces no parallelism.

Neither intercept nor the cylinder helpers read flux surfaces, grid dimensions,
cell positions or cell areas. Receiver apparent diameter is a scalar diameter for
a continuous cylinder. Grid independence follows from these reads and will also
be checked across 25x25, 50x50 and 100x100 output snapshots and call counts.

## Allocation and numerical risks

`matrix_t`/`block_t` constructors allocate even their initial single element;
resize reallocates on dimension changes. Repeated calls reuse H output matrices
but allocate temporary srange, factorial matrix (uncorrelated branch), saved mirror
moments, facet centers/power blocks, spill/power vectors and quadrature h matrix.
Bounds helpers JMN/JMX/IMN are out-of-line member calls in the old translation
unit. Structural overhead and actual mathematical cost must be separated by
opt-in stage profiling and uninstrumented aggregate timing, not guessed from
allocation counts. Allocations will not be attributed isolated time without a
separate allocator measurement.

Preconditions: positive tower and receiver optical height; normalized finite unit
vectors; nonzero focal/cant distances where divided; positive moment normalization
and sigmas; positive facet counts matching actual panel dimensions; initialized
seven-term tables. Zero covariance is explicitly handled, zero zenith sine gets
1e-6, Eij gets 1e-10. These guards do not make arbitrary singular inputs valid:
A21 divides by cos(n_zen), projection divides by E12/E22/step, correlated moments
by rho and rho_sq, coefficients by sigmas. Zero facets can zero normalization;
invalid aim/sun vectors can yield NaN. Direct intercept does not check IsEnabled;
that check belongs to the performance caller. Existing unsupported user-vector
cant errors and undefined singular inputs must not be silently repaired here.
The fixed `h` recurrence starts from initialized zeros (including h(0,1) and
h(2,1)); these historical values must remain unchanged.

## Planned flat boundary (before extraction)

Use trivial fixed arrays for seven-term tables, four output matrices, 16 packed
coefficients, sigmas and intercept. Copy only required scalar inputs and panel
centers, with a bounded supported facet capacity and legacy fallback above that
capacity. Split immutable tables from per-heliostat input; build tables once at
the start of a simulation, with explicit invalidation at table initialization.
The pure core will have no object graph, virtual calls, heap allocation, growing
vectors or map lookup. Keep the complete old algorithm as private oracle.
Preparation checks support/visibility; writeback restores every historically
modified H field. Diagnostic selector and verification remain opt-in.

A future GPU work item could be one heliostat: no field reduction is required.
Large local moment/facet arrays, pow/exp/trig and cant/covariance/clipping branches
are likely more consequential than launch configuration. Input/output bytes,
local stack and final timings must be measured before deciding a CUDA mapping.
No device structures, kernels, buffers or block sizes are introduced in 2D-A.
