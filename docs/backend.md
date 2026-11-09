# Execution backends

CoPylot selects `cpu` or `cuda` with `set_compute_backend`. The execution
approaches share the Hermite optical formulation and expose the usual receiver
map, summary and per-heliostat results. Backend selection belongs to each
CoPylot context.

## CPU

The standard CPU path uses the refactored Flat image-plane and flux-density
calculation. Pass `nthreads=1` to `simulate` for Refactored CPU or a higher
thread count for Multicore CPU. The [multicore design](cpu-multicore-design.md)
describes parallel work within a simulation. The temporal benchmark also
distributes states across independent contexts.

A diagnostics build recognizes `SOLARPILOT_INTERCEPT_PATH=legacy` and
`SOLARPILOT_FLUX_PATH=legacy`. Set both and use one CPU thread for the retained
Original calculation. Use a separate process or reset these environment
variables before running the standard Flat or CUDA paths. Diagnostic comparison
modes are for numerical checks.

## CUDA

CUDA evaluates the image-plane and receiver flux-density stages in double
precision. The CPU handles geometry preparation, optical output writeback and
post-processing. The API checks device availability and reports unsupported
configurations as backend errors. Retrieve simulation failures through
`get_last_backend_error`.

The validated path supports Hermite analytical flux with one enabled receiver.
Use a closed external cylinder or rectangular flat plate without a snout,
simple or Keep existing aiming, and specified-sun or Hour/Day inputs. The
image-plane path also checks the canting mode and supports up to 64 facets per
heliostat. An ordinary CUDA simulation uses one CPU preparation thread. See the
[flat-receiver validation](phase3b-report.md) and the
[CUDA handoff design](cuda-imageplane-fluxdensity-handoff.md) for the tested
configurations and numerical comparisons.

The temporal CUDA harness can evaluate multiple states using independent GPU
contexts. The [annual workflow](public-reproducibility.md#optional-complete-commercial-year)
describes the rolling-context protocol used for the archived annual comparison.
