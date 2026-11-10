# Apache Kafka — stack skill de ENSAYO
**Estado:** CANDIDATE_SANDBOX_ONLY. **Área declarada:** BACKEND. **Código:** KAFKA_EXP. **Versión:** 3.

## Vinculación
La skill se obtiene exclusivamente de project_stack_binding_exp por proyecto, área y versión con prioridad explícita; la IA no la escoge.

## Reglas expertas verificables
- **KF3-01:** Diseñar key y particiones para satisfacer el orden dentro de cada partición; no prometer orden global. **Fuente oficial:** https://kafka.apache.org/documentation/
- **KF3-02:** Definir producer acks, retries e idempotencia conforme al objetivo de entrega, sin prometer exactly-once por defecto. **Fuente oficial:** https://kafka.apache.org/documentation/
- **KF3-03:** Documentar consumer groups, commits de offset, rebalance y reprocesamiento con pruebas de duplicados. **Fuente oficial:** https://kafka.apache.org/documentation/
- **KF3-04:** Especificar el contrato del mensaje y la estrategia de compatibilidad de esquema antes de publicación. **Fuente oficial:** https://kafka.apache.org/documentation/
- **KF3-05:** Exigir evidencia observable de lag, fallos y recuperación, sin atribuir pruebas no ejecutadas. **Fuente oficial:** https://kafka.apache.org/documentation/

## L1/L2 y L3
Familia `STD-BE` referenciada en `supabase/migrations/20261028160000_lf_programming_pg00_standards_checkpoints_decisions_v2.sql`, que NO contiene el texto normativo completo. `PG00_STANDARD_TEXT_UNAVAILABLE` hasta recuperar el catálogo canónico versionado con huella. Guías del stack no sustituyen normas internas LF.

## Salida y límites
Pasar al Worker visible un mínimo de tres reglas verificadas de esta skill, con ID y fuente; no incluir oráculo ni autoridad. `production_authority=false`; `runtime_enabled=false`; `promotion_allowed=false`.
