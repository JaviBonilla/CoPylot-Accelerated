"""Focused tests that can run without a native library or upstream data."""

import csv
import json
import math
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

from commercial_demo import save_run
from report import cylindrical_flux_figure, field_figure, render_saved_report
from results import DETAIL_COLUMNS, RECEIVER_COORDINATES, bottom_first, validate_power
from simulation import map_metrics, physical_grid, select_weather


class CommercialDemoTests(unittest.TestCase):
    def test_weather_selection_and_override(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "weather.csv"
            path.write_text(
                "Location ID,Latitude,Longitude,Time Zone,Elevation\n"
                "test,34.85,-116.8,-8,588\n"
                "Year,Month,Day,Hour,DNI\n"
                "1975,6,21,0,0\n1975,6,21,12,849\n", encoding="utf-8",
            )
            state = select_weather(path, "2011-06-21", "12:30")
            self.assertEqual(state["hour"], 12.5)
            self.assertEqual(state["weather_record_source_year"], 1975)
            self.assertEqual(state["site"]["utc_offset_hours"], -8)
            self.assertEqual(state["dni_w_m2"], 849)
            override = select_weather(path, "2011-06-21", "12:30", 800)
            self.assertEqual(override["dni_w_m2"], 800)
            self.assertEqual(override["tmy2_dni_w_m2"], 849)
            self.assertEqual(override["dni_source"], "User override")
            for day, clock, dni, message in [
                ("2026-06-21", "12:30", None, "reference year"),
                ("2011-02-29", "12:30", None, "out of range"),
                ("2011-06-21", "12:00", None, "midpoint"),
                ("2011-06-21", "00:30", None, "daylight"),
                ("2011-06-21", "12:30", float("inf"), "finite DNI"),
                ("2011-06-21", "13:30", None, "exactly one"),
            ]:
                with self.subTest(day=day, clock=clock, dni=dni), self.assertRaisesRegex(ValueError, message):
                    select_weather(path, day, clock, dni)

    def test_receiver_geometry_and_orientation(self):
        receiver = {"type": "cylindrical", "diameter_m": 17.65, "height_m": 21.6029}
        grid = physical_grid(receiver, 0.5)
        self.assertEqual((grid["nx"], grid["ny"]), (111, 44))
        flux = np.full((44, 111), 10.)
        metrics = map_metrics(flux, grid)
        self.assertAlmostEqual(metrics["integrated_incident_power_kw"], math.pi * 17.65 * 21.6029 * 10)
        np.testing.assert_array_equal(bottom_first([[50, 70], [10, 20]]), [[10, 20], [50, 70]])
        with self.assertRaisesRegex(ValueError, "shape"):
            map_metrics(flux.T, grid)

    def test_power_consistency(self):
        summary = {"Power absorbed by the receiver": 94, "Simulated heliostat count": 2}
        metrics = {"integrated_incident_power_kw": 100.01}
        details = {"absorbed_receiver_power_kw": np.array([40., 54.0094])}
        self.assertEqual(validate_power(summary, metrics, details, .94, 2), 94)
        with self.assertRaisesRegex(ValueError, "disagrees"):
            validate_power(summary, metrics, details, .92, 2)

    def test_cylindrical_flux_cells_and_seam(self):
        flux = np.arange(1., 17.).reshape(2, 8)
        s, z = (np.arange(8) + .5) * math.pi / 4, np.array([.5, 1.5])
        trace = cylindrical_flux_figure({"diameter_m": 2., "height_m": 2.}, flux, s, z, 16).data[0]
        vertices = np.column_stack((trace.x, trace.y, trace.z))
        faces = np.column_stack((trace.i, trace.j, trace.k))
        np.testing.assert_array_equal(vertices[::9], vertices[8::9])
        np.testing.assert_array_equal(vertices[::9], [[0, -1, 0], [0, -1, 1], [0, -1, 2]])
        np.testing.assert_array_equal(trace.intensity, np.repeat(flux.ravel(), 2))
        self.assertEqual(trace.intensitymode, "cell")
        for row, col in ((0, 0), (0, 7), (1, 0), (1, 7), (1, 3), (0, 5)):
            with self.subTest(row=row, col=col):
                first = 2 * (8 * row + col)
                picked = vertices[np.unique(faces[first:first + 2])]
                theta = math.pi - s[col]
                center = math.cos(math.pi / 8) * np.array([math.sin(theta), math.cos(theta)])
                np.testing.assert_allclose(picked.mean(axis=0), [*center, z[row]], atol=1e-15)
                np.testing.assert_array_equal(picked[:, 2], [row, row, row + 1, row + 1])
                np.testing.assert_array_equal(trace.customdata[first:first + 2], [[s[col], z[row]]] * 2)

    def test_sun_direction_uses_clockwise_azimuth_from_north(self):
        details = {"id": np.array([0]), "x_east_m": np.array([100.]), "y_north_m": np.array([200.]),
                   "optical_efficiency_fraction": np.array([.5]), "absorbed_receiver_power_kw": np.array([28.])}
        for azimuth in (0, 90, 180, 220.76253797330307, 270):
            with self.subTest(azimuth=azimuth):
                figure = field_figure(details, azimuth)
                arrow, label = figure.layout.annotations[:2]
                self.assertEqual((arrow.xref, arrow.yref, arrow.axref, arrow.ayref), ("x", "y", "x", "y"))
                actual = math.degrees(math.atan2(arrow.x - arrow.ax, arrow.y - arrow.ay)) % 360
                self.assertAlmostEqual(actual, azimuth)
                self.assertEqual(label.text, "Sun direction")
                self.assertEqual(figure.layout.yaxis.scaleanchor, "x")

    def test_exports_and_offline_report(self):
        # A small unit-test fixture. The end-to-end demo always uses the pinned case.
        receiver = {"type": "cylindrical", "diameter_m": 2., "height_m": 2.,
                    "tower_optical_height_m": 10., "absorptance": .94, "circumference_m": 2 * math.pi,
                    "surface_area_m2": 4 * math.pi}
        grid = {**physical_grid(receiver, 4.), "export_coordinates": RECEIVER_COORDINATES}
        flux = bottom_first([[3., 4.], [1., 2.]])
        data = {
            "case_id": "test-fixture", "grid": grid, "receiver": receiver, "limitations": ["Fixture only"],
            "field": {"heliostats": 1, "heliostat_width_m": 1, "heliostat_height_m": 1,
                      "physical_mirror_area_m2": 1, "effective_aperture_area_m2": 1,
                      "layout_bounds_m": {"x": [1, 1], "y": [2, 2]}},
            "operating_point": {"site": {"name": "Test site"}, "date": "2011-06-21", "local_time": "12:30",
                                "dni_w_m2": 849, "dni_source": "Test", "weather_record_hour": 12,
                                "weather_record_source_year": 1975, "tmy2_dni_w_m2": 849,
                                "solar_azimuth_deg": 220, "solar_elevation_deg": 75, "weather_convention": "Test"},
            "configuration": {"mode": "refactored", "optical_model": "Hermite", "aiming": "Simple",
                              "threads": 1, "backend": "cpu"},
            "metrics": {**map_metrics(flux, grid), "optical_efficiency_percent": 61, "receiver_absorbed_power_kw": 28},
            "timing_seconds": {"simulate": .1}, "sources": {},
            "provenance": {"repository_revision": "revision", "library_sha256": "hash"},
        }
        details = {name: np.array([0.]) for name, _ in DETAIL_COLUMNS}
        details.update(x_east_m=np.array([1.]), y_north_m=np.array([2.]),
                       optical_efficiency_fraction=np.array([.5]), absorbed_receiver_power_kw=np.array([28.]))
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            with patch("report.write_report", side_effect=OSError("test export interruption")):
                with self.assertRaisesRegex(OSError, "interruption"):
                    save_run(target, data, flux, details)
                self.assertEqual(list(Path(tmp).iterdir()), [])
            report = save_run(target, data, flux, details)
            self.assertEqual(report, target / "report.html")
            self.assertEqual(json.loads((target / "results.json").read_text()), data)
            with (target / "receiver_flux.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
                self.assertEqual([r["row_from_bottom"] for r in rows], ["0", "0", "1", "1"])
                self.assertEqual([float(r["incident_flux_kw_m2"]) for r in rows], [1, 2, 3, 4])
                self.assertAlmostEqual(float(rows[-1]["s_m"]), 1.5 * math.pi)
            with (target / "heliostats.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
                self.assertEqual(len(rows), 1)
                self.assertEqual(float(rows[0]["absorbed_receiver_power_kw"]), 28)
            html = report.read_text(encoding="utf-8")
            self.assertNotRegex(html, r"<script[^>]*\bsrc=")
            self.assertIn("plotly.js v", html)
            self.assertIn("<h1>Commercial Solar Tower - Optical Simulation</h1>", html)
            figures = json.loads(re.search(r'id="figures">(.*?)</script>', html).group(1))
            self.assertEqual(figures["flux-chart"]["layout"]["yaxis"]["scaleanchor"], "x")
            heatmap = figures["flux-chart"]["data"][0]
            mesh = figures["cylinder-flux-chart"]["data"][0]
            self.assertEqual((mesh["cmin"], mesh["cmax"]), (heatmap["zmin"], heatmap["zmax"]))
            self.assertEqual(mesh["colorscale"], heatmap["colorscale"])
            field = figures["field-chart"]
            self.assertEqual(field["data"][0]["type"], "scattergl")
            marker = field["data"][1]
            self.assertEqual((marker["x"], marker["y"], marker["mode"]), ([0], [0], "markers"))
            self.assertEqual(marker["hovertemplate"], "Tower at field origin<extra></extra>")
            tower = next(item for item in field["layout"]["annotations"] if item["text"] == "Tower")
            self.assertEqual((tower["x"], tower["y"], tower["xref"], tower["yref"]), (0, 0, "x", "y"))
            self.assertEqual(tower["yanchor"], "bottom")
            self.assertGreater(tower["yshift"], 0)
            self.assertFalse(tower["captureevents"])
            scene = figures["geometry-chart"]["layout"]["scene"]
            for axis in "xy":
                self.assertAlmostEqual(
                    scene["aspectratio"][axis] / scene["aspectratio"]["z"],
                    np.ptp(scene[f"{axis}axis"]["range"]) / np.ptp(scene["zaxis"]["range"]),
                )
            with self.assertRaisesRegex(FileExistsError, "already exist"):
                save_run(target, data, flux * 2, details)
            saved = {path: path.read_bytes() for path in target.iterdir()}
            self.assertEqual(render_saved_report(target), report)
            self.assertEqual({path: path.read_bytes() for path in target.iterdir()}, saved)

            flux_csv = target / "receiver_flux.csv"
            header, first, *remaining = flux_csv.read_text(encoding="utf-8").splitlines()
            flux_csv.write_text("\n".join([header, *remaining, first]) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "bottom-first"):
                render_saved_report(target)
            self.assertEqual(report.read_text(encoding="utf-8"), html)


if __name__ == "__main__":
    unittest.main()
