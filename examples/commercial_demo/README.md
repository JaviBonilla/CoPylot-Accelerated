# Commercial solar tower optical demo

The demo evaluates one operating point of the public SSC Daggett commercial-scale reference with 8,790 heliostats and an external cylindrical receiver. It uses the pinned layout, weather and optical settings documented in the [commercial reference case](../../docs/commercial-reference-case.md). The API calls for configuring the field, selecting a backend, running the simulation and retrieving results are in [simulation.py](simulation.py).

## Run from source

From the repository root, use the project build prerequisites and a Python 3.12 environment.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r examples/commercial_demo/requirements.txt
.venv/bin/python scripts/bootstrap.py
scripts/build_cpu.sh -DSOLARPILOT_ENABLE_FLUX_DIAGNOSTICS=ON
.venv/bin/python examples/commercial_demo/commercial_demo.py --no-open
```

Refactored CPU is the default. Use `--mode original` with flux diagnostics enabled, `--mode multicore --threads 8` to share one simulation across CPU threads, or `--mode cuda` with a [CUDA development build](../../docs/backend.md). Set `COPILOT_LIB_DIR` to select a development library directory.

```sh
.venv/bin/python examples/commercial_demo/commercial_demo.py \
  --mode multicore --threads 8 --date 2011-06-21 --time 12:30 \
  --cell-size 0.5 --output artifacts/commercial-demo/commercial-multicore --no-open
```

Dates use the native SolarPILOT 2011 reference calendar. Times are Daggett local standard time (UTC−08:00), with `HH:30` selecting the TMY2 row at hour `HH`. The June 21 default uses 849 W/m² from the row at hour 12, sourced from 1975. TMY2 assembles historical observations into a typical year. SolarPILOT calculates the sun for the selected calendar date and uses the row's DNI directly. A positive `--dni` override is recorded alongside the original TMY2 value. Nighttime and unsupported times are rejected.

## Results

The default output directory is `artifacts/commercial-demo/commercial-2011-06-21-1230/`. Use `--output` for subsequent runs at the same instant. Each successful run prints the absolute path to `report.html`. Omit `--no-open` to open it automatically in a desktop session. The report works offline in a browser with JavaScript enabled.

- `report.html` contains interactive views of incident receiver flux, the heliostat field and the modeled receiver geometry.
- `results.json` records the operating point, settings, provenance, receiver summary and timings. The simulation timing covers the native simulation call.
- `receiver_flux.csv` uses zero-based row and column indices and physical cell centers in metres. Rows ascend from the receiver bottom and columns follow the native order from the south seam toward decreasing azimuth. The values are sampled incident flux densities in kW/m². Integration uses the [cylindrical cell area](../../docs/receiver-grid-convergence.md).
- `heliostats.csv` retains reference ordering and includes East/North/pivot coordinates in metres, optical factors as fractions and the native absorbed contribution in kW. The reported field optical efficiency excludes receiver absorption. The per-heliostat efficiency and absorbed contribution include it.

To regenerate `report.html` from the saved results, run the report script with the run directory. This command uses NumPy and Plotly and does not need the native library or the case inputs.

```sh
.venv/bin/python examples/commercial_demo/report.py artifacts/commercial-demo/commercial-2011-06-21-1230
```

Run the focused tests with

```sh
.venv/bin/python -m unittest discover -s examples/commercial_demo -p 'test_*.py'
```
