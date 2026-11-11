# Corrección de arquitectura — Análisis como una única skill

**Fecha:** 2026-11-04 · **PR:** #3529 · **Alcance:** reestructuración source-only.

## Decisión

`PROGRAMMING_ANALYSIS_LF` es el **único candidato registrable como SKILL** para toda la etapa de Análisis del Agente de Programación. Sus **15 unidades A1–A15** son pasos internos, no quince habilidades ni perfiles. A1 conserva sus validadores como módulo `steps/a1/`.

- **Antes:** `skills/programming_analysis_a1/SKILL.md`, contrato con `skill_code=PROGRAMMING_ANALYSIS_A1` (incorrecto para la arquitectura final).
- **Después:** `skills/programming_analysis/SKILL.md`, `contracts/analysis_skill_manifest_v1.json`; A1 en `steps/a1/STEP.md` (sin `SKILL.md`).
- **Código nuevo propuesto:** `PROGRAMMING_ANALYSIS_LF`. Validar contra el catálogo oficial antes de registrar; todavía **no** está dado de alta en `lf_activos`.
- El sobre de A1 expone `skill_code=PROGRAMMING_ANALYSIS_LF` y `step_code=A1`. No publica un resultado de skill independiente.
- Las referencias documentales y los contratos anteriores de A1 son **históricos internos**. No se interpretan como habilitación ni como ejecuciones separadas.

## Fuente y secuencia

- A1–A9: reutilizar sin copiar `sandbox/lf_contract_gate_test/programming_agent_four_stage/wave1_boundary_contracts/analysis_procedure_v1.json` y contratos de sus nueve etapas.
- A10–A15: conservar sus referencias canónicas de validación histórica, adversarial, benchmark, remediación, holdout y freeze. Su estatus dentro del paquete es `HISTORICAL_QUALIFICATION_REFERENCE_UNWIRED`.
- Externo: Perfil → una llamada a `PROGRAMMING_ANALYSIS_LF` → `ANALYSIS_IMPLEMENTATION_PACKAGE_V1` + `PROGRAMMING_CONTEXT_SNAPSHOT_V1` → Perfil.
- Interno: A1 → A2 → … → A9 para análisis de un caso; A10–A15 son gates de calificación/reparación/freeze, **no** efectos automáticos ejecutados cada vez.
- **Separación de numeraciones:** `EJECUCION_SKILL_LF` tiene nueve pasos operativos de control (`init_execution`, `router`, `skill_resolve`, …, `report_output`), distintos de las quince unidades funcionales A1–A15 del paquete.

## Integridad de lo migrado

Los 28 archivos del paquete candidato A1 fueron trasladados a `skills/programming_analysis/steps/a1/`; el anterior `SKILL.md` pasó a `STEP.md`. Se corrigieron rutas, identidad de sobre y cálculo del ROOT del validador Python tras la reubicación.

Se agregaron pruebas estructurales en `skills/programming_analysis/evals/test_analysis_package_v1.py`: secuencia 15/15, fuente de A1–A9, referencias canónicas, ausencia de skill anidada, identidad y bloqueo de claims operativos. **No se ha ejecutado en este lote una suite Python completa contra el HEAD corregido**; el antiguo 69/69 pertenece al paquete de antes de la reestructuración.

## Gates sin ejecutar

1. Validador de paquete + suite Python 100% en HEAD final y CI de esos tests.
2. Implementar/conectar A2–A15 dentro de la skill y demostrar ejecución real de flujos internos, sin implementar motor paralelo.
3. Modelo productor real de A1 y juez independiente con recibos verificables.
4. Alta de **una** skill `PROGRAMMING_ANALYSIS_LF` por autoridad canónica; **nunca** dar de alta `PROGRAMMING_ANALYSIS_A1`.
5. Consumidor de `EJECUCION_SKILL_LF` y registrador scoped; escritura solo desde ejecutor con OIDC/Edge y autoridad de servidor. Ninguna función de `CREACION_SKILL_LF` se usa para registrar pasos internos.
6. Pruebas negativas, persistencia y readback del mismo RUN; autorización independiente para cualquier promoción, merge, despliegue o cambio DB.

## Restricciones

No se alteran Router ACT-0001, Supabase, políticas, perfiles oficiales ni los 15 cierres históricos del plan. No reutilizar A1Q DONE como evidencia operativa de una nueva ejecución. La skill está **empaquetada a nivel de contrato**, no lista ni integrada.
