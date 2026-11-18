"""Validate the two teaching examples against the extracted native package."""

import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_quickstart(root, scratch):
    for script, cwd in (("quickstart.py", root), (str(root / "quickstart.py"), scratch)):
        subprocess.run([sys.executable, script], cwd=cwd, check=True, timeout=30)

    sys.path.insert(0, str(root / "python"))
    from copylot_accelerated import CoPylot

    quickstart = runpy.run_path(str(root / "quickstart.py"))
    smoke = runpy.run_path(str(root / "example.py"))
    reference_flux, _, _ = smoke["simulate"](root / "quickstart_weather.csv", "refactored")
    captured = {}
    free_calls = []
    native_fluxmap = CoPylot.get_fluxmap
    native_summary = CoPylot.summary_results
    native_free = CoPylot.data_free

    def get_fluxmap(api, context):
        flux = native_fluxmap(api, context)
        captured["flux"] = np.array(flux, copy=True)
        return flux

    def summary_results(api, context):
        summary = native_summary(api, context)
        captured["summary"] = summary["All receivers"]
        return summary

    def data_free(api, context):
        released = native_free(api, context)
        free_calls.append(released)
        return released

    with patch.multiple(CoPylot, get_fluxmap=get_fluxmap, summary_results=summary_results, data_free=data_free):
        with redirect_stdout(io.StringIO()):
            quickstart["main"]()
        require(free_calls == [True], "Quick Start did not release its successful simulation")
        with patch.object(CoPylot, "assign_layout", return_value=False):
            try:
                quickstart["main"]()
            except RuntimeError as error:
                require("Could not assign the synthetic heliostat layout" in str(error), str(error))
            else:
                raise ValueError("Quick Start accepted a failed layout assignment")
        require(free_calls == [True, True], "Quick Start did not release its failed simulation")

    flux, summary = captured["flux"], captured["summary"]
    require(flux.shape == (25, 25) and np.isfinite(flux).all() and flux.min() >= 0,
            "Invalid Quick Start receiver flux")
    np.testing.assert_allclose(flux, reference_flux, rtol=1e-9, atol=1e-10)
    np.testing.assert_allclose(flux.max(), 52.346894672901776, rtol=1e-9)
    require(summary["Simulated heliostat count"] == 12, "Unexpected Quick Start heliostat count")
    # Native summary rounds field efficiency to 0.01 percentage point and
    # absorbed power to 0.1 kW.
    np.testing.assert_allclose(summary["Solar field optical efficiency"], 86.52, rtol=0, atol=.01)
    np.testing.assert_allclose(summary["Power absorbed by the receiver"], 1268.1, rtol=0, atol=.11)
    print("Quick Start matched the synthetic reference and released both contexts.", flush=True)


def validate_commercial(root, scratch, cuda):
    demo = root / "commercial_demo"
    modes = ["refactored", "cuda"] if cuda else ["refactored"]
    maps = {}
    for mode in modes:
        output = scratch / mode
        subprocess.run([sys.executable, str(demo / "commercial_demo.py"), "--mode", mode,
                        "--output", str(output), "--no-open"], cwd=scratch, check=True, timeout=45)
        state = json.loads((output / "results.json").read_text(encoding="utf-8"))
        grid, point = state["grid"], state["operating_point"]
        require((grid["nx"], grid["ny"], state["field"]["heliostats"]) == (111, 44, 8790),
                "Unexpected Commercial Demo grid or heliostat count")
        require((point["date"], point["local_time"], point["dni_w_m2"]) == ("2011-06-21", "12:30", 849),
                "Unexpected Commercial Demo operating point")
        require(state["configuration"]["backend"] == ("cuda" if mode == "cuda" else "cpu"),
                "Unexpected Commercial Demo backend")
        flux = np.loadtxt(output / "receiver_flux.csv", delimiter=",", skiprows=1, usecols=4)
        require(flux.shape == (111 * 44,) and np.isfinite(flux).all() and flux.min() >= 0,
                "Invalid Commercial Demo receiver flux")
        np.testing.assert_allclose(flux.max(), 1911.2525598149134, rtol=1e-9)
        np.testing.assert_allclose(state["metrics"]["integrated_incident_power_kw"], 668804.8351224513, rtol=1e-9)
        with (output / "heliostats.csv").open(encoding="utf-8") as heliostats:
            require(sum(1 for _ in heliostats) == 8791, "Incomplete Commercial Demo heliostat output")
        maps[mode] = flux
        report = output / "report.html"
        rendered = report.read_bytes()
        require(b'role="tablist"' in rendered and b"Plotly.newPlot" in rendered and b"plotly.js v" in rendered,
                "Missing standalone Commercial Demo plots")
        subprocess.run([sys.executable, str(demo / "report.py"), str(output)],
                       cwd=scratch, check=True, timeout=30)
        require(report.read_bytes() == rendered, "Commercial Demo report changed on regeneration")
    if cuda:
        np.testing.assert_allclose(maps["cuda"], maps["refactored"], rtol=1e-9, atol=1e-10)
    print(f"Commercial Demo matched the optical reference and regenerated its report ({', '.join(modes)}).",
          flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--cuda", action="store_true")
    args = parser.parse_args()
    with TemporaryDirectory() as temp:
        root, scratch = args.package.resolve(), Path(temp)
        validate_quickstart(root, scratch)
        validate_commercial(root, scratch, args.cuda)
