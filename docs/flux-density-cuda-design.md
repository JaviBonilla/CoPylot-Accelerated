# Flux density CUDA design (Phase 2A only)

No optical CUDA kernel, optical allocation/copy, pinned memory, device reduction or host/device annotations were implemented. CPU coefficient generation and the existing host normalization/dimensional conversion remain the first-port boundary. The numerical function and direct fixtures define the input/result contract.

## Payload estimates

For H enabled heliostats and C cells: geometry/aim/sigma/normalization **72H** bytes; Hermite **128H**; cells **48C**; read-only parameters **16**; persistent input **200H+48C+16**; output **8C**; input plus output **200H+56C+16**. A naive one-double-per-interaction temporary adds **8HC** bytes (before any masks or reduction scratch). Estimates exclude allocator granularity, host identity tables, launch dimensions and unrelated solar-field memory. The CPU implementation only stores 56C bytes plus one 200-byte h record, so the full H-record estimate describes future residency, not current extra host allocation.

| H | Grid | H numeric B | Hermite B | Cell B | Output B | Persistent input B | Input+output B | Naive H×C B |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1000 | 25×25 | 72,000 | 128,000 | 30,000 | 5,000 | 230,016 | 235,016 | 5,000,000 |
| 1000 | 50×50 | 72,000 | 128,000 | 120,000 | 20,000 | 320,016 | 340,016 | 20,000,000 |
| 1000 | 100×100 | 72,000 | 128,000 | 480,000 | 80,000 | 680,016 | 760,016 | 80,000,000 |
| 5000 | 25×25 | 360,000 | 640,000 | 30,000 | 5,000 | 1,030,016 | 1,035,016 | 25,000,000 |
| 5000 | 50×50 | 360,000 | 640,000 | 120,000 | 20,000 | 1,120,016 | 1,140,016 | 100,000,000 |
| 5000 | 100×100 | 360,000 | 640,000 | 480,000 | 80,000 | 1,480,016 | 1,560,016 | 400,000,000 |
| 10000 | 25×25 | 720,000 | 1,280,000 | 30,000 | 5,000 | 2,030,016 | 2,035,016 | 50,000,000 |
| 10000 | 50×50 | 720,000 | 1,280,000 | 120,000 | 20,000 | 2,120,016 | 2,140,016 | 200,000,000 |
| 10000 | 100×100 | 720,000 | 1,280,000 | 480,000 | 80,000 | 2,480,016 | 2,560,016 | 800,000,000 |

Largest input+output is 2,560,016 B (~2.44 MiB), versus 800,000,000 B (~763 MiB) for a full contribution matrix. That temporary has no scientific necessity. Estimated bounded tile scratch for T heliostats/tile is 8C×ceil(H/T) bytes if each tile produces one partial/cell; a block/cell design needs only a block-sized shared reduction workspace and 8C output. Capacity is small even while vLLM reserves ~42 GiB, but available VRAM and external contention must be rechecked in Phase 2B; no service changes were made or proposed here.

## Candidate mappings

| Strategy | Parallelism and reuse | Costs and reduction behavior | Assessment |
|---|---|---|---|
| A: thread/cell, serial h loop | C threads; nearby threads read same h coefficients, potential broadcast/cache reuse; each thread retains its point | Only ~20 warps at C=625; long serial dependency and few blocks, poor GPU coverage likely; exact h sum order; H inputs reread per cell | Useful simple correctness reference; more credible for large grids or many independent simulations |
| B: block/cell, cooperative h loop | C independent blocks; each lane processes a strided h subset, point shared/broadcast; SoA gives adjacent h loads per coefficient | Repeated H loads between cells; each thread has a double partial and HX/HY scratch; fixed block tree changes h sum order but no global atomic or H×C buffer | Recommended first functional port, contingent on measured register use and occupancy |
| C: thread/(cell,h), atomic or full reduction | HC threads, easy abundant parallelism and point/h reuse via caching | Atomic contention on only C doubles, nondeterministic addition order; full materialized contributions consume 8HC and another pass; isolated per-pair math testing is easy | Avoid global atomic-per-pair as first production reference; use per-pair diagnostic tiles only if needed |
| D: cell×h tiles | Many tiles, staged coefficient reuse across several cells, shared point/h tiles | More indexing/synchronization, shared-memory footprint may limit occupancy; register live ranges grow with cells/thread; bounded partials need second fixed reduction | Strong follow-up if B is limited by repeated loads or small-C occupancy |
| E: segmented block/cell×h-chunk | Split one cell across several h blocks; bounded O(C×chunks) partials | Two deterministic reduction passes, more launches/storage; tunable chunks independent of C | Fallback when B has too few blocks or long serial work; avoid full HC scratch |

These occupancy judgments are **design inferences**, not GPU benchmark findings. Coefficient evaluation uses two nine-double polynomial arrays (144 bytes of source scratch) plus coordinates/angles/series; actual register allocation and possible local-memory spills must be inspected with ptxas/Nsight. Do not infer a fixed register count from the source or fix block size now.

Adjacent h lanes favor `coefficient[term][h]` SoA loads for B; one point can be staged once/block. Cross-cell coefficient sharing is attractive in D but storing T×200 bytes in shared memory competes with resident blocks. Only pi/height and small packing metadata are constant-memory candidates. Whole coefficient fields are too large, and divergent per-lane h addresses would serialize constant-cache reads. Register/shared-memory pressure can limit occupancy; confirm the actual compiled kernel rather than maximizing thread count blindly. See NVIDIA's [CUDA Best Practices Guide](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#constant-memory).

## First Phase 2B contract

Implement B for the validated external cylinder with one block per cell and lane-strided double partial sums, followed by a fixed block tree and one output write. Keep host optics production and normalization unchanged. Choose trial block sizes only when actual GPU measurement is permitted. Start by comparing isolated CPU/device contributions using the 24 direct fixtures, then raw maps and dimensional maps for all nine cases at rtol=1e-9 / atol=1e-10. Capability-check geometry and coefficient packing, propagate runtime errors, and preserve an explicit CPU fallback. Do not expand to intercept, shadows or batching in this first kernel.

A fixed tree is reproducible for a fixed launch/configuration but will not reproduce the CPU's sequential h0+h1+… rounding. Transcendentals and fused multiply-add may introduce additional CPU/device differences; log per-pair error separately from reduction error, and test with/without FMA contraction during diagnosis without relaxing tolerances. This distinction follows NVIDIA's [floating-point discussion](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/mathematical-functions.html#fused-multiply-add-fma).

Double atomic addition is available on the validated sm_89, but atomics do not impose the original h order; the current mapping would also create many writers per cell. Use fixed double block reductions initially, not float intermediates or compensated/reordered CPU sums masquerading as the oracle. Near-zero cells require absolute tolerance; cancellation in the polynomial followed by clamping can amplify relative differences. Preserve division order, Hermite packing, projection signs, clamp location and dimensional units. NVIDIA documents [atomic operations](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/cpp-language-extensions.html#atomicadd) separately from their floating-point numerical consequences.

Larger grids supply more blocks but increase pair count by C; multi-receiver work supplies independent surface blocks but requires correct geometry/normalization boundaries. Future batching supplies another independent grid dimension and opportunities for static-cell reuse, while multiplying h optical payload per candidate. Neither is implemented here. No GPU speedup is claimed; CudaProbe is functional validation only. Controlled future measurements must record external workload/VRAM, separate kernel, transfer, packing and full simulate time, and compare against this native CPU evidence.
