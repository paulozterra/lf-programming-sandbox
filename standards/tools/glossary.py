"""Glosario ES→EN (PG-00·C4): validación, vista para el agente, check en sombra y cobertura positiva.

Subcomandos:
  validate                    Valida base + glosarios de proyecto. Sale 1 si hay errores.
  render [--check]            Genera standards/GLOSARIO.md (--check: verifica que esté al día).
  digest                      Imprime la versión y el sha256 del glosario.
  check-diff --base <ref>     STD-GEN-01 en sombra: revisa solo las líneas agregadas respecto de <ref>.
  coverage <mapa.json>        Cobertura positiva: cada identificador de dominio nuevo cita sus term_id.

Solo librería estándar. Los literales y comentarios no se revisan (el copy y los códigos de la
Fase 1 son datos, STD-GEN-07).
"""

import fnmatch
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GLOSSARY_DIR = ROOT / "standards" / "glossary"
OUTPUT = ROOT / "standards" / "GLOSARIO.md"
TERM_ID = re.compile(r"^GLOSS-[A-Z]+-[A-Z]+(?:-[A-Z]+)*-\d{3}$")
CONTRACT = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?$")
SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
STATUSES = {"APROBADO", "PROPUESTO", "REQUIRES_DECISION"}
REQUIRED = (
    "term_id", "term_es", "term_en", "plural_en", "definition", "level", "synonyms_es", "rejected_en",
    "legacy_en", "contexts", "examples", "sources", "decision_ref", "status",
)
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


# ---------------------------------------------------------------- carga y validación

def load() -> list[dict]:
    files = [GLOSSARY_DIR / "base.json", *sorted((GLOSSARY_DIR / "projects").glob("*.json"))]
    return [json.loads(path.read_text(encoding="utf-8")) for path in files]


def terms(glossaries: list[dict]) -> list[dict]:
    return [term for glossary in glossaries for term in glossary["terms"]]


def validate(glossaries: list[dict]) -> list[str]:
    errors: list[str] = []
    seen: dict[str, set[str]] = {"term_id": set(), "term_en": set(), "term_es": set()}
    for glossary in glossaries:
        if glossary.get("schema_version") != "LF_GLOSSARY_V1":
            errors.append("schema_version debe ser LF_GLOSSARY_V1")
        contexts = set(glossary.get("context_paths", {}))
        decisions = {d["id"] for d in glossary.get("decisions", [])}
        for term in glossary.get("terms", []):
            label = term.get("term_id", "<sin term_id>")
            missing = [field for field in REQUIRED if field not in term]
            if missing:
                errors.append(f"{label}: faltan campos {missing}")
                continue
            if not TERM_ID.match(term["term_id"]):
                errors.append(f"{label}: term_id con formato inválido")
            for key in seen:
                value = term[key].lower()
                if value in seen[key]:
                    errors.append(f"{label}: {key} duplicado ({term[key]}): una sola traducción por término")
                seen[key].add(value)
            for key in ("term_en", "plural_en"):
                if not SNAKE.match(term[key]):
                    errors.append(f"{label}: {key} debe ir en snake_case")
            if term["status"] not in STATUSES:
                errors.append(f"{label}: estado desconocido {term['status']}")
            if term["decision_ref"] not in decisions:
                errors.append(f"{label}: decision_ref {term['decision_ref']} no está registrada")
            if not term["sources"]:
                errors.append(f"{label}: sin fuentes")
            if not (term["examples"].get("good") and term["examples"].get("bad")):
                errors.append(f"{label}: faltan ejemplos ✅/❌")
            if not set(term["contexts"]) <= contexts:
                errors.append(f"{label}: contexto desconocido en {term['contexts']}")
            if "values" in term:
                values = term["values"]
                if not isinstance(values, dict) or not values:
                    errors.append(f"{label}: values debe ser diccionario español → inglés no vacío")
                else:
                    for es, en in values.items():
                        if not isinstance(es, str) or not es.strip() or not isinstance(en, str) or not SNAKE.fullmatch(en):
                            errors.append(f"{label}: values contiene una traducción inválida")
            for rejected in term["rejected_en"]:
                if rejected.get("match", "token") not in ("token", "standalone"):
                    errors.append(f"{label}: rechazo '{rejected.get('form')}' con match inválido")
                if rejected.get("form") == term["term_en"]:
                    errors.append(f"{label}: la forma canónica aparece como rechazada")
                if not rejected.get("reason") or not set(rejected.get("contexts", [])) or not set(rejected["contexts"]) <= contexts:
                    errors.append(f"{label}: rechazo '{rejected.get('form')}' sin motivo o con contextos inválidos")
            for legacy in term["legacy_en"]:
                contracts = legacy.get("contracts", [])
                if not legacy.get("form") or not contracts:
                    errors.append(f"{label}: forma heredada sin contratos concretos")
                for contract in contracts:
                    if not CONTRACT.match(contract):
                        errors.append(f"{label}: contrato heredado '{contract}' debe ser esquema.tabla[.columna] exacto")
    return errors


def digest(glossaries: list[dict]) -> str:
    canonical = json.dumps(glossaries, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- vista para el agente

def render(glossaries: list[dict]) -> str:
    version = glossaries[0]["glossary_version"]
    lines = [
        f"# Glosario ES→EN · v{version}",
        "",
        "> Generado desde `standards/glossary/*.json` con `standards/tools/glossary.py render`. No editar a mano.",
        "",
        f"Digest: `{digest(glossaries)}`",
        "",
        "**Precedencia de nombres:** contrato existente consumido > glosario del proyecto > glosario base > "
        "propuesta nueva (`REQUIRES_DECISION`). Una forma heredada vale solo en sus contratos exactos.",
    ]
    for glossary in glossaries:
        title = "Glosario base (L1)" if glossary["level"] == "base" else f"Glosario del proyecto {glossary['project']} (L3)"
        lines += ["", f"## {title} · `{glossary['status']}`", ""]
        for term in glossary["terms"]:
            lines.append(f"### {term['term_es']} → `{term['term_en']}` · {term['term_id']} · {term['status']}")
            lines.append("")
            lines.append(f"{term['definition']} Plural: `{term['plural_en']}`. Contextos: {', '.join(term['contexts'])}.")
            if term["synonyms_es"]:
                lines.append(f"Sinónimos en español: {', '.join(term['synonyms_es'])}.")
            for rejected in term["rejected_en"]:
                lines.append(f"- Rechazado `{rejected['form']}` en {', '.join(rejected['contexts'])}: {rejected['reason']}.")
            for legacy in term["legacy_en"]:
                lines.append(f"- Heredado `{legacy['form']}` solo en: {', '.join(f'`{c}`' for c in legacy['contracts'])}.")
            if term.get("values"):
                lines.append("- Valores: " + ", ".join(f"`{es}` → `{en}`" for es, en in term["values"].items()) + ".")
            if term.get("notes"):
                lines.append(f"- Nota: {term['notes']}")
            lines += [f"- ✅ `{example}`" for example in term["examples"]["good"]]
            lines += [f"- ❌ `{example}`" for example in term["examples"]["bad"]]
            lines.append(f"- Fuentes: {'; '.join(term['sources'])} · Decisión: {term['decision_ref']}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------- check en sombra

def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def split_tokens(identifier: str) -> list[str]:
    tokens: list[str] = []
    for part in re.split(r"[_.]", identifier):
        tokens += [token.lower() for token in CAMEL.findall(part)]
    return tokens


def strip_code(text: str, suffix: str) -> str:
    """Quita comentarios y literales para no revisar texto en español legítimo."""
    if suffix == ".sql":
        text = re.sub(r"--[^\n]*", " ", text)
        text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
        return re.sub(r"'(?:''|[^'])*'", "''", text)
    if suffix in (".yaml", ".yml"):
        text = re.sub(r"#[^\n]*", " ", text)
        text = re.sub(r"(description|summary|title|example)\s*:[^\n]*", r"\1:", text)
        return re.sub(r"\"(?:\\.|[^\"\\])*\"|'(?:''|[^'])*'", '""', text)
    if suffix == ".json":
        return re.sub(r"\"(description|summary|title|example)\"\s*:\s*\"(?:\\.|[^\"\\])*\"", '"":""', text)
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    return re.sub(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`[^`]*`", '""', text)


def _matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


class Scanner:
    def __init__(self, glossaries: list[dict]):
        self.context_paths = glossaries[0]["context_paths"]
        self.spanish_paths = glossaries[0]["spanish_check_paths"]
        self.exclusions = set().union(*(set(g.get("spanish_token_exclusions", [])) for g in glossaries))
        self.spanish: dict[str, str] = {}
        self.rejected: list[tuple[list[str], set[str], set[str], str, dict]] = []
        self.technical_tokens = set(glossaries[0]["technical_tokens"])
        self.legacy: list[tuple[str, str]] = []
        for term in terms(glossaries):
            words = [term["term_es"], *term["synonyms_es"]]
            for word in words:
                for token in _ascii(word).split():
                    if len(token) > 2 and token not in self.exclusions:
                        for form in (token, token + "s", token + "es"):
                            self.spanish.setdefault(form, term["term_id"])
            for rejected in term["rejected_en"]:
                self.rejected.append((rejected["form"].split("_"), set(rejected["contexts"]), set(rejected.get("except_after", [])), rejected.get("match", "token"), term))
            for legacy in term["legacy_en"]:
                for contract in legacy["contracts"]:
                    parts = contract.split(".")
                    self.legacy.append((".".join(parts[:2]), parts[-1]))

    def contexts_for(self, path: str) -> set[str]:
        return {name for name, patterns in self.context_paths.items() if _matches(path, patterns)}

    def _legacy_ok(self, name: str, file_text: str) -> bool:
        if any(name == qualified.split(".")[0] for qualified, _ in self.legacy):
            return True  # el nombre del esquema heredado (p. ej. lf_client) es parte del contrato
        return any(name == last and qualified in file_text for qualified, last in self.legacy)

    def scan(self, path: str, file_text: str, line_numbers: set[int] | None = None) -> list[str]:
        suffix = Path(path).suffix
        contexts = self.contexts_for(path)
        spanish_on = _matches(path, self.spanish_paths)
        if not contexts and not spanish_on:
            return []
        clean = strip_code(file_text, suffix)
        violations: list[str] = []
        for number, line in enumerate(clean.splitlines(), 1):
            if line_numbers is not None and number not in line_numbers:
                continue
            for match in IDENT.finditer(line):
                for name in match.group(0).split("."):
                    if self._legacy_ok(name, file_text):
                        continue
                    tokens = split_tokens(name)
                    if spanish_on:
                        for token in tokens:
                            if token in self.spanish and token not in self.exclusions:
                                violations.append(
                                    f"STD-GEN-01 {path}:{number}: '{name}' usa '{token}' en español (ver {self.spanish[token]})"
                                )
                    for form, where, except_after, match_mode, term in self.rejected:
                        if not contexts & where:
                            continue
                        canonical = split_tokens(term["term_en"])
                        if any(tokens[i:i + len(canonical)] == canonical for i in range(len(tokens) - len(canonical) + 1)):
                            continue
                        if match_mode == "standalone":
                            semantic = [token for token in tokens if token not in self.technical_tokens]
                            forms = (form, [*form[:-1], form[-1] + "s"])
                            if semantic not in forms:
                                continue
                        for i in range(len(tokens) - len(form) + 1):
                            if tokens[i : i + len(form)] == form and not (i > 0 and tokens[i - 1] in except_after):
                                violations.append(
                                    f"STD-GEN-01 {path}:{number}: '{name}' usa '{'_'.join(form)}', rechazado para "
                                    f"{term['term_es']} → usar '{term['term_en']}' ({term['term_id']})"
                                )
        return sorted(set(violations))


def added_lines(base: str) -> dict[str, set[int]]:
    diff = subprocess.run(
        ["git", "diff", "--unified=0", "--no-color", f"{base}...HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    result: dict[str, set[int]] = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@") and current:
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            start, count = int(match.group(1)), int(match.group(2) or 1)
            result.setdefault(current, set()).update(range(start, start + count))
    return result


# ---------------------------------------------------------------- cobertura positiva

def coverage(glossaries: list[dict], mapping: dict) -> list[str]:
    by_id = {term["term_id"]: term for term in terms(glossaries)}
    technical = set(glossaries[0]["technical_tokens"])
    problems: list[str] = []
    for entry in mapping.get("identifiers", []):
        name, refs = entry["identifier"], entry.get("glossary_refs", [])
        allowed = set(technical)
        for ref in refs:
            term = by_id.get(ref)
            if term is None:
                problems.append(f"{name}: term_id desconocido {ref}")
                continue
            if term["status"] != "APROBADO":
                problems.append(f"{name}: {ref} no está APROBADO ({term['status']})")
            allowed |= set(term["term_en"].split("_")) | set(term["plural_en"].split("_"))
        for token in split_tokens(name):
            if token not in allowed:
                problems.append(f"REQUIRES_DECISION {name}: '{token}' no está cubierto por {refs or 'ningún término'}")
    return problems


# ---------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    glossaries = load()
    command = argv[1] if len(argv) > 1 else ""
    if command == "validate":
        errors = validate(glossaries)
        for error in errors:
            print(f"ERROR {error}")
        print("OK glosario" if not errors else "")
        return 1 if errors else 0
    if command == "render":
        content = render(glossaries)
        if "--check" in argv:
            ok = OUTPUT.exists() and OUTPUT.read_text(encoding="utf-8") == content
            print("OK GLOSARIO.md al día" if ok else "ERROR GLOSARIO.md desactualizado: ejecutar glossary.py render")
            return 0 if ok else 1
        OUTPUT.write_text(content, encoding="utf-8")
        print(f"Generado {OUTPUT}")
        return 0
    if command == "digest":
        print(f"{glossaries[0]['glossary_version']} {digest(glossaries)}")
        return 0
    if command == "check-diff" and len(argv) == 4 and argv[2] == "--base":
        scanner = Scanner(glossaries)
        violations: list[str] = []
        for path, lines in sorted(added_lines(argv[3]).items()):
            full = ROOT / path
            if full.is_file() and not path.startswith("standards/"):
                violations += scanner.scan(path, full.read_text(encoding="utf-8", errors="replace"), lines)
        for violation in violations:
            print(violation)
        print("OK glosario en el diff" if not violations else "")
        return 1 if violations else 0
    if command == "coverage" and len(argv) == 3:
        problems = coverage(glossaries, json.loads(Path(argv[2]).read_text(encoding="utf-8")))
        for problem in problems:
            print(problem)
        print("OK cobertura" if not problems else "")
        return 1 if problems else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
