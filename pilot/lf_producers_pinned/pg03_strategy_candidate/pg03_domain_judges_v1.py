"""PG-03_C5 minimal domain projection + deterministic/semantic judge boundary.
Source-only qualification. Reuses PG-02 active domains and C6 mandatory-rule concept.
"""
import hashlib
import json

class DomainJudgeBlocked(ValueError):
    pass

def project_rules(*, strategy, catalog, requested_domains, global_domains=("GLOBAL",)):
    if not isinstance(strategy,dict) or strategy.get("status")!="CANDIDATE_NOT_ADMITTED" or strategy.get("production_authority") is not False:
        raise DomainJudgeBlocked("STRATEGY_UNTRUSTED")
    active=strategy.get("active_domains")
    if not isinstance(active,list) or not active or any(not isinstance(x,str) for x in active):
        raise DomainJudgeBlocked("ACTIVE_DOMAINS_INVALID")
    if not isinstance(requested_domains,list) or not requested_domains or len(set(requested_domains))!=len(requested_domains):
        raise DomainJudgeBlocked("DOMAIN_REQUEST_INVALID")
    if not set(requested_domains).issubset(set(active)):
        raise DomainJudgeBlocked("UNCLASSIFIED_DOMAIN_REQUEST")
    if not isinstance(catalog,dict) or not isinstance(catalog.get("rules"),list):
        raise DomainJudgeBlocked("CATALOG_INVALID")
    rule_by_id={}
    for r in catalog["rules"]:
        if not isinstance(r,dict) or not isinstance(r.get("id"),str) or not r["id"] or r["id"] in rule_by_id:
            raise DomainJudgeBlocked("CATALOG_RULE_INVALID")
        if not isinstance(r.get("domain"),str) or not isinstance(r.get("text"),str) or not r["text"]:
            raise DomainJudgeBlocked("CATALOG_RULE_INVALID")
        rule_by_id[r["id"]]=r
    allowed=set(requested_domains)|set(global_domains)
    selected=[rule_by_id[rid] for rid in sorted(rule_by_id) if rule_by_id[rid]["domain"] in allowed]
    if not selected: raise DomainJudgeBlocked("NO_APPLICABLE_RULES")
    if any(r.get("pending_decision") is True for r in selected):
        raise DomainJudgeBlocked("REQUIRES_DECISION_PENDING_RULE")
    if any(r.get("status") not in ("APROBADO","REQUIRED") for r in selected):
        raise DomainJudgeBlocked("RULE_STATUS_NOT_ADMITTED")
    # This is a minimum projection, not independent catalog authority.
    payload={"schema_version":"PG03_C5_DOMAIN_CONTEXT_CANDIDATE_V1",
             "status":"CANDIDATE_NOT_ADMITTED","production_authority":False,
             "requested_domains":sorted(requested_domains),
             "rules":[{"id":r["id"],"domain":r["domain"],"text":r["text"]} for r in selected],
             "source_catalog_sha256":hashlib.sha256(json.dumps(catalog,sort_keys=True).encode()).hexdigest()}
    raw=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
    payload["projection_sha256"]=hashlib.sha256(raw).hexdigest()
    payload["estimated_tokens"]=(len(raw)+3)//4
    return payload

def deterministic_judge(*, projection, mandatory_ids):
    if not isinstance(projection,dict) or projection.get("status")!="CANDIDATE_NOT_ADMITTED":
        return {"status":"BLOCKED","code":"PROJECTION_NOT_CANDIDATE"}
    rules=projection.get("rules",[])
    if not isinstance(rules,list) or not isinstance(mandatory_ids,list) or len(set(mandatory_ids))!=len(mandatory_ids):
        return {"status":"BLOCKED","code":"REQUIRED_RULE_SET_INVALID"}
    ids={r.get("id") for r in rules if isinstance(r,dict)}
    if not set(mandatory_ids).issubset(ids):
        return {"status":"BLOCKED","code":"REQUIRED_RULE_OMITTED"}
    return {"status":"PASS_CANDIDATE_ONLY","code":"DETERMINISTIC_STRUCTURAL_PASS_NOT_AUTHORIZED"}

def semantic_judge_boundary(*, deterministic_result, semantic_review):
    if deterministic_result.get("status")!="PASS_CANDIDATE_ONLY":
        return {"status":"BLOCKED","code":"DETERMINISTIC_JUDGE_REQUIRED"}
    if not isinstance(semantic_review,dict) or semantic_review.get("verdict")!="PASS" or semantic_review.get("independent_attestation") is not True:
        return {"status":"REQUIRES_REVIEW","code":"SEMANTIC_INDEPENDENT_JUDGE_REQUIRED"}
    # Caller-supplied assertion alone is not authenticated, hence no admission even on PASS.
    return {"status":"CANDIDATE_NOT_ADMITTED","code":"SEMANTIC_ASSERTION_UNVERIFIED"}

def project_rules_with_analysis(*, strategy, catalog, requested_domains, analysis_rules, analysis_invariants):
    """Conservative lossless type-A extension; no model judge, no authority."""
    projected = project_rules(strategy=strategy,catalog=catalog,requested_domains=requested_domains)
    if not isinstance(analysis_rules,list) or not isinstance(analysis_invariants,list):
        raise DomainJudgeBlocked("ANALYSIS_RULES_MISSING")
    seen={r["id"] for r in projected["rules"]}
    selected=[]
    for collection,kind in ((analysis_rules,"RULE"),(analysis_invariants,"INVARIANT")):
        for r in collection:
            if not isinstance(r,dict) or not isinstance(r.get("id"),str) or not r["id"] or r["id"] in seen:
                raise DomainJudgeBlocked("ANALYSIS_RULE_INVALID")
            if not isinstance(r.get("text"),str) or not r["text"].strip():
                raise DomainJudgeBlocked("ANALYSIS_RULE_INVALID")
            if r.get("pending_decision") is True:
                raise DomainJudgeBlocked("REQUIRES_DECISION_PENDING_ANALYSIS_RULE")
            domains=r.get("domains")
            if not isinstance(domains,list) or not domains or any(not isinstance(d,str) or not d for d in domains):
                raise DomainJudgeBlocked("ANALYSIS_DOMAIN_BINDING_MISSING")
            if any(d not in strategy["active_domains"] and d!="GLOBAL" for d in domains):
                raise DomainJudgeBlocked("UNCLASSIFIED_ANALYSIS_DOMAIN")
            if set(domains).intersection(set(requested_domains)|{"GLOBAL"}):
                selected.append({"id":r["id"],"domain":kind,"text":r["text"],"source_ref":r.get("source_ref")})
            seen.add(r["id"])
    if any(not isinstance(r["source_ref"],str) or not r["source_ref"] for r in selected):
        raise DomainJudgeBlocked("ANALYSIS_PROVENANCE_MISSING")
    projected["analysis_rules"]=sorted(selected,key=lambda r:r["id"])
    projected["required_rule_ids"]=sorted([r["id"] for r in projected["rules"]]+[r["id"] for r in selected])
    content=json.dumps({k:v for k,v in projected.items() if k not in ("projection_sha256","estimated_tokens")},sort_keys=True,separators=(",",":")).encode()
    projected["projection_sha256"]=hashlib.sha256(content).hexdigest()
    projected["estimated_tokens"]=(len(content)+3)//4
    return projected

def deterministic_judge_complete(*, projection):
    """Self-contained structural floor; does not accept caller-selected required IDs."""
    if not isinstance(projection,dict) or projection.get("status")!="CANDIDATE_NOT_ADMITTED":
        return {"status":"BLOCKED","code":"PROJECTION_NOT_CANDIDATE"}
    rules=projection.get("rules")
    analysis=projection.get("analysis_rules")
    ids=projection.get("required_rule_ids")
    if not isinstance(rules,list) or not isinstance(analysis,list) or not isinstance(ids,list):
        return {"status":"BLOCKED","code":"RULE_COLLECTION_MISSING"}
    expected=[r.get("id") for r in rules+analysis if isinstance(r,dict)]
    if len(expected)!=len(rules)+len(analysis) or any(not isinstance(x,str) or not x for x in expected):
        return {"status":"BLOCKED","code":"RULE_COLLECTION_INVALID"}
    if len(set(expected))!=len(expected) or sorted(expected)!=ids:
        return {"status":"BLOCKED","code":"REQUIRED_RULE_OMITTED"}
    for r in analysis:
        if not isinstance(r.get("source_ref"),str) or not r["source_ref"]:
            return {"status":"BLOCKED","code":"ANALYSIS_PROVENANCE_MISSING"}
    # Detect post-projection mutations before returning PASS on the collection.
    # This is local integrity only; the producer/caller SHA still needs
    # independent, governed source attestation before real admission.
    content = json.dumps(
        {k:v for k,v in projection.items()
         if k not in ("projection_sha256","estimated_tokens")},
        sort_keys=True,separators=(",",":"),
    ).encode()
    digest = hashlib.sha256(content).hexdigest()
    if (projection.get("projection_sha256") != digest or
            projection.get("estimated_tokens") != (len(content)+3)//4):
        return {"status":"BLOCKED","code":"PROJECTION_CONTENT_DIGEST_DRIFT"}
    return {"status":"PASS_CANDIDATE_ONLY","code":"DETERMINISTIC_COLLECTION_PARITY_NOT_AUTHORIZED"}
