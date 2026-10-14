# Fase 0/1: plan y puertas de validación

1. Fijar dependencias y decisión de ramas (`repos.lock.json`, `docs/dependencies.md`).
2. Superbuild headless (`CMakeLists.txt`, `scripts/build_cpu.sh`, `docs/build.md`). Sin cambios algorítmicos: build Release y carga ctypes con enlaces resueltos.
3. Casos Python (`benchmarks/cases.py`, `smoke_test.py`, `run_cpu.py`): generate_layout en smoke; layouts deterministas de 1000/5000/10000 para benchmarks. Medir generación y asignación por separado.
4. Capturar baseline legible (`tests/baselines/*.json`): métricas, flux y detalles por heliostato. Comparar antes de introducir dispatch.
5. Perfil opt-in (`ssc/solarpilot/CoreProfile.*`, scopes en tres archivos) y `docs/cpu-profile.md`: medidas inclusivas/exclusivas y número de llamadas; no sumar tiempos anidados.
6. Dispatch y API (`ComputeBackend.*`, `CoPilot_API.*`, `copylot.py`): CPU llama al cuerpo existente; CUDA rechaza explícitamente simulaciones aún no implementadas. Reejecutar regresión completa antes/después.
7. CUDA opcional y prueba trivial (`CudaProbe.cu`, CMake): CPU sin Toolkit, fallo de configuración claro con ON sin nvcc; ejecución real sólo cuando exista GPU/toolchain.
8. Diseño y roadmap (`docs/gpu-data-model.md`, `backend.md`, `soltrace.md`, `report.md`).

## Matriz de validación

| Cambio | Validación |
|---|---|
| Build | Release, no GUI/wx, `ldd -r`, biblioteca sin símbolos sin resolver |
| Casos | Contexto, layout, simulate, flux no vacío/finito y potencia positiva; liberación en finally |
| Baseline | Tres tamaños, cada celda y cada heliostato, tolerancias explícitas; repetición de estado solar/DNI |
| Perfil | OFF/ON equivalentes; llamadas y tiempos incluidos/excluidos; overhead medido |
| Backend/API | CPU default/selección, opciones inválidas, CUDA no implementado, error visible, API antigua |
| CUDA CMake | OFF sin CUDA; ON sin Toolkit falla explícitamente; GPU pendiente si no disponible |
| Memoria | ASan/UBSan CPU smoke y regresión representativa cuando viable |

Cada puerta debe pasar antes de tocar algoritmos. No se implementa kernel Hermite en esta iteración.
