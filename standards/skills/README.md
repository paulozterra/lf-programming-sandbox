# Skills L2 — V1

**Solo** `spring-boot`, `nextjs` y `postgres-flyway`. No incluir Python, Supabase, Terraform ni contenedores como skills V1. Los controles STD-IAC y STD-CONT siguen POR_DEFINIR.

El catálogo no se copia: `catalog_compat` indica major.minor compatible; la huella SHA-256 exacta se obtiene del pin del pedido y figura en el recibo. El selector usa evidencia verificable PG-03 y dominios PG-02; no selecciona el modelo. Las reglas pendientes se muestran como no obligatorias y se guardan en el recibo.

Cristhian: incorporar resolver de skills, pin por pedido, selector externo determinista y recibos verificables al Worker v0.8. Mantener spec L3, arquitectura y copy fuera del paquete L2; no añadir agentes especialistas ni abrir acceso a Supabase.

Uso: `python3 standards/tools/skills.py validate`, `select --evidence <fixture> --domains ...`, `assemble --pin <pin.json> --skills spring-boot --domains ... --out <salida>`. Sin llamadas a modelos.

Los checks se declaran en `checks/stack-checks.json` y el CI usa `stack_checks.py`; `shadow` solo avisa.

## Dominios expresamente fuera de V1

`STD-PY` y `STD-SB`: plataforma, fuera de V1 por D13. `STD-IAC` y `STD-CONT`: sin severidad decidida (`POR_DEFINIR`). La constante `EXCLUDED_V1_DOMAINS` en `standards/tools/skills.py` controla estas cuatro excepciones; los demás dominios requieren cobertura.

## Recibo de ensayo Spring reproducible

```sh
python3 -c 'import hashlib,json,pathlib; p=pathlib.Path("standards/catalog.json"); d=json.loads(p.read_text()); print(json.dumps({"catalog_version":d["catalog_version"],"catalog_sha256":hashlib.sha256(p.read_bytes()).hexdigest()}))' > /tmp/skill-pin.json
python3 standards/tools/skills.py assemble --pin /tmp/skill-pin.json --skills spring-boot --domains STD-BE,STD-API,STD-SEC,STD-GEN,STD-LOG,STD-MSG,STD-AUD,STD-GIT,STD-NAV,STD-CONS --out /tmp/c6-spring.txt
```

La vista sin NAV/CONS usa los mismos comandos omitiendo estos dos dominios. El recibo conserva los `pending_rule_ids`; no obliga las reglas marcadas `VALIDAR_CON_LEGAL`.
