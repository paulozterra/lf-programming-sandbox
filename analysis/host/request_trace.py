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


LEXICON_PATH = Path(__file__).with_name("request_lexicon_v1.json")


def _lexicon() -> set[str]:
    try:
        doc = json.loads(LEXICON_PATH.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise RequestTraceBlocked("LEXICO_NO_DISPONIBLE") from exc
    if (doc.get("schema_version") != "T71_REQUEST_LEXICON_V1"
            or doc.get("language") != "es"
            or not all(isinstance(doc.get(k), list) for k in ("stop_words", "request_grammar"))):
        raise RequestTraceBlocked("LEXICO_NO_DISPONIBLE")
    return set(_words(" ".join(doc["stop_words"] + doc["request_grammar"])))


def _variants(term: str) -> set[str]:
    """Deterministic lightweight Spanish inflection / infinitive-clitic forms.

    Does not translate domain concepts, infer synonyms or claim embeddings.
    """
    values={term}
    if len(term)>5 and term.endswith(("es", "s")):
        values.add(term[:-2] if term.endswith("es") else term[:-1])
    for clitic in ("las", "los", "les", "la", "lo", "le"):
        if len(term)>len(clitic)+4 and term.endswith(clitic):
            stem=term[:-len(clitic)]
            if stem.endswith(("ar","er","ir")):
                values.add(stem)
    if len(term)>5 and term.endswith(("ada","ado","adas","ados","ando","iendo",
                                     "ara","aron","are","era","era","era",
                                     "ia","io","o","a")):
        root=re.sub(r"(adas|ados|ando|iendo|aron|ada|ado|ara|are|era|ia|io|o|a)$","",term)
        if len(root)>=5:
            values.add(root)
    return values


def _covers(term: str, known: set[str]) -> bool:
    variants=_variants(term)
    if variants & known:
        return True
    # Match morphology only when both have an independently meaningful stem.
    return any(a==b for a in variants for k in known for b in _variants(k))


def _verified_reuse_words(root: Path) -> tuple[set[str], dict[str, str]]:
    """Only verified index entries and SHA-valid registry artifacts count."""
    known=set()
    witnesses={}
    from pilot.orchestrator.reuse_assessment import index, ReuseBlocked
    try:
        ix=index(root)
    except (OSError, ValueError, ReuseBlocked) as exc:
        raise RequestTraceBlocked("REUTILIZACION_INDETERMINADA") from exc
    for row in ix.get("entries", []):
        if row.get("kind") not in ("endpoint", "public_signature",
                                   "error_code", "implemented_rule"):
            continue
        for word in _words(str(row.get("key",""))):
            known.add(word)
            witnesses.setdefault(word, "CODE_INDEX:" + str(row.get("path","")))
        # A route file's canonical path can name an existing component,
        # but only for a pinned index entry with file SHA evidence.
        if row.get("kind")=="endpoint":
            for word in _words(Path(str(row.get("path",""))).stem):
                known.add(word)
                witnesses.setdefault(word,"CODE_INDEX:" + str(row.get("path","")))
    ledger=root/"pilot/registry/implemented.json"
    if ledger.is_symlink():
        raise RequestTraceBlocked("REUTILIZACION_INDETERMINADA")
    if ledger.is_file():
        try:
            reg=json.loads(ledger.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            raise RequestTraceBlocked("REUTILIZACION_INDETERMINADA") from exc
        if (reg.get("schema_version")!="T7_IMPLEMENTED_REGISTRY_V1"
                or not isinstance(reg.get("entries"),list)):
            raise RequestTraceBlocked("REUTILIZACION_INDETERMINADA")
        for row in reg["entries"]:
            if not isinstance(row,dict) or row.get("status")!="ATTESTED":
                continue
            files=row.get("files")
            if not isinstance(files,list) or not files:
                continue
            verified=True
            for item in files:
                if not isinstance(item,dict):
                    verified=False
                    break
                rel=item.get("path")
                digest=item.get("sha256")
                if (not isinstance(rel,str) or rel.startswith("/")
                        or ".." in Path(rel).parts or not isinstance(digest,str)):
                    verified=False
                    break
                file=root/rel
                if file.is_symlink() or not file.is_file() or hashlib.sha256(
                        file.read_bytes()).hexdigest()!=digest:
                    verified=False
                    break
            if not verified:
                raise RequestTraceBlocked("REUTILIZACION_INDETERMINADA")
            for value in list(row.get("rule_codes",[]))+list(row.get("endpoints",[])):
                for word in _words(str(value)):
                    known.add(word)
                    witnesses.setdefault(word, "REGISTRY:" + str(row.get("merge_sha","")))
    return known,witnesses


def trace(request: str, target: str, sections: dict, *,
          root: Path | None = None, data: dict | None = None) -> list[dict]:
    if not isinstance(request,str) or not request.strip():
        raise RequestTraceBlocked("PEDIDO_AMBIGUO")
    if not isinstance(sections,dict):
        raise RequestTraceBlocked("ANALISIS_FUENTE_NO_COMPATIBLE")
    # Pinned source fiche includes the entire contract plus typed rule
    # descriptions, elements, errors and states; no screen-specific literals.
    source={"sections":sections}
    if data is not None:
        for name in ("direct_rules.json","effective_rules.json",
                     "elements.json","states.json","variants.json"):
            source[name]=data.get(name,{})
    known=set(_words(target))
    for value in _strings(source):
        known.update(_words(value))
    neutral=_lexicon()
    reuse,witnesses=_verified_reuse_words(root or Path(__file__).resolve().parents[2])
    extraneous=[]
    reused=[]
    for word in _words(request):
        if _covers(word,known):
            continue
        matched=next((candidate for candidate in sorted(reuse)
                      if _covers(word,{candidate})),None)
        if matched is not None:
            reused.append({"term":word,"decision":"REUTILIZAR",
                           "evidence":witnesses[matched]})
            continue
        if word in neutral:
            continue
        if word not in extraneous:
            extraneous.append(word)
    if extraneous:
        raise RequestTraceBlocked("PEDIDO_EXCEDE_FICHA", extraneous)
    return reused


def derive_rule_obligations(data: dict) -> list[dict] | None:
    """A6 WHAT is the pinned LF regla.descripcion, never a fabricated HOW.

    Legacy Login without descriptions keeps A6's old corpus as historical
    compatibility. All nonlegacy 13-file screens fail on missing description.
    """
    linked=data["direct_rules.json"].get("linked_rules",[])
    effective=data["effective_rules.json"].get("rules",[])
    if not isinstance(linked,list) or not isinstance(effective,list):
        raise RequestTraceBlocked("ANALISIS_FUENTE_NO_COMPATIBLE")
    by_code={r.get("code"):r for r in linked if isinstance(r,dict)}
    if len(by_code)!=len(linked):
        raise RequestTraceBlocked("ANALISIS_FUENTE_NO_COMPATIBLE")
    active=[r for r in effective if r.get("status")=="VIGENTE"
            and r.get("pending_decision") is False]
    # Distinguish the one existing pinned Login legacy corpus by exact rule
    # coverage rather than a screen-code literal. No new fixture can opt in.
    absent=[r.get("code") for r in active
            if not isinstance((by_code.get(r.get("code")) or r).get("descripcion"),str)
            or not (by_code.get(r.get("code")) or r)["descripcion"].strip()]
    if absent:
        return None, absent
    return ([{"source_requirement_id":r["code"],
              "outcome":(by_code.get(r["code"]) or r)["descripcion"].strip(),
              "acceptance_checks":[(by_code.get(r["code"]) or r)["descripcion"].strip()]}
             for r in active], [])


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
        # The canonical A9 identity lives in request_context and snapshot,
        # not a guessed top-level target_ref alias.
        context=data.get("request_context")
        snapshot=data.get("programming_context_snapshot")
        canonical=(context.get("target_ref") if isinstance(context,dict) else None)
        shadow=(snapshot.get("target") if isinstance(snapshot,dict) else None)
        if canonical==target and (shadow is None or shadow==target):
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
    reuse_traces=trace(request,target,contract,root=root,data=data)
    intent=implementation_state(root,target)
    inventory=data["inventory.json"]
    if intent=="CREATE" and any(inventory.get(k) for k in ("objects","impacts")):
        raise RequestTraceBlocked("ANALISIS_SENALES_NO_DERIVABLES")
    refs=data["effective_rules.json"]["rules"]
    active=[r for r in refs if r.get("status")=="VIGENTE" and
            r.get("pending_decision") is False]
    # Source-backed constraints independent of request phrasing.
    constraints=[str(row["title"]) for row in active
                 if isinstance(row.get("title"),str) and row["title"]]
    constraints=sorted(set(constraints))
    # Materiality is source-derived only when a pinned effective category
    # expresses security/rate limiting. Otherwise UNKNOWN, never a guessed LOW.
    risk_categories={"security", "seguridad", "rate_limiting"}
    high_risk=any(str(row.get("categoria","")).casefold() in risk_categories
                  for row in active)
    known_impacts=bool(inventory.get("impacts"))
    empty_inventory=not any(inventory.get(k) for k in
                            ("objects","impacts"))
    depth={"materiality_level":"HIGH" if high_risk else "UNKNOWN",
           "scope_bounded":("TRUE" if empty_inventory and intent=="CREATE"
                            else "UNKNOWN"),
           "authority_state":"UNKNOWN", "reversibility_state":"NOT_DEMONSTRATED",
           "currentness_decision":"UNKNOWN_FAIL_CLOSED",
           "material_contradiction":False,
           "known_cross_scope_impact":known_impacts,
           "unresolved_material_signal_count":0,"required_specialist_count":0}
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
    result["reuse_traces"]=reuse_traces
    if "source_obligations" in legacy:
        obligations=legacy["source_obligations"]
        if not isinstance(obligations,list) or not obligations:
            raise RequestTraceBlocked("ANALISIS_SENALES_NO_DERIVABLES")
        result["source_obligations"]=deepcopy(obligations)
    else:
        derived,missing=derive_rule_obligations(data)
        if missing:
            # Exactly the historical F1 Login pinned corpus may use its
            # already-reviewed WHAT; rule identities must match the original
            # closed corpus. Never identify this fallback by screen code.
            corpus=json.loads((Path(__file__).resolve().parents[1]/
                               "a6/a6_what_v1.json").read_text("utf-8"))
            approved={r["code"] for r in data["effective_rules.json"]["rules"]
                      if r.get("status")=="VIGENTE"
                      and r.get("pending_decision") is False}
            structured=legacy.get("a1_structured")
            a2_legacy=legacy.get("a2_signals")
            historical=bool(isinstance(structured,dict) and
                            isinstance(a2_legacy,dict) and
                            structured.get("target_hints")==[target] and
                            a2_legacy.get("target_ref")==target and
                            legacy.get("simulation") is True and
                            corpus.get("schema_version")=="A6_FIXED_WHAT_CORPUS_V1"
                            and approved==set(corpus["requirements"]))
            if not historical:
                raise RequestTraceBlocked("REGLA_SIN_DESCRIPCION", sorted(set(missing)))
            # Omission preserves the existing A6 legacy behaviour.
        else:
            result["source_obligations"]=derived
    return result
