# CPU/CUDA boundary

Implemented public selection remains CPU/CUDA with the existing C/Python signatures. CPU defaults to flat; the original legacy implementation is retained through internal benchmark controls. CUDA now performs real Hermite flux-density evaluation, with CPU optical preparation and post-processing. See [the Phase 2B backend contract](cuda-flux-density.md).

CopilotObject owns selected backend, requested device, unique_ptr<GpuContext> and error string. GpuContext now owns reusable heliostat/cell/output buffers and optional events with RAII. Selecting CUDA validates the device/probe and creates a context lazily without optical allocation; buffers grow on first evaluation and remain reusable across simulations and explicit CPU runs. Switching device closes the prior context; data_free performs checked teardown. Failed initialization/unsupported simulation never silently selects CPU.

Supported CUDA simulations are Hermite analytical, one enabled cylindrical receiver, simple aiming with updates, specified sun position and one CPU preparation thread. C simulate returns false on capability/runtime errors; Python callers retrieve get_last_backend_error. Backend/device setters retain their existing RuntimeError behavior. CPU-only selection reports CUDA support not enabled; hidden devices report No CUDA devices. Availability queries indicate runtime devices, not capability of every physical configuration.

The density hook is a non-owning pointer scoped to one sp_simulate call and reset by RAII. The owned context persists independently. All numerical device inputs are flat double arrays; no host objects/pointer graphs are copied. Host state remains canonical. Comprehensive mutation epochs, static-cell upload skipping, time-series and batch operations are future work; current independent buffers/transfers preserve that extension path.

## Proposed versions (not active in this iteration)

Monotonic uint64 versions owned by CopilotObject: layout, receiver, aiming, optics, sunshape. The GPU stores last uploaded versions. Track sun/DNI separately as small per-call scalars. Increment versions at successful mutations, never at getters; conservative invalidation for unknown setters protects correctness. Derive tracking and sun-dependent neighbor validity from input epochs, not just layout.

| Mutation | GPU action |
|---|---|
| DNI | Upload scalar only; no static geometry, may need receiver thermal state update |
| Sun position | Upload sun vector; recompute tracking, intercept and sun-dependent neighbors; retain geometry/CSR storage |
| Aimpoint | Increment aiming; upload affected aimpoints, regenerate tracking/intercept |
| Reflectivity/soiling | Increment optics; update per-heliostat/template optics, power/reductions |
| Sunshape/error/cant/focus | Update corresponding optical coefficients; changed focal/cant geometry also invalidates panel-derived data |
| Receiver dimension/offset/type | Increment receiver; rebuild flux grid and receiver association/acceptance as necessary |
| Layout/template membership | Increment layout; rebuild geometry, panel ranges, association and neighbor CSR |
| `update_geometry`, load/reset/add/drop | Conservatively invalidate all affected epochs |
| Optimizer/internal mutation | Use same invalidation boundary; APIs alone are insufficient |

Important correction: fixed heliostat positions do not imply fixed neighbor lists. `SolarField::Simulate` calls UpdateNeighborList using zenith and current geometry. Layout neighbors use zenith=0. GPU candidate/sun batches must regenerate or cache the right neighbor state; merely uploading geometry once must not freeze shadow/blocking relationships.

No same-context concurrent simulate/mutation is supported by the legacy API. Future multi-stream batch operations need explicit ownership/locking; independent contexts are preferable meanwhile.
