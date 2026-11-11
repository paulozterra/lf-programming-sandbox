"""PG-02 candidate classifier; pure function; NO admission authority."""
import hashlib
import json

class PG02Blocked(ValueError):
    pass

def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def digest(obj):
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()

def verify_catalog_binding(mapping, expected_ref=None, expected_sha256=None):
    """Optional readback pin. An assertion of CURRENT by a caller is never authority."""
    if not isinstance(mapping, dict):
        raise PG02Blocked("CATALOG_INVALID")
    if expected_ref is not None and mapping.get("source_ref") != expected_ref:
        raise PG02Blocked("CATALOG_SOURCE_DRIFT")
    if expected_sha256 is not None and digest(mapping) != expected_sha256:
        raise PG02Blocked("CATALOG_DIGEST_DRIFT")
    return digest(mapping)



VALID_STATUSES={"REQUIRED","REUSE_AS_IS","NOT_APPLICABLE"}
VALID_CLOSURES={"CLOSED","BLOCKED"}
VALID_SCOPE_STATES={"READY","NEED_MORE_EVIDENCE","REQUIRES_DECISION","BLOCKED","NOT_APPLICABLE"}

def classify(snapshot, mapping, *, expected_catalog_ref=None, expected_catalog_sha256=None, pg01_binding=None):
    if not isinstance(snapshot,dict): raise PG02Blocked("CONTRADICTION:INVALID_SHAPE")
    if snapshot.get("schema_version")!="PROGRAMMING_CONTEXT_SNAPSHOT_V1":
        raise PG02Blocked("SNAPSHOT_SCHEMA_INVALID")
    cov=snapshot.get("material_front_coverage")
    if not isinstance(cov,dict) or cov.get("all_material_fronts_accounted") is not True or cov.get("unmapped_material_signals") != []:
        raise PG02Blocked("CONTRADICTION:A7_UNACCOUNTED_MATERIAL_SIGNAL")
    scopes=snapshot.get("scope_readiness")
    matrix=snapshot.get("scope_front_matrix")
    fronts=cov.get("material_fronts")
    if not all(isinstance(x,list) for x in (scopes,matrix,fronts)) or not scopes or not fronts:
        raise PG02Blocked("CONTRADICTION:INVALID_SCOPE_MATRIX")
    if any(not isinstance(x,dict) for x in scopes+matrix+fronts):
        raise PG02Blocked("CONTRADICTION:INVALID_SHAPE")
    if any(not isinstance(x.get("scope_id"),str) or not x["scope_id"] or not isinstance(x.get("material_front_refs"),list)
           or any(not isinstance(v,str) for v in x["material_front_refs"]) for x in scopes):
        raise PG02Blocked("CONTRADICTION:INVALID_SHAPE")
    if any(not isinstance(f.get("front_id"),str) or not f["front_id"] or not isinstance(f.get("scope_refs"),list)
           or not f["scope_refs"] or any(not isinstance(v,str) for v in f["scope_refs"]) for f in fronts):
        raise PG02Blocked("CONTRADICTION:INVALID_SHAPE")
    if any(not isinstance(r.get("scope_id"),str) or not isinstance(r.get("front_id"),str) for r in matrix):
        raise PG02Blocked("CONTRADICTION:INVALID_SHAPE")
    if any(x.get("status") not in VALID_SCOPE_STATES for x in scopes):
        raise PG02Blocked("CONTRADICTION:READINESS_INVALID")
    if not isinstance(snapshot.get("target_granularity"),dict) or not snapshot["target_granularity"]:
        raise PG02Blocked("CONTRADICTION:A2_MISSING")
    sidx={x["scope_id"]:x for x in scopes}
    fidx={x["front_id"]:x for x in fronts}
    if len(sidx)!=len(scopes) or len(fidx)!=len(fronts):
        raise PG02Blocked("CONTRADICTION:DUPLICATE")
    if any(sid not in sidx for f in fronts for sid in f["scope_refs"]) or any(r["scope_id"] not in sidx for r in matrix):
        raise PG02Blocked("CONTRADICTION:A7_UNKNOWN_SCOPE")
    if any(r["front_id"] not in fidx for r in matrix):
        raise PG02Blocked("CONTRADICTION:A7_UNKNOWN_FRONT")
    if any(f.get("status") not in VALID_STATUSES or f.get("closure") not in VALID_CLOSURES for f in fronts):
        raise PG02Blocked("CONTRADICTION:A7_ENUM")
    expected={(sid,fid) for fid,f in fidx.items() for sid in f["scope_refs"]}
    observed={(r["scope_id"],r["front_id"]) for r in matrix}
    if observed!=expected or len(observed)!=len(matrix):
        raise PG02Blocked("CONTRADICTION:MATRIX_MISMATCH")
    for r in matrix:
        f=fidx[r["front_id"]]
        if f.get("status") not in VALID_STATUSES or f.get("closure") not in VALID_CLOSURES:
            raise PG02Blocked("CONTRADICTION:A7_ENUM")
        if (r.get("front_status"),r.get("front_closure"))!=(f["status"],f["closure"]):
            raise PG02Blocked("CONTRADICTION:A7_PARITY")
    if not isinstance(mapping,dict): raise PG02Blocked("CATALOG_NOT_AUTHORIZED")
    rules=mapping.get("front_kind_domains")
    if mapping.get("state")!="SOURCE_ONLY_CANDIDATE" or not isinstance(rules,dict):
        raise PG02Blocked("CATALOG_NOT_AUTHORIZED")
    verify_catalog_binding(mapping,expected_catalog_ref,expected_catalog_sha256)
    # A2 and target stack remain source-bound; no default stack is inferred.
    granularity = snapshot["target_granularity"]
    if not granularity.get("level") or not granularity.get("target_ref"):
        raise PG02Blocked("CONTRADICTION:A2_TARGET_IDENTITY_MISSING")
    # PG-01_C4 owns the architecture framework; A9 does not define stack_profile.
    # This candidate is not an authenticated reader; external readback is still required.
    if not isinstance(pg01_binding,dict) or pg01_binding.get("source")!="PG01_C4":
        raise PG02Blocked("MISSING:PG01_C4_FRAMEWORK_REQUIRED")
    if not all(isinstance(pg01_binding.get(k),str) and pg01_binding[k] for k in ("architecture_repo","architecture_commit","manifest_digest_sha256")):
        raise PG02Blocked("MISSING:PG01_C4_FRAMEWORK_INCOMPLETE")
    stack = pg01_binding.get("architecture_profile")
    if not isinstance(stack,dict) or not isinstance(stack.get("active_layers"),list) or not stack["active_layers"]:
        raise PG02Blocked("MISSING:PG01_C4_ARCHITECTURE_LAYERS")
    layers = stack["active_layers"]
    if any(not isinstance(x, str) or not x for x in layers):
        raise PG02Blocked("CONTRADICTION:STACK_LAYERS_INVALID")
    active_layers = set(layers)
    if len(active_layers) != len(layers):
        raise PG02Blocked("CONTRADICTION:STACK_LAYERS_INVALID")
    scoped_layers = mapping.get("domain_stack_layers")
    if not isinstance(scoped_layers,dict):
        raise PG02Blocked("MISSING:DOMAIN_STACK_BINDINGS")
    rows=[]
    for s in sorted(scopes,key=lambda x:x["scope_id"]):
        sid=s["scope_id"]
        links=sorted((r for r in matrix if r["scope_id"]==sid),key=lambda x:x["front_id"])
        if {r["front_id"] for r in links}!=set(s.get("material_front_refs",[])):
            raise PG02Blocked("CONTRADICTION:BIDIRECTIONAL_MAPPING")
        reasons=[]
        domains=set()
        for r in links:
            f=fidx[r["front_id"]]
            status=f["status"]
            effect=r.get("effect_on_scope")
            if status=="NOT_APPLICABLE":
                if effect!="NOT_APPLICABLE": raise PG02Blocked("CONTRADICTION:NA_EFFECT")
                continue
            if f["closure"]=="BLOCKED" or effect=="BLOCKS":
                reasons.append(f["front_id"]+":BLOCKED")
                continue
            if effect!="PRESERVE": raise PG02Blocked("CONTRADICTION:EFFECT")
            kinds=rules.get(f.get("front_kind"))
            if not kinds: reasons.append(f["front_id"]+":UNMAPPED")
            else:
                for domain in kinds:
                    applicable = scoped_layers.get(domain)
                    if not isinstance(applicable,list) or not applicable:
                        raise PG02Blocked("MISSING:DOMAIN_STACK_BINDING:"+str(domain))
                    if any(not isinstance(layer, str) or not layer for layer in applicable) or len(set(applicable)) != len(applicable):
                        raise PG02Blocked("CONTRADICTION:DOMAIN_STACK_LAYERS_INVALID:"+str(domain))
                    if active_layers.intersection(applicable):
                        domains.add(domain)
                    else:
                        reasons.append(f["front_id"]+":STACK_NOT_APPLICABLE:"+domain)
        if s["status"]=="READY" and any(fidx[r["front_id"]]["status"]!="NOT_APPLICABLE" and fidx[r["front_id"]]["closure"]=="BLOCKED" for r in links):
            raise PG02Blocked("CONTRADICTION:READY_SCOPE_BLOCKING_FRONT")
        if any(fidx[r["front_id"]]["closure"]=="CLOSED" and r.get("effect_on_scope")=="BLOCKS" for r in links):
            raise PG02Blocked("CONTRADICTION:CLOSED_FRONT_BLOCKS")
        ready=s.get("status")=="READY" and not reasons
        rows.append({"scope_id":sid,"state":"READY_FOR_CLASSIFICATION" if ready else "BLOCKED",
                     "candidate_domains":sorted(domains) if ready else [],"blockers":sorted(reasons)})
    # M6: include PG-01 context identity only as externally supplied evidence.
    # Python JSON digest is NOT PostgreSQL jsonb::text SHA256.
    identity = pg01_binding.get("context_binding")
    if not isinstance(identity,dict) or not all(isinstance(identity.get(k),str) and identity[k] for k in ("context_id","context_sha256","receipt_ref")):
        raise PG02Blocked("MISSING:PG01_CONTEXT_RECEIPT_BINDING")
    h=identity["context_sha256"]
    if len(h)!=64 or any(c not in "0123456789abcdef" for c in h):
        raise PG02Blocked("CONTRADICTION:PG01_CONTEXT_DIGEST_INVALID")
    return {"schema_version":"PG02_CLASSIFICATION_CANDIDATE_V2",
            "status":"CANDIDATE_NOT_ADMITTED","source_digest":digest(snapshot),"source_digest_note":"PYTHON_JSON_ONLY_NOT_PG01_HASH","context_id":identity["context_id"],"context_sha256":identity["context_sha256"],"pg01_receipt_ref":identity["receipt_ref"],"architecture_repo":pg01_binding["architecture_repo"],"architecture_commit":pg01_binding["architecture_commit"],"manifest_digest_sha256":pg01_binding["manifest_digest_sha256"],"target_granularity":granularity,
            "scopes":rows}


# Compatibility: old module delegates to the single primary implementation.
def classify_scopes(snapshot, mapping):
    return classify(snapshot, mapping)
