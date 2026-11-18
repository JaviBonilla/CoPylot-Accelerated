"""Run one synthetic optical simulation with the CoPylot Python API."""

import sys
from pathlib import Path

import numpy as np


def main():
    # The extracted package keeps its Python wrapper in python/ beside this script.
    package = Path(__file__).resolve().parent
    sys.path.insert(0, str(package / "python"))
    from copylot_accelerated import CoPylot

    api = CoPylot()
    context = api.data_create()
    if not context:
        raise RuntimeError("Could not create a CoPylot simulation context.")

    try:
        # Layout preparation reads the synthetic hourly weather file. The
        # optical run below uses the sun position and DNI specified explicitly.
        weather = package / "quickstart_weather.csv"
        if not weather.is_file():
            raise FileNotFoundError(weather)
        if not api.data_set_string(context, "ambient.0.weather_file", str(weather)):
            raise RuntimeError("Could not set the weather file.")

        settings = {
            "solarfield.0.tht": 195,            # Receiver center above the heliostat pivot plane (m).
            "receiver.0.rec_type": 0,           # External cylinder.
            "receiver.0.rec_diameter": 17.65,   # m
            "receiver.0.rec_height": 21.6,      # m
            "receiver.0.absorptance": 0.94,     # Fraction of incident power absorbed.
            "solarfield.0.des_sim_detail": 0,   # Keep the explicitly assigned heliostats.
            "fluxsim.0.flux_model": 0,          # Analytical Hermite model.
            "fluxsim.0.flux_time_type": 0,      # Use the specified sun position.
            "fluxsim.0.flux_solar_az_in": 180,  # Due south, clockwise from north (degrees).
            "fluxsim.0.flux_solar_el_in": 55,   # Above the horizon (degrees).
            "fluxsim.0.flux_dni": 900,          # Direct normal irradiance (W/m²).
            "fluxsim.0.aim_method": 0,          # Simple aiming.
            "fluxsim.0.x_res": 25,              # Circumferential columns.
            "fluxsim.0.y_res": 25,              # Vertical rows.
            "land.0.is_bounds_scaled": 0,       # Use fixed land bounds in metres.
            "land.0.is_bounds_fixed": 1,
            "land.0.min_fixed_rad": 100,
            "land.0.max_fixed_rad": 600,
        }
        for name, value in settings.items():
            if not api.data_set_number(context, name, value):
                raise RuntimeError(f"Could not set {name}.")

        # Three rows of four mirrors. Each record is [template ID, East m, North m, pivot height m].
        layout = [[0, east, north, 0] for north in (160, 200, 240) for east in (-60, -20, 20, 60)]
        if not api.assign_layout(context, layout, nthreads=1):
            raise RuntimeError("Could not assign the synthetic heliostat layout.")

        api.set_compute_backend(context, "cpu")
        if not api.simulate(context, nthreads=1, update_aimpoints=True):
            raise RuntimeError(api.get_last_backend_error(context) or "The optical simulation failed.")

        summary = api.summary_results(context)["All receivers"]
        flux = np.array(api.get_fluxmap(context), copy=True)
    finally:
        api.data_free(context)

    # The flux map gives incident power density before receiver absorption.
    if flux.shape != (25, 25) or not np.isfinite(flux).all() or flux.min() < 0 or flux.max() <= 0:
        raise RuntimeError("Expected a finite, nonnegative 25 × 25 incident flux map with a positive peak.")
    print("CoPylot-Accelerated Quick Start")
    print(f"Heliostats simulated: {summary['Simulated heliostat count']:.0f}")
    print(f"Solar-field optical efficiency: {summary['Solar field optical efficiency']:.2f}%")
    print(f"Receiver absorbed power: {summary['Power absorbed by the receiver']:,.1f} kW")
    print(f"Peak incident receiver flux: {flux.max():.2f} kW/m²")
    print(f"Receiver flux map: {flux.shape[0]} rows × {flux.shape[1]} columns")


if __name__ == "__main__":
    try:
        main()
    except (ImportError, OSError, RuntimeError) as error:
        raise SystemExit(f"Quick Start: {error}") from None
