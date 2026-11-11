# Registro gobernado de la skill Análisis — alta de catálogo, no creación de código

**Estado:** PREPARADO / NO EJECUTADO · 2026-11-04 · PR #3529.

## Decisión

Registrar **un único activo** `PROGRAMMING_ANALYSIS_LF` como `SKILL` candidato de tipo READ_ONLY. No registrar los 15 pasos como activos; no usar `CREACION_SKILL_LF` para repetir un ciclo de diseño/escritura. El paquete GitHub debe conservarse exactamente. El registro es de **inventario y gobernanza**, no habilitación de runtime ni invocación del modelo.

Se consultaron los contratos reales de `CREACION_SKILL_LF`: obligan `canonical_design`, `partial_scope_guard`, `github_write`, `github_readback` y `close`. Su reservador `lf_reserve_creation_factory_execution_v1` inicia la ejecución y sus pasos; su recorder `lf_record_creacion_skill_step_v1` no inserta `lf_activos`. Por tanto, no sirve como simple operación de alta del paquete existente.

## Precedente

`supabase/migrations/20260930215000_lf_input_source_inventory_l1_candidate_asset_v1.sql` es un ejemplo de alta sin regenerar código, como candidato y con guardas de duplicado/readback. Otro activo `SKILL-GENERACION-PDF-PROFESIONAL-LF` confirma en vivo estados `CANDIDATO`/`READ_ONLY`, `REGISTER_SKILL_CANDIDATE` y provenance `LF_OPERATION_CONTROLLED_CANDIDATES`. **No copiar su ID, lote o ejecución.**

## Entrada para futura migración (aprobación de fuente y transporte gobernados)

Ver `registration/asset_registration_candidate_v1.json`. Tabla única prevista `public.lf_activos`; su `id` exige tratar la secuencia `public.lf_activos_id_seq`. Los campos `source_spreadsheet_*`, `migration_batch_id`, `created_by_execution_id` y `raw_payload` deben tener procedencia real. El `codigo_activo` es UNIQUE.

Gates **obligatorios** en este orden:

1. PR #3529 integrado por procedimiento autorizado, no solo PASE; verificar que `main` contiene el mismo `skills/programming_analysis/SKILL.md` y el manifiesto A1–A15. Si difiere, BLOQUEAR y reconciliar.
2. Registrar en expediente la revisión exacta de `main`, blob SHA de `SKILL.md`, pruebas 121/121, fuente/contratos y acuse del juez de cambios, sin tratar los tests sintéticos como E2E.
3. Preparar migración específica `ACTUALIZACION_DB_LF` con `DB_WRITE_TRANSPORT`/Merge Train: `INSERT` **solo** de `PROGRAMMING_ANALYSIS_LF`, idempotencia con bloqueo explícito de duplicado, CANDIDATO/READ_ONLY/NO_RUNTIME, no actualización de otros activos.
4. Readback bajo el mismo execution_id: exactamente un activo con código, tipo, estados, rutas, main_sha y metadata verificables; comprobar que no apareció `PROGRAMMING_ANALYSIS_A1` separado.

## Estado y riesgos

- `lf_activos`: **0 filas** para `PROGRAMMING_ANALYSIS_LF` y `PROGRAMMING_ANALYSIS_A1` al momento de consulta.
- `main`: **no contiene todavía** el paquete de Análisis; sigue en PR draft.
- Pruebas Python: **109 tests A1 + 12 tests paquete = 121 PASS**, GitHub Actions run #41871619926 para HEAD `4fdea26`.
- Para respetar `test_single_pr_entrypoint_v1.py`, el workflow temporal fue retirado del PR en `b761257`; la comparación entre ambos commits muestra únicamente esa eliminación. No modificar la política PASE.
- Faltan integración real del modelo, juez independiente y A2–A15; el registro candidato no es su calificación.
- **No existe en este lote una migración lista para aplicar**: falta la revisión exacta de main posterior al merge y la ejecución gobernada de DB. No inventar IDs, UUIDs, recibos ni usar conexión RO para DML.

**Nada en este expediente inserta, activa o modifica activos.**
