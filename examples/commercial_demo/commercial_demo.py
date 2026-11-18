#!/usr/bin/env python3
"""Simulate one public SSC commercial-reference operating point and export a report."""

import argparse
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import webbrowser


def save_run(destination, data, flux, details):
    """Publish a run directory only after all four outputs have been written."""
    from report import write_report
    from results import cell_centers, write_numerical_results

    destination = destination.parent.resolve() / destination.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Results already exist at {destination}. Choose another --output.")
    s, z = cell_centers(data["grid"])
    with TemporaryDirectory(dir=destination.parent, prefix=".commercial-") as temp:
        stage = Path(temp) / "completed"
        stage.mkdir()
        write_numerical_results(stage, data, flux, details, s, z)
        write_report(stage / "report.html", data, flux, details, s, z)
        # The sibling directory can be renamed atomically on the same filesystem.
        stage.rename(destination)
    return destination / "report.html"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="2011-06-21", help="SolarPILOT reference-calendar date")
    parser.add_argument("--time", default="12:30", help="TMY2 midpoint HH:30, Daggett local standard time")
    parser.add_argument("--dni", type=float, help="Override the record's DNI in W/m²")
    parser.add_argument("--mode", choices=("original", "refactored", "multicore", "cuda"), default="refactored")
    parser.add_argument("--threads", type=int, help="Multicore threads (default 4)")
    parser.add_argument("--cell-size", type=float, default=0.5, metavar="METRES")
    parser.add_argument("--output", type=Path, help="Fresh output directory")
    parser.add_argument("--no-open", action="store_true", help="Print the report path without opening a browser")
    args = parser.parse_args()
    if args.threads is None:
        args.threads = 4 if args.mode == "multicore" else 1
    if (args.mode == "multicore" and not 2 <= args.threads <= 2**31 - 1
            or args.mode != "multicore" and args.threads != 1):
        parser.error("Use a valid native thread count of at least two for Multicore, or one for other modes.")
    try:
        from simulation import ROOT, run_simulation

        data, flux, details = run_simulation(
            date=args.date, local_time=args.time, dni=args.dni, mode=args.mode,
            threads=args.threads, target_cell_m=args.cell_size,
        )
        state = data["operating_point"]
        name = f"commercial-{state['date']}-{state['local_time'].replace(':', '')}"
        output = args.output or ROOT / "artifacts/commercial-demo" / name
        report = save_run(output, data, flux, details)
    except (ValueError, OSError, RuntimeError, KeyError, OverflowError, ImportError) as error:
        parser.exit(1, f"Commercial demo: {error}\n")
    print(report, flush=True)
    headless = sys.platform.startswith("linux") and not (os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"))
    if not args.no_open and not headless and not os.getenv("CI") and not os.getenv("SSH_CONNECTION"):
        try:
            webbrowser.open(report.as_uri())
        except (OSError, webbrowser.Error):
            pass


if __name__ == "__main__":
    main()
