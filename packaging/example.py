#!/usr/bin/env python3
"""Run a small optical simulation using only generated inputs."""

import argparse
import csv
from datetime import datetime, timedelta
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

CPU_MODES = ("original", "refactored", "multicore")
MACOS_ARM64_FLUX_TOLERANCE = (1e-15, 1e-15)  # rtol, atol in kW/m²


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


def simulate(weather, mode, *, check_flux=True):
    from copylot_accelerated import CoPylot

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
    if check_flux and not valid_flux(flux):
        raise RuntimeError("Invalid receiver flux")
    return flux, summary, details


def valid_flux(flux):
    return (flux.shape == (25, 25) and bool(np.isfinite(flux).all())
            and bool(np.all(flux >= 0)) and bool(flux.max() > 0))


def array_comparison(actual, reference, *, sample_limit=3, tolerance=None):
    """Compare logical indices as little-endian binary64 in row-major order."""
    actual = np.asarray(actual, dtype="<f8", order="C")
    reference = np.asarray(reference, dtype="<f8", order="C")
    result = {} if tolerance is None else {"within_tolerance": False}
    if actual.shape != reference.shape:
        return {**result, "bitwise": False, "actual_shape": list(actual.shape),
                "reference_shape": list(reference.shape)}

    left, right = actual.view("<u8"), reference.view("<u8")
    different = left != right
    count = int(np.count_nonzero(different))
    finite = np.isfinite(actual) & np.isfinite(reference)
    has_nonfinite = not finite.all()
    signed_zero_mismatches = int(np.count_nonzero(different & (actual == 0) & (reference == 0)))
    result.update({
        "bitwise": count == 0 and not has_nonfinite,
        "elements": actual.size,
        "differing_elements": count,
        "differing_percent": 100 * count / actual.size if actual.size else 0.0,
        "signed_zero_only": 0 < count == signed_zero_mismatches,
        "signed_zero_mismatches": signed_zero_mismatches,
        "has_nonfinite": has_nonfinite,
        "max_abs_difference": None,
        "max_relative_difference": None,
        "max_ulp_difference": None,
    })
    if has_nonfinite:
        result["nonfinite"] = {
            label: {kind: int(np.count_nonzero(predicate(values)))
                    for kind, predicate in (("nan", np.isnan), ("pos_inf", np.isposinf), ("neg_inf", np.isneginf))}
            for label, values in (("actual", actual), ("reference", reference))
        }
    if finite.any():
        a, b = actual[finite], reference[finite]
        with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
            absolute = np.abs(a - b)
            relative = np.where(absolute == 0, 0.0, absolute / np.abs(b))
            # Avoid an overflowing subtraction before division when both values are large.
            overflow = np.isinf(absolute)
            relative[overflow] = np.abs(a[overflow] / b[overflow] - 1.0)
        if tolerance is not None and not has_nonfinite and not signed_zero_mismatches:
            rtol, atol = tolerance
            result["within_tolerance"] = bool(np.all(absolute <= atol + rtol * np.abs(b)))
        for key, maximum in (("max_abs_difference", absolute.max()),
                             ("max_relative_difference", relative.max())):
            result[key] = float(maximum) if np.isfinite(maximum) else "inf"
        # Map adjacent binary64 values to adjacent integers, folding +0 and -0
        # together for ULP distance. The bitwise check still distinguishes zeros.
        sign = np.uint64(1 << 63)
        ranks = []
        for bits in (left[finite], right[finite]):
            magnitude = bits & (sign - np.uint64(1))
            ranks.append(np.where(bits & sign, sign - magnitude, sign + magnitude))
        result["max_ulp_difference"] = int((np.maximum(*ranks) - np.minimum(*ranks)).max())
    if not result["bitwise"]:
        result["samples"] = [
            {"index": [int(i) for i in np.unravel_index(index, actual.shape)],
             "actual": repr(float(actual.flat[index])), "reference": repr(float(reference.flat[index])),
             "actual_bits": f"{left.flat[index]:016x}", "reference_bits": f"{right.flat[index]:016x}"}
            for index in np.flatnonzero(different | ~finite)[:sample_limit]
        ]
    return result


def output_differences(actual, reference):
    differences = {}
    if actual.keys() != reference.keys():
        differences["schema"] = {"only_actual": sorted(actual.keys() - reference.keys()),
                                 "only_reference": sorted(reference.keys() - actual.keys())}
    for key in sorted(actual.keys() & reference.keys()):
        if isinstance(actual[key], dict) and isinstance(reference[key], dict):
            result = output_differences(actual[key], reference[key])
        elif isinstance(actual[key], dict) or isinstance(reference[key], dict):
            result = {"schema": "nested output differs from numeric output"}
        else:
            result = array_comparison(actual[key], reference[key], sample_limit=1)
            if result["bitwise"]:
                continue
        if result:
            differences[key] = result
    return differences


def is_apple_silicon_package(info):
    return (info["os"] == "macos" and info["architecture"] == "arm64"
            and platform.system() == "Darwin" and platform.machine() == "arm64")


def cpu_comparison(actual_mode, reference_mode, actual_state, reference_state, *, apple_silicon):
    actual, summary, details = actual_state
    reference, reference_summary, reference_details = reference_state
    # Both comparison entry points put Original first and the optimized mode second.
    use_tolerance = (apple_silicon and actual_mode == "original"
                     and reference_mode in ("refactored", "multicore"))
    tolerance = MACOS_ARM64_FLUX_TOLERANCE if use_tolerance else None
    flux = array_comparison(actual, reference, tolerance=tolerance)
    summary_differences = output_differences(summary, reference_summary)
    detail_differences = output_differences(details, reference_details)
    outputs_match = not summary_differences and not detail_differences
    flux_matches = flux["within_tolerance"] if use_tolerance else flux["bitwise"]
    result = {
        "actual_mode": actual_mode,
        "reference_mode": reference_mode,
        "cpu_outputs_bitwise": flux["bitwise"] and outputs_match,
        "validation_passed": flux_matches and outputs_match and valid_flux(actual) and valid_flux(reference),
        "flux_policy": "tolerance" if use_tolerance else "bitwise",
        "flux_kw_m2": flux,
        "summary_differences": summary_differences,
        "detail_differences": detail_differences,
    }
    if use_tolerance:
        rtol, atol = tolerance
        result["flux_tolerance"] = {"rtol": rtol, "atol_kw_m2": atol}
    return result


def compare_cpu_modes(weather, *, apple_silicon):
    states = {mode: simulate(weather, mode, check_flux=False) for mode in CPU_MODES}
    invalid = [mode for mode, (flux, _, _) in states.items() if not valid_flux(flux)]
    passed = not invalid
    print(json.dumps({"cpu_flux_sha256": {
        mode: hashlib.sha256(flux.astype("<f8", copy=False).tobytes()).hexdigest()
        for mode, (flux, _, _) in states.items()
    }, "invalid_flux_modes": invalid}), flush=True)
    for actual_mode, reference_mode in combinations(CPU_MODES, 2):
        result = cpu_comparison(actual_mode, reference_mode, states[actual_mode], states[reference_mode],
                                apple_silicon=apple_silicon)
        passed = passed and result["validation_passed"]
        print(json.dumps(result, allow_nan=False), flush=True)
    if not passed:
        raise RuntimeError("CPU modes failed numerical validation")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("original", "refactored", "multicore", "cuda"),
                        default="refactored")
    comparison = parser.add_mutually_exclusive_group()
    comparison.add_argument("--compare", action="store_true",
                            help="Compare outputs against a fresh refactored CPU run")
    comparison.add_argument("--compare-cpu-modes", action="store_true",
                            help="Validate and report every pair of CPU modes")
    parser.add_argument("--package-directory", type=Path, default=Path(__file__).resolve().parent,
                        help="Use the Python wrapper and library from this extracted package")
    args = parser.parse_args()
    sys.path.insert(0, str(args.package_directory.resolve() / "python"))
    from copylot_accelerated import build_info

    info = build_info()
    apple_silicon = is_apple_silicon_package(info)
    if (args.mode == "original" or args.compare_cpu_modes) and not info["diagnostics"]:
        parser.error("Original mode requires a diagnostics-enabled package")
    if args.mode == "cuda" and not info["cuda_architecture"]:
        parser.error("CUDA mode requires a CUDA-enabled package")

    with TemporaryDirectory() as temp:
        weather = Path(temp) / "synthetic.csv"
        synthetic_weather(weather)
        if args.compare_cpu_modes:
            compare_cpu_modes(weather, apple_silicon=apple_silicon)
            return
        flux, summary, details = simulate(weather, args.mode)
        result = {"mode": args.mode, "flux_shape": list(flux.shape),
                  "peak_incident_flux_kw_m2": float(flux.max()),
                  "flux_sha256": hashlib.sha256(flux.astype("<f8", copy=False).tobytes()).hexdigest(),
                  "summary": summary}
        if args.compare:
            reference, reference_summary, reference_details = simulate(weather, "refactored")
            if args.mode == "cuda":
                np.testing.assert_allclose(flux, reference, rtol=1e-9, atol=1e-10)
            else:
                cpu_result = cpu_comparison(args.mode, "refactored", (flux, summary, details),
                                            (reference, reference_summary, reference_details),
                                            apple_silicon=apple_silicon)
                if not cpu_result["validation_passed"]:
                    raise RuntimeError(f"CPU modes failed numerical validation: {json.dumps(cpu_result)}")
                result.update(cpu_result)
            result["max_abs_flux_difference_kw_m2"] = float(np.max(np.abs(flux - reference)))
        print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
