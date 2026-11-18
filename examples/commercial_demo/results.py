"""Validate, save and reload the demo's numerical outputs."""

import csv
import hashlib
import json
import math

import numpy as np


RECEIVER_COORDINATES = (
    "The arc coordinate s starts at the south seam (180° clockwise from north) "
    "and increases toward the east side of the cylinder in native column order. "
    "Rows ascend from the receiver bottom (z = 0). Both coordinates are cell centers."
)

DETAIL_COLUMNS = (
    ("id", "id"), ("x_east_m", "x_location"), ("y_north_m", "y_location"), ("z_pivot_m", "z_location"),
    ("optical_efficiency_fraction", "efficiency"), ("absorbed_receiver_power_kw", "power_to_receiver"),
    ("cosine_fraction", "cosine"), ("intercept_fraction", "intercept"),
    ("reflectance_fraction", "reflectance"), ("attenuation_fraction", "attenuation"),
    ("blocking_fraction", "blocking"), ("shading_fraction", "shading"),
)
FLUX_COLUMNS = ("row_from_bottom", "column_from_seam", "s_m", "z_from_bottom_m", "incident_flux_kw_m2")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_details(details, positions):
    """Check that native detailed outputs follow the original, unfiltered layout."""
    columns = {name: np.asarray(details[key], dtype=float) for name, key in DETAIL_COLUMNS}
    count = len(positions)
    if any(values.shape != (count,) or not np.isfinite(values).all() for values in columns.values()):
        raise ValueError("Expected a complete, finite per-heliostat result for every input coordinate.")
    if not np.array_equal(columns["id"], np.arange(count)):
        raise ValueError("CoPylot heliostat IDs differ from the reference input order.")
    xyz = np.column_stack([columns[key] for key in ("x_east_m", "y_north_m", "z_pivot_m")])
    if not np.array_equal(xyz, positions[:, 1:]):
        raise ValueError("CoPylot coordinates differ from the ordered commercial reference.")
    return columns


def validate_power(summary, metrics, details, absorptance, count):
    """Check absorbed power against the incident map and per-heliostat contributions."""
    # Native summary powers are rounded to whole kW.
    absorbed = summary["Power absorbed by the receiver"]
    incident = metrics["integrated_incident_power_kw"]
    if (summary["Simulated heliostat count"] != count or not 0 < absorbed <= incident
            or not math.isclose(incident * absorptance, absorbed, rel_tol=0, abs_tol=0.51)
            or not math.isclose(float(details["absorbed_receiver_power_kw"].sum()), absorbed,
                                rel_tol=0, abs_tol=0.51)):
        raise ValueError("Receiver power, absorptance or heliostat power sum disagrees with the native summary.")
    return absorbed


def bottom_first(native_map):
    """Reverse the C API's top-first rows, preserving native columns."""
    return np.asarray(native_map, dtype=np.float64)[::-1, :].copy()


def cell_centers(grid):
    """Return the arc-length and vertical cell centers in metres."""
    return ((np.arange(grid["nx"]) + 0.5) * grid["cell_width_m"],
            (np.arange(grid["ny"]) + 0.5) * grid["cell_height_m"])


def write_numerical_results(directory, data, flux, details, s, z):
    """Save the incident kW/m² map, ordered heliostat results and metadata."""
    with (directory / "receiver_flux.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(FLUX_COLUMNS)
        for row, height in enumerate(z):
            writer.writerows((row, col, position, height, flux[row, col]) for col, position in enumerate(s))
    with (directory / "heliostats.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(details.keys())
        writer.writerows(zip(*details.values(), strict=True))
    (directory / "results.json").write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_numeric_table(path, columns):
    with path.open(encoding="utf-8", newline="") as stream:
        header = next(csv.reader(stream), None)
        if header != list(columns):
            raise ValueError(f"Unexpected columns in {path.name}.")
        values = np.loadtxt(stream, delimiter=",", ndmin=2)
    if values.shape[1] != len(columns) or not np.isfinite(values).all():
        raise ValueError(f"Expected finite numeric data in {path.name}.")
    return values


def read_numerical_results(directory):
    """Reload the saved run for visualization without simulating or recalculating metrics."""
    data = json.loads((directory / "results.json").read_text(encoding="utf-8"))
    grid = data["grid"]
    nx, ny = grid["nx"], grid["ny"]
    values = read_numeric_table(directory / "receiver_flux.csv", FLUX_COLUMNS)
    if values.shape[0] != nx * ny:
        raise ValueError("The saved flux map size does not match the receiver grid.")
    values = values.reshape(ny, nx, len(FLUX_COLUMNS))
    s, z = cell_centers(grid)
    expected = (np.arange(ny)[:, None], np.arange(nx)[None, :], s[None, :], z[:, None])
    if any(not np.array_equal(values[:, :, index], np.broadcast_to(axis, (ny, nx)))
           for index, axis in enumerate(expected)):
        raise ValueError("The saved flux coordinates do not match the bottom-first receiver grid.")

    columns = [name for name, _ in DETAIL_COLUMNS]
    field = read_numeric_table(directory / "heliostats.csv", columns)
    if field.shape[0] != data["field"]["heliostats"]:
        raise ValueError("The saved heliostat count does not match results.json.")
    details = dict(zip(columns, field.T, strict=True))
    return data, values[:, :, 4], details, s, z
