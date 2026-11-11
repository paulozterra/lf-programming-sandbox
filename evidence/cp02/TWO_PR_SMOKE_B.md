# CP0.2 · segundo PR (B)

Marcador inerte de la prueba de humo: dos PRs internos abiertos simultáneamente desde `main` `2290a222ca074fad422f50b5578bba3e137e4f79`.

Este PR contiene su propio CHG-0040. Después del merge del PR A (CHG-0039), debe quedar atrás de `main` y con conflicto exclusivamente en `standards/CAMBIOS.md`.

La verificación exige regeneración con `changes.py render`, validación C9, push del HEAD nuevo, `workflow_dispatch` de `ci.yml`, seis checks obligatorios sobre ese HEAD, merge commit de dos padres y recibo. Sin secretos, Supabase ni cambios funcionales.
