# F5.1 Login · decisión del owner para el sandbox

**OWNER_DECISION_SANDBOX** · 2026-11-12 · Paulo (owner).
Se autoriza un **único lote BACKEND** en el sandbox ficticio,
con las 6 obligaciones de A6, todos sus criterios, las 6 reglas tipadas
A9 y la cobertura de los 19 frentes A7. No se crea lote DATA.

La decisión está fijada en `owner_area_decision.json` y vinculada al
SHA del paquete `analysis.json`. Sin ese archivo el adaptador debe conservar
`F51_DATA_REQUIREMENT_NOT_SOURCE_BOUND`. El hueco de asignación de
frentes/áreas debe resolverse por **Análisis antes de cualquier traslado a LF**.

Usuarios por defecto: la implementación futura debe obtener su
configuración de `apps/time-service/.env.example` y hashes **BCrypt**.
Ese archivo y las clases Java de Login **aún no están implementados**:
son límites/criterios de una tarea candidata, no código producido.

`planning_fixture.json` lo construye el adaptador del paquete y de la
decisión tipada para invocar `plan_lots.plan()` con los productores reales
fijados PG-02→PG-05 y selector PostgreSQL desechable. La escritura permitida
está acotada a cuatro rutas Java `lf/sandbox/time/auth/` (máximo seis).

En `.lf/worker-context/f5backend/` se guardan, en archivos distintos:
`reglas_tecnicas.json`: STD-BE + STD-SEC pinneados de PG-00;
`reglas_negocio.json`: las seis reglas A9 con `valor_config`,
`source_ref`, `requirement_id`, `front_id` y los criterios originales.
No se crea ni conserva `f5data`. Ningún contexto es tarea registrada.

**No autoriza producción, entrega ni merge.** PG-01 sigue
`FIXTURE_UNATTESTED`. No se modifica A1–A9, intake, texto libre de P4,
ex6, ex7, ex8 ni los exámenes. Sin etiquetas.
