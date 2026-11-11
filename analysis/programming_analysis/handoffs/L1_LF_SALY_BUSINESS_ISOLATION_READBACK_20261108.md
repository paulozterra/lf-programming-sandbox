# L1 — Aislamiento LF/SALY | Readback de fuentes y decisión candidata
**Proyecto:** PROGRAMMING_ANALYSIS_LF · **PR:** #3624 · **HEAD fuente inspeccionada:** cac946c3feb32f0b70a91b283037b46966afad84
**Estado:** DIAGNOSTICADO_SOURCE_ONLY / CORRECCION_RUNTIME_PENDIENTE
**Fecha:** 2026-11-08 (America/Lima). **Efectos:** ninguno; SELECT/readback solamente antes de registrar este documento en rama candidata.

## Alcance vinculante
Aislamiento de negocio A1→A2→A3 sin reescribir Router, contratos oficiales, main, permisos, ejecución ni Supabase. No habilitar SALY como consumidor de PROGRAMMING_ANALYSIS_LF.

## Evidencia directa
1. Router: public.lf_router_business_catalog_v1: LF=ENABLED, SALY=RECOGNIZED_NOT_ENABLED (SELECT vigente a la revisión).
2. Fuentes separadas: LF=lf_ops.reglas (578: 412 VIGENTE / 166 CANDIDATO); SALY=saly.reglas (14: VALIDADO, vigente=true). No equiparar significados de estados.
3. A1: steps/a1/validators/run.py blob 39b46057b5fc82e2c92b95855b76c0332e2b36f3; líneas 122, 152 y 220: exclusivamente LF; rechaza algunos prefijos SALY en source_refs. El reconocimiento por prefijo NO acredita en general procedencia de toda referencia.
4. A2: steps/a2/validators/run.py blob 7c4282fe10f211ef1d33a3e2371209e0f5d02038; líneas 149-182: source-only compara negocio del resultado A1 con señales A2 y hechos.
5. Handoff: adapters/a2_a3_business_handoff_v1.py blob 0bc8d274db2ac849476a4f5d31c68add5f477029; líneas 66-99: rechaza negocio esperado diferente; research_brief.business_boundary=SAME_BUSINESS_UNLESS_GROUNDED_DEPENDENCY. Sin fuente externa atestada.
6. RUN candidato: adapters/native_pending_run_binding_v1.py blob bc9fbda78bf0add02aa034998ce31ac96969827f; valida consistencia de cuatro documentos pero no autentica el host. No hay autorización operational A3.
7. EKB activo: PROGRAMMING-ANALYSIS-STAGE-SOURCE-ATTESTATION-GAP-001, PROGRAMMING-ANALYSIS-A14-EVIDENCE-TIER-FALSE-READY-001, PROGRAMMING-ANALYSIS-CONTEXT-SNAPSHOT-HANDOFF-001.
8. No se halló steps/a3/STEP.md ni steps/a3/validators/run.py en HEAD exacto, y el contrato A3 publicado exige exclusivamente REQUEST_CONTEXT_V1 + ANALYSIS_CHANGE_CLASSIFICATION_V1.

## Evaluación: conservar, corregir, excluir
| Clasificación | Resultado |
|---|---|
| CONSERVAR | Restricción A1 business=LF, igualdad A1/A2, veto expected_business, readback parent/child RUN, dos entradas canónicas A3 |
| CORREGIR EN FUTURO LOTE CONTROLADO | Validar **todas** las refs por procedencia/ámbito con resolver de fuentes y autoridad, no solo prefijos textuales; demostrar binding contra el Router/RUN real y el mapa específico LF; incorporar negativas de referencias disfrazadas y de contaminación por relaciones derivadas |
| NO HACER | Habilitar SALY, asumir que saly.reglas es catálogo LF, crear duplicado de Router, modificar políticas, declarar fuente CURRENT por contenido de payload, abrir A3 a partir de este readback |

## Matriz de pruebas de regresión requerida (casos propuestos, NO ejecutados)
| ID | Entrada | Resultado esperado |
|---|---|---|
| BIZ-01 | A1 LF, señales A2 LF, negocio RUN LF, fuente LF acreditada | Candidato coherente; no habilita A3 por sí solo |
| BIZ-02 | A1 SALY con skill PROGRAMMING_ANALYSIS_LF | Bloqueo; sin reconversión a LF |
| BIZ-03 | A1 LF, señales A2 SALY | A2_BUSINESS_SCOPE_MISMATCH |
| BIZ-04 | A1/A2 LF, negocio esperado del caller SALY | CROSS_BUSINESS_HANDOFF_FORBIDDEN |
| BIZ-05 | A1 LF, business fact TARGET_BUSINESS=SALY | A2_BUSINESS_FACT_CONFLICT |
| BIZ-06 | A1 LF, source_ref de SALY en formato canónico conocido | Rechazo con ref identificada; no lectura cruzada |
| BIZ-07 | A1 LF, source_ref que encubre SALY en otro esquema o alias | Resolver de procedencia detecta otro negocio o marca UNKNOWN y no permite CURRENT |
| BIZ-08 | Dependencia LF→SALY declarada | Solo investigación de dependencia con autoridad y ámbito explícito; prohibida promoción de reglas SALY a LF |
| BIZ-09 | Fuente LF válida pero negocio RUN no atestado | No A3 |
| BIZ-10 | SALY reconocido pero no ENABLED en Router | No admisión operacional mediante esta skill |

## Cierre limitado
**Lote 1 readback:** realizado. **Lote 1 corrección de código, tests exact HEAD y runtime:** pendientes.
**Siguiente:** Lote 2, preservación semántica de instrucciones de alcance, reglas aprobadas, exclusiones y seguridad obligatoria; usar el ejemplo B2B-AUTH-001 como caso adversarial. No cambiar runtime o contrato oficial para satisfacer el test.
