# Auditor de la ruta — cómo atender un issue `audit-request`

Instructivo genérico (cualquier proyecto) para el auditor declarado en
`pilot/audit/projects/<proyecto>.json` (`audit.auditor`). El auditor **nunca** es
el constructor del pedido. Con `GPT_ISOLATED_SESSION` (decisión del owner, 19/11, por costo)
la auditoría se hace en un **chat nuevo** de GPT, sin el historial del chat que construyó el
pedido; en el PR se declara `Auditor: GPT (sesión aislada)` como límite de independencia. La skill se usa desde el repositorio de su dueño, en el
commit fijado: no se copia ni se modifica.

## 0. Preparar la copia del repositorio (Windows)
La auditoría compara bytes exactos con `base_commit`. En Windows, git convierte LF a CRLF al
extraer los archivos y todo parece cambiado (`SCAFFOLD_CHECKOUT_EOL_CONVERTED`). Antes de
auditar, en la copia del repo:
```
git config core.autocrlf false
git config core.eol lf
git rm -r --cached -q .
git reset --hard
```
`git status` debe quedar limpio. No modifica el contenido del repo.

## 1. Tomar el pedido
1. Elegir el issue abierto `audit-request` más antiguo que **no** tenga ya un PR
   abierto con la rama `audit-<pedido>`. Uno por corrida.
2. Del cuerpo del issue: pedido (`<!-- audit-request:<pedido> -->`), proyecto
   (título `[AUDIT][<proyecto>]`) y la entrada JSON.
3. Rama `audit-<pedido>` desde `main`. Guardar la entrada sin cambios en
   `pilot/runs/<pedido>/audit/audit_input_v2.json`.

## 2. Preparar la skill
```
python3 -m pilot.workflow_entrypoint pilot/audit/skill_pin.py --project <proyecto> --dest /tmp/audit-skill
```
Debe responder `SKILL_VERIFIED`. Si no, detenerse y comentar el error en el issue.
Leer `SKILL.md` de la skill y seguir sus **seis fases**.

## 3. Auditar (lo que solo puede hacer el auditor)
- Leer línea por línea los `entrypoints` y `read_scope` de la entrada en `base_commit`,
  y seguir a sus dependencias (servicios reutilizados, contratos, consumidores).
- **Una tarea por regla** (`RULE:<código>`): `VERIFIED` con evidencia y motivo
  `CUMPLE` / `CUMPLE parcial` / `INCUMPLE: ver <hallazgo>`; otro estado exige motivo.
- Revisar también cómo Análisis asignó cada regla a los lotes (`lots.json`).
- **Un hallazgo es `CONFIRMED` solo con un reproductor ejecutado** (prueba positiva
  que muestra el defecto y negativa de control). Sin ejecución: `HYPOTHESIS`.
  Medir lo que se pueda medir (tiempos, estados, textos), no suponerlo.
- Reproductores y sus salidas JSON en `pilot/runs/<pedido>/audit/evidence/`.
  Los códigos concretos del caso van en un JSON de argumentos, nunca en un `.py`
  bajo `pilot/` (guarda T2).
- Checklist EKB: solo códigos que existan en el EKB del proyecto (el CI lo comprueba
  en vivo); `NOT_APPLICABLE` con motivo.
- No ejecutar código ajeno sin leerlo, no usar credenciales, no tocar producción.

## 4. Armar y validar el informe
Escribir solo el juicio en `pilot/runs/<pedido>/audit/draft.json`
(`LF_ROUTE_AUDIT_DRAFT_V1`; ver `report_scaffold.py` y el ejemplo de `req-286`), más
`cohort_sample.json` con `{"rows": []}`. Luego:
```
python3 -m pilot.workflow_entrypoint pilot/audit/report_scaffold.py --skill-dir /tmp/audit-skill/<path> --audit-dir pilot/runs/<pedido>/audit
python3 /tmp/audit-skill/<path>/validators/validate_audit_v2.py pilot/runs/<pedido>/audit/report.json --repo-root .
python3 -m pilot.workflow_entrypoint pilot/audit/validate_report.py --project <proyecto> --skill-dir /tmp/audit-skill/<path> --report pilot/runs/<pedido>/audit/report.json
```
Las dos validaciones deben dar `PASS` / `AUDIT_REPORT_VALID`.

## 5. Entregar
- PR `[AUDIT][<proyecto>] <pedido>` con `audit_input_v2.json`, `draft.json`,
  `report.json`, `cohort_sample.json` y `evidence/`. Esperar el CI (incluye
  `audit-report`, que valida el EKB en vivo). Si pasa: etiqueta `ready-to-merge`.
- Comentar en el issue: enlace al PR y resumen en español
  `Alcance | Hallazgos (n, severidad) | Reglas cumplidas/parciales/incumplidas | Límites`.
- Al fusionarse el informe, `audit-request.yml` cierra el issue solo.

## Límites
Modo `SHADOW`: el informe no bloquea el pedido ni autoriza efectos
(`promotion_authorized=false`). Las correcciones se proponen; se implementan en un
pedido nuevo.
