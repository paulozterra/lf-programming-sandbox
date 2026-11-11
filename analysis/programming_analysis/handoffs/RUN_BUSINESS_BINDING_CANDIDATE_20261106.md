# A2 Golden | RUN → negocio → A3 — contrato candidato de lectura (2026-11-06)

**Alcance:** exclusivamente `PROGRAMMING_ANALYSIS_LF` dentro de `EJECUCION_SKILL_LF` y su perfil invocador. Ninguna modificación a Router, Main, Supabase, EKB, grants, catálogo o juez. **No es un procedimiento de admisión ni prueba operativa.**

## Autoridades reales consultadas (solo lectura)

- `public.lf_operation_execution` RUN de perfil `EJECUCION_PERFIL_LF`: `execution_id`, `target_code`, `status`, `request_sha256`, `manifest.business`, `manifest.router_profile_handoff.business`, `manifest.router_profile_handoff.router_authorization_receipt`.
- Recibo interno existente `LF_ROUTER_PROFILE_AUTHORIZATION_RECEIPT_V1`: `router=ACT-0001`, `business`, `profile_code`, `request_sha256`, `operation_code`, `fingerprint_sha256`, `gate2_semantic_receipt_sha256`, `operation_revision_sha256`, `router_source_md5`. Estas huellas **no son una firma criptográfica**; no sustituyen el readback autorizado.
- `public.lf_skill_invocation_v1`: `skill_run_id`, `skill_code`, `parent_execution_id`, `profile_code`, `input_sha256`, `evidence_ref`, `child_execution_id`, `status`.
- `public.lf_operation_execution` RUN hijo `EJECUCION_SKILL_LF`: identidad, `request_sha256`, `created_by_execution_id` y `manifest.profile_handoff.{source_execution_id,skill_run_id}`.
- EKB `PROGRAMMING-ANALYSIS-STAGE-SOURCE-ATTESTATION-GAP-001` y `PROGRAMMING-ANALYSIS-A14-EVIDENCE-TIER-FALSE-READY-001`: no declarar CURRENT, juez o RUN sin recibos.
- `public.lf_skill_invoke_v1` consultado en Supabase: solo crea RUN hijo de skill en la rama `effect='WRITE_GOVERNED'`; para otros efectos la invocación puede terminar sin RUN hijo. Por tanto, **no se puede inferir un RUN hijo para PROGRAMMING_ANALYSIS_LF**.
- `public.lf_profile_native_bridge_begin_v1` está RETIRADO, devuelve `DUPLICATE_NATIVE_BRIDGE_ENTRY_RETIRED`. No usarlo como transportador.

## Contrato de enlace candidato (no admisión)

`adapters/run_business_binding_v1.py::reconcile(parent,invocation,child,actor_parent_execution_id)` comprueba:

1. RUN de perfil activo y mismo `execution_id` del actor autorizado.
2. `manifest.business` obligatorio; misma identidad en handoff Router y recibo; misma referencia de perfil.
3. `request_sha256` coincidente en RUN, handoff, recibo y RUN hijo; huellas de recibo con formato válido.
4. Skill exacta `PROGRAMMING_ANALYSIS_LF`, invocación que pertenece al perfil y `skill_run_id` consistente.
5. RUN hijo existente y exacto de `EJECUCION_SKILL_LF`, enlazado al mismo padre y misma invocación.
6. Cualquier ausencia o contradicción ⇒ `BLOCKED`, sin fallback ni deducción a partir del nombre de la pantalla.

**Incluso cuando todo coincide:** `status=CANDIDATE_CONSISTENT`, `readback_authenticated=false`, `a3_allowed=false`. Solo demuestra consistencia de los datos proporcionados, no que se consultaron desde un host de confianza.

El puente `a1_a2_candidate_bridge_v1.py` acepta opcionalmente `run_readback` y `actor_parent_execution_id`, pero `expected_business` del consumidor es **solo veto**, nunca autoridad. No permite A3 ni altera el contrato canónico de clasificación.

## Consulta ilustrativa para el ejecutor gobernado (SELECT; no ejecutada por este contrato)

Los parámetros `$1` y `$2` son **identidades obtenidas del contexto autorizado**, nunca valores elegidos para acceder a RUN ajenos.

```sql
SELECT
  jsonb_build_object(
    'execution_id', p.execution_id, 'operation_code', p.operation_code,
    'status', p.status, 'target_code', p.target_code,
    'request_sha256', p.request_sha256,
    'manifest', jsonb_build_object(
       'business', p.manifest->'business',
       'router_profile_handoff', p.manifest->'router_profile_handoff')
  ) AS parent_run,
  jsonb_build_object(
    'skill_run_id', i.skill_run_id, 'skill_code', i.skill_code,
    'parent_execution_id', i.parent_execution_id,
    'profile_code', i.profile_code, 'status', i.status,
    'input_sha256', i.input_sha256, 'evidence_ref', i.evidence_ref,
    'child_execution_id', i.child_execution_id
  ) AS skill_invocation,
  jsonb_build_object(
    'execution_id', c.execution_id, 'operation_code', c.operation_code,
    'status', c.status, 'target_code', c.target_code,
    'created_by_execution_id', c.created_by_execution_id,
    'request_sha256', c.request_sha256,
    'manifest', jsonb_build_object('profile_handoff', c.manifest->'profile_handoff')
  ) AS child_run
FROM public.lf_operation_execution p
JOIN public.lf_skill_invocation_v1 i ON i.parent_execution_id = p.execution_id
JOIN public.lf_operation_execution c ON c.execution_id = i.child_execution_id
WHERE p.execution_id = $1 AND i.skill_run_id = $2
  AND p.operation_code = 'EJECUCION_PERFIL_LF'
  AND p.status = 'IN_PROGRESS'
  AND i.skill_code = 'PROGRAMMING_ANALYSIS_LF'
  AND c.operation_code = 'EJECUCION_SKILL_LF'
  AND c.target_code = 'PROGRAMMING_ANALYSIS_LF';
```

## Readback real de Supabase (2026-11-06)

- Operaciones históricas de perfil: 53; `manifest.business` ausente en 34; `router_profile_handoff.business` ausente en 33; conflictos simultáneos observados: 0. La población histórica incluye completadas/canceladas; **no se concluye que 34 RUN activos estén inválidos**.
- Hay por lo menos un RUN de perfil `IN_PROGRESS` con negocio ausente en raíz y LF en handoff. Debe bloquearse hasta reconciliación canónica, sin mutar el histórico por este lote.
- `PROGRAMMING_ANALYSIS_LF`: 0 invocaciones, 0 RUN de `EJECUCION_SKILL_LF` y 0 filas en catálogo READY. No hay cadena real para acreditar.
- Fuentes de las funciones consultadas: `lf_skill_invoke_v1` MD5 `289ef129239ba1a4cbb33314f4484f4b`; `lf_profile_native_bridge_begin_v1` MD5 `6b0c52f209d58fba01bddbba7ed88ada`. MD5 aquí es huella de readback del cuerpo SQL, **no autorización**.

## Requisitos de runtime pendientes — BLOQUEANTES

1. El **host autorizado**, no el consumidor, deriva el RUN padre del actor y lee bajo ACL la invocación y RUN hijo. Protege contra RUN ajeno, suplantación y datos autodeclarados.
2. Calificar qué ruta vigente abre `EJECUCION_SKILL_LF` para una skill de solo lectura; no modificar `lf_skill_invoke_v1` ni usar `WRITE_GOVERNED` para forzar la creación.
3. Exigir recibo de `readback` real, evento y revisión nativa del juez vinculados por el mismo RUN/HEAD/sha256; nunca aceptar `readback_authenticated=true` desde el modelo.
4. Solo después del PASS real del juez, permitir handoff A2→A3 con nombre de negocio y ficha de investigación. Mantener límite 3 intentos y reporte terminal al perfil.
5. Resolver admisión por proceso aprobado; hasta entonces `PROGRAMMING_ANALYSIS_LF` sigue `CANDIDATE_READ_ONLY`.

**Seguridad:** análisis y pruebas sobre repositorios propios autorizados, sin bypass de seguridad OpenAI ni ZIP; usar rutas nativas y fuentes en Main cuando estén vigentes. No se declara ingreso, ejecución de modelo, avance A3 ni cierre de ticket.
