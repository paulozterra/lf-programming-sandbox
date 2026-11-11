> **Nota de arquitectura 2026-11-04:** A1 es un paso **interno** de la única skill `PROGRAMMING_ANALYSIS_LF`. Este artefacto procede del antiguo candidato individual; sus referencias a ejecución/registro deben interpretarse a nivel de la **skill completa**. No documenta una habilidad A1 registrable ni recibos operativos.

# A1 — Evidencia de regresión local del paquete semántico

## Alcance
Habilidad `PROGRAMMING_ANALYSIS_LF`, PR #3529, rama `agent/analysis-a1-independent-skill-20261103`.
Sin ejecución real de modelo, juez independiente, perfil, Router, Supabase, RUN, merge ni despliegue.

## Fuente verificada por Git blob SHA (idéntica a lo ejecutado)
- `validators/run.py`: `cd21eff984b7c3be2a5805609a3c89ab6ab6d772`
- `judges/semantic_guard.py`: `c556b6994aaee5459bca6dad38900a3fb16d80c5`
- `evals/test_a1.py`: `c267af277696ee174ef32535d5bb28a0c83db6d2`
- `semantic/semantic_boundary_v1.py`: `9d3e4e087f3493af0d54d16f1124e2b7a99442ae`
- `evals/test_semantic_boundary_v1.py`: `dcade49ab7f28e01c68a25113bc3e11fcd94051d`
- `fixtures/semantic_original_context_v1.json`: `775c8fec7654f89c18e0550774dbddac4b0a5a2d`
- `fixtures/semantic_model_candidate_fixture_v1.json`: `f1207e5571b53e81adee3db8766f123dc975c10f`

Los demás schemas y la fuente canónica de `REQUEST_CONTEXT_V1` estaban presentes en el árbol local ya usado para los 35 casos anteriores.

## Ejecución
Comando local (raíz de árbol):
`python -m coverage run --branch --source=skills/programming_analysis/steps/a1/semantic,skills/programming_analysis/steps/a1/validators,skills/programming_analysis/steps/a1/judges -m unittest discover -s skills/programming_analysis/steps/a1/evals -p 'test_*.py' -q`

**Resultado: 69 pruebas PASS** (35 del normalizador y 34 de frontera semántica).
Cobertura total de tres módulos evaluados: **86%**.

## Escenario testigo
Entrada literal: «Evalúa las reglas y definiciones de la talla de login o inicio de sesión de B2B e inmolementa lo que falta».
Contexto aportado: `business=LF`, pantalla `B2B-AUTH-001`, nombre «Inicio de sesión B2B» y fuente declarada.
El candidato semántico sintético identifica dos acciones por spans literales: `Evalúa→evaluar` e `inmolementa→implementar`.
Se comprueba conservación del código y nombre recibidos, estado `REQUIRES_INDEPENDENT_SEMANTIC_REVIEW` y `next_capability=null`.
El resultado de revisión sintética queda exclusivamente `REVIEW_STRUCTURAL_PASS_ONLY`, `independence_verified=false`.

## Gates no satisfechos
- Invocación real de modelo: **NOT_TESTED**.
- Fidelidad semántica juzgada independientemente con recibo real: **NOT_TESTED**.
- Autorización del consumidor para llamar a A2: **NOT_WIRED**.
- Registro de habilidad / RUN / Supabase: **NOT_WIRED**.
- `SKILL_READY` y `SKILL_INTEGRATED`: **NO DECLARAR**.

Esta evidencia de regresión local no sustituye CI, evidencia operativa ni calificación independiente.
