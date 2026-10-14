# Flux density analysis (Phase 2A)

Reference: SSC `9ce2c8c6424bbc8e91718734404266c8137170ae`, Flux.cpp, Toolbox.cpp, Receiver.cpp and SolarField.cpp. The preceding ~84–86% is inclusive single-thread `Flux::fluxDensity` wall time divided by API simulation time, at 25×25. It includes geometry, visibility, polynomial/exponential evaluation, getters, grid access and accumulation; it is not a measurement of polynomial arithmetic alone. Coefficient production (~9%) and shading/blocking (~2–4%) occur upstream, outside this scope. Normalization and dimensional conversion occur downstream.

## Actual call and iteration structure

`HermiteFluxSimulation` first prepares each heliostat's optics, calling `imagePlaneIntercept` → `hermiteIntEval` → `hermiteIntegralSetup` → `hermiteIntegral`. Sun, error and mirror moments are transformed and convolved into a 7×7 moment matrix. `hermiteIntEval` stores sigmas `sqrt(mu_F(2,0))`, `sqrt(mu_F(0,2))` and 16 packed coefficients; coefficients include the original `6.2832` normalization. Flux density reads sigmas and coefficients, not moment matrices or facets. Tracking, aimpoint, intercept and total efficiency have already been computed.

`AnalyticalFluxSimulation` loops enabled receivers, then surfaces, clears each map and calls `fluxDensity` with the supplied heliostat vector. It does not filter that vector by receiver association inside fluxDensity. Preserve this behavior; adding an association filter is a physical change. A cavity's surface zero is the virtual aperture. Within one call the order is **heliostat → x → y**. The smallest evaluated work unit is one enabled heliostat × one visible surface point; cylinder points facing away are skipped. Candidate count H×C is an upper bound.

## Pseudocode matching the original

```text
prepare surface: grid[nx][ny], surface offset, receiver global offset, tower height
for h in supplied heliostats (original order):
    update optional simulation progress every max(H/20,1)
    if disabled: continue
    sigma_x, sigma_y = h.imageSize                   # tower-normalized
    aim = h.aimPoint                                # global metres
    r = unit(h.location - receiver.offset - (0,0,tower_height))
    cnorm = h.area * h.totalEfficiency / (tower_height*tower_height)
    for x in [0,nx):
        for y in [0,ny):
            c = grid[x][y]
            cosine = dot(c.normal, r)
            if cosine < 0 or cosine > 1: continue   # zero is accepted
            p = c.location + surface.offset + receiver.offset + (0,0,tower_height)
            if cavity or falling particle:
                if not checkApertureSnout(p, h.location, aim, receiver): continue
            intersection = plane_intersect(aim, r, p, r)
            relative = intersection - aim
            relative = rotation(pi - atan2(r.x,r.y), Z, relative)
            relative = rotation(acos(r.z), X, relative)
            xn = -relative.x / tower_height / sigma_x
            yn =  relative.y / tower_height / sigma_y
            HX[0]=HY[0]=1; HX[1]=HY[1]=0; FX=-2
            for i=1..7:
                FX += 1
                HX[i+1] = xn*HX[i] - FX*HX[i-1]
                HY[i+1] = yn*HY[i] - FX*HY[i-1]
            series=0; packed=0
            for i=1..7:
                for j=(i-1)%2+1 .. 8-i step 2:
                    series += coefficient[packed]*HX[i+1]*HY[j+1]
                    packed += 1
            if series < 0: series=0
            hfe = series * exp(-0.5*(xn*xn + yn*yn))
            c.flux += cosine * hfe * cnorm          # sequential h0+h1+...
reset optional progress
normalize and dimension maps outside this routine
```

Preparation and per-heliostat constants: height, offsets, geometry type per surface; unit r, aim, sigma, cnorm and coefficients per h. Cell constants: global position and normal. Interaction values: dot/visibility, projected point, normalized image coordinates, Hermite polynomials, Gaussian and contribution. Angles/rotation terms mathematically depend only on h; the original recomputes atan2/acos and sin/cos per visible interaction. Phase 2A retains those formulas and their arithmetic rather than introducing reciprocal multiplication or approximate math.

## Hot-path costs and branches

The ordinary cylinder path calls concrete, nonvirtual getters and Toolbox functions; there is no virtual dispatch or heap allocation per interaction. `Hvector` and `FluxGrid` are vectors of pointers and vectors of vectors; `.at()` checks bounds. Hermite coefficients live in a dynamic matrix with checked element access; HX/HY are fixed nine-element stack arrays. Grid objects, coefficients and receiver variables are pointer dependent. `unitvect` uses sqrt(pow(x,2)+pow(y,2)+pow(z,2)) once per h, with an explicit zero-vector branch. Each accepted pair executes plane intersection dot sums/division; atan2, acos, two sin/cos pairs; two scalar 3×3 matrix-vector rotations including zero terms; two sequential divisions per coordinate; polynomial recurrence/16 multiply-add terms; exp; clamp and accumulation. No generic dynamic matrix multiply is used here.

`plane_intersect` sums its two dot products starting at zero, returns false for a zero denominator and leaves the sp_point unchanged. That default constructor does not initialize coordinates; the original caller ignores the return value, so zero-direction geometry is undefined in the oracle. The flat helper defines a zero initial projection for that invalid case; numerical equivalence is asserted for valid nonzero receiver-to-heliostat directions. Dot tests use two comparisons rather than `0 <= dot <= 1`, retaining NaN comparison semantics. Nonfinite results are rejected by differential validation, not silently repaired by the new arithmetic helper.

For cavity/falling particle, `checkApertureSnout` computes a point-to-h unit vector, aperture normal from receiver azimuth/elevation (particle elevation forced to zero), intersection with aperture at (offset_x, offset_y, optical_height), rotations and width/height limits. Particle snout adds depth-offset plane, second intersection/rotations, width from horizontal angle and top/bottom tangent limits; invalid horizontal angle throws. `aim` is passed but unused there. These branches remain in the host adapter; a first CUDA cylinder kernel must reject/fallback other geometries. The separate projected-aperture polygon helper is called upstream by intercept calculations, not inside fluxDensity.

## Post-processing and conventions

Single surface: `Normalize` sums x then y, floors the denominator to 1e-6 and multiplies each cell by 1/sum. Multi-panel receivers normalize virtual aperture separately and active surfaces by their combined sum (without the single-surface floor). Then `CalcDimensionalFluxProfiles` sums h.totalEfficiency × h.area × DNI × 0.001 into each associated receiver's power, divides surface area by nx×ny, multiplies each normalized cell by power/cell-area and computes maximum flux. Exported maps are incident kW/m²; absorbed receiver power additionally includes absorptance. The raw kernel has no DNI or absorptance input: applying either again would double count. Map normalization hides uniform raw amplitude errors, hence differential checks must also compare the unnormalized map on exactly the same prepared state.

The flat adapter prepares immutable contiguous cells and a contiguous accumulator, packs one h's fixed numeric record at a time, evaluates pairs with the independent helper, and scatters results. No optical GPU allocation or CUDA dependency is introduced. The original body stays available unchanged as an oracle; opt-in diagnostics can run legacy, flat or both before normalization.
