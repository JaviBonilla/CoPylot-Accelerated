# CoPylot-Accelerated Quick Start

Run a single optical simulation for a synthetic field of 12 heliostats and an external cylindrical receiver. The example uses the Hermite model with Simple aiming, a fixed solar position and 900 W/m² direct normal irradiance. It runs on one CPU thread.

## Run the example

With the package's Python requirements installed, put `quickstart.py` and `quickstart_weather.csv` in the extracted CoPylot-Accelerated directory alongside `BUILD.json`, `lib/` and `python/`. The repository version can be used this way with the v0.1.0 package. Run with the package's Python environment.

```sh
python quickstart.py
```

The script locates the wrapper and weather file beside itself, so you can also run it by path from another directory.

## What the script does

1. Creates a CoPylot context, sets the weather path and configures the model, receiver, solar position and flux grid.
2. Assigns three rows of heliostats using records in the form `[template ID, East m, North m, pivot height m]`.
3. Runs one optical calculation on the CPU, retrieves the summary and flux map, and frees the context.
4. Prints the simulated heliostat count, field optical efficiency before receiver absorption, absorbed receiver power in kW, peak incident flux in kW/m² and the grid size. The script writes no output files.

The weather CSV supplies the site and hourly input required during layout preparation. It contains 8,760 artificial records for 2001, with DNI of 900 W/m² from hour 06 through 17 and zero otherwise. All site and weather values are invented. The flux calculation uses the fixed solar angles and DNI in the Python script.

The Commercial Demo uses a public commercial-scale reference field of 8,790 heliostats and produces an interactive HTML report. See the README in `commercial_demo/`.
