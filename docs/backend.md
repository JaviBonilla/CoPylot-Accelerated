# Minimal CPU/CUDA boundary

Implemented: additive C symbols and Python wrappers. `CopilotObject` owns `ComputeBackendState`: selected backend (CPU by default), requested device, `unique_ptr<GpuContext>`, per-context error string. `GpuContext` is only an ownership boundary with a virtual destructor; no buffers are allocated and no transfer/invalidation system is active yet.

`sp_simulate` performs one switch outside numerical loops. CPU calls `simulate_cpu`, whose original body is preserved. CUDA has no optical implementation: selecting it returns false in C and raises `RuntimeError("CUDA backend not implemented yet")` in Python; the previous selection remains active. No silent execution fallback after a requested CUDA operation fails. The existing CPU remains available by explicit selection and as the default.

New C exports:

* `sp_cuda_available()` and `sp_cuda_device_count()` are context-independent. CPU-only builds return false/0. CUDA enumeration errors return -1 and expose a thread-local message through `sp_cuda_last_error()`; Python raises it. A visible device does not establish optical CUDA support.
* `sp_set_compute_backend(context, 0/1)`, `sp_get_compute_backend(context)`; getters return -1 for null context. Future CUDA support will make enum 1 selectable only when initialization succeeds.
* `sp_set_cuda_device(context, index)` checks range and executes the trivial CUDA probe when compiled with CUDA. The probe restores the calling thread's prior device. Successful selection records the requested device and releases any future GPU context if it changes; failed selection preserves it.
* `sp_get_last_backend_error(context)` reports selection errors. New functions handle null contexts. Existing general C ABI functions retain upstream preconditions.

Python retains old constructor/method signatures, adding `cuda_available`, `cuda_device_count`, `set_compute_backend`, `get_compute_backend`, `set_cuda_device`, `get_last_backend_error`. The extensions require the extended library only when called. Result-array ownership for the three exercised exports (layout, fluxmap, details) is corrected using try/finally and the existing `_sp_free_var`; successful results have unchanged types and values.

## Future persistent context

Create the CUDA context lazily on first GPU simulation after choosing device. Concrete GpuContext owns device buffers/stream/events with RAII, tracks capacities, grows only on layout-size changes, and reuses all allocations across simulate/evaluate_batch calls. Never copy SolarField or Heliostat objects to VRAM. Clear it on data_free or device replacement. Keep CPU state canonical and synchronize only modified numeric inputs; an explicit CPU run remains the regression oracle.

Add `ensure_capacity`, `upload_changed_inputs`, `simulate`, `download_requested_outputs` to the concrete implementation once kernels exist. Keep dispatch outside heliostat loops; do not use a virtual call per heliostat. Batch evaluation needs a dimensions/stride contract plus reductions and constraints on device, returning a small objective vector rather than details/fluxmaps to Python. Batch APIs are deliberately not exposed until those semantics are implemented.

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
