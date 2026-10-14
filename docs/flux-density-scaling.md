# Native CPU flux-density scaling

Measured on Servidor GPU (benchmark-host), Xeon w5-3423, GCC 13.3 / CMake 3.28.3 / Ninja 1.11.1 / Python 3.12.3, using the native host, not Docker. Release, one simulation thread, Hermite/double, external cylindrical receiver, simple aim, DNI 950, azimuth 180°, elevation 55°. Fields use the existing deterministic concentric rings and weather; no original baseline was regenerated. Both paths are in the same final diagnostic/profile-enabled binary: SSC c73d4d5ea40e633b5bfe993ac9ca9761d1bca83d, integration 5b465b2. SolarPILOT 53640fd and SolTrace 699263f are unchanged.

One excluded warm simulation, then three measured repetitions per case, serial execution without project builds/tests running simultaneously on the host. The largest original case takes ~10 seconds/simulation, so three repetitions bound the sweep cost while exposing its observed range. These are descriptive statistics, not confidence intervals or controlled isolated-host guarantees. Existing vLLM stayed running; no GPU timings were collected. Native pre-extraction evidence is separately retained in phase2a-native-legacy-before.json; source/build differences preclude attributing previous Docker-to-native differences to this refactor.

Times below are **milliseconds, median [minimum, maximum]**. Flux density scope includes packing/scattering and diagnostic evaluated-pair counter for flat, but not normalization/post-processing. Verification mode timings include both routes and comparison and are excluded from performance tables.

| H | Grid | Legacy simulate | Legacy density | Flat simulate | Flat density | Density change | Total change |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1000 | 25×25 | 72.444 [71.443, 73.992] | 62.322 [61.555, 63.903] | 35.996 [35.039, 36.085] | 25.316 [24.838, 25.780] | -59.38% | -50.31% |
| 1000 | 50×50 | 262.059 [259.799, 263.250] | 252.041 [250.394, 253.154] | 107.872 [107.447, 111.784] | 97.834 [97.702, 101.364] | -61.18% | -58.84% |
| 1000 | 100×100 | 1005.656 [994.170, 1013.475] | 995.323 [984.017, 1003.151] | 414.885 [409.935, 420.761] | 404.598 [399.414, 409.754] | -59.35% | -58.74% |
| 5000 | 25×25 | 361.310 [357.260, 364.148] | 305.135 [304.110, 310.911] | 182.596 [178.246, 184.057] | 127.623 [123.812, 128.231] | -58.17% | -49.46% |
| 5000 | 50×50 | 1283.280 [1277.450, 1292.986] | 1228.062 [1224.265, 1239.261] | 559.029 [558.823, 561.370] | 504.757 [504.198, 505.785] | -58.90% | -56.44% |
| 5000 | 100×100 | 4961.831 [4942.343, 4965.882] | 4907.587 [4886.361, 4911.257] | 2080.061 [2077.795, 2173.851] | 2023.998 [2019.097, 2116.480] | -58.76% | -58.08% |
| 10000 | 25×25 | 740.082 [739.535, 741.474] | 619.421 [617.997, 622.267] | 369.534 [368.197, 373.387] | 248.567 [247.641, 255.309] | -59.87% | -50.07% |
| 10000 | 50×50 | 2633.759 [2607.852, 2634.249] | 2514.157 [2485.578, 2517.880] | 1127.515 [1115.353, 1128.284] | 1008.634 [999.325, 1009.806] | -59.88% | -57.19% |
| 10000 | 100×100 | 10065.859 [10031.136, 10080.056] | 9946.069 [9915.171, 9963.825] | 4170.857 [4118.181, 4198.772] | 4047.312 [4000.834, 4076.578] | -59.31% | -58.56% |

## Interaction counts and equivalence

The raw same-prepared-state comparison restores each initial cell before running flat. All nine cases have max absolute error **0**, max relative error **0**, and bitwise equality in every repetition. Zero-based maximum-error coordinates are (0,0), the first of tied zero-error cells; there is no unique worst cell. Final source was checked once/case after the coefficient safety guard, plus three/case on the identical arithmetic extraction before that guard. At each resolution, independently selected legacy/flat runs also have identical exported-map SHA256, peak, integrated incident flux and rounded absorbed power. Existing full baselines separately verify summary and every heliostat result column.

| H | Grid | Candidate HC | Evaluated visible pairs | Peak kW/m² (both) | Incident integral kW (both) | Absorbed power kW (both) |
|---:|---:|---:|---:|---:|---:|---:|
| 1000 | 25×25 | 625,000 | 312,500 | 426.011709827102 | 95688.422362766 | 89947 |
| 1000 | 50×50 | 2,500,000 | 1,250,050 | 425.194027936339 | 95688.422362766 | 89947 |
| 1000 | 100×100 | 10,000,000 | 5,000,000 | 426.592408022878 | 95688.422362766 | 89947 |
| 5000 | 25×25 | 3,125,000 | 1,562,525 | 1036.088078498208 | 380888.431399913 | 358035 |
| 5000 | 50×50 | 12,500,000 | 6,250,200 | 1033.785204336356 | 380888.431399913 | 358035 |
| 5000 | 100×100 | 50,000,000 | 25,000,000 | 1036.132283576782 | 380888.431399914 | 358035 |
| 10000 | 25×25 | 6,250,000 | 3,125,050 | 1369.842313876623 | 609943.500965611 | 573347 |
| 10000 | 50×50 | 25,000,000 | 12,500,200 | 1367.145759582848 | 609943.500965610 | 573347 |
| 10000 | 100×100 | 100,000,000 | 50,000,000 | 1369.892699454814 | 609943.500965606 | 573347 |

Facing tests accept almost exactly half the cylinder interactions; a few exactly/near-tangent dot-zero points pass because the original accepts zero. Polynomial-negative clamp does not eliminate the evaluation count; it only sets the contribution to zero. Candidate HC is therefore distinct from evaluated polynomial/exp calls. Integral equals delivered incident power after normalization, while the API absorbed summary is rounded and includes receiver absorptance.

## Quantified scaling

Legacy: median density time per candidate pair ranges **97.64–100.82 ns** across all nine cases (max/min 1.032).

* H=1000: increasing 25→50 cells per side gives 4.044× density (ideal 4×, deviation +1.10%); 25→100 gives 15.971× (ideal 16×, deviation -0.18%).
* H=5000: increasing 25→50 cells per side gives 4.025× density (ideal 4×, deviation +0.62%); 25→100 gives 16.083× (ideal 16×, deviation +0.52%).
* H=10000: increasing 25→50 cells per side gives 4.059× density (ideal 4×, deviation +1.47%); 25→100 gives 16.057× (ideal 16×, deviation +0.36%).

* Grid 25: 1k→5k gives 4.896× (ideal 5×); 1k→10k gives 9.939× (ideal 10×, deviation -0.61%).
* Grid 50: 1k→5k gives 4.872× (ideal 5×); 1k→10k gives 9.975× (ideal 10×, deviation -0.25%).
* Grid 100: 1k→5k gives 4.931× (ideal 5×); 1k→10k gives 9.993× (ideal 10×, deviation -0.07%).

Flat: median density time per candidate pair ranges **39.13–40.84 ns** across all nine cases (max/min 1.044).

* H=1000: increasing 25→50 cells per side gives 3.865× density (ideal 4×, deviation -3.39%); 25→100 gives 15.982× (ideal 16×, deviation -0.11%).
* H=5000: increasing 25→50 cells per side gives 3.955× density (ideal 4×, deviation -1.12%); 25→100 gives 15.859× (ideal 16×, deviation -0.88%).
* H=10000: increasing 25→50 cells per side gives 4.058× density (ideal 4×, deviation +1.45%); 25→100 gives 16.283× (ideal 16×, deviation +1.77%).

* Grid 25: 1k→5k gives 5.041× (ideal 5×); 1k→10k gives 9.819× (ideal 10×, deviation -1.81%).
* Grid 50: 1k→5k gives 5.159× (ideal 5×); 1k→10k gives 10.310× (ideal 10×, deviation +3.10%).
* Grid 100: 1k→5k gives 5.002× (ideal 5×); 1k→10k gives 10.003× (ideal 10×, deviation +0.03%).

The density scope is consistent with O(HC), with small measurement/geometry/caching deviations. Total simulate also contains O(H) optical preparation and neighbor work, so it scales less than 4×/16× when increasing C. At 10k the legacy density fraction grows from 83.70% at 25² to 98.81% at 100².

The flat extraction improves the density scope by 58.17–61.18% here, including the adapter allocation/packing cost. The small fixed helper permits ordinary compiler inlining and propagation through scalar/fixed-array geometry and Hermite evaluation, removing repeated out-of-line getter/index calls. This is a structural explanation inferred from code; the instrumentation does not partition speedup into individual instructions. No manual SIMD, parallel sum, reciprocal reformulation, fast-math or physical approximation was added. These CPU results are not a prediction or claim of GPU speedup.

Raw samples, output hashes, source SHAs and parameters are retained in [legacy](../benchmarks/results/phase2a-native-legacy.json), [flat](../benchmarks/results/phase2a-native-flat.json), [same-state final](../benchmarks/results/phase2a-native-verify.json), and [three-repeat extraction comparisons](../benchmarks/results/phase2a-native-verify-extraction.json). The pre-extraction nine-case sweep is in [original native evidence](../benchmarks/results/phase2a-native-legacy-before.json).
