# Phase 3B restoration and flat-aperture design

The initial audit found clean pinned repositories and passing CPU baseline tests
(45 Python methods, nine CUDA skips; three native tests). `load_spt` parses the
variable map, receiver/template definitions, embedded weather and layout text,
then leaves the runtime field empty and marks it pending. `SolarField::Create`
parses the layout shell but does not instantiate its heliostats.

`generate_layout` and `assign_layout` unconditionally open the external weather
file, prepare design weather and invoke managed layout. Even refresh mode applies
land/acceptance exclusions and runs a default design-point simulation. Therefore
it is not a faithful deserialization operation. Its serialized-focus branch also
passes through a switch that overwrites saved focal lengths with template values.

The explicit `restore_loaded_layout` C/Python operation validates serialized rows,
requires one enabled receiver, reuses Create and PrepareFieldLayout in a narrowly
scoped restoration mode, bypasses exclusions and design simulation, preserves
saved focal lengths after slant initialization, and prepares neighbor/ID lists.
No generated replacement field or weather substitution is used. Failure cleans
runtime objects and leaves the loaded project pending. Existing generation and
refresh semantics remain separate.

At SPT load, an existing stored weather path wins. Otherwise a relative reference
is checked against the project directory, followed by exactly its stored basename
beside the SPT. No directory scan or arbitrary EPW substitution is performed. A
missing reference remains missing, so weather-dependent operations fail normally.
Only the in-memory variable is resolved; the input project is never rewritten.

Weather dependency matrix:

| Operation | External weather dependency |
| --- | --- |
| Existing managed generation / assignment | Yes, before layout preparation |
| Existing geometry update | Yes, before refresh |
| Explicit serialized restoration | None |
| Single-state Hour/Day | Existing Ambient solar position from project site/date/time |
| Single-state Hermite simulation | Project DNI and ambient/site variables; no external weather read |

Hour/Day already resolves solar azimuth/elevation through PerformanceSimulationPrep
and Ambient; the new numerical adapter will consume its resulting sun vector.
Keep existing already projects saved global aims through receiver geometry; this
operation must be reused unchanged.

The flat numerical extension will extract only the existing Legacy rectangular
aperture quadrature/projection branch. Independent synthetic optical fixtures must
prove bitwise equality of all 215 doubles before CUDA support is enabled. Receiver
cells and normals must continue to come from existing receiver geometry. Existing
cylindrical tests and selected commercial anchors remain mandatory. The private
project and reference weather will be inspected only after public correctness
gates; private inputs and detailed outputs stay ignored and unchanged.
