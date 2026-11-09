#!/usr/bin/env python3
"""Run one Hermite optical state on a synthetic 1,000-heliostat field."""
import argparse
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
# Use the same field generator and library loader as the benchmarks.
sys.path.insert(0, str(ROOT / "benchmarks"))


def simulate(mode, threads):
    import numpy as np

    from cases import SIZES, api, configure, layout

    # An empty selector lets the backend choose its standard numerical path.
    path = "legacy" if mode == "original" else ""
    with patch.dict(os.environ, {
        "SOLARPILOT_INTERCEPT_PATH": path,
        "SOLARPILOT_FLUX_PATH": path,
    }):
        cp = api()
        context = cp.data_create()
        if not context:
            raise RuntimeError("Could not create a CoPylot context")
        try:
            configure(cp, context, "small")
            positions = layout(SIZES["small"])
            if not cp.assign_layout(context, positions, nthreads=1):
                raise RuntimeError("Could not assign the synthetic heliostat field")

            cp.set_compute_backend(context, "cuda" if mode == "cuda" else "cpu")
            if not cp.simulate(context, nthreads=threads):
                raise RuntimeError(cp.get_last_backend_error(context) or "Optical simulation failed")

            flux = np.asarray(cp.get_fluxmap(context), dtype=np.float64)
            summary = cp.summary_results(context)
            heliostats = cp.detail_results(context, restype="dictionary")
        finally:
            cp.data_free(context)

    if flux.shape != (25, 25) or not np.isfinite(flux).all() or flux.max() <= 0:
        raise RuntimeError("Expected a finite, nonzero 25 by 25 receiver map")
    if len(heliostats["id"]) != SIZES["small"]:
        raise RuntimeError("Unexpected heliostat count")
    return flux, summary, heliostats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("original", "refactored", "multicore", "cuda"),
                        default="refactored")
    parser.add_argument("--threads", type=int, help="CPU threads for multicore mode (default 2)")
    parser.add_argument("--compare", action="store_true",
                        help="Compare the receiver map with a fresh refactored 1-thread CPU run")
    parser.add_argument("--flux-csv", type=Path, help="Write the incident flux map in kW/m²")
    args = parser.parse_args()
    threads = 1
    if args.mode == "multicore":
        threads = args.threads if args.threads is not None else 2
        if threads < 2:
            parser.error("multicore mode requires at least two threads")
    elif args.threads is not None:
        parser.error("--threads is only available in multicore mode")

    library_dir = Path(os.environ.get("COPILOT_LIB_DIR", ROOT / "build/cpu/lib")).resolve()
    if not (library_dir / "solarpilot.so").is_file():
        parser.error("build solarpilot.so first or set COPILOT_LIB_DIR to its directory")
    if args.mode == "original":
        cache = library_dir.parent / "CMakeCache.txt"
        if not cache.is_file() or "SOLARPILOT_ENABLE_FLUX_DIAGNOSTICS:BOOL=ON" not in cache.read_text().splitlines():
            parser.error("Original mode requires a build configured with SOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON")

    import numpy as np

    flux, summary, heliostats = simulate(args.mode, threads)
    result = {
        "mode": args.mode,
        "threads": threads,
        "heliostats": len(heliostats["id"]),
        "flux_shape": list(flux.shape),
        "peak_incident_flux_kw_m2": float(flux.max()),
        "receiver_summary": summary,
    }
    if args.compare:
        reference, _, _ = simulate("refactored", 1)
        if args.mode == "cuda":
            np.testing.assert_allclose(flux, reference, rtol=1e-9, atol=1e-10)
        elif flux.tobytes() != reference.tobytes():
            raise RuntimeError("CPU flux map differs bitwise from the refactored 1-thread map")
        result["max_abs_flux_difference_kw_m2"] = float(np.max(np.abs(flux - reference)))

    if args.flux_csv is not None:
        args.flux_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.flux_csv.open("x") as stream:
            np.savetxt(stream, flux, delimiter=",")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
