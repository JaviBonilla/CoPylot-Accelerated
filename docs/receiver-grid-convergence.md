# Physical receiver-grid convergence

This tooling studies minimum *tested* converged resolution for declared metrics,
tolerances and operating states. It does not identify a universal optimum or
validate the underlying optical physics. The 25²/50²/100² Phase 2 grids remain
computational scaling fixtures, not scientific receiver-resolution choices.

## Physical parameterization

For a rectangle of width W and height H, choose Nx=ceil(W/Δ), Ny=ceil(H/Δ).
For a cylinder of diameter D and height H, use surface width S=πD and choose
Ntheta=ceil(S/Δ), Nz=ceil(H/Δ). There are at least two cells per axis. Thus ds=S/Ntheta
and dz=H/Nz do not exceed the target size and approach comparable dimensions.
No SolarPILOT mathematics or native geometry is changed to enforce square cells.
The generic flat-grid path is independently tested but not executed on private
experimental data. Only continuous complete cylinders are executed in Phase 3A.

The reference series uses physical targets 8, 4, 2, 1, 0.5 and 0.25 m. An additional
0.125 m level tests the previous finest grid and becomes the final numerical
reference. Grids are deterministic, aspect-aware and bounded in cell count.
Further levels can be supplied by extending the manifest after inspecting costs
and errors; an unconverged band is reported honestly rather than refined without
limit. Duplicate, malformed and excessive grids are rejected.

## Native map semantics and conservation

The current analytical core evaluates flux at cell centers. `FluxSurface::Normalize`
normalizes by the sum of these samples; `CalcDimensionalFluxProfiles` then scales
them to delivered heliostat power divided by cell area. The public dimensional
map's integral is consequently constrained by the heliostat/intercept model and
is almost grid invariant. This is *not independent evidence* of spatial energy
convergence or of annual-energy accuracy.

The framework represents each normalized midpoint value as a uniform value over
its equal-area cell. `peak_cell_average_proxy_kw_m2` is deliberately labelled a
proxy: the core does not integrate an exact cell average. Rebinning a finer map
to a coarse grid provides an additional approximate cell-average peak comparison.
No claim of a true subcell maximum or exact physical cell average is made.

C API maps arrive top-first; the adapter reverses rows so z grows from bottom.
Cylinder columns follow the native clockwise-edge to counterclockwise-edge
ordering (decreasing physical azimuth). The same seam, direction and origin are
used across all grids. Surface centroid is seam-dependent; an additional circular
centroid/resultant is recorded, with undefined angle for a uniform distribution.

## Conservative common-grid comparison

Compare on the same unwrapped [0,S]×[0,H] surface. For each target cell, compute
one-dimensional interval overlaps along both axes. Their product gives the
source/target overlap area; divide by target area to obtain target averages.
The separable calculation avoids a four-dimensional cell-pair array. Every
source cell contributes its complete area exactly up to floating-point rounding.
This handles noninteger refinement ratios as well as aligned grids.

Coarse maps are rebinned onto the finest reference grid, never compared by
unmatched cell indices or nearest-neighbor values. Retain relative integral
residual for every transformation. Conservation does not imply zero projection
error: piecewise-constant reconstruction loses subcell structure, and this
comparison measures discretization plus representation error. Exact constant,
known ramp and noncommensurate-grid tests quantify these properties independently
of SolarPILOT. Fine-reference-to-coarse rebinning also reports the coarse-average
peak and native/coarse-reference peak difference.

## Metrics and criteria

Each native map supplies integrated incident kW, peak proxy kW/m², mean, standard
deviation, CV=std/mean and flux-weighted surface/z centroid. Comparison supplies:

- Relative integrated power and peak change.
- L1=mean(abs(F−R))/mean(R), using equal-area common-grid cells.
- L2=sqrt(mean((F−R)²))/sqrt(mean(R²)).
- Absolute L-infinity in kW/m² and normalized L-infinity divided by reference peak.
- Centroid distance divided by receiver-surface diagonal and absolute CV change.
- Conservative remap's relative integral residual.

Tolerance bands 0.1%, 0.25%, 0.5%, 1% and 2% are configurable *study criteria*.
For dimensionless centroid error and CV change the band is an absolute threshold,
not a claim of a universal percentage standard. A control candidate must pass
all six configured peak/map/centroid/CV criteria for every representative state,
and every tested finer nonreference level must also pass. The reference grid
cannot qualify itself by its automatic zero self-error. Report the controlling
state/metric and recommendation sensitivity to the previous reference.

Energy-only normalized-integral candidates are published for diagnosis but are
not scientific ENERGY/ANNUAL recommendations. An independent energy discretization
study or alternative observable is needed to identify that resolution. A
CONTROL recommendation is conditional on the chosen tolerance, model, states,
proxy representation and measured finer-reference change. REFERENCE means a
computed numerical comparator, never an exact solution. Results and actual
recommendations are recorded in `phase3a-report.md` after the campaign.

## Reproduction

```sh
OPENBLAS_NUM_THREADS=1 COPILOT_LIB_DIR=build/cpu/lib .venv/bin/python benchmarks/commercial_reference.py --output artifacts/phase3a/case.json
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m unittest discover -s tests -p test_receiver_grid.py -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 COPILOT_LIB_DIR=build/cuda/lib .venv/bin/python benchmarks/receiver_grid_convergence.py --output artifacts/phase3a/convergence.json
```

The timing campaign refuses existing output and rejects an external GPU process,
thermal slowdown or invalid load window. It never manages external services.
`--cpu-only` permits non-GPU work without publishing GPU performance. The formal
run reuses the exact Phase 2D-C library and retains all first calls, warmups,
samples, CPU/GPU errors, map archives, hashes and telemetry. No core optimization,
new physics support, time-series API or multithreaded CPU baseline is introduced.

To reproduce spatial analysis from the published capture/maps without simulations:

```sh
.venv/bin/python benchmarks/summarize_phase3a.py --input benchmarks/results/phase3a-grid-convergence-capture.json --case benchmarks/results/phase3a-commercial-case.json --maps-root benchmarks/results/phase3a-grid-maps --output artifacts/phase3a/republication
```

The immutable capture retains the executed measurement SHA and original relative
map paths. The map-root option resolves those paths to the public archive. Derived
results separately record the analysis SHA and capture hash. An identical grid
uses the identity transform exactly, avoiding roundoff-only reference self-errors;
this comparison utility change does not alter any measured map or timing.
