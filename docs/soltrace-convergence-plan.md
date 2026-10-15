# Future Hermite–SolTrace convergence experiment (design only)

Phase 3A does not execute, modify, rebuild or update SolTrace. Its pinned source
remains 699263f12b2de1c6f12e211e3e8906a80054cc1b. This document is an experiment
plan, not a claim of validated bridge compatibility or stochastic results.

## Existing interfaces inspected

- `SolarPILOT/deploy/api/copylot.py`: `export_soltrace` and
  `load_soltrace_structure` construct/export optical geometry. The example
  `test_solarpilot_soltrace.py` bins receiver hits on an unwrapped cylinder.
- `SolTrace/coretrace/stapi.h`: `st_sim_params` accepts desired ray count and
  maximum launched count; `st_sim_run` has an unsigned seed. Intersection and
  sun-statistics APIs expose interactions and launched-ray normalization data.
- `SolTrace/app/deploy/api/pysoltrace.py`: `num_ray_hits`, `max_rays_traced`,
  `raydata`, `sunstats`, `powerperray` and `run(seed,...)` provide the necessary
  control/normalization concepts. Successful imports/exports are not established
  merely by reading these signatures and must be checked in the future phase.
- The pinned Python wrapper passes `c_uint16(runseed)` to an unsigned C seed.
  A future campaign must record requested and effective seeds and avoid modulo
  65536 aliases. Positive distinct 16-bit seeds are a conservative initial
  choice; do not silently assume arbitrary Python integers are distinct seeds.
  Record all execution-thread details because wrapper multithreading changes
  seed allocation. No source correction is made in this phase.

## Two independent convergence dimensions

Use receiver spatial grid × Monte Carlo ray budget × independent seeds. A fine
receiver grid with few hits per cell can be noisier than a coarse grid. Neither
the highest resolution nor one stochastic run is an exact reference.

Start with a bounded pilot to estimate runtime, hit efficiency and between-seed
variance on selected coarse/intermediate grids and representative sun states.
Choose N0 from that evidence, then a logarithmic progression (for example
multipliers near 1, 3 and 10) until explicit uncertainty and runtime criteria are
met. These are progression concepts, not fixed final ray counts. Retain several
spatial levels from the physical grid generator, including levels finer than a
candidate converged grid. Do not prescribe the final grid/rays independently.

Record requested hits, maximum launch cap, actual launched solar rays, actual
receiver hits, accepted/absorbed hits, stop reason, runtime, effective seed and
power per ray. Desired hits and launched rays are different quantities. A run
hitting the launch cap is not equivalent to reaching the requested receiver-hit
count. Prefer a fixed launched-ray budget where supported; otherwise account for
the engine's stopping/normalization convention and test for stopping bias.

## Repeatability and uncertainty

Use several independent seeds in the pilot and increase the replicate count
until confidence intervals are stable for the retained decisions. Choose and
record the final number after the pilot rather than declaring one arbitrary
universal count. Freeze a reproducible, alias-free seed list before confirmation.

For integrated power and other well-behaved replicate statistics, report seed
mean, sample standard deviation, standard error and a stated confidence interval
(e.g. mean ± Student-t quantile × s/sqrt(K), with K−1 degrees of freedom).
Use seed-level bootstrap sensitivity checks for nonlinear peak, centroid and
uniformity metrics. Peak-of-one-noisy-map is biased upward; compare both the peak
of the ensemble-mean map and the distribution of seed-wise peaks. They answer
different questions and must not be substituted silently.

For maps, report per-cell between-seed standard deviations, normalized map RMS
noise and covariance-aware aggregate errors. Do not claim global agreement from
pointwise intervals without simultaneous-coverage/multiple-comparison treatment.
Bootstrap whole seed maps, not individual hits/cells as independent observations.
Multiple interactions of one ray are correlated. Keep raw hit/launch counts and
normalization evidence so uncertainty can be audited.

Spatial error is assessed at high enough ray counts (or from ensemble means)
while sampling noise is assessed at fixed grids across seeds. The numerical
reference must itself have documented uncertainty. Use both dimensions to show
that apparent grid changes are distinguishable from seed dispersion. Where
possible, rebin the same stored hit set to multiple grids to isolate spatial
binning effects; use independent seed families for final confirmation rather
than relying only on correlated refinements.

## Shared physical comparison

Use identical public geometry, heliostat states, sun/optical error distributions,
DNI, aiming, visibility rules and attenuation assumptions as far as the model
interfaces permit. Record every remaining model difference. A bridge smoke test
must verify coordinate axes, units, facet geometry, mirror/receiver reflectance,
sunshape, receiver orientation and relevant error conventions before comparison.

For cylinders, use unwrapped s=Rθ and z with explicit seam and angular direction;
for rectangles, use x and y. The Phase 3A API adapter reverses top-first Hermite
rows into bottom-first z. Its native columns follow decreasing physical azimuth;
SolTrace hit azimuth must be transformed into that same seam/direction. Points
on a periodic seam are wrapped once, and top/right boundaries have explicit
half-open bin rules. Compare incident power and absorbed power separately.

Normalize stochastic hit weights from launched solar-ray area and physical
power-per-ray, retaining actual engine bookkeeping. Receiver absorption flags
must not be mistaken for incident flux. Do not force stochastic map integrals
to match Hermite: that would erase a real model or normalization discrepancy.

Each solver may keep its own independently converged native grid. Transform
piecewise cell averages with conservative area-overlap rebinning onto a common
physical comparison grid. Retain the integral-conservation residual, and assess
projection/coarsening error using known analytic maps and finer references.
Hermite values are normalized midpoint samples represented as cell averages;
that approximation must remain explicit in the comparison.

## Retained metrics and decision

Compare integrated incident power, peak cell-averaged flux at a stated common
resolution, surface/circular centroid, mean, CV/uniformity, normalized L1/L2,
absolute/normalized L-infinity, and vertical/circumferential profiles. Common-grid
peaks and native-grid peaks must have separate labels. Report model differences
alongside Monte Carlo intervals, not just one deterministic error percentage.

SolTrace is a higher-fidelity stochastic optical model, with finite-sampling
noise and its own geometry/optical assumptions. It is not physical truth.
Laboratory or field measurements would form a separate validation layer.
No final ray count, stochastic reference grid, accuracy claim or performance
number is selected by this planning-only phase.
