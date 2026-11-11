# Agente de Programación — Implementación de pantallas sobre inventario existente
**Versión:** CANDIDATE_V1 · 2026-11-06 · **Estado:** diseño operativo candidato, NO contrato canónico ni runtime calificado.

## Aclaración de objetivo final y comparación obligatoria (2026-11-06)

El entregable del análisis completo (A9) es un paquete **Spec-Driven** para Programación, construido desde definiciones/reglas **almacenadas y reconciliadas**, no desde un checklist ni desde la petición sin registrar. Comparar dos deltas por componente: **definiciones actuales vs. definición anterior/alcance aprobado** y **definiciones vigentes vs. código existente**. No cambiar una regla que no tiene delta; si esa regla aún no está implementada, emitir solamente el trabajo de programación pendiente. `NO_OP` exige ambos deltas en cero con evidencias CURRENT. Documentación incompleta exige alertas, decisión del dueño y subalcance seguro independiente; aprobación humana no suprime gates obligatorios de seguridad/autoridad. Los contratos canónicos A1–A9 se preservan.

Fuentes candidatas: `SPEC_DRIVEN_DELTA_DOCUMENTACION_GATE_CANDIDATE_20261106.md` y su matriz de 16 casos `SPEC_DRIVEN_DELTA_DECISION_MATRIX_CANDIDATE_20261106.json`. Los resultados de pruebas son de referencia, sin run gobernado real ni autorización de A3/A9.

## Objetivo y decisión de alcance

Implementar una pantalla es producir la funcionalidad comprendida en el alcance aceptado por el usuario, reutilizando toda definición, regla, diseño, decisión, API, estado e implementación existente que sea aplicable, vigente y compatible. No equivale a dibujar la UI, no obliga a empezar de cero y no implica despliegue.

Se deben admitir cuatro modos semánticos sin imponerlos por palabra clave:

1. **CREAR**: el usuario requiere una pantalla nueva. A3 debe acreditar búsqueda acotada de definiciones e implementaciones reutilizables y ausencia pertinente de pantalla existente antes de concluir NEW.
2. **COMPLETAR/IMPLEMENTAR**: el usuario acepta construir la funcionalidad definida, que puede estar completa, parcial o solo documentada; A3 prueba el AS-IS de implementación y entrega el delta pendiente. **Este es el caso por defecto cuando pide «implementar la pantalla» sin indicar reemplazo.**
3. **MODIFICAR**: conservar todo lo existente salvo el delta expresamente solicitado y sus impactos necesarios; no reinterpretar como reescritura.
4. **REESTRUCTURAR/REHACER**: permitir rediseñar/reemplazar componentes hasta el alcance autorizado, conservando trazabilidad de autoridades y políticas vigentes; no confundir reemplazo de implementación con eliminación de reglas.

**Precedencia:** intención y restricciones expresas del usuario > alcance autorizado gobernado > interpretación candidata > investigación. Un alcance ya aceptado no debe volver a preguntarse. La aceptación del alcance no prueba que un artefacto esté en producción ni autoriza modificación de fuente oficial, bypass de políticas o despliegue.

## Repartición exacta de responsabilidades

### A1 — Entender y transportar la solicitud

**Entrada:** solicitud literal, negocio declarado, actor/alcance autorizado (cuando esté disponible de forma gobernada), objetivo, target(s), restricciones, decisiones explícitas y fuentes proporcionadas.

**Proceso:**
- Fijar el modo solicitado como `DECLARED`, nunca determinar «creación desde cero» sin consulta.
- Expresar el resultado funcional esperado en lenguaje natural. «Implementar pantalla» significa el flujo funcional conforme al alcance aceptado, no solamente el mockup.
- Conservar literalmente inclusiones, exclusiones, restricciones y aprobaciones previas en el mismo alcance; marcar su procedencia. No inventar un consentimiento.
- Distinguir **ambigüedad material real** de detalles ya resolubles mediante inventario. No preguntar otra vez qué ha sido autorizado.
- Enumerar targets y negocio exacto; `LF` no debe confundirse con `SALY`.

**Salida canónica inalterada:** `REQUEST_CONTEXT_V1` + **anexo candidato** `IMPLEMENTATION_INTENT_BRIEF` con `mode_requested`, `accepted_scope_ref` (si hay evidencia), `included`, `excluded`, `acceptance_outcome`, `unresolved_owner_decisions`. Ausencia de aprobación `UNKNOWN`, nunca `ACCEPTED` automática.

### A2 — Definir alcance del análisis e inventario obligatorio

**Entrada:** A1, señales tipadas, negocio, target, aceptación de alcance con referencia, contrato canónico de profundidad.

**Proceso:**
- Mantener la clasificación L1/L2/L3 por señales y contrato existentes. No derivar el nivel sólo porque el tema sea «login».
- Identificar el **modo solicitado** (CREAR/COMPLETAR/MODIFICAR/REESTRUCTURAR) y el plan de evidencia para A3, sin decidir todavía `implementation_state`.
- Solicitar inventario integral de familias pertinentes: pantalla/objetivos; campos/elementos; validaciones/acciones; reglas vigentes y candidatas; políticas con parámetro central; estados y transiciones; perfiles/permisos/tenant; rutas/menús; mensajes/errores; analítica/auditoría; variantes/componentes/tokens/assets; API/integraciones; implementación GitHub; tests/CI; despliegues/consumidores; EKB y decisiones/ADR. Un elemento no aplicable exige motivo/evidencia; un vínculo ausente no prueba que no exista.
- Exigir separación `definition_state` vs `implementation_state` vs `verification_state` vs `deployment_state` **por componente**, no sólo por pantalla. No concluir COMPLETO de registro CANDIDATO ni de tests sintéticos.
- Proponer preguntas al usuario sólo para decisiones materiales no resolubles por fuentes, y preguntas de investigación para A3. Proteger decisiones ya aceptadas; eliminar preguntas genéricas reiterativas.
- Los 59 controles Golden son cobertura interna, **no** el documento humano principal ni la cantidad de investigaciones a ejecutar indiscriminadamente.

**Salida:** `ANALYSIS_CHANGE_CLASSIFICATION_V1` **inalterado** + anexo propuesto `SCREEN_INVENTORY_REQUEST_V1` (familias y criterios de prueba), resumen humano y preguntas dirigidas. Gate A2 juez interno PASS antes de A3, como norma, NO implementado operacionalmente.

### A3 — Investigar el inventario y estado real

**Entrada canónica inalterada:** `REQUEST_CONTEXT_V1` + `ANALYSIS_CHANGE_CLASSIFICATION_V1`; anexos tipados de A2 no sustituyen esos dos.

**Proceso:**
1. Identidad exacta del target y fuentes CURRENT, con EKB/decisiones/autoridad, respetando el Router→perfil→skill y resolutores existentes.
2. **Inventariar pertenencia y familias** con consultas ligeras (IDs, estado, versión, source refs); NO recargar todas las 71 reglas completas a la vez.
3. Resolver únicamente contenido material y vinculaciones con fuentes vigentes; marcar reglas candidatas por separado. Recoger las mejoras previas y versiones/decisiones relevantes, evitando duplicarlas o perderlas.
4. Inspeccionar GitHub/servicios/tests/CI/deploy para demostrar implementación real. `DEFINED` o `CANDIDATO` en BD no implica `CODED`, `INTEGRATED`, `TESTED` ni `DEPLOYED`. Si no encuentra evidencia, usar `UNKNOWN_UNVERIFIED`, no `NOT_IMPLEMENTED` por presunción.
5. Construir matriz **por componente**: alcance aceptado, definición canónica/version/ref, estado y autoridad, evidencia de implementación, delta `REUSE_AS_IS|COMPLETE|MODIFY|REBUILD|CREATE|BLOCKED|UNKNOWN`, dependencia, riesgo y siguiente dueño. No determinar arquitectura HOW (PG-03).
6. Distinguir inventario completo de **familias y vínculos pertinentes** vs lectura profunda dirigida: evita tanto omisiones como búsqueda indiscriminada. Resolver contradicciones, exigir evidencia negativa acotada antes de marcar NEW.
7. Producir brechas tipadas, `authority_state` e `implementation_state` independientes, y suficiencia `SUFFICIENT|NEED_MORE_EVIDENCE|REQUIRES_DECISION|BLOCKED`, conforme al contrato canónico `TARGETED_EVIDENCE_SET_V1`.

**Salida:** `TARGETED_EVIDENCE_SET_V1` y anexos de inventario/materialidad a A4–A9. A3 NO entrega programa ni decide cambios no autorizados. A9 produce el expediente para implementar con AS-IS, DELTA y trazabilidad por componente.

## Caso comprobado en Supabase — B2B-AUTH-001 (snapshot 2026-11-06, lectura únicamente)

- Pantalla `id=51`, `B2B-AUTH-001`, nombre `Iniciar sesión`, módulo `B2B_AUTENTICACION`, `v0.5`, `estado=CANDIDATO`, objetivo: autenticar usuario B2B y habilitar acceso según perfil, empresa y seguridad.
- Inventario vinculado: 71 reglas (38 VIGENTE, 33 CANDIDATO), 13 vínculos de políticas (candidatos; NO confundir con estado de políticas subyacentes), 17 elementos UI, 2 campos, 3 estados, 3 variantes, 6 perfiles, 6 errores, 5 eventos analytics, 8 screenshots candidatos y 1 ruta candidata. **0** mensajes vinculados de forma directa y **0** permisos vinculados de forma directa: esto **NO prueba ausencia total** de fuentes indirectas.
- Políticas subyacentes verificadas por ID: `RATE-B2B-LOGIN` VIGENTE (5 solicitudes/900 s, scope IP_USER), `SESSION-B2B-DEFAULT` VIGENTE (inactividad 900 s, absoluto 28800 s, concurrencia 3), `TIMEOUT-B2B-AUTH-LOGIN` VIGENTE (15 s, retry 0), `SEC-B2B-MFA` VIGENTE. `SEC-B2B-MFA-FACTOR-ELIGIBILITY` sigue CANDIDATO.
- Evidencia de antecedentes GitHub en main: `supabase/migrations/20260928221654_lf_b2b_auth_api_contract_v1.sql` indica **contrato técnico, no ruta runtime física**; `supabase/migrations/20260928212155_lf_b2b_auth_routing_transitions_authority_v1.sql` indica **story-definition only** y rutas/transiciones candidatas. No inferir que exista pantalla implementada, test E2E o deploy.
- Antes de estimar completitud/DELTA, A3 deberá acreditar código real, integraciones, currentness y recepciones. Inventario de 71 reglas es solo su pertenencia; su aplicabilidad final se determina con el target y el alcance aceptado, no por su cantidad.

## Gates mínimos de calidad

| Gate | Debe probar | Falla si |
|---|---|---|
| G1_INTENT | Negocio, objetivo, modo y alcance/autoridad sin inferencia de consentimiento | Confunde LF/SALY, repregunta alcance aceptado o inventa aprobación |
| G2_INVENTORY | Cobertura y vínculos de todas las familias materiales pertinentes con source/status | Omitió reglas, visuales, permisos, estados, rutas, API o tests sin motivo |
| G3_TIER_SEPARATION | Definición, implementación, verificación y despliegue independientes | Cuenta una definición como software funcionando |
| G4_DELTA | `REUSE/COMPLETE/MODIFY/REBUILD/CREATE` por componente y alcance autorizado | Recrea componente reutilizable sin explicación o altera fuera de alcance |
| G5_CURRENTNESS | Fuente/version/hash/fecha/scope y EKB reconciliados | Usa fuente vieja o dato candidato como vigente |
| G6_SEMANTIC | Juez independiente revisa intención, brechas y no pérdida antes de A3 | PASS simulado o emitido por A2 mismo |
| G7_HANDOFF | Identidad, 2 contratos canónicos, recibos y RUN sin drift | Enruta directamente a A3 sin gate nativo |

## Secuencia y límites

```
Usuario acepta alcance
  → Router → Perfil → PROGRAMMING_ANALYSIS_LF
  → A1 (qué quiere + alcance aceptado)
  → A2 (modo + profundidad + solicitud de inventario)
  → Juez A2 [bloquea si FAIL]
  → A3 (inventario de definiciones + evidencia real de código + AS-IS)
  → A4–A9 (impacto → requisitos/delta → paquete para programar)
```

**Estado de implementación de este documento:** PROPUESTA versionada en rama candidata; no se ha cambiado `A1`, `A2`, `A3` runtime, contratos oficiales, RPC, Router, Supabase ni producción. A3 sigue sin módulo ejecutable declarado y `EJECUCION_SKILL_LF` no está admitido. La ejecución del siguiente lote debe convertir esta propuesta en contratos anexos y pruebas adversariales, no en otra infraestructura genérica.
