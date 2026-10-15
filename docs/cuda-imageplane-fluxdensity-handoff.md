# Image-plane to density dependency analysis

This analysis precedes implementation. It describes the current consumers and
the conservative candidate to test, not an already accepted performance result.

## Complete output dependency table

Flat output contains exactly 215 doubles, in the following contiguous families.
The updated flag additionally controls the historical no-write behavior.

| Family | Values | CUDA density | Flat/Legacy density | CoPylot C/Python API | Other C++ consumers | Candidate lifetime |
|---|---:|---|---|---|---|---|
| Sun moments | 49 | No | No | Not directly exported | Legacy coefficient construction, CopyImageData, public Heliostat getter, diagnostics | Device until eager completion |
| Error moments | 49 | No | No | Not directly exported | Same internal/historical optical state and public C++ getter | Device until eager completion |
| Mirror moments | 49 | No | No | Not directly exported | Same internal/historical optical state and public C++ getter | Device until eager completion |
| Flux moments | 49 | No | No | Not directly exported | Legacy Hermite coefficient construction and public C++ getter | Device until eager completion |
| Hermite coefficients | 16 | Yes | Yes | Indirectly through flux maps | hermiteFluxEval, public C++ getter, CopyImageData | Device through density, then eager completion |
| Sigmas | 2 | Yes | Yes | Indirectly through flux maps | Sigma/probability/image-size aiming outside current dispatch; public C++ getter | Device through density, then eager completion |
| Intercept | 1 | Indirectly through CPU-derived normalization | Same | detail_results, efficiency, power and summaries | Per-H efficiency clamp and calcPowerEnergy | Mandatory early host value |

The existing sp_detail_results returns 25 columns plus optional corners/receiver;
it exports intercept and derived efficiencies/powers, not the four moment
matrices, sigmas or coefficients. get_layout_info optical details exports focal
and facet geometry, not these computed image-plane outputs. This does not make
the other state disposable: Heliostat exposes C++ getters, and later CPU calls
or alternative aiming paths can consume the stored state.

References: CoPilot_API.cpp sp_detail_results/sp_get_layout_info;
FluxDensityCuda.cpp and Flux.cpp fluxDensityFlat/Legacy, hermiteFluxEval,
sigmaAimPoint, probabilityShiftAimPoint and imageSizeAimPoint;
SolarField.cpp SimulateHeliostatEfficiency/calcAllAimPoints;
Heliostat.cpp CopyImageData and optical getters.

## Exact existing density input

The density record is 25 doubles (200 B): direction[3], aim[3], sigma_x/y,
normalization, coefficients[16]. Its device representation is SoA with stride
equal to the current H, independently of allocation capacity.

Eighteen doubles (144 B) come directly from image-plane output: sigmas and
coefficients. Seven doubles (56 B) remain CPU-derived: direction[3], aim[3], and
area * total_efficiency / tower_height^2. Normalization is computed after the
existing intercept clamp, attenuation, cosine and shading/blocking work.
Direction retains the original receiver-offset geometry and normalization order;
it must not be blindly replaced by an image-plane tracking/tower vector.

## Conservative resident candidate

Keep the two numerical kernels separate. A small checked device conversion can
combine resident image-plane output with the seven CPU-derived doubles into the
unchanged density SoA. This avoids downloading optical values for the purpose of
repacking/reuploading them between kernels.

Before the CPU efficiency loop, download only intercept/update/validation status.
The candidate must validate every output, not merely intercept, on device before
using any value. A simulation-scoped pending-materialization flag must describe
the state explicitly. Unexpected ordering/filtering or an unupdated image must
use complete materialization with the same CUDA numerical stages, preserving
the historical no-write semantics. They must never silently execute CPU optics.

For compatibility, eagerly download and write the complete optical output before
the public simulate call returns, and before final completion callbacks. This
preserves every C++ optical getter and subsequent CPU operation. It is not lazy
materialization, and no returned successful result leaves stale optical state.
Therefore the candidate may reduce intermediary H2D and host repacking without
reducing total complete-output D2H; transfer accounting must state this honestly.
Whether that tradeoff helps total simulate must be measured before acceptance.

The existing full-output route remains independently selectable for validation,
mixed CUDA/CPU density and scientific v1 comparison. No Python signature changes.
Sixty fixtures and complete 215-double field verification remain mandatory.

## Static and dynamic inputs

| Input group | Physical category | Invalidation/handling in this phase |
|---|---|---|
| Tower/receiver dimensions and offsets | Geometry/configuration | Repacked and uploaded every simulation |
| Normalized mirror moments and facet center arrays | Heliostat geometry/configuration | Repacked every simulation; no template-equivalence assumption |
| Cant method/radius, focal lengths, optical-error model | Configuration, potentially user-modified | Re-read every simulation |
| Sun moments/error/binomial/factorial/quadrature tables | Shared optical configuration | Uploaded for each nonempty evaluation |
| Sun/tracking/tower directions, slant/radial position, image-plane aim | Per-simulation geometry | Refreshed by the existing preparation and repacked |
| Intercept, image moments, sigmas, coefficients | Per-simulation numerical output | Resident only within this simulation |
| Direction/aim/total-efficiency normalization for density | Current geometry and efficiency | CPU retains original formulas and uploads current metadata |

No cross-timestep cache, annual state, batch API or multi-GPU scheduling is
introduced. Future temporal work could reuse some geometry only after explicit
mutation/version semantics are designed and tested separately.

## Required verification before accepting the candidate

Compare full and resident paths against Flat across all nine cases; verify all
215 output doubles and canonical host getters after return, not just maps.
Exercise backend switches, enable/disable changes, geometry/optical modifications,
repetition, growth/shrink, rejected devices and unsupported inputs. Check GPU
output flags and strict rtol=1e-9/atol=1e-10, plus same-build determinism. Preserve
the density arithmetic and reduction token sequence and block size 256.
