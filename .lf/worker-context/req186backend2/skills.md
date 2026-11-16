# LF pinned stack skills / CANDIDATE_SANDBOX_ONLY
Standards source: paulozterra/lf-programming-sandbox@f18b2d96b7e1a8263749d35a7afcc9c043521cb8:standards/catalog.json
Catalog SHA-256: 26ca9cf9936ef01b50f9af504e4a9b796ee7d7d538d5724ff388c9fb90e8ddb3

## SPRINGBOOT_EXP@3 priority 1
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


### Source-bound expert rules
{
  "schema_version": "LF_STACK_EXPERT_RULES_EXP_V1",
  "skill_code": "SPRINGBOOT_EXP",
  "version": "3",
  "area": "BACKEND",
  "standard_family": "STD-BE",
  "rules": [
    {
      "rule_id": "SB3-01",
      "text": "Separar controller para HTTP, service para casos de uso y repository para persistencia cuando esa arquitectura aplique al proyecto; probar el límite entre capas.",
      "source_url": "https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html"
    },
    {
      "rule_id": "SB3-02",
      "text": "Definir contratos HTTP mediante DTO de request/response; no exponer automáticamente una entidad persistente como contrato externo sin revisar el diseño.",
      "source_url": "https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html"
    },
    {
      "rule_id": "SB3-03",
      "text": "Aplicar Bean Validation a entradas cuando corresponda y verificar casos inválidos y respuesta de error.",
      "source_url": "https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html"
    },
    {
      "rule_id": "SB3-04",
      "text": "Centralizar el mapeo de errores HTTP con @ControllerAdvice y @ExceptionHandler, y verificar códigos y formato acordados.",
      "source_url": "https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html"
    },
    {
      "rule_id": "SB3-05",
      "text": "Ubicar límites transaccionales con @Transactional en la operación de servicio que requiera atomicidad; comprobar rollback y propagación con pruebas.",
      "source_url": "https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html"
    },
    {
      "rule_id": "SB3-06",
      "text": "Escoger pruebas de corte con @WebMvcTest para la capa MVC y @DataJpaTest para repositorios JPA, cuando existan esas dependencias.",
      "source_url": "https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html"
    },
    {
      "rule_id": "SB3-07",
      "text": "Usar @SpringBootTest para integración de contexto cuando el escenario lo requiera; no sustituir todas las pruebas aisladas ni afirmar ejecución.",
      "source_url": "https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html"
    }
  ]
}


### Literal PG00 STD-BE rules
- STD-BE-01 [APROBADO]: Paquetes en minúscula; clases e interfaces en PascalCase; métodos y variables en camelCase; constantes en UPPER_SNAKE
- STD-BE-02 [APROBADO]: DTOs separados de las entidades (`…Request`/`…Response`); nunca exponer entidades JPA
- STD-BE-03 [APROBADO]: Si el perfil de arquitectura del proyecto (D15) declara módulos, sus límites se verifican con una prueba automatizada en el CI (en Spring Modulith: `ApplicationModules.verify()`). Sin módulos declarados, no aplica.
- STD-BE-04 [APROBADO]: Logs técnicos en JSON con el formato estructurado nativo de Spring Boot. Campos mínimos: `timestamp`, `level`, `logger`, `message`, `request_id` y `correlation_id` (D9). Nunca PII (STD-GEN-04). El proyecto puede exigir campos adicionales (L3).
- STD-BE-05 [APROBADO]: Formato automático con palantir-java-format (4 espacios, 120 columnas) aplicado con Spotless; el CI y el agente usan el mismo comando
- STD-BE-06 [APROBADO]: Toda llamada saliente (HTTP, BD, colas) tiene un timeout explícito tomado de la configuración, nunca un literal en el código ni el valor por defecto sin límite. Solo se reintentan operaciones idempotentes, con límite y espera configurados. La política concreta la fija el proyecto (L3).

## KAFKA_EXP@3 priority 2
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


### Source-bound expert rules
{
  "schema_version": "LF_STACK_EXPERT_RULES_EXP_V1",
  "skill_code": "KAFKA_EXP",
  "version": "3",
  "area": "BACKEND",
  "standard_family": "STD-BE",
  "rules": [
    {
      "rule_id": "KF3-01",
      "text": "Diseñar key y particiones para satisfacer el orden dentro de cada partición; no prometer orden global.",
      "source_url": "https://kafka.apache.org/documentation/"
    },
    {
      "rule_id": "KF3-02",
      "text": "Definir producer acks, retries e idempotencia conforme al objetivo de entrega, sin prometer exactly-once por defecto.",
      "source_url": "https://kafka.apache.org/documentation/"
    },
    {
      "rule_id": "KF3-03",
      "text": "Documentar consumer groups, commits de offset, rebalance y reprocesamiento con pruebas de duplicados.",
      "source_url": "https://kafka.apache.org/documentation/"
    },
    {
      "rule_id": "KF3-04",
      "text": "Especificar el contrato del mensaje y la estrategia de compatibilidad de esquema antes de publicación.",
      "source_url": "https://kafka.apache.org/documentation/"
    },
    {
      "rule_id": "KF3-05",
      "text": "Exigir evidencia observable de lag, fallos y recuperación, sin atribuir pruebas no ejecutadas.",
      "source_url": "https://kafka.apache.org/documentation/"
    }
  ]
}


### Literal PG00 STD-BE rules
- STD-BE-01 [APROBADO]: Paquetes en minúscula; clases e interfaces en PascalCase; métodos y variables en camelCase; constantes en UPPER_SNAKE
- STD-BE-02 [APROBADO]: DTOs separados de las entidades (`…Request`/`…Response`); nunca exponer entidades JPA
- STD-BE-03 [APROBADO]: Si el perfil de arquitectura del proyecto (D15) declara módulos, sus límites se verifican con una prueba automatizada en el CI (en Spring Modulith: `ApplicationModules.verify()`). Sin módulos declarados, no aplica.
- STD-BE-04 [APROBADO]: Logs técnicos en JSON con el formato estructurado nativo de Spring Boot. Campos mínimos: `timestamp`, `level`, `logger`, `message`, `request_id` y `correlation_id` (D9). Nunca PII (STD-GEN-04). El proyecto puede exigir campos adicionales (L3).
- STD-BE-06 [APROBADO]: Toda llamada saliente (HTTP, BD, colas) tiene un timeout explícito tomado de la configuración, nunca un literal en el código ni el valor por defecto sin límite. Solo se reintentan operaciones idempotentes, con límite y espera configurados. La política concreta la fija el proyecto (L3).
