# Informe Fase 0/1 — CoPylot-GPU

Fecha: 14 de octubre de 2026. Base CPU headless compilada y verificada. Infraestructura CUDA opcional preparada; no hay backend óptico CUDA y el probe .cu todavía requiere compilación/ejecución en un entorno con NVIDIA/nvcc.

## 1. Repositorios y decisión de ramas

| Repositorio | Base | SHA upstream | SHA local con parches |
|---|---|---|---|
| SolarPILOT | develop | `c74618a70fd8e85708957b1ee57b157ba75a5045` | `53640fdfd671f06255a6b35db2e139ea0d6d1b24` |
| ssc | solarpilot-develop | `e9469f34d4703cd71ec5eb77aa6b7a96eea8dcec` | `9ce2c8c6424bbc8e91718734404266c8137170ae` |
| SolTrace | v3.4.0 | `79b2ca3dfec496506d24ae56055c0d7e240ba368` | `699263f12b2de1c6f12e211e3e8906a80054cc1b` |

Todos los checkouts trabajan en feature/copilot-gpu. SolarPILOT/develop aporta la API Python actual. SSC oficial develop no contiene CoPilot_API: se utiliza el fork mjwagner2/ssc recomendado por el README oficial. SolTrace v3.4.0 conserva el bridge legacy compatible para este baseline; develop actual se inspeccionó, pero no se integró. Evidencia y comparación con copilot histórica en [dependencies.md](dependencies.md).

## 2. Compilar desde cero

Desde una copia de los archivos de este workspace:

```bash
python3 scripts/bootstrap.py
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
scripts/build_cpu.sh
```

Resultado: build/cpu/lib/solarpilot.so. CMake >=3.24/<4, Ninja, GCC/G++ y Python 3.12; sin GUI/wxWidgets/LK/WEX. Las dependencias están vendorizadas/fijadas. El bootstrap aplica la serie de parches y recrea exactamente los SHAs locales; no sobrescribe repositorios existentes que difieran. Se ha comprobado clone → parches → configure → build limpio en /tmp/copilot-repro. Detalles en [build.md](build.md).

## 3. Pruebas y evidencia

```bash
scripts/test_cpu.sh
```

* Smoke Python: 1425 heliostatos generados, simulate correcto, flux 25×25 finito/positivo, resultados finitos y liberación del contexto.
* Regresión: 1000/5000/10000 heliostatos asignados, todas las métricas, 625 celdas/caso y todas las columnas por heliostato. rtol=1e-9, atol=1e-10; baselines capturados antes de dispatch/profiling. Ninguna tolerancia se relajó.
* Siete tests unittest: baseline completo, rechazo de drift, DNI/posición solar/restauración, dispatch CPU/rechazo CUDA, detección/dispositivo, contexto null y compatibilidad dataframe/diccionario/matriz con liberación incluso si falla la conversión.
* Native CTest: generación y tres simulaciones con resultados finitos; incluye factorial 13! sin overflow.
* Release, profiling ON/OFF y reconstrucción limpia: pruebas pasadas. ASan/UBSan Python: los seis tests iniciales completos y el test adicional de exports; native ASan/UBSan/LeakSanitizer sin errores/fugas. LeakSanitizer requirió permiso de inspección de hilos fuera del sandbox.
* Dos defectos legacy detectados y corregidos: overflow en factorial_d y bool/punteros de nodos ópticos no inicializados. Los resultados CPU siguen pasando el baseline original.
* Tres exports Python ya liberan sus arrays C++ con try/finally; formas y valores públicos preservados.

## 4. Benchmarks y profiling

```bash
.venv/bin/python benchmarks/run_cpu.py --repeats 10
.venv/bin/python benchmarks/export_overhead.py
scripts/profile_cpu.sh
.venv/bin/python scripts/summarize_profile.py
```

Raw data versionados en benchmarks/results, con commits y hashes de fuentes/meteorología/layout para las mediciones finales. Hermite, doble precisión, un thread, receptor cilíndrico, aiming simple, 25×25, DNI 950, azimut 180°, elevación 55°. Generación con filtrado se mide separadamente; simulate usa los campos asignados deterministas.

## 5. Tiempos CPU finales

Host: 12th Gen Intel(R) Core(TM) i5-1240P. Release/O3. Medianas de 10 llamadas; generación/asignación son una llamada por caso. Sin fijar frecuencia/afinidad; no interpretar variaciones respecto al original como aceleración.

| Caso | generate_layout ms | assign_layout ms | simulate ms | get_fluxmap ms | detail_results ms |
|---|---:|---:|---:|---:|---:|
| small (1000) | 83.984 | 54.544 | 64.476 | 0.065 | 1.881 |
| medium (5000) | 174.923 | 124.425 | 322.782 | 0.072 | 9.391 |
| large (10000) | 226.737 | 204.324 | 659.102 | 0.067 | 19.858 |

Los campos generados tienen 1421/6291/13704 heliostatos respectivamente. Las simulaciones medidas utilizan exactamente 1000/5000/10000. La captura original y las tablas de funciones inclusivas/exclusivas están en [cpu-profile.md](cpu-profile.md).

## 6. Hot spots medidos

| Función/bucle | small % | medium % | large % |
|---|---:|---:|---:|
| Flux::fluxDensity | 85.92 | 84.91 | 84.30 |
| Flux::imagePlaneIntercept | 9.36 | 9.43 | 9.28 |
| ShadingBlockingNeighbors | 2.04 | 3.09 | 3.87 |
| calcHeliostatShadows | 0.24 | 0.25 | 0.25 |

AnalyticalFluxSimulation contiene prácticamente todo fluxDensity; sus tiempos no deben sumarse. CalcDimensionalFluxProfiles supone ~0.03–0.04%. Shading/blocking real se midió en su bucle de vecinos, no se confundió con la preparación calcHeliostatShadows.

Exportación de detalles de 10000 heliostatos: mediana C ~1.113 ms frente a diccionario Python completo ~21.905 ms. Flux: C ~0.008 ms frente a Python ~0.061 ms. Reestructuración/cachés se identifican como oportunidades por lectura de código; overhead de multiprocessing, optimizadores, copias profundas y geometrías/elevaciones diferentes no fue medido.

## 7. Arquitectura CPU/GPU

CopilotObject posee ComputeBackendState: CPU por defecto, dispositivo solicitado, unique_ptr<GpuContext> y error. sp_simulate realiza un dispatch único y conserva el cuerpo CPU existente. CUDA devuelve un error explícito y no cambia el backend al rechazarse. C/Python exponen disponibilidad, número de dispositivos, selección de backend/dispositivo y errores. CPU-only devuelve false/0 para detección.

CMake permite SOLARPILOT_ENABLE_CUDA=ON; detecta lenguaje/Toolkit y enlaza un probe con kernel trivial que escribe 42, errores explícitos y RAII. OFF no requiere CUDA. ON sin nvcc falla con un mensaje comprobado. Disponible no significa que exista el backend óptico.

Persistencia en VRAM, buffers SoA, capacidad reutilizable, epochs y evaluate_batch están diseñados, todavía no implementados. DNI/sol no requieren recargar posiciones, pero sol/tracking sí afectan vecinos y óptica; las listas no pueden considerarse inmutables sólo porque el layout lo sea. Ver [backend.md](backend.md) y [gpu-data-model.md](gpu-data-model.md).

## 8. Archivos y commits

* Workspace: CMakeLists.txt, repos.lock.json, requirements.txt, README.md; scripts de build/test/bootstrap/export/profiling; benchmarks/smoke_test.py, cases.py, run_cpu.py, export_overhead.py; tests y baselines JSON; documentación y datos brutos.
* SSC: CoPilot_API.cpp/.h, ComputeBackend.cpp/.h, CudaProbe.cu, CoreProfile.cpp/.h, CMakeLists.txt del core; scopes opt-in en Flux.cpp/SolarField.cpp/interop.cpp; macro HELIO_INTERCEPT válida; correcciones localizadas Toolbox.cpp/OpticalMesh.h.
* SolarPILOT: sólo deploy/api/copylot.py (wrappers añadidos y ownership de arrays). Ningún archivo GUI modificado.
* SolTrace: sólo coretrace/treemesh.cpp (inclusión limits).
* Cada repositorio conserva commits pequeños separados, exportados en patches/*.patch. Workspace: scripts/workspace_git.sh log --oneline; repositorios internos: git -C ssc/SolarPILOT/SolTrace log. No se han publicado cambios remotos.

## 9. Riesgos y límites

* GPU, driver y nvcc no están disponibles en el entorno: no se ha compilado ni ejecutado CudaProbe.cu. Esta es la principal validación pendiente; no hay tiempos ni speedup GPU.
* La base CoPylot depende del fork SSC recomendado, no del SSC SAM actual. Actualizar esa dependencia requiere comparación/regresión, no un git pull.
* Regresión inicial cubre receptor cilíndrico/aiming simple y los tres tamaños. Ampliar a receptores múltiples, cavidades, partículas, canting y elevaciones extremas antes de afirmar cobertura GPU general.
* El profiling es instrumentación de scopes seleccionados en un thread, no un call graph completo. perf está restringido; porcentajes se limitan a los casos medidos.
* APIs legacy fuera de los caminos probados conservan sus precondiciones y pueden requerir auditoría adicional de ownership/errores. No se refactorizó toda la API.
* SolTrace actual/OptiX no está validado con CoPylot. Su bridge legacy pierde cosenos/elementos/etapas y tiene problemas de propagación de errores/build opcional; relinkar no selecciona OptiX ni garantiza equivalencia. [soltrace.md](soltrace.md) documenta evidencia y requisitos.

## 10. Próximo paso recomendado

Primero validar el probe opcional en un equipo NVIDIA/CUDA. Después extraer la contribución numérica de fluxDensity a una función CPU independiente y comprobar CPU-old vs CPU-new antes de portar nada. El 84–86% medido hace que sea el candidato inicial más rentable de estos casos; imagePlaneIntercept queda como port posterior con sus momentos, sigma e hcoef, no sólo el escalar intercept.

Roadmap completo de Fases 2–9 en [roadmap.md](roadmap.md). No se ha implementado ningún algoritmo óptico CUDA, batch/evaluate_batch ni integración OptiX.

## Entregables

- [x] Repositorios/SHAs/parches reproducibles y decisión de ramas.
- [x] Build headless, solarpilot.so, smoke y pruebas CPU.
- [x] Benchmarks small/medium/large y perfil medido.
- [x] Regresión original vs CPU actualizado.
- [x] Backend CPU explícito y extensiones C/Python.
- [x] Scaffolding CUDA opcional y comportamiento CPU-only/error sin nvcc comprobados.
- [ ] Compilar/ejecutar el probe CUDA y comprobar detección con GPU real.
- [x] Diseño de residencia/dirty/SoA y roadmap de Fase 2.
