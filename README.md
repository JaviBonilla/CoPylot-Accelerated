# CoPylot-GPU: preparación Fase 0/1

Workspace headless para acelerar el núcleo C++ de CoPylot con CUDA manteniendo la API Python y la referencia CPU. La simulación Hermite CPU, los tres benchmarks y las regresiones funcionan. El backend óptico CUDA todavía no está implementado. El probe/toolchain opcional está preparado; su compilación y ejecución reales requieren validación en un entorno NVIDIA con nvcc.

```bash
# Desde una copia de este workspace, reconstruir los repositorios y parches fijados:
python3 scripts/bootstrap.py
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
scripts/build_cpu.sh
scripts/test_cpu.sh
.venv/bin/python benchmarks/run_cpu.py --repeats 5
scripts/profile_cpu.sh
```

La biblioteca está en `build/cpu/lib/solarpilot.so`. El build usa SSC solarpilot-develop y SolTrace legacy; no compila SolarPILOT GUI, wxWidgets, LK ni WEX. Las ramas locales son `feature/copilot-gpu`; commits y parches exactos: [repos.lock.json](repos.lock.json).

Documentación:

* [Informe y estado verificado](docs/report.md).
* [Decisión de repositorios/ramas](docs/dependencies.md), [build y pruebas](docs/build.md).
* [Perfil CPU medido](docs/cpu-profile.md), [datos brutos](benchmarks/results).
* [Backend y versiones propuestas](docs/backend.md), [modelo de datos GPU](docs/gpu-data-model.md).
* [Roadmap y próximo kernel](docs/roadmap.md), [análisis SolTrace/OptiX](docs/soltrace.md).
* [Plan y matriz de validación](docs/plan.md).

La serie de parches conserva los commits pequeños de los tres repositorios; `bootstrap.py` recrea sus mismos SHAs y se niega a sobrescribir checkouts que no coincidan. Por el `.git` reservado y de sólo lectura del entorno desktop, los commits del workspace usan `.workspace-git`; aquí se consultan con `scripts/workspace_git.sh log --oneline`. Los repositorios internos usan Git normalmente. No se ha publicado ninguna rama ni PR.

Casos: 1000, 5000 y 10000 heliostatos asignados de forma determinista; mapa 25×25, un thread, doble precisión, Hermite, DNI 950, azimut 180°, elevación 55°. Los JSON de regresión almacenan todas las celdas y resultados por heliostato; `rtol=1e-9`, `atol=1e-10`. Captura original anterior al dispatch y profiling; los tests nunca regeneran los baselines.

La primera prioridad GPU recomendada por las medidas es `Flux::fluxDensity()` y su reducción, tras extraer y validar una función numérica CPU. `imagePlaneIntercept()` sigue en el roadmap; no se ha portado ningún algoritmo a CUDA.
