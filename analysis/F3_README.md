# F3: A7 cobertura de frentes y A8 regla de parada

Estado **SIMULATED_SANDBOX_ONLY**, materialidad HIGH, examen independiente
obligatorio, sin fuentes CURRENT ni autoridad productiva.

## Contratos fuente (F0, intocables)

- A7: `analysis_material_front_coverage_contract_v1.json`, blob Git `a0ef134afc07ed6fcc2385b37212d01e678f0cc6`.
- A8: `analysis_stop_rule_contract_v1.json`, blob Git `4bb7265c985b06e23cc2428c4332187a9330fdae`.

A7 valida los nombres, valores y guards. Estructura `MATERIAL_FRONT_COVERAGE_V1`
con `front_candidate_refs`, `material_fronts`,
`unmapped_material_signals`, `all_material_fronts_accounted`,
`coverage_fingerprint_sha256`, `source_refs` y `currentness_refs`.
Los frentes usan los once campos obligatorios de `front_contract.required_fields`.
No representa recibos de ejecución o aprobación; los `evidence_refs` son
lecturas candidatas sin atestación.

## Descubrimiento de candidatos

- A3 `material_contract_readback.status_items`: cada ruta JSON pointer con
  estado da exactamente un frente por su `source_ref`. Las reglas explícitamente
  excluidas se conservan como NOT_APPLICABLE, **con fuente y motivo**, solo para
  el alcance aprobado, nunca se convierten en una obligación.
- A3 `context`/`metadata` no vacíos generan frentes de sección.
  Las secciones vacías no generan trabajo material.
- A4 `direct_impacts` reutiliza los mismos refs materializados por A3
  (sin lectura duplicada), mientras indirectos/consumidores desconocidos
  pasan a un frente BLOCKED.
- A6: exactamente seis `requirement_id` con `evidence_refs` del alcance
  aprobado; cada uno genera un frente REQUIRED vinculado.
- A4 `unresolved_material_impacts` genera un frente REQUIRED/BLOCKED.
  Esto evita que un inventario vacío se confunda con dependencias cerradas.

En material sin tipo semántico sustentado se usa `OTHER`, valor explícito
del contrato abierto, en vez de inventar clasificación a partir del texto
libre de la regla.

## Área de ejecución: tabla SANDBOX_HINT (no decisión A5)

| front_kind | execution_area_hint | candidatos |
|---|---|---|
| UI_VISUAL, RESPONSIVE, ACCESSIBILITY | FRONTEND | FRONTEND |
| DATA_CONTRACT | DATA | DATA |
| API_CONTRACT, PERMISSION, SECURITY_PRIVACY, OBSERVABILITY | BACKEND | BACKEND |
| STATE_ERROR | UNKNOWN | BACKEND, FRONTEND |
| ANALYTICS, SIDE_EFFECT, PERFORMANCE, MIGRATION_CUTOVER, ROLLBACK_RECOVERY, CONSUMER_HANDOFF, OTHER | UNKNOWN | sin fuente de área |

La tabla cubre exactamente los `front_kind_hints` fijados. Ninguna
asignación proviene del texto libre o de una presunción del agente.
`execution_area_policy=SANDBOX_HINT` distingue el hint de A5.

## A8: decisión sin falso STOP

A8 consume A3, A5 y A7. Implementa los cuatro `stop_requires` literales:
`decision_stable=true`,
`all_material_fronts_accounted=true`,
`unresolved_decision_changing_questions[]=empty`,
`additional_available_evidence_capable_of_changing_material_decision[]=empty`.

La fuente F1/F2 conserva en A4
`A4_EXISTING_SHARED_DEPENDENCIES_NOT_ATTESTED` y A5
`status=UNRESOLVED`. Por tanto **un resultado STOP para Login
sería falso**: un frente permanece BLOCKED aunque todos los candidatos
estén contabilizados. La salida honesta es CONTINUE con la petición
de evidencia material exacta. No se cambian fixtures para fabricar STOP.
A8 no investiga por curiosidad ni repite lecturas. Una decisión de
owner explícita produce REQUIRES_DECISION; entrada inválida, BLOCKED.

## Ejecución offline

```bash
python3 -m pytest -q analysis/host analysis/a7 analysis/a8
python3 -m analysis.host.run_a1_a8_fixture --output-dir /tmp/sbx-f3
```

El runner **extiende** F2 sin duplicarlo y genera A7 y A8 además de los
artefactos F1/F2. Todo el material se mantiene simulado, sin Supabase.

## Revisión Claude — cierre simulado, N variable y categoría tipada

- A7 acepta **N >= 1** obligaciones de A6; no existe mínimo fijo seis.
  Una lista vacía se bloquea. Login conserva seis como dato observado.
- A7 respeta la admisión sellada por F2. Solo un frente con exactamente un
  blocker presente en `admission.lifted_codes` cambia a CLOSED, con
  `closure_basis=SIMULATED_ADMISSION_LIFT`, `lifted_code` explícito y
  `admission_evidence_ref=sha256:<digest del recibo>` incluido en
  `evidence_refs`. Otros motivos siguen BLOCKED.
  No hay nueva autoridad, CURRENT ni garantía de cierre real.
- `lf_ops.reglas.categoria` se representa con valores **ficticios** únicamente
  en `direct_rules.json` y `effective_rules.json`; ambos archivos quedan
  pinneados por SOURCE_PIN.json. El host F1 lee los bytes verificados con SHA
  y entrega a A7 el vínculo `(rule_code, source_ref, categoria)`. A3 no se
  modifica ni se consulta Supabase.
- Tabla normalizada con `strip().casefold()`:
  `seguridad|SECURITY|ataques|rate_limiting` → SECURITY_PRIVACY;
  `ux|estados_ui|copy` → UI_VISUAL;
  `error_states` → STATE_ERROR;
  `datos` → DATA_CONTRACT;
  `api` → API_CONTRACT;
  `analytics` → ANALYTICS;
  cualquier otro valor, incluidos `flujo`, `negocio`, `BUSINESS`,
  `legal` y `tecnico`, → OTHER.
  Nunca se usa `title` o descripción para elegir el kind.
- El estado real A8 se lee del runner después de la corrección y **no**
  se fuerza a STOP: la estabilidad de A5 es independiente del lift simulado.


## Última revisión Claude: A5 estable exclusivamente por lift simulado

A8 recibe el recibo SIMULATED_ADMISSION_V1 verificado en A7. Solo bajo
`A5.status=UNRESOLVED`, blockers normalizados sin perder trazabilidad,
todos presentes en `admission.lifted_codes`, sin `decision_items` ni preguntas
de decisión abiertas y fila `decisions[]` con `adr_disposition=NOT_REQUIRED`,
puede declarar `decision_stable=true`, `decision_stable_basis=SIMULATED_ADMISSION_LIFT`
y los códigos levantados explícitos. `REQUIRES_DECISION` nunca se levanta.
El STOP, si se produce, se limita al **análisis de sandbox**; no cambia
`source_attested=false` ni permite producción, merge o despliegue.
