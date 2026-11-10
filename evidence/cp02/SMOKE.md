# CP0.2 — Merge Train smoke

Marcador inerte de una prueba operativa del Merge Train del sandbox.

- Rama creada desde `5a4c6a1aae6c0cf5bd44e6214a29eba728977003` anterior al merge #77 `fbff5ae89d645afc212e4e3435159d8e041270cb`.
- Precondición: PR interno abierto y no draft, `behind_by > 0` confirmado antes de aplicar `ready-to-merge`.
- Ruta a observar: `update-branch` → `workflow_dispatch` de `ci.yml` en la rama → 6 checks sobre HEAD nuevo → merge commit de dos padres y recibo.
- Paulo coloca la etiqueta; el autor de la prueba no la coloca ni hace merge manual.

Sin cambios de producto, secretos, Supabase, proveedores ni modelos.
