# Phase 2D-C execution plan

Initial clean integration: ddffe62; SSC: 012b1a2ce. SolarPILOT and SolTrace stay
pinned. The initial-state inventory protects all published 2C/2D-A/2D-B evidence.

1. Capture the exact unmodified 2D-B library in a dedicated v1 snapshot. Root
   benchmark/test-harness changes may record measurements; library/source hashes
   must prove that no numerical implementation changes precede the baseline.
2. Same-server direct 1k/5k/10k and nine-case simulate baseline: Legacy, Flat,
   density-only CUDA, v1 full-output CUDA. Separate cold process probe, fresh
   context first use, instrumented breakdown and plain steady-state samples.
3. Trace every optical family through density, API results and subsequent state.
   Document the full dependency and static/dynamic input tables before choosing
   reduced materialization or a resident interface. Preserve complete verification.
4. Bounded 64/128/256 launch experiment; check 512 resource feasibility. Keep
   density arithmetic/reduction and its 256 threads unchanged. Select from total
   pipeline evidence; stop kernel work when its contribution is minor.
5. Implement only justified preparation/writeback/handoff changes in SSC, with
   simulation-scoped validity, checked errors, separate kernels and reusable
   capacity. No cross-simulation optical cache, fusion, streams or pinned memory.
6. After each substantial change run native fixtures/edges, complete field state,
   mixed pipelines and nine downstream cases. Recheck determinism and API state.
7. Measure final plain simulate and instrumented profile; compute separate staged
   ratios and measured-profile Amdahl upper bounds, classified by workload.
8. CPU production/diagnostics, CUDA regression, CPU sanitizers, existing GPU tools,
   fresh mailbox replay/build/tests, evidence/docs commits, clean local/remote
   audits. No push and no next-hotspot implementation.

File-level scope: root benchmarks/tests/profiling and reports; SSC image-plane
executor/host adapter and narrowly scoped density interface/context integration.
Legacy and Flat numerical formulas, physical dispatch, shading/blocking algorithms,
SolarPILOT and SolTrace remain unchanged.

Every valid timing campaign requires stable idle preflight, exact owned GPU PID
monitoring, thermal checks and no simultaneous server build/test/benchmark jobs.
No services, clocks, governor or power limits are changed. All samples are kept;
failed windows remain ignored artifacts, never published performance evidence.
