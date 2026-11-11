# A1–A9 · Gate de documentación almacenada → delta real → paquete Spec-Driven
**Estado:** PROPUESTA CANDIDATA; sin runtime, sin nuevo motor, sin cambios a contratos canónicos; 2026-11-06.

## Objetivo vinculante

La skill `PROGRAMMING_ANALYSIS_LF` produce, tras completar A1–A9, un paquete **Spec-Driven** que el agente de Programación puede consumir para decidir el CÓMO y construir sin reinterpretar el QUÉ. No es un checklist ni una orden de modificar definiciones. Su base son **especificaciones y reglas almacenadas**, sus mejoras históricas, sus estados de autoridad/currentness y la implementación real.

**Precondición:** la definición solicitada debe existir en fuente canónica almacenada y reconciliada. Si el usuario aporta una decisión nueva no registrada, enviarla por Input Governance/operación gobernada antes de considerarla autoritativa; no convertir el texto del chat en regla CURRENT. Registrar propuesta/cambio y esperar el receipt necesario. Esto **no** implica que una pantalla de nueva creación deba tener código previo: es posible crearla a partir de especificaciones nuevas ya almacenadas.

## Principio de cambio mínimo

- **Reglas/definiciones:** si no existe delta nuevo autorizado, `DEFINITION_ACTION=REUSE_AS_IS`; prohibido editar reglas, versiones, diseño, políticas o decisiones sólo porque se pide implementar. El usuario puede aceptar ejecutar bajo el alcance ya definido sin autorizar un cambio de políticas.
- **Implementación:** contrastar `definition_fingerprint` actual vs `implementation_baseline` por componente. Si la definición existe pero el código falta o no cumple, el delta de **programación** sigue siendo válido aunque no hayan reglas nuevas.
- **NO_OP** únicamente cuando `definition_delta=NONE` **y** `implementation_delta=NONE`, ambos probados con fuente CURRENT + hashes/readback + alcance; si implementación desconocida, `UNKNOWN` ≠ `NONE`.
- Las decisiones previas del propietario sobre alcance aplican si están atestadas y vinculadas al mismo target/versión; no solicitar microaprobación repetida.

## Estados de salida (anexo candidato, no introducir estados nuevos en tablas)

| Estado | Condición verificable | Efecto |
|---|---|---|
| `NO_OP_VERIFIED` | Documentación vigente, sin cambio de definición y sin pendiente de código comprobado | No emitir tareas de modificación; cerrar con evidencia |
| `SPEC_DRIVEN_READY_CANDIDATE` | Todas las obligaciones materiales de **ese alcance** definidas y actuales; delta real, sin bloqueos | A9 prepara paquete Spec-Driven para gobernanza/admisión posterior; NO ejecutar código |
| `SPEC_PARTIAL_OWNER_DECISION` | Documentación material faltante, pero existe un subalcance independiente y seguro para programar; alertas explícitas y decisión pendiente | No emitir como READY hasta decisión registrada y revalidación del subalcance |
| `SPEC_PARTIAL_SCOPE_APPROVED_CANDIDATE` | Propietario aceptó **alcance reducido exacto**, recibo vigente; bloqueos materiales excluidos y dependencias revisadas | A9 puede preparar **solamente el subalcance READY**, con alertas y exclusiones completas |
| `BLOCKED_MISSING_DEFINITION` | No existe fuente almacenada/versión/currentness para obligación requerida; no hay subalcance autónomo | Bloquear la preparación ejecutable, alertar y encaminamiento gobernado |
| `BLOCKED_UNKNOWN_IMPLEMENTATION` | No hay evidencias suficientes para distinguir trabajo pendiente de NO-OP, o delta/impacto incierto | Resolver AS-IS en A3; nunca concluir no-op por falta de datos |
| `BLOCKED_UNWAIVABLE_GATE` | Falta validación obligatoria de autoridad/seguridad/privacidad/permiso/efectos o hay contradicción material | Ni aceptación del usuario permite saltar controles o declarar READY |

**Importante:** son estados del **gate candidato**, no valores instalados de `ANALYSIS_IMPLEMENTATION_PACKAGE_V1`. Los estados reales de A9 (`READY`, `PARTIAL_READY`, etc.) mantienen sus reglas canónicas.

## A1 → A2 → A3 → A9, sin atribuciones cruzadas

**A1 — qué se aceptó.** Identidad del negocio, target, modo CREAR/COMPLETAR/MODIFICAR/REESTRUCTURAR, resultados esperados, inclusiones/exclusiones, aceptaciones y referencias exactas. `UNKNOWN` si no existe recibo, nunca consentimiento supuesto. No interpreta ausencia de definiciones como permiso de crear.

**A2 — qué hay que comparar.** Clasifica profundidad por predicados canónicos L1/L2/L3, identifica dominios del inventario y preguntas de investigación. Entrega tarea A3 para reconciliar versiones, cambios normativos/funcionales, historia de mejoras y componentes faltantes. No modifica reglas. La existencia de 59 controles Golden no implica 59 cambios.

**A3 — evidencia de qué existe y cambió.** Resuelve inventario de fuente canónica (pantalla, reglas, políticas, campos, estados, errores, rutas, API, diseño, tokens, permisos, pruebas, EKB, decisiones) y de fuente de implementación (código GitHub, pruebas CI, integraciones/despliegue si aplica). Para cada componente acredita: `definition_ref/version/hash/currentness`, `prior_version/hash`, `definition_delta`, `implementation_ref/hash/status`, `implementation_delta`, `authority_state`, blockers, decisión y refs históricas. Escanea vínculos completos y profundiza sólo en los relevantes. Si faltan docs materialmente, emite alerta con scope, fuente faltante, severidad y efecto.

**A4–A8 — impacto, riesgo, obligatoriedad, decisiones y STOP.** Prohíben descartar requerimientos materiales sin justificación. `STOP` de investigación no equivale a READY. Priorizan reutilización e identifican subalcances autónomos.

**A9 — ensamblado Spec-Driven.** Debe conservar `ANALYSIS_IMPLEMENTATION_PACKAGE_V1` y `PROGRAMMING_CONTEXT_SNAPSHOT_V1` canónicos más un anexo legible para programación; nunca sustituirlos por resumen. Señala explícitamente `NO_OP` si el delta está acreditado como cero. No elegirá stack, endpoints, algoritmos ni patrones técnicos (eso corresponde a Programación/PG-03).

## Contenido mínimo del Spec-Driven entregable por A9

1. **Mandato:** negocio, objetivo funcional, modo de trabajo, alcance aprobado y límites (recibos).
2. **Inventario CURRENT:** fuente/version/hash y autoridad de cada regla, política, definición, visual, API, estado, error y dependencia pertinente; mejoras/versiones anteriores relevantes.
3. **AS-IS:** qué está realmente implementado, probado y desplegado, cada uno con evidencia independiente.
4. **DELTA:** tabla por componente `KEEP|ADD|UPDATE|REBUILD|DELETE_WITH_EXPLICIT_AUTHORITY`; WHAT, WHY, origen del cambio, entradas/salidas, estados, errores, permisos, efectos, dependencias y contrato/versión.
5. **Pruebas de aceptación:** qué resultado observable confirma cada requisito, casos negativos y de regresión; cuando aplique, seguridad, accesibilidad, responsive y rendimiento.
6. **Alertas y exclusiones:** faltantes, riesgos, impacto, dueño, decisión registrada, parte afectada, condiciones de bloqueo o reducción segura del alcance.
7. **Gate:** `NO_OP_VERIFIED|SPEC_READY_CANDIDATE|PARTIAL_OWNER_DECISION|PARTIAL_SCOPE_APPROVED_CANDIDATE|BLOCKED`, receipts y fingerprint del paquete para Programación.

## Algoritmo de decisión (especificación, no runtime)

```
A1 identifica solicitud y alcance con refs
A2 propone investigación proporcional
A3 localiza fuente almacenada y reconcilia versión CURRENT
   si definición obligatoria no almacenada:
      ALERTA + bloqueo del alcance afectado + ruta gobernada para registrar decisión
   si existe definición:
      comparar versiones (delta de definición)
      comparar código/pruebas (delta de implementación)
   si faltan evidencias para clasificar delta: BLOCKED_UNKNOWN_IMPLEMENTATION
A4–A8 comprueban impactos, dependencias, necesidades materiales y STOP
   si no hay delta en definiciones NI implementación y ambos están verificados:
      NO_OP_VERIFIED (sin reescrituras ni tareas inventadas)
   si existen deltas sin bloqueos:
      A9 emite SPEC_DRIVEN_READY_CANDIDATE
   si hay gaps:
      emitir alertas y definir un posible subalcance independiente
      sin recibo de aceptación: SPEC_PARTIAL_OWNER_DECISION, no ejecutar
      con recibo, verificar que las obligaciones excluidas no bloqueen lo incluido
      si pasa: SPEC_PARTIAL_SCOPE_APPROVED_CANDIDATE
      si seguridad/autoridad/efecto obligatorio falta: BLOCKED_UNWAIVABLE_GATE
```

## Casos de prueba obligatorios

1. Mismas reglas vigentes + código íntegro acreditado + sin requerimiento nuevo → NO_OP.
2. Mismas reglas vigentes + pantalla no implementada demostrada → Spec-Driven para construir código; **cero cambios en reglas**.
3. Nueva definición almacenada y aprobada + código antiguo → Spec-Driven sobre delta exacto.
4. Nueva petición sin definición almacenada → alerta y entrada a registro gobernado, no inventar spec aprobada.
5. Documentación incompleta de texto de ayuda no material + subalcance autónomo + aceptación atestada → parcial con alerta y exclusión.
6. Documentación incompleta de MFA/tenant/permisos obligatorios + «usuario acepta riesgo» → bloqueo del alcance dependiente.
7. Implementación desconocida y ninguna regla cambiada → `BLOCKED_UNKNOWN_IMPLEMENTATION`, NO_OP prohibido.
8. Usuario solicita reestructuración y reglas iguales → delta de código autorizado, no rehacer policies.
9. Solicitud de un negocio vs inventario de otro → BLOCKED_CROSS_BUSINESS.
10. Versión fuente drift o missing hash → bloquear; no usar recuerdos del chat como autoridad.

## Caso B2B-AUTH-001 verificado como inventario de definiciones

Fuente `lf_ops.pantallas` id 51, v0.5, CANDIDATO; 71 reglas vinculadas (38 VIGENTE, 33 CANDIDATO), 13 links de políticas, 17 elementos, 2 campos, 3 estados, 3 variantes, 8 artefactos visuales, 6 perfiles, 6 errores y ruta de login. Las políticas subyacentes pueden estar VIGENTE aunque el vínculo a la pantalla sea CANDIDATO. Esto no prueba que haya código deployado. No declarar NO_OP ni READY sin GitHub AS-IS exacto.

## Gobierno / cierre

Esta propuesta es **anexo para la skill existente**, no una skill, operación, Edge, tabla ni RPC nueva. Se reutilizan `REQUEST_CONTEXT_V1`, `ANALYSIS_CHANGE_CLASSIFICATION_V1`, `TARGETED_EVIDENCE_SET_V1`, `IMPLEMENTABILITY_SCHEMA_V1`, `MATERIAL_FRONT_COVERAGE_V1` y los dos outputs de A9. `SPEC_DRIVEN` es el formato de consumo para Programación.

**Evidencia de EKB consultada:** `PROGRAMMING-ANALYSIS-STAGE-SOURCE-ATTESTATION-GAP-001`, `PROGRAMMING-ANALYSIS-A14-EVIDENCE-TIER-FALSE-READY-001`, `PROFILE-JUDGE-INVARIANT-COVERAGE-001`. Sin efectos: Main, Supabase, Router, juez, permisos, PR de Edge, ejecución de skills y producción intactos. Activación real pendiente de una implementación gobernada posterior.
