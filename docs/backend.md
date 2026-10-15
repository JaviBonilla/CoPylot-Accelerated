# CPU/CUDA boundary

Implemented public selection remains CPU/CUDA with the existing C/Python signatures. CPU defaults to flat; the original legacy implementation is retained through internal benchmark controls. CUDA now performs the validated image-plane numerical core followed by the existing flux-density kernel. CPU still prepares objects/inputs, downloads and writes all optical outputs, and performs normalization/post-processing. See [the current Phase 2D-C handoff](cuda-imageplane-fluxdensity-handoff.md) and [the original Phase 2D-B design](image-plane-cuda-design.md); [the Phase 2B density contract](cuda-flux-density.md) remains the historical density-only reference.

CopilotObject owns selected backend, requested device, unique_ptr<GpuContext> and error string. GpuContext owns the unchanged reusable density heliostat/cell/output buffers plus a separate RAII image-plane executor with independent input/output/table capacities. Optional events belong to their respective executor. Selecting CUDA validates the device/probe and creates a context lazily without optical allocation; buffers grow on first evaluation and remain reusable across simulations and explicit CPU runs. Switching device closes the prior context; data_free performs checked teardown. Failed initialization/unsupported simulation never silently selects CPU.

Supported CUDA simulations are Hermite analytical, one enabled cylindrical receiver, simple aiming with updates, specified sun position and one CPU preparation thread. The CUDA image-plane path additionally requires a continuous closed cylinder, no-cant or on-axis slant/user-radius canting, and at most 64 facets. Unsupported inputs raise a clear backend error, never a CPU fallback. C simulate returns false on capability/runtime errors; Python callers retrieve get_last_backend_error. Backend/device setters retain their existing RuntimeError behavior. CPU-only selection reports CUDA support not enabled; hidden devices report No CUDA devices. Availability queries indicate runtime devices, not capability of every physical configuration.

The two GPU hooks are non-owning pointers scoped to one sp_simulate call and reset by RAII. A single image-plane batch runs after tracking; its prepared-intercept flag is scoped to the performance simulation and cleared on exceptions. The existing per-H loop retains its intercept clamp and shading/blocking logic. The owned context persists independently. All numerical device inputs are flat double arrays; no host objects/pointer graphs are copied. Host state remains canonical. Comprehensive mutation epochs, static-cell upload skipping, time-series and batch operations are future work; current independent buffers/transfers preserve that extension path.

## Internal scientific paths

Diagnostics builds retain `SOLARPILOT_INTERCEPT_PATH=legacy|flat|verify|cuda|verify_cuda`.
With public CUDA selected, `flat` explicitly requests the historical CPU-intercept
plus CUDA-density pipeline. The Phase 2B/2C harnesses select that path themselves.
With CPU selected, `cuda`/`verify_cuda` are internal tests of CUDA intercept plus
Flat CPU density. No public backend signature or serialized setting is added.
Without diagnostic overrides, public CUDA uses both CUDA numerical stages.

Every nonempty CUDA image-plane call uploads all inputs and tables. Production
uses 64 image threads per block. A separate health kernel checks all 215 outputs
and returns intercept/update/status. The existing CPU efficiency loop supplies
current direction, aim and normalization; a separate conversion kernel combines
those seven doubles with 18 resident optical doubles for the unchanged density
kernel (256 threads/block). Complete optical output is then downloaded and
written before final completion callbacks and successful public return.

The pending flag and exact heliostat ordering are scoped to one simulation.
Unsupported ordering or an unupdated image uses full materialization with the
same CUDA optics; there is no silent CPU fallback. Full verification and mixed
CUDA-image/Flat-density routes retain all outputs and comparisons. Diagnostic
`SOLARPILOT_IMAGE_PIPELINE=v1` with `SOLARPILOT_IMAGE_BLOCK_SIZE=128` selects
the full-output launch control; production ignores diagnostic selection knobs.
No public argument or serialization setting was added.

Total H2D decreases by 144 B/H; total D2H increases by 16 B/H because eager C++
compatibility remains mandatory. See the handoff report for exact formulas.
Allocation reuse is retained, without cross-state optical caching. The per-H
`Flux::imagePlaneIntercept` scope measures retrieval; use image batch preparation,
materialization and CUDA event statistics for full optical costs.

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
