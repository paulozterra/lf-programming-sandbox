# Reglas para agentes en este repo

Este repo es el entorno de calificación de la Fase 2 (Programación). **No es productivo.**

1. Todo cambio entra por PR a `main`; nunca commit directo.
2. Ningún secreto ni credencial en el repo; solo `.env.example`. No leer ni imprimir `.env`.
3. Contenido de LF: derivado sí, real no.
   - Permitido: reglas, pantallas y criterios **derivados** de LF, reescritos con identificadores del sandbox (`SBX-…`), recortados al alcance del ejercicio y con datos de prueba ficticios; métodos y plantillas genéricas (fases, taxonomías, esquemas). La procedencia se anota como referencia de documento (p. ej. "derivada de B2B-AUTH-001 v0.5"), sin enlaces internos.
   - Prohibido: datos reales (clientes, montos, usuarios, correos, documentos); credenciales, URLs, `project_ref`, nombres de tablas o funciones reales de Supabase; código de negocio de LF copiado tal cual; contenido literal del EKB (solo sus códigos); fotos de datos o lecturas SQL de LF.
   - Ante la duda, se pregunta al owner antes de subirlo: el repo es público.
   Excepción conocida (A11): `pilot/audit/projects/<proyecto>.json` nombra la vista y la columna de códigos del EKB
   que lee la etapa de auditoría (solo lectura, con el secreto del repo); nunca su contenido.
   Excepción conocida (decisión del owner, 20/11/2026, T56, CHG-0242): la ruta **lee contenido** del EKB
   (código, categoría, título, patrón, causa raíz, prevención, validación, severidad, frecuencia; nunca `evidencia`)
   solo a través de la función de consulta existente nombrada en `pilot/ekb/route_ekb.json`, saneado (URLs, correos,
   tokens, claves y refs se reemplazan; filas mayormente sensibles se descartan) y únicamente para el contexto del lote
   del worker. Escribe solo filas propias (`source_context` `LF_ROUTE*`, códigos `LF-ROUTE-*`) por el writer gobernado
   existente del EKB, con su operación propia, un secreto aparte y desde un paso de confianza; la evidencia es solo una
   referencia (PR, run, CHG, lote) y un texto con datos sensibles se rechaza.
   Excepción conocida (decisión del owner, 19/11/2026, CHG-0236): las fichas `analysis/fixtures/sbx_*` y sus derivados
   (`.lf/worker-context/req186*`, `req286*`) contienen texto derivado de reglas LF B2B-AUTH. Se dejan como están; no se
   agregan más textos reales. Sus IDs `supabase://lf_ops.*` son simulados (`"simulation": true`) y pueden coincidir con
   filas reales de LF: nunca se resuelven contra el Supabase real.
   Excepción conocida (decisión del owner, 23/11/2026, CHG-0256): para que el ejercicio del login integrado sea fiel a las
   maquetas de la pantalla 51, se guardan en `frontend/public/brand/` el logo de dos líneas y la marca de agua (escudo)
   de la marca, tal cual, y la ficha `sbx_b2b_login` incluye la composición y las medidas derivadas de las maquetas.
   No se agregan las maquetas ni otros activos de marca.
4. El oráculo de las pruebas ciegas vive fuera de este repo; no buscarlo ni reconstruirlo.
5. Nada se despliega en la nube. Floci emula AWS en local; ningún endpoint de AWS en el código.
6. Terminado = probado: el CI de este repo es la verificación; si no corrió, no está listo.
7. Estándares: catálogo STD-* (PG-00). Mientras se publica aquí, el plan de la Fase 2 es la referencia.
