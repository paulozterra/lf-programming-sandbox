# Reglas para agentes en este repo

Este repo es el entorno de calificación de la Fase 2 (Programación). **No es productivo.**

1. Todo cambio entra por PR a `main`; nunca commit directo.
2. Ningún secreto ni credencial en el repo; solo `.env.example`. No leer ni imprimir `.env`.
3. Ningún código de negocio ni dato real de LF. Los casos de prueba son ficticios.
   Excepción conocida (decisión del owner, 19/11/2026, CHG-0236): las fichas `analysis/fixtures/sbx_*` y sus derivados
   (`.lf/worker-context/req186*`, `req286*`) contienen texto derivado de reglas LF B2B-AUTH. Se dejan como están; no se
   agregan más textos reales. Sus IDs `supabase://lf_ops.*` son simulados (`"simulation": true`) y pueden coincidir con
   filas reales de LF: nunca se resuelven contra el Supabase real.
4. El oráculo de las pruebas ciegas vive fuera de este repo; no buscarlo ni reconstruirlo.
5. Nada se despliega en la nube. Floci emula AWS en local; ningún endpoint de AWS en el código.
6. Terminado = probado: el CI de este repo es la verificación; si no corrió, no está listo.
7. Estándares: catálogo STD-* (PG-00). Mientras se publica aquí, el plan de la Fase 2 es la referencia.
