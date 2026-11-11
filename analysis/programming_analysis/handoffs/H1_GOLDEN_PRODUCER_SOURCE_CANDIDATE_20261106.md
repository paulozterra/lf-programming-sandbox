# LF — A2 Golden H1 | Productor dimensional candidato

**Lote:** H1, solo `PROGRAMMING_ANALYSIS_LF.steps.A2`. **Estado:** `SOURCE_CANDIDATE_IMPLEMENTED_AND_LOCAL_TESTED`. No es un cierre operacional, no autoriza A3 ni edita el contrato canónico de salida `ANALYSIS_CHANGE_CLASSIFICATION_V1`.

## Alcance y lectura EKB

Reutiliza la clasificación vigente de A2 (`steps/a2/validators/run.py`), sin reimplementar los 23 predicados del contrato canónico ni introducir otra skill o Router. Reglas EKB revisadas: `PROGRAMMING-ANALYSIS-STAGE-SOURCE-ATTESTATION-GAP-001`, `PROGRAMMING-ANALYSIS-A14-EVIDENCE-TIER-FALSE-READY-001`, `PROFILE-JUDGE-INVARIANT-COVERAGE-001`.

## Implementación publicada en esta rama

| Archivo | SHA-256 fuente | Función |
|---|---|---|
| `steps/a2/catalog/A2_GOLDEN_CATALOGO_DIMENSIONAL_v0_2.json` | `67c235e0b855086176a5f6b0f348095bdb96f711187c5772fd48987d2d1ef6ba` | Catálogo original 12/59 con metadatos completos |
| `steps/a2/schemas/A2_GOLDEN_CONTRATO_SALIDA_PROPUESTA_v0_3.schema.json` | `3cfff9ba5d9df8d3ab88283ff99c04d70af46ec20d971b3bca45baa8afea79e4` | Esquema existente Golden v0.3 (no canónico) |
| `steps/a2/adapters/golden_dimensions_v1.py` | `83969f5c4d9bafe72afb91991896d31b8d693460a36ee8691c6d5413eeea7147` | Evalúa los 26 activadores conservadores y produce 59 elementos |
| `steps/a2/adapters/golden_handoff_v03.py` | `41dfb9333cd9b71910914b9b55fa56275fc58ce9d1a0a1b077b7a5f1cc3e74af` | Proyecta al esquema Golden v0.3 existente y verifica su SHA |
| `steps/a2/evals/test_golden_dimensions_v1.py` | `1bbd203446e17b0fbf60156242655fb3cb57ef5c480f8959f353055d82191b61` | Verifica integridad, 26 positivos, seguridad y pruebas negativas |
| `steps/a2/evals/test_golden_handoff_v03.py` | `103efdc82513859f96de566973256985483c91cef02617c7564ad4a20ac33c07` | Valida 12/59 contra el esquema propuesto, digest, A3 y rechazos |

Los seis blobs GitHub se compararon contra los blobs Git de sus bytes locales: **6/6 exactos**.

### Ejecución local reproducible

Desde raíz del repositorio, con `jsonschema` disponible:

```bash
python -m unittest discover -s skills/programming_analysis/steps/a2/evals -p 'test_golden*.py' -v
```

En checkout local de los seis archivos: **41 pruebas PASS, 0 FAIL**. Incluye 26 subcasos de activación positiva sobre el esquema v0.3. **PASE** fue `SUCCESS` en el commit que publicó los seis archivos; se debe comprobar nuevamente para cualquier nuevo HEAD. PASE no sustituye la ejecución de estas 41 pruebas.

### Reglas fail-closed preservadas

- **12/12** dimensiones, **59/59** elementos, **33** fijos y **26** condicionales siempre visibles.
- Dos ejes independientes: `applicability` y `fulfilment`. Falta de prueba de trigger falso implica `UNRESOLVED_TRIGGER` + `PENDING_EVIDENCE`, nunca `NOT_APPLICABLE`. No se fabrican negativos.
- Todas las fuentes aportadas por A1/A2 permanecen `DECLARED_UNATTESTED`, aunque se calculen valores y hashes locales. Ninguna entrada user/model puede otorgar `SATISFIED` o activar A3.
- `D12-E05` (recibo del juez) permanece `finding=null`, `PENDING_EVIDENCE`; el productor no acredita su propia revisión.
- `golden_handoff_v03.py` produce la salida `A2_GOLDEN_HANDOFF_PROPOSAL_V0_3` **solo como artefacto adicional**: no cambia ni reemplaza `ANALYSIS_CHANGE_CLASSIFICATION_V1` que A3 consume canónicamente.
- El plan dirigido a A3 tiene **26 solicitudes de verificación condicional y 1 solicitud de identidad target** en el fixture L1 local; son propuestas, no consultas ejecutadas. A3 deberá consolidar/seleccionar las consultas materialmente necesarias.

## Deuda residual y ruta crítica

**H1 código candidato: IMPLEMENTADO / PROBADO LOCALMENTE. H1 operacional: PENDIENTE.** Siguen sin estar admitidos el catálogo/esquema Golden como fuente canónica y sin recepción real de las señales. No hay modelo real, output independiente, juez ni RUN de skill acreditados.

- **H2:** productor real A1 + nueve señales firmadas/readback + negocio. Conectar adaptadores al perfil, sin elevar contexto declarado a CURRENT.
- **H3:** juez nativo independiente para A2, misma salida SHA, original + 2 reparaciones, bloqueo de A3 ante tres FAIL.
- **H4:** apertura de RUN `EJECUCION_SKILL_LF` por caller autorizado, paso 0, 10–80, recibos y E2E; PR #3681 sólo se consume si aporta un requisito genuino para este caso, no ampliar genéricamente.

No merge, no SQL, no cambios a Main, Router, juez ni permisos. Toda promoción requiere revisión independiente y gobernanza vigente.
