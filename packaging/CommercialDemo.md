# Commercial solar tower demo

This example evaluates one optical operating point of the public Daggett reference field with 8,790 heliostats and an external cylindrical receiver.

From the extracted package root, use the Python environment set up in [the package README](../README.md).

```sh
python -m pip install -r commercial_demo/requirements.txt
python commercial_demo/commercial_demo.py --no-open
```

The default run uses the Refactored CPU backend at 12:30 local standard time on June 21 in the 2011 reference calendar. It reads 849 W/m² of DNI from the Daggett TMY2 input. Use `--mode multicore --threads 8` for a multicore run, `--mode original` for the retained CPU reference, or `--mode cuda` on a CUDA package with a compatible GPU. Use `--help` for date, time, irradiance and grid options.

The script prints the path to an offline HTML report, with the incident flux map, heliostat field and receiver geometry. The same directory contains a JSON summary and two numerical CSV files. The result is one modeled optical operating point of a public reference case. It does not represent measurements of an operating plant. Use `--output` to choose a writable, unused directory. You can regenerate the report from an existing run with `python commercial_demo/report.py RUN_DIRECTORY`.

## Input provenance

The input manifest records the exact checked files, SHA-256 digests and underlying optical settings. The heliostat coordinates and variable definitions come from the pinned SSC reference. The Daggett TMY2 series was derived from the 1961–1990 National Solar Radiation Data Base by NREL and is included as the pinned reference CSV distributed with SolarPILOT(TM). Its weather records describe a typical year assembled from historical data. The 2011 date determines the solar position. The archive includes the SSC BSD-3-Clause notice and the SolarPILOT(TM) license in [licenses](../licenses/).

- [Pinned case manifest](inputs/cases/commercial-reference/case_manifest.json)
- [NREL user's manual for TMY2s](https://doi.org/10.2172/87130)
