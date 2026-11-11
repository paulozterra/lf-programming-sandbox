# Agente de Análisis — Perfil candidato A1–A9

**Estado:** `CANDIDATE_NOT_RELEASED / SOURCE_ONLY / OPERATIONAL_QUALIFICATION_BLOCKED`.

## Alcance

La infraestructura existente de `ProfileRuntimeEngine`, `RepositoryBindings`, `OutputGates`, `EJECUCION_PERFIL_LF` y `LlamaHTTPClient` procesa perfiles gobernados. Este lote añade **un perfil candidato** (no un segundo runtime ni un ejecutor paralelo) que propone material de Análisis A1–A9, con validación estructural independiente de las afirmaciones del LLM.

El candidato **NO** queda registrado como capacidad `CURRENT RELEASED` en Supabase, no participa todavía del Router y no ejecuta PG-01. Ningún archivo habilita producción ni programación de producto.

## Archivos

- `SKILL.md` — método model-facing A1–A9 basado en los contratos existentes, preservando autoridad y desconocidos.
- `contracts/runtime_binding.json` — usa los hooks del runtime existente; requiere el SKILL y el manifiesto de fuente como entradas canónicas.
- `contracts/analysis_source_binding.json` — relación exacta con contratos A1–A9, procedimiento en PR #2145; `current_release_verified=false`.
- `schemas/runtime_output.schema.json` — modelo solo entrega `ANALYSIS_IMPLEMENTATION_PACKAGE_V1` **candidate_only**; no huellas/recibos de proveedor autogenerados.
- `validators/runtime_validate.py` — fail-closed para faltantes, L1 con UNKNOWN, falsos READY, decisiones, material fronts, matrix bidireccional y research STOP.
- `validators/runtime_semantic_utility.py` — utilidad determinista acotada; **no es** el juez semántico independiente.
- `evals/test_runtime_candidate_v1.py` — 15 controles, positivos y negativos.

## Hallazgo de frontera compartida

Antes de este macrolote, `RepositoryBindings.profile_model_sources` **ignoraba** el `required_source_refs[]` declarado en `runtime_binding.json`. Un perfil podía ejecutarse con un subconjunto de sus fuentes obligatorias. La corrección genérica de `services/profile_runtime_api/profile_runtime_api/repository.py` exige fuentes requeridas y respeta `allow_additional_sources`; no se limita a este perfil.

Control de compatibilidad existente: `systemic_root_cause_repair_lf` (source SKILL vigente, model projection) sigue funcionando tras el cambio. Las pruebas se definieron como `services/profile_runtime_api/tests/test_runtime_required_profile_sources_v1.py`.

## Comprobaciones de fuente exacta en scalora-vps

Todos los archivos se trajeron de la rama Git, se montaron en directorio temporal y se ejecutaron con `/opt/lf-profile-runtime-api/venv/bin/python`. **Nada fue copiado sobre el runtime vivo ni desplegado**.

| Control | Resultado |
|---|---|
| Contrato y matriz del perfil candidato | 15/15 PASS (incluye positivos y negativos) |
| Hook real `RepositoryBindings` + `OutputGates` | PASS: salida BLOCKED y READY_CANDIDATE estructural, ambas `downstream_authorized=false`, juez `NOT_EXECUTED` |
| 5 entradas inválidas por el hook real | 5/5 FAIL correctamente, `utility=NOT_EVALUATED` |
| Reglas genéricas de required/additional source refs | 8/8 PASS |
| Manifest obligatorio A1–A9 omitido | `PROFILE_RUNTIME_REQUIRED_SOURCE_MISSING` (correctamente bloqueado) |
| Manifest + SKILL provistos | PASS, 2 fuentes |
| Compatibilidad SRCR existente | PASS, fuente 1, proyección 4905 caracteres |

Una prueba independiente del modelo local previa a esta fuente devolvió un falso READY ante información material ausente. Este perfil candidato **no ha superado evaluación semántica sobre ejecuciones reales**, por lo que el hallazgo **no** se considera remediado por la existencia de tests estructurales.

## Bloqueadores de admisión

1. Resolver y aprobar como CURRENT RELEASED el contrato A1–A9 de PR #2145; revalidar currentness/contratos de A1–A9 y sus ref.
2. Reconciliar PR #2071 (evidence tier A14 + snapshot A9) antes del gate final; sus cambios aún no están en main.
3. Registrar/seleccionar el perfil por Router → `EJECUCION_PERFIL_LF`, con autoridad, evaluación aislada y recepción exacta. **No permitir llamada directa que ignore Router**.
4. Ejecutar solicitudes frescas a través del perfil real y obtener recibos de modelo/proveedor desde transporte; comprobar discovery con oráculo externo, no basado en etiquetas del candidato.
5. Integrar el único juez semántico independiente gobernado; exigir 0 omisiones críticas, 0 falsos READY críticos, >=95% clasificación y >=95% paquetes utilizables sin reinterpretación.
6. Handoff físico A9 → `DECISION_CONTEXT_ASOF@CURRENT` → PG-01, con readback, digests, currentness y negativos sin alterar producto.
7. Solo con pruebas operativas independientes, pedir `ANALYSIS_V1_OPERATIONALLY_QUALIFIED`; **no inferir 100% del ledger 15/15 DONE ni de esta PR**.

**Invariantes:** EKB preflight; no untrusted source as authority; REUSE_OR_TRANSVERSALIZE_BEFORE_BUILD; NO_PARALLEL_ENGINE; no merges, migrations, product writes or runtime/prod activation.

## Macrolote 2026-10-12 — pinning Git A1–A9

- EKB consultado: `PROGRAMMING-ANALYSIS-STAGE-SOURCE-ATTESTATION-GAP-001` (ACTIVO). PR #2071, #2145 y #2214 permanecen Draft sin merge.
- Git `main` observado: `e1c238f48a9fc17c2870243eb2b0b6d14d4bf26b`. Los nueve contratos A1–A9 existen y sus Git blob SHA coinciden **9/9** entre `main`, el manifiesto candidato y la rama del PR #2214. Un pin A9 deliberadamente alterado no coincide (negativo de comparación, no prueba del runtime).
- `contracts/analysis_source_binding.json` ahora registra las nueve huellas exactas por etapa y `GIT_BLOB_EXISTENCE_ONLY`. No equivale a CURRENT RELEASED, receipt de autoridad, lectura del modelo ni consumo PG-01.
- Frontera defectuosa confirmada: `RepositoryBindings.profile_sources` admite únicamente archivos dentro del perfil; `profile_model_sources` exige SKILL + manifiesto, pero no resuelve ni atestigua los nueve contratos externos. No ampliar silenciosamente ese límite ni convertir el manifiesto en autoridad.
- Perfil Reparador encontrado en `profiles/systemic_root_cause_repair_lf`, método `SRCR_V0_7R1`; su manifiesto declara `CANDIDATO / READ_ONLY / NO_HABILITADO`. Se aplicó su método de análisis de primera frontera y reutilización, **no** se invocó un runtime Reparador.
- Alternativa elegible: adaptar el Router/fuentes gobernadas existentes para entregar recibos tipados de los nueve contratos y validarlos antes de inferencia. No crear motor, no hacer auto-READY ni insertar referencias sin currentness. Reconciliar por separado los 3 blobs A14/A9 distintos en PR #2071 y sus negativos antes de admisión.
- **Cursor persistido:** SOURCE_BLOBS_9_OF_9_READBACK; siguiente `NEXT_SAFE_BATCH=ROUTER_AUTHORITY_SOURCE_RECEIPTS_A1_A9`. Evidencia operativa independiente: `0/3` (ejecutor real, juez independiente, PG-01 persistido). `ANALYSIS_READY=false`. Sin merge, despliegue ni SQL.

### Router transport readback 2026-10-12

Existing `ProfileTask.lf_adapter_sources` and `RouterAdapterSource` support Router-bound typed adapter context (maximum 4 adapters), with `lf-governed-context-receipt/v2`. Supabase `CURRENTNESS_AUTHORITY@1.0.0` exists, but `v_lf_router_adapter_bindings` has 0 rows for `PERFIL-PROGRAMMING-ANALYSIS-LF`. Use one bounded A1-A9 aggregate authority receipt; no nine adapters, no runtime activation. NEXT_SAFE_BATCH=AGGREGATE_RECEIPT_CONTRACT_AND_FAILCLOSED_TESTS. Operational proofs 0/3.
