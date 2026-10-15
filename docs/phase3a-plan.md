# Phase 3A execution plan

Start from clean root 48bf782 and unchanged Phase 2D-C dependencies. Preserve
all prior evidence and private data. No core or SolTrace change is planned.

1. Inventory existing public examples and evaluate SSC MSPT, Crescent Dunes and
   Gemasolar against completeness, physical scope and public reconstruction.
2. Reuse the pinned public SSC 8790-coordinate field and tower/receiver geometry;
   classify the optical mapping and every explicit assumption in a manifest.
3. Test a physical flat/cylinder grid utility, conservative area-overlap remap,
   metrics, invalid inputs and selection across all operating points.
4. Run six physically generated levels and a finer validation level for four
   specified-sun states. Keep point-sample/normalization limitations explicit.
5. Check Flat/CUDA at every level; use Legacy coarse/intermediate anchors.
   Measure one-thread CPU and CUDA only inside a monitored idle window.
6. Publish samples/maps/metrics, conservative comparison error and supported
   recommendations. Write the future grid x rays x seeds SolTrace plan only.
7. Recheck tests, pinned reconstruction, immutable previous evidence and clean
   Git trees; commit logical root changes without pushing. Stop after Phase 3A.

## File plan and validation matrix

| Files | Purpose | Validation |
|---|---|---|
| cases/commercial-reference/case_manifest.json | Parameters/provenance/assets | Hash checks, count, geometry and area checks |
| benchmarks/commercial_reference.py | Reconstruct supported optical case | Deterministic coordinates, CPU smoke, actual API geometry |
| benchmarks/receiver_grid.py | Physical grids/remap/metrics/selection | Analytical constant/ramp/nonmatching grids, conservation, malformed inputs |
| benchmarks/receiver_grid_convergence.py | CPU/CUDA study | All states/levels, strict numerical comparisons, retained samples/telemetry |
| tests/test_receiver_grid.py | Independent utility checks | Focused unittest suite |
| docs/phase3a-report.md and scientific design docs | Evidence/limits/future design | Review against actual result JSON and source |

The public dimensional flux integral is normalized to heliostat delivered power.
Its grid invariance must not be interpreted as independent integration accuracy.
Map/peak criteria and conservative remap are required for spatial conclusions.
