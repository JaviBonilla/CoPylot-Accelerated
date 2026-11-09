#!/usr/bin/env python3
"""Run a small optical simulation using only generated inputs."""

import argparse
import csv
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "python"))
from hermite_optics import CoPylot, build_info


def synthetic_weather(path):
    """Write a synthetic SAM CSV. The site and all hourly values are invented."""
    start = datetime(2001, 1, 1)
    with path.open("w", encoding="ascii", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Source", "Location ID", "City", "State", "Country",
                         "Latitude", "Longitude", "Time Zone", "Elevation"])
        writer.writerow(["Synthetic", "0", "Example", "", "", 35, 0, 0, 100])
        writer.writerow(["Year", "Month", "Day", "Hour", "GHI", "DNI", "DHI",
                         "Tdry", "Tdew", "RH", "Pres", "Wspd", "Wdir"])
        for hour in range(8760):
            stamp = start + timedelta(hours=hour)
            daylight = 6 <= stamp.hour < 18
            writer.writerow([stamp.year, stamp.month, stamp.day, stamp.hour,
                             700 if daylight else 0, 900 if daylight else 0,
                             80 if daylight else 0, 25, 10, 40, 1013, 2, 0])


def simulate(weather, mode):
    selection = "legacy" if mode == "original" else ""
    with patch.dict(os.environ, {
        "SOLARPILOT_INTERCEPT_PATH": selection,
        "SOLARPILOT_FLUX_PATH": selection,
    }):
        api = CoPylot()
        context = api.data_create()
        if not context:
            raise RuntimeError("CoPylot could not allocate a context")
        try:
            if not api.data_set_string(context, "ambient.0.weather_file", str(weather)):
                raise RuntimeError("Could not select synthetic weather")
            settings = {
                "solarfield.0.des_sim_detail": 0,
                "fluxsim.0.flux_model": 0,
                "fluxsim.0.flux_time_type": 0,
                "fluxsim.0.flux_solar_az_in": 180,
                "fluxsim.0.flux_solar_el_in": 55,
                "fluxsim.0.flux_dni": 900,
                "fluxsim.0.aim_method": 0,
                "fluxsim.0.x_res": 25,
                "fluxsim.0.y_res": 25,
                "land.0.is_bounds_scaled": 0,
                "land.0.is_bounds_fixed": 1,
                "land.0.min_fixed_rad": 100,
                "land.0.max_fixed_rad": 600,
            }
            for key, value in settings.items():
                if not api.data_set_number(context, key, value):
                    raise RuntimeError(f"Could not configure {key}")
            layout = [[0, x, y, 0] for y in (160, 200, 240) for x in (-60, -20, 20, 60)]
            if not api.assign_layout(context, layout, nthreads=1):
                raise RuntimeError("Could not assign the synthetic field")
            api.set_compute_backend(context, "cuda" if mode == "cuda" else "cpu")
            if not api.simulate(context, nthreads=2 if mode == "multicore" else 1):
                raise RuntimeError(api.get_last_backend_error(context) or "Simulation failed")
            flux = np.asarray(api.get_fluxmap(context), dtype=np.float64)
            summary = api.summary_results(context)
            details = api.detail_results(context, restype="dictionary")
            if len(details["id"]) != len(layout):
                raise RuntimeError("Unexpected heliostat count")
        finally:
            api.data_free(context)
    if flux.shape != (25, 25) or not np.isfinite(flux).all() or flux.max() <= 0:
        raise RuntimeError("Invalid receiver flux")
    return flux, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("original", "refactored", "multicore", "cuda"),
                        default="refactored")
    parser.add_argument("--compare", action="store_true",
                        help="Compare flux against a fresh refactored CPU run")
    args = parser.parse_args()
    info = build_info()
    if args.mode == "original" and not info["diagnostics"]:
        parser.error("Original mode requires a diagnostics-enabled package")
    if args.mode == "cuda" and not info["cuda_architecture"]:
        parser.error("CUDA mode requires a CUDA-enabled package")

    with TemporaryDirectory() as temp:
        weather = Path(temp) / "synthetic.csv"
        synthetic_weather(weather)
        flux, summary = simulate(weather, args.mode)
        result = {"mode": args.mode, "flux_shape": list(flux.shape),
                  "peak_incident_flux_kw_m2": float(flux.max()),
                  "flux_sha256": hashlib.sha256(flux.astype("<f8", copy=False).tobytes()).hexdigest(),
                  "summary": summary}
        if args.compare:
            reference, _ = simulate(weather, "refactored")
            if args.mode == "cuda":
                np.testing.assert_allclose(flux, reference, rtol=1e-9, atol=1e-10)
            elif flux.tobytes() != reference.tobytes():
                raise RuntimeError("CPU receiver map differs bitwise from refactored")
            result["max_abs_flux_difference_kw_m2"] = float(np.max(np.abs(flux - reference)))
        print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
