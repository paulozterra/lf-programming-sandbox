# Spring Boot — stack skill de ENSAYO
**Estado:** CANDIDATE_SANDBOX_ONLY. **Área declarada:** BACKEND. **Código:** SPRINGBOOT_EXP. **Versión:** 3.

## Contrato de conocimiento
La skill no se selecciona por IA, nombre de perfil ni texto de la solicitud. El vínculo versionado del proyecto determina `SPRINGBOOT_EXP@3`, su prioridad y SHA-256. Nunca ejecuta código ni crea permisos.

## Reglas expertas verificables
- **SB3-01:** Separar controller para HTTP, service para casos de uso y repository para persistencia cuando esa arquitectura aplique al proyecto; probar el límite entre capas. **Fuente oficial:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html
- **SB3-02:** Definir contratos HTTP mediante DTO de request/response; no exponer automáticamente una entidad persistente como contrato externo sin revisar el diseño. **Fuente oficial:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html
- **SB3-03:** Aplicar Bean Validation a entradas cuando corresponda y verificar casos inválidos y respuesta de error. **Fuente oficial:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- **SB3-04:** Centralizar el mapeo de errores HTTP con @ControllerAdvice y @ExceptionHandler, y verificar códigos y formato acordados. **Fuente oficial:** https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html
- **SB3-05:** Ubicar límites transaccionales con @Transactional en la operación de servicio que requiera atomicidad; comprobar rollback y propagación con pruebas. **Fuente oficial:** https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- **SB3-06:** Escoger pruebas de corte con @WebMvcTest para la capa MVC y @DataJpaTest para repositorios JPA, cuando existan esas dependencias. **Fuente oficial:** https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- **SB3-07:** Usar @SpringBootTest para integración de contexto cuando el escenario lo requiera; no sustituir todas las pruebas aisladas ni afirmar ejecución. **Fuente oficial:** https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html

## Autoridad L1/L2 LF y precedencia
Familia PG-00: `STD-BE`. Registro verificado: `supabase/migrations/20261028160000_lf_programming_pg00_standards_checkpoints_decisions_v2.sql`. Ese registro NO contiene texto normativo L1/L2 completo. La carga de estándares debe recuperar la versión y huella de la fuente canónica antes de habilitar su uso; mientras tanto: `PG00_STANDARD_TEXT_UNAVAILABLE`. Las guías oficiales de stack no sustituyen los estándares LF ni las decisiones L3.

## Resultado y frontera de autoridad
Anexar reglas expertas **por ID y fuente**, al menos tres, a la especificación visible Worker v0.8; no copiar oráculos ocultos. La tarea sigue restringida al alcance PG-05 C2, pruebas protegidas, límites y comandos visibles. `production_authority=false`, `runtime_enabled=false`, `promotion_allowed=false`.
