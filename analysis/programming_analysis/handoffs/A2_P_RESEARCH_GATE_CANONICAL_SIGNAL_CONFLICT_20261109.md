# A2-P — bloqueo de preclasificación sin evidencia tipada | 2026-11-09

**Programa:** PROGRAMMING_ANALYSIS_LF · **PR:** #3624 · **HEAD leído antes del lote:** `5c61ce9ea310897d69ce23014da2d43b460f8184`.
**Estado:** DIAGNOSTICADO, diseño de admisión NO APROBADO, implementación A2-P→A3 NO AUTORIZADA. No modificó contratos, Router, Supabase, permisos ni PASE.

## Objetivo
Resolver el ciclo A1 `REQUIRES_DECISION` → A2 necesita datos → A3 exige `ANALYSIS_CHANGE_CLASSIFICATION_V1`, sin confundir investigación de fuentes con una decisión del propietario y sin fabricar señales de riesgo.

## Hallazgo P0 nuevo y verificable
- Contrato canónico exacto: `sandbox/lf_contract_gate_test/programming_agent_four_stage/wave1_boundary_contracts/analysis_change_classification_contract_v1.json`, **Git blob `0f07d3603c1bf3e4d2a4b9de5d6c3a3968bb4051`**.
- `depth_policy.signals.material_contradiction="BOOLEAN"` (solo `true` o `false`), mientras autoridad, currentness, materialidad, alcance y reversibilidad sí permiten `UNKNOWN`/estados no verificados.
- `steps/a2/validators/run.py` (blob `b22ee1b1129bc22b5f0f81fbd11b5d236ee0064a`) rechaza un `material_contradiction="UNKNOWN"` en `_signals_valid`. **Es incorrecto sustituir lo desconocido por `false` sin evidencia negativa**, aunque ello produzca L2 por otras señales.
- `steps/a1/validators/run.py` mantiene `REQUIRES_DECISION` en ambigüedad material y `next_capability=null`. A2.run rechaza el status distinto de VALID_OUTPUT.
- `steps/a2/adapters/unresolved_research_preview_v1.py` emite tareas dirigidas, `a2_classification=null`, `a3_canonical_inputs=null`, `a3_dispatch_allowed=false`. El preview no resuelve el ciclo por sí mismo.

## Readback de resolutores existentes
- `inventory.fn_lookup_v3(text,text[],integer,text[])`, `lf_ops.fn_screen_contract_v1(text,text,text)` y `private.fn_lf_source_investigation_prepare_v1(text,integer)` EXISTEN. Las funciones son STABLE.
- `private.fn_lf_source_investigation_prepare_v1` realiza descubrimiento y verificación de metadatos **sin autorización para filas de negocio**, `business_data_read_authorized=false`, `runtime_dispatched=false`; debe reutilizarse por su fachada/autorización gobernada, no como bypass.
- Readback directo `SELECT private.fn_lf_source_investigation_prepare_v1('B2B-AUTH-001',12)` devolvió SQLSTATE **42501, permission denied**. Se respetó el límite; no se intentó evadir.
- `private.lf_evidence_resolver_registry_v1` registra activos `LF_SUPABASE_READBACK_V1` y `LF_GITHUB_SOURCE_READBACK_V1`. Esto no prueba acceso operativo desde A2 o A3.
- Router: LF ENABLED; SALY RECOGNIZED_NOT_ENABLED. SALY fuera de esta skill.

## Decisión de diseño acotada
1. **A1 no cambia de estado** por preparar investigación. Se conservan literal, ambigüedad material, negocio y negaciones.
2. **A2-P no acepta cast implícito** de señales sin prueba. Si `material_contradiction` no tiene lectura negativa o positiva vinculada a fuente y alcance, marcar `A2_P_TYPED_CONTRADICTION_EVIDENCE_MISSING`; no emitir clasificación canónica inventada.
3. Resolver primero la evidencia faltante **por el mecanismo de fuente/resolver ya gobernado**, con autoridad del perfil y permisos de ejecución apropiados. La vía metadata-only no declara READY ni accede a filas sin fachada.
4. Con nueve señales tipadas y trazables, A2-P puede **proyectar** una clasificación de investigación usando la misma política `_depth` de A2; NO crear un segundo clasificador. A1 sigue `REQUIRES_DECISION`; output A2-P es una **ficha de investigación**, no sustituto de A2-F.
5. Solo una **revisión técnica y semántica independiente**, contrato fuente CURRENT, juez y RUN pueden autorizar cualquier gate específico de *investigación* para A3. El contrato A3 se mantiene exactamente con `REQUEST_CONTEXT_V1` + `ANALYSIS_CHANGE_CLASSIFICATION_V1`. `a3_allowed=false` en todos los previews actuales.
6. A3 comprueba fuente, autoridad, implementación, vigencia y brechas. A2-F reconcilia señales/resultados; si la duda no se resuelve con fuentes, el propietario decide. Nunca declarar L1, NO_CHANGE ni READY por una hipótesis.

## Alternativas descartadas
- Hacer pasar `REQUIRES_DECISION` por `VALID_OUTPUT`: elude una barrera material.
- Completar `material_contradiction=false` solo para satisfacer el esquema: falso negativo de seguridad.
- Cambiar el contrato canónico para aceptar UNKNOWN sin decisión gobernada: ampliación de alcance.
- Invocar D4 desde A1, agregar un tercer input A3 o crear motor paralelo: contradice diseño aprobado.
- Ejecutar preparación privada con otro rol para vencer 42501: prohibido.

## Regresiones obligatorias
- Señal UNKNOWN como contradicción => bloqueo tipado, jamás cast a `false`.
- Falta de prueba negativa para contradicción `false` => no CURRENT/readiness.
- `material_contradiction=true` acreditada => preservar prioridad L3 aunque existan otros UNKNOWN.
- Cualquier A1 con negación omitida o review alterada => REJECT.
- A1 `REQUIRES_DECISION` no pasa a `VALID_OUTPUT` automáticamente.
- El preview A2-P jamás invoca A3 ni el juez.
- El contrato A3 sigue exactamente con dos inputs.
- La identidad SALY se bloquea en esta skill.
- La fachada de metadatos con 42501 no desencadena estrategia alternativa de escalamiento sin permiso.

## Evidencia / pendiente
La lectura exacta de fuentes y el 42501 están **verificados**; los tests especializados aún no han corrido en checkout de repositorio. Este documento NO es un cambio de política ni admisión de runtime. Revisión independiente, operación gobernada de resolutor, y ejecución Python de regresiones permanecen P0 antes de habilitar A2-P→A3.

**Estado:** `P0_CANONICAL_SIGNAL_EVIDENCE_AND_GOVERNED_RESOLVER_GATE_OPEN`.
