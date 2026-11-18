"""Configure and run a single commercial SSC optical reference point."""

import csv
from datetime import date, time
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch

from results import RECEIVER_COORDINATES, bottom_first, checked_details, sha256, validate_power

HERE = Path(__file__).resolve().parent
PACKAGE_ROOT = HERE.parent
PACKAGED = (PACKAGE_ROOT / "BUILD.json").is_file()
ROOT = PACKAGE_ROOT if PACKAGED else HERE.parent.parent
ASSET_ROOT = HERE / "inputs" if PACKAGED else ROOT
MANIFEST = ASSET_ROOT / "cases/commercial-reference/case_manifest.json"

# Use the installed Python wrapper or the helpers in a development checkout.
if PACKAGED:
    sys.path.insert(0, str(PACKAGE_ROOT / "python"))
else:
    sys.path.insert(0, str(ROOT / "benchmarks"))

from commercial_reference import coordinates, layout_settings, load_manifest, sanity
from receiver_grid import map_metrics, physical_grid


REFERENCE_YEAR = 2011

WEATHER_CONVENTION = (
    "Daggett TMY2 is a typical meteorological year assembled from historical records. "
    "The hour is the weather row hour plus 0.5 in local standard time (UTC−08:00, no daylight saving). "
    "SolarPILOT uses the 2011 reference calendar to derive the sun; the selected date "
    "does not represent weather measured in 2011. DNI is used directly without interpolation."
)


def select_weather(path, date_text, time_text, override=None):
    """Select one TMY2 row in Daggett local standard time, without interpolation."""
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", date_text):
        raise ValueError("Use --date YYYY-MM-DD with the SolarPILOT reference year 2011.")
    selected_date = date.fromisoformat(date_text)
    if selected_date.year != REFERENCE_YEAR:
        raise ValueError(f"Use {REFERENCE_YEAR} as the SolarPILOT reference year for the TMY2 calendar.")
    if not re.fullmatch(r"[0-9]{2}:30", time_text):
        raise ValueError("Use an hourly midpoint HH:30 in Daggett local standard time (UTC−08:00).")
    clock = time.fromisoformat(time_text)
    with path.open(encoding="utf-8", newline="") as stream:
        rows = csv.reader(stream)
        site = dict(zip(next(rows), next(rows), strict=True))
        matches = [row for row in csv.DictReader(stream)
                   if (int(row["Month"]), int(row["Day"]), int(row["Hour"]))
                   == (selected_date.month, selected_date.day, clock.hour)]
    if len(matches) != 1:
        raise ValueError("Expected exactly one matching hourly TMY2 record.")
    row = matches[0]
    tmy2_dni = float(row["DNI"])
    if not math.isfinite(tmy2_dni) or tmy2_dni < 0:
        raise ValueError("The matching TMY2 record has invalid DNI.")
    dni = tmy2_dni if override is None else override
    if not math.isfinite(dni) or dni <= 0:
        raise ValueError("This demo requires positive finite DNI. Choose a daylight record or give a positive --dni override.")
    return {
        "date": date_text, "local_time": time_text, "timezone": "UTC-08:00 (LST)",
        "reference_year": REFERENCE_YEAR, "month": selected_date.month, "day": selected_date.day,
        "hour": clock.hour + 0.5, "weather_record_hour": int(row["Hour"]),
        "weather_record_source_year": int(row["Year"]), "tmy2_dni_w_m2": tmy2_dni,
        "dni_w_m2": dni, "dni_source": "User override" if override is not None else "Daggett TMY2",
        "weather_convention": WEATHER_CONVENTION,
        "site": {"name": "Daggett, California", "location_id": site["Location ID"],
                 "latitude_deg": float(site["Latitude"]), "longitude_deg": float(site["Longitude"]),
                 "utc_offset_hours": float(site["Time Zone"]), "elevation_m": float(site["Elevation"])},
    }


def open_library(mode):
    """Load CoPylot and describe the native build used for this run."""
    if PACKAGED:
        from copylot_accelerated import CoPylot, build_info

        build = build_info()
        if mode == "original" and not build["diagnostics"]:
            raise ValueError("Original mode requires a diagnostics-enabled package.")
        api = CoPylot()
        library = PACKAGE_ROOT / build["library"]
        options = {
            "CMAKE_BUILD_TYPE": build["build_type"],
            "SOLARPILOT_ENABLE_FLUX_DIAGNOSTICS": "ON" if build["diagnostics"] else "OFF",
            "SOLARPILOT_ENABLE_CUDA": "ON" if build["cuda_toolkit"] else "OFF",
        }
        if build["cuda_architecture"]:
            options["CMAKE_CUDA_ARCHITECTURES"] = build["cuda_architecture"]
        revision, dirty = build["source_revision"], build["source_dirty_at_configure"]
        dependency_pins = build["dependencies"]
    else:
        # The upstream development loader expects the current directory to
        # contain the native library. The benchmark adapter restores it.
        from cases import api as load_development_api

        try:
            api = load_development_api()
        except OSError as error:
            raise RuntimeError("Cannot load the development CoPylot library. Build it with "
                               f"scripts/build_cpu.sh or set COPILOT_LIB_DIR. {error}") from error
        directory = Path(os.getenv("COPILOT_LIB_DIR", ROOT / "build/cpu/lib")).resolve()
        library = (directory / api.pdll._name).resolve()
        options = development_build_options(library.parent.parent / "CMakeCache.txt")
        if mode == "original" and options.get("SOLARPILOT_ENABLE_FLUX_DIAGNOSTICS") != "ON":
            raise ValueError("Original requires a development build with SOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON "
                             "and its CMakeCache.txt.")
        revision, dirty = checkout_revision()
        lockfile = ROOT / "repos.lock.json"
        pins = json.loads(lockfile.read_text(encoding="utf-8"))
        dependency_pins = {name: pin["patched_sha"] for name, pin in pins.items()}
    provenance = {
        "library_filename": library.name,
        "library_sha256": sha256(library),
        "build_options": options,
        "repository_revision": revision,
        "repository_dirty": dirty,
        "dependency_pins": dependency_pins,
    }
    return api, provenance


def development_build_options(cache):
    """Read the native options used to distinguish development backends."""
    options = {}
    if cache.is_file():
        for line in cache.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.startswith(("SOLARPILOT_ENABLE_", "CMAKE_BUILD_TYPE:", "CMAKE_CUDA_ARCHITECTURES:")):
                options[key.split(":")[0]] = value
    return options


def checkout_revision():
    """Read the source revision and worktree state for development builds."""
    options = {"cwd": ROOT, "text": True, "stderr": subprocess.DEVNULL}
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], **options).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], **options))
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("Cannot read source provenance from the Git checkout.") from error
    return revision, dirty


def run_simulation(*, date, local_time, dni, mode, threads, target_cell_m):
    """Return the metadata, incident flux map and ordered heliostat columns for one state."""
    start = perf_counter()
    # The public SSC reference pins the layout, weather and optical assumptions,
    # including the Hermite model and Simple aiming.
    manifest = load_manifest(MANIFEST, asset_root=ASSET_ROOT)
    parameters = manifest["parameters"]
    reference = {name: parameter["value"] for name, parameter in parameters.items()}
    weather_path = ASSET_ROOT / manifest["assets"]["weather"]["path"]
    operating_point = select_weather(weather_path, date, local_time, dni)
    site = operating_point["site"]
    if any(site[site_key] != reference[native_key] for site_key, native_key in (
            ("latitude_deg", "ambient.0.latitude"), ("longitude_deg", "ambient.0.longitude"),
            ("utc_offset_hours", "ambient.0.time_zone"))):
        raise ValueError("The TMY2 site does not agree with the commercial manifest.")

    # Unwrap the external cylinder to a rectangle of width πD and height H.
    # The grid uses equal cells with both dimensions at or below the target.
    receiver = {
        "type": "cylindrical",
        "diameter_m": reference["receiver.0.rec_diameter"],
        "height_m": reference["receiver.0.rec_height"],
        "tower_optical_height_m": reference["solarfield.0.tht"],
        "absorptance": reference["receiver.0.absorptance"],
    }
    grid = physical_grid(receiver, target_cell_m)
    receiver["circumference_m"] = grid["surface_width_m"]
    receiver["surface_area_m2"] = grid["surface_width_m"] * grid["height_m"]
    heliostat_layout = coordinates(manifest, asset_root=ASSET_ROOT)
    api, provenance = open_library(mode)
    context = api.data_create()
    if not context:
        raise RuntimeError("CoPylot did not allocate a simulation context.")

    # Original selects the legacy CPU kernels. Refactored and Multicore
    # use the same CPU kernels with different thread counts in simulate().
    backend = "cuda" if mode == "cuda" else "cpu"
    kernel_selection = "legacy" if mode == "original" else ""
    try:
        with patch.dict(os.environ, {
            "SOLARPILOT_INTERCEPT_PATH": kernel_selection,
            "SOLARPILOT_FLUX_PATH": kernel_selection,
        }):
            if not api.data_set_string(context, "ambient.0.weather_file", str(weather_path)):
                raise RuntimeError("Cannot configure public climate asset")
            initial_point = manifest["operating_points"][0]
            settings = layout_settings(manifest, grid["nx"], grid["ny"], initial_point)
            for name, value in settings.items():
                if not api.data_set_number(context, name, value):
                    raise RuntimeError(f"Cannot set {name}")

            # The API expects [template ID, East m, North m, pivot height m].
            # Assign the pinned layout in its original row order.
            if not api.assign_layout(context, heliostat_layout.tolist(), nthreads=1):
                raise RuntimeError("Cannot assign public layout")
            assigned = api.get_layout_info(context, restype="dictionary")
            if len(assigned["id"]) != manifest["heliostats"]["count"]:
                raise RuntimeError("Unexpected filtered heliostat count")
            field = sanity(api, context, manifest, heliostat_layout)

            # The initial point seeds layout preparation. Hour/Day mode makes
            # SolarPILOT compute the sun from the local 2011 reference calendar.
            for name, value in (
                ("flux_time_type", 1),
                ("flux_month", operating_point["month"]),
                ("flux_day", operating_point["day"]),
                ("flux_hour", operating_point["hour"]),
                ("flux_dni", operating_point["dni_w_m2"]),
            ):
                if not api.data_set_number(context, f"fluxsim.0.{name}", value):
                    raise RuntimeError(f"CoPylot rejected {name}.")
            if not api.set_compute_backend(context, backend) or api.get_compute_backend(context) != backend:
                raise RuntimeError(f"The {backend} backend is unavailable.")
            prepared = perf_counter()
            completed = api.simulate(context, nthreads=threads, update_aimpoints=True)
            simulated = perf_counter()

        azimuth = api.data_get_number(context, "fluxsim.0.flux_solar_az")
        elevation = api.data_get_number(context, "fluxsim.0.flux_solar_el")
        if not math.isfinite(azimuth) or not math.isfinite(elevation):
            raise ValueError("SolarPILOT returned an invalid solar position.")
        if elevation <= 0:
            raise ValueError("The selected time is nighttime in SolarPILOT. Choose a daytime TMY2 midpoint.")
        if not completed:
            raise RuntimeError(api.get_last_backend_error(context) or "CoPylot did not complete the simulation.")
        operating_point.update(solar_azimuth_deg=azimuth, solar_elevation_deg=elevation)

        # The C API returns top-first rows. Reverse them once for bottom-first
        # export, retaining the columns from the south seam toward the east.
        flux = bottom_first(api.get_fluxmap(context))
        # Equal-area cells let us integrate incident kW/m² as the mean times
        # the cylindrical lateral area in m². Receiver absorption is separate.
        metrics = map_metrics(flux, grid)
        summary = api.summary_results(context)["All receivers"]
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in summary.values()):
            raise ValueError("CoPylot returned a non-finite or non-numeric summary.")
        details = checked_details(api.detail_results(context, restype="dictionary"), heliostat_layout)
        absorbed_kw = validate_power(summary, metrics, details, receiver["absorptance"], field["heliostats"])
        provenance["native_version"] = api.version(context)
    finally:
        api.data_free(context)

    field["heliostat_width_m"] = reference["heliostat.0.width"]
    field["heliostat_height_m"] = reference["heliostat.0.height"]
    provenance.update(case_manifest_sha256=sha256(MANIFEST), assets=manifest["assets"])
    # The map integral is incident power. The second efficiency and the
    # native absorbed power include the receiver absorptance.
    metadata = {
        "demo": "CoPylot-Accelerated commercial optical simulation", "case_id": manifest["case_id"],
        "kind": manifest["kind"], "exact_real_plant_reproduction": False,
        "operating_point": operating_point, "receiver": receiver, "field": field,
        "grid": {**grid, "export_coordinates": RECEIVER_COORDINATES},
        "configuration": {"optical_model": "Hermite analytical", "aiming": "Simple, updated for this simulation",
                          "mode": mode, "backend": backend, "threads": threads, "reference_parameters": parameters},
        "metrics": {**metrics, "optical_efficiency_percent": summary["Solar field optical efficiency"],
                    "optical_efficiency_including_receiver_percent": summary["Optical efficiency incl. receiver"],
                    "receiver_absorbed_power_kw": absorbed_kw},
        "native_receiver_summary": summary,
        "timing_seconds": {"preparation": prepared - start, "simulate": simulated - prepared,
                           "readback_and_checks": perf_counter() - simulated},
        "provenance": provenance, "sources": manifest["sources"], "limitations": manifest["limitations"],
    }
    return metadata, flux, details
