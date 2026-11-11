# L2 — Semántica de alcance autorizado | Login B2B
**Skill:** PROGRAMMING_ANALYSIS_LF · **PR:** #3624 · **Evidencia de origen:** GitHub HEAD a543559c4b258ff3ee7d234e70950cf1cbeb3f0b y SELECT Supabase en 2026-11-08.
**Estado:** DIAGNÓSTICO SOURCE_ONLY; no ejecución A1/A2 nativa ni juez, no autorización de implementación.

## Petición literal de prueba
> Programa la pantalla b2b inicio de sesión o login utiliza todas sus reglas y definiciones que ya están aprobadas, si hay reglas que aún están pendientes no las consideres no es requisito para continuar la implementación

## Intención/alcance esperado (juicio humano de prueba, no output del modelo)
- Negocio: LF (proviene del binding de contexto, NO debe inferirse por el nombre del target).
- Operación: IMPLEMENT; no inferir CREATE ni REBUILD.
- Target pista: B2B login/inicio de sesión. Identidad encontrada mediante readback: lf_ops.pantallas codigo=B2B-AUTH-001, id=51, estado=CANDIDATO, version=v0.5.
- Acción de definición: REUSE_AS_IS para lo ya aprobado; no reescribir políticas/reglas por la orden de programar.
- Alcance positivo: todas las reglas/definiciones aprobadas vigentes y APLICABLES al target.
- Exclusión: decisiones y funcionalidades que permanezcan candidatas/pendientes, sin promoverlas a requerimientos nuevos.
- Limitación no derogable: una omisión de dependencia obligatoria de regla vigente o de seguridad no se convierte en READY por la exclusión del usuario. Separar BLOCKED, PARTIAL_READY, REQUIRES_DECISION y lagunas de evidencia según alcance autónomo.

## Readback de fuentes y estados
- lf_ops.reglas + reglas_pantallas en B2B-AUTH-001: 38 reglas VIGENTE/pendiente_decision=false, 31 CANDIDATO/false, 2 CANDIDATO/true. No confundir estado CANDIDATO con aprobación.
- lf_ops.pantalla_elementos: 17 CANDIDATO; lf_ops.pantallas_estados: 3 CANDIDATO; variantes: 3 CANDIDATO.
- lf_ops.pantallas_politicas: 13 asociaciones CANDIDATO; los objetos de política de destino pueden ser VIGENTE y no debe inferirse que su asociación a esta pantalla esté aprobada.
- B2B-RULE-AUTH-003 y AUTH-022 VIGENTE: MFA gobernado por política central y sesión tras autenticación completa; no deben omitirse por excluir otras definiciones candidatas.
- B2B-RULE-AUTH-047 / THEME-002: CANDIDATO, pendiente_decision=true; quedan fuera del alcance de implementación autorizado salvo decisión posterior.
- Estado de la pantalla y de sus elementos es CANDIDATO; la solicitud de implementación no los promueve automáticamente a VIGENTE ni autoriza producción.

## Estado del código
- steps/a1/semantic_intake_candidate_v1.py (blob 798a5059a1bb66aab27f3684d21babe0e3563267): exige evidencia textual de explicit_constraints, lo que permite transportar exclusiones literales solo si el productor semántico las extrae.
- steps/a2/adapters/intent_brief_v1.py (blob eaa314f21e5733d1591309786d2fc93c01b05e41): transporta scope_constraints_declared sin acreditarlas. No efectúa filtro de autoridad.
- steps/a2/adapters/unresolved_research_preview_v1.py (blob e53e4bed4859b7839a2aac05490f54309472cb54): coteja igualdad completa de restricciones A1/intención en preview de investigación, no despacha A3.
- No hay evidencia de que el productor nativo haya interpretado esta frase ni que A3 haya consultado y aplicado la separación aprobadas/pendientes.
- Clasificación de autoridad por estado, aplicabilidad y dependencias corresponde a la investigación A3, no a una lista hardcodeada en A2.

## Contrato de verificación deseado
A1: extraer dos obligaciones de origen distinguibles: (1) usar aprobadas aplicables, (2) excluir pendientes sin detener subalcances seguros; conservar textual y semánticamente ambas, con sus negaciones.
A2: evaluar scope incluido/excluido, materialidad, contradicciones y preguntas dirigidas A3; conservar el binding LF y no fabricar el status de regla.
A3: consultar catálogo LF fuente-current y vínculos exactos, devolver por regla/definición id, estado, vigencia, autoridad, aplicabilidad, dependencias y razones de exclusión.
A4–A9: determinar subalcance implementable y readiness con gates obligatorios; no declarar READY por decisión sintética.

## Matriz mínima de regresión requerida (NO ejecutada)
- SEM-01: conservar "utiliza todas sus reglas y definiciones que ya están aprobadas" como selección positiva, no "todas las reglas".
- SEM-02: conservar "si hay reglas pendientes no las consideres" como exclusión explícita, no omitir por simplificación.
- SEM-03: conservar "no es requisito para continuar" como aceptación de alcance reducido, no como permiso de producción.
- SEM-04: no confundir CANDIDATO/pendiente_decision=false con APROBADO.
- SEM-05: una regla VIGENTE con dependencia candidata esencial produce brecha o subalcance bloqueado, nunca bypass.
- SEM-06: no inventar MFA, intentos, timeout ni proveedores donde falta una política aplicable atestada.
- SEM-07: no asumir que implementación ya existe; contrastar AS-IS real antes del Spec-Driven.
- SEM-08: preservar LF y no consultar saly.reglas por coincidencia genérica.

## Siguiente corrección mínima
Agregar test semántico adversarial A1→A2 con esta frase exacta y juez independiente; conectar A3 a fuentes gobernadas por ámbito/estado/aplicabilidad. Resolver primero el ciclo de preclasificación de A2/entrada A3; no modificar contratos canónicos para producir artificialmente un PASS.
