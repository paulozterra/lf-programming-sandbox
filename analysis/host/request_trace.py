"""T7.1 deterministic typed signals and conservative screen-sheet traceability.

Only pinned screen readbacks, verified implementation ledger, and literal request
are inputs. New behavior with no traceable lexeme blocks before A1; unknown
authority stays UNKNOWN, never becomes a simulated assertion.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unicodedata


class RequestTraceBlocked(ValueError):
    def __init__(self, code: str, fragments: list[str] | None = None):
        self.code, self.fragments = code, fragments or []
        super().__init__(code + (":" + json.dumps(self.fragments, ensure_ascii=False)
                                   if self.fragments else ""))


def _words(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(c for c in normalized if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", text)


def _strings(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)
    elif isinstance(node, str):
        yield node


# Fixed Spanish request grammar, not a screen-specific whitelist. Any term
# outside the grammar or the pinned fiche stays an unattributed fragment.
GRAMMAR = set(_words("""
implementa implementar implementes implementen implementacion implementacion
crea crear cree crees desarrollo desarrolla desarrollar construye construir
quiero queremos necesito necesitamos solicito solicitamos por favor
la el los las un una unos unas de del al para por con y e o u
que se sea es son en esta este esto estos estas pantalla pantallas
ficha fichas reglas regla campos campo errores error elementos elemento
estados estado comportamientos comportamiento segun tal como definidos
definidas definidos definido definida existentes vigente vigentes
completa completo basado basada basado acorde incluye incluir
ademas tiene tengan debe deben tenga el usuario usuario
su sus mis mi nuestro nuestra sus funcionalidad funcionalidades
codigo codigo lo mismo sin agregar nada adicional sigue seguir
"""))


def trace(request: str, target: str, sections: dict) -> None:
    if not isinstance(request, str) or not request.strip():
        raise RequestTraceBlocked("PEDIDO_AMBIGUO")
    if not isinstance(sections, dict):
        raise RequestTraceBlocked("ANALISIS_FUENTE_NO_COMPATIBLE")
    known=set(_words(target))
    for value in _strings(sections):
        known.update(_words(value))
    # Screen identifiers from the requested code are already resolved by
    # request_catalog. Match only source-sheet vocabulary, never guess synonyms.
    supplied=_words(request)
    uncovered=[word for word in supplied if word not in known and word not in GRAMMAR]
    if uncovered:
        fragments=list(dict.fromkeys(uncovered))
        raise RequestTraceBlocked("PEDIDO_EXCEDE_FICHA", fragments)


def implementation_state(root: Path, target: str) -> str:
    """ATTESTED plus matched A9 target is the only positive code evidence."""
    registry=root/"pilot/registry/implemented.json"
    if not registry.exists():
        return "CREATE"
    if registry.is_symlink():
        raise RequestTraceBlocked("ANALISIS_SENALES_NO_DERIVABLES")
    try:
        value=json.loads(registry.read_text("utf-8"))
    except (OSError,ValueError) as exc:
        raise RequestTraceBlocked("ANALISIS_SENALES_NO_DERIVABLES") from exc
    if value.get("schema_version")!="T7_IMPLEMENTED_REGISTRY_V1":
        raise RequestTraceBlocked("ANALISIS_SENALES_NO_DERIVABLES")
    matched=[]
    for row in value.get("entries", []):
        slug=row.get("request")
        if not isinstance(slug,str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}",slug):
            continue
        package=root/"pilot/runs"/slug/"analysis.json"
        if package.is_symlink() or not package.is_file():
            continue
        try:
            data=json.loads(package.read_text("utf-8"))
        except (OSError,ValueError):
            continue
        if data.get("target_ref")==target or data.get("target_screen_ref")==target:
            matched.append(row)
    if not matched:
        return "CREATE"
    if any(x.get("status")!="ATTESTED" or not x.get("files") for x in matched):
        raise RequestTraceBlocked("ANALISIS_SENALES_NO_DERIVABLES")
    for entry in matched:
        for file in entry["files"]:
            path=file.get("path")
            if (not isinstance(path,str) or ".." in Path(path).parts
                    or not isinstance(file.get("sha256"),str)):
                raise RequestTraceBlocked("ANALISIS_SENALES_NO_DERIVABLES")
            full=root/path
            if (full.is_symlink() or not full.is_file()
                    or hashlib.sha256(full.read_bytes()).hexdigest()!=file["sha256"]):
                raise RequestTraceBlocked("ANALISIS_SENALES_NO_DERIVABLES")
    return "MODIFY"


def signals(root: Path, target: str, request: str, data: dict) -> dict:
    contract=data["screen_contract.json"]["contract"]
    trace(request,target,contract)
    intent=implementation_state(root,target)
    inventory=data["inventory.json"]
    if intent=="CREATE" and any(inventory.get(k) for k in ("objects","impacts","dependencies")):
        raise RequestTraceBlocked("ANALISIS_SENALES_NO_DERIVABLES")
    refs=data["effective_rules.json"]["rules"]
    active=[r for r in refs if r.get("status")=="VIGENTE" and
            r.get("pending_decision") is False]
    # Source-backed constraints independent of request phrasing.
    constraints=[str(row["title"]) for row in active
                 if isinstance(row.get("title"),str) and row["title"]]
    constraints=sorted(set(constraints))
    depth={"materiality_level":"HIGH", "scope_bounded":"TRUE",
           "authority_state":"UNKNOWN", "reversibility_state":"NOT_DEMONSTRATED",
           "currentness_decision":"UNKNOWN_FAIL_CLOSED",
           "material_contradiction":False,"known_cross_scope_impact":False,
           "unresolved_material_signal_count":0,"required_specialist_count":0}
    # An existing implementation introduces impact uncertainty, not an
    # invented proof of reversibility or neighboring systems.
    if intent=="MODIFY":
        depth["scope_bounded"]="UNKNOWN"
    ref="fixture://derived/"+target+"/semantic_signals"
    a1={"business":"LF",
        "request_identity":{"request_ref":ref,"request_kind":"USER_REQUEST"},
        "objective":{"problem_statement":request,
                     "desired_outcome":"Cumplir la ficha verificada de "+target},
        "target_hints":[target],"source_refs":[ref],
        "provided_facts":[{"fact_code":"SOURCE_SCREEN_HINT","value":target,
                           "source_ref":ref}],
        "constraints":constraints,"ambiguities":[],
        "declared_intent_kind":intent}
    a2={"schema_version":"ANALYSIS_A2_TYPED_SIGNAL_CANDIDATE_V1",
        "business":"LF","target_ref":target,"change_type":intent,
        "target_granularity":"SCREEN","nested_parent_ref":None,
        "evidence_refs":[ref],"depth_signals":depth}
    legacy=data.get("semantic_signals.json",{})
    result={"imitates":"deterministic typed A1/A2 candidate from pinned screen and actual request",
            "simulation":True,"request_text":request,
            "a1_structured":a1,"a2_signals":a2}
    # A6's source-obligation contract distinguishes absent (legacy
    # independently pinned rules) from present (complete SOURCE_SCREEN list).
    # An empty supplied list would be false evidence, not legacy.
    if "source_obligations" in legacy:
        obligations=legacy["source_obligations"]
        if not isinstance(obligations,list) or not obligations:
            raise RequestTraceBlocked("ANALISIS_SENALES_NO_DERIVABLES")
        result["source_obligations"]=deepcopy(obligations)
    return result
