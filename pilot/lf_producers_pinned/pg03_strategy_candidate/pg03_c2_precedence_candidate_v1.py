"""PG-03_C2 source-only precedence audit. Does NOT decide semantic collisions.

Canonical order: L1 > A (Analysis) > B (project manifest) > L2.
The source catalog can label domains L1/L2, without per-rule levels.
Those rules must fail closed pending independently attested levels.
"""
import hashlib
import json
import re

ORDER={"L1":0,"A":1,"B":2,"L2":3}
HEX64=re.compile(r"^[a-f0-9]{64}$")

def blocked(code, **extra):
    return {"status":"BLOCKED","code":code,"authority":False,
            "handoff_allowed":False,"precedence_verified":False,**extra}

def candidate_precedence(*, catalog_bytes, expected_catalog_sha256,
                         selected_rule_ids, level_evidence,
                         analysis_rules, project_rules, conflicts):
    if not isinstance(catalog_bytes,bytes) or not catalog_bytes:
        return blocked("CATALOG_SOURCE_INVALID")
    if not isinstance(expected_catalog_sha256,str) or not HEX64.fullmatch(expected_catalog_sha256):
        return blocked("CATALOG_PIN_INVALID")
    if hashlib.sha256(catalog_bytes).hexdigest()!=expected_catalog_sha256:
        return blocked("CATALOG_PIN_DRIFT")
    try: catalog=json.loads(catalog_bytes)
    except (ValueError,UnicodeDecodeError):
        return blocked("CATALOG_JSON_INVALID")
    if not isinstance(catalog,dict) or catalog.get("schema_version")!="LF_STANDARDS_CATALOG_V1" or catalog.get("status")!="BORRADOR_EN_REPO_DE_CALIFICACION":
        return blocked("CATALOG_NOT_QUALIFICATION_SOURCE")
    if catalog.get("precedence") != [
        "L1 (piso que nadie rebaja)",
        "Lo que trae el spec de la Fase 1 (reglas tipo A)",
        "Contratos existentes y perfil técnico del proyecto (reglas tipo B, por manifiesto)",
        "Valor por defecto del catálogo (L2)"
    ]:
        return blocked("CATALOG_PRECEDENCE_DRIFT")
    domains=catalog.get("domains")
    rules=catalog.get("rules")
    if not isinstance(domains,list) or not isinstance(rules,list):
        return blocked("CATALOG_RULES_INVALID")
    dmap={}
    for d in domains:
        if not isinstance(d,dict) or not isinstance(d.get("id"),str) or d["id"] in dmap or d.get("level") not in ("L1","L2","L1/L2"):
            return blocked("CATALOG_DOMAIN_LEVEL_INVALID")
        dmap[d["id"]]=d["level"]
    rmap={}
    for r in rules:
        if not isinstance(r,dict) or not isinstance(r.get("id"),str) or not r["id"] or r["id"] in rmap or r.get("domain") not in dmap:
            return blocked("CATALOG_RULE_INVALID")
        rmap[r["id"]]=r
    # A nonempty, unique selection from the upstream C2/C5 projection is
    # required. Never treat an empty catalogue selection as a strategy.
    # Check types before set() to fail closed on unhashable caller payloads.
    if (not isinstance(selected_rule_ids,list) or not selected_rule_ids
        or any(not isinstance(x,str) or not x or x not in rmap for x in selected_rule_ids)
        or len(set(selected_rule_ids))!=len(selected_rule_ids)):
        return blocked("SELECTED_RULES_INVALID")
    if not isinstance(level_evidence,dict):
        return blocked("LEVEL_EVIDENCE_INVALID")
    # A level claim for an unselected or single-level rule is NOT authority.
    if set(level_evidence)-set(selected_rule_ids):
        return blocked("EXTRANEOUS_LEVEL_CLAIM")
    selected=[]
    for rid in selected_rule_ids:
        rule=rmap[rid]
        domain_level=dmap[rule["domain"]]
        if rule.get("status")!="APROBADO":
            return blocked("CATALOG_RULE_NOT_APPROVED", rule_id=rid)
        if domain_level=="L1/L2":
            ev=level_evidence.get(rid)
            if not isinstance(ev,dict) or ev.get("level") not in ("L1","L2") or not isinstance(ev.get("source_ref"),str) or not ev["source_ref"].strip() or not HEX64.fullmatch(str(ev.get("source_sha256",""))):
                return blocked("MIXED_DOMAIN_RULE_LEVEL_MISSING",rule_id=rid)
            # Even a complete claim remains untrusted; no independent source identity here.
            return blocked("MIXED_DOMAIN_LEVEL_READBACK_UNATTESTED",rule_id=rid)
        if rid in level_evidence:
            return blocked("UNEXPECTED_RULE_LEVEL_OVERRIDE",rule_id=rid)
        selected.append({"id":rid,"level":domain_level,"text":rule.get("rule"),"source":"CATALOG"})
    for field,rows,level in (("ANALYSIS",analysis_rules,"A"),("PROJECT",project_rules,"B")):
        if not isinstance(rows,list):
            return blocked(field+"_RULES_INVALID")
        for r in rows:
            if not isinstance(r,dict) or not isinstance(r.get("id"),str) or not r["id"] or not isinstance(r.get("text"),str) or not r["text"].strip() or not isinstance(r.get("source_ref"),str) or not r["source_ref"].strip():
                return blocked(field+"_RULE_INVALID")
            if r.get("pending_decision") is True:
                return blocked(field+"_PENDING_DECISION",rule_id=r["id"])
            if field=="PROJECT" and (r.get("modifies_l1") is True or r.get("waives_standard") is True):
                return blocked("PROJECT_L1_OVERRIDE_UNAUTHORIZED",rule_id=r["id"])
            selected.append({"id":r["id"],"level":level,"text":r["text"],"source":field})
    ids=[r["id"] for r in selected]
    if len(set(ids))!=len(ids):
        return blocked("RULE_ID_COLLISION")
    if not isinstance(conflicts,list):
        return blocked("CONFLICT_REGISTER_MISSING")
    for issue in conflicts:
        if not isinstance(issue,dict) or issue.get("status")!="INDEPENDENTLY_CLOSED" or not isinstance(issue.get("evidence_ref"),str) or not issue["evidence_ref"].strip():
            return blocked("CONFLICT_UNRESOLVED_REQUIRES_DECISION")
        # A self-reported closure is never independently authenticated here.
        return blocked("CONFLICT_CLOSURE_UNATTESTED")
    result=sorted(selected,key=lambda r:(ORDER[r["level"]],r["id"]))
    return {"status":"CANDIDATE_NOT_ADMITTED","code":"PRECEDENCE_ORDER_STRUCTURAL_ONLY",
            "authority":False,"handoff_allowed":False,"precedence_verified":False,
            "semantic_conflicts_verified":False,"source_release_verified":False,
            "ordered_rules":result,"order":["L1","A","B","L2"]}
