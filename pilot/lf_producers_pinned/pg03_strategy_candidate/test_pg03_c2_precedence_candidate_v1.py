"""PG-03_C2 precedence 1.5 source-only qualification and negatives."""
import copy
import hashlib
import json
from pg03_c2_precedence_candidate_v1 import candidate_precedence

catalog={
    "schema_version":"LF_STANDARDS_CATALOG_V1",
    "status":"BORRADOR_EN_REPO_DE_CALIFICACION",
    "precedence":[
        "L1 (piso que nadie rebaja)",
        "Lo que trae el spec de la Fase 1 (reglas tipo A)",
        "Contratos existentes y perfil técnico del proyecto (reglas tipo B, por manifiesto)",
        "Valor por defecto del catálogo (L2)"],
    "domains":[{"id":"STD-SEC","level":"L1"},{"id":"STD-BE","level":"L2"},
               {"id":"STD-API","level":"L1/L2"}],
    "rules":[{"id":"STD-BE-01","domain":"STD-BE","status":"APROBADO","rule":"Default backend"},
             {"id":"STD-SEC-01","domain":"STD-SEC","status":"APROBADO","rule":"L1 security"},
             {"id":"STD-API-01","domain":"STD-API","status":"APROBADO","rule":"Mixed API"}]
}
def raw(data):
    return json.dumps(data,sort_keys=True,separators=(",",":")).encode()
def params(c=catalog):
    blob=raw(c)
    return dict(catalog_bytes=blob,expected_catalog_sha256=hashlib.sha256(blob).hexdigest(),
        selected_rule_ids=["STD-BE-01","STD-SEC-01"],level_evidence={},
        analysis_rules=[{"id":"A-01","text":"Exact Analysis rule","source_ref":"fixture://A9"}],
        project_rules=[{"id":"B-01","text":"Exact project rule","source_ref":"fixture://L3"}],
        conflicts=[])

args=params()
out=candidate_precedence(**args)
assert out["status"]=="CANDIDATE_NOT_ADMITTED" and out["precedence_verified"] is False
assert [x["level"] for x in out["ordered_rules"]]==["L1","A","B","L2"]
assert [x["id"] for x in out["ordered_rules"]]==["STD-SEC-01","A-01","B-01","STD-BE-01"]
assert out==candidate_precedence(**copy.deepcopy(args))
assert out["handoff_allowed"] is False and out["semantic_conflicts_verified"] is False

cases=[]
def neg(label,reason,edit):
    a=params()
    edit(a)
    res=candidate_precedence(**a)
    assert res["status"]=="BLOCKED" and res["code"]==reason,(label,res)
    assert res["handoff_allowed"] is False and res["authority"] is False
    cases.append(label)
    print("PG03_C2_PRECEDENCE_NEGATIVE_PASS="+label)
def edit_catalog(a,change):
    c=copy.deepcopy(catalog)
    change(c)
    a.update(params(c))
neg("digest_drift","CATALOG_PIN_DRIFT",lambda a:a.update(expected_catalog_sha256="0"*64))
neg("catalog_draft_only","CATALOG_NOT_QUALIFICATION_SOURCE",
    lambda a:edit_catalog(a,lambda c:c.update(status="RELEASED")))
neg("precedence_changed","CATALOG_PRECEDENCE_DRIFT",
    lambda a:edit_catalog(a,lambda c:c["precedence"].reverse()))
neg("mixed_level_unknown","MIXED_DOMAIN_RULE_LEVEL_MISSING",
    lambda a:a.update(selected_rule_ids=["STD-API-01"]))
neg("mixed_level_claim_unattested","MIXED_DOMAIN_LEVEL_READBACK_UNATTESTED",
    lambda a:a.update(selected_rule_ids=["STD-API-01"],level_evidence={
        "STD-API-01":{"level":"L1","source_ref":"fixture://rule-level","source_sha256":"a"*64}}))
neg("unselected_level_claim","EXTRANEOUS_LEVEL_CLAIM",
    lambda a:a.update(level_evidence={"STD-API-01":{"level":"L1"}}))
neg("single_level_override","UNEXPECTED_RULE_LEVEL_OVERRIDE",
    lambda a:a.update(level_evidence={"STD-BE-01":{"level":"L1"}}))
neg("catalog_pending_rule","CATALOG_RULE_NOT_APPROVED",
    lambda a:edit_catalog(a,lambda c:c["rules"][0].update(status="PENDIENTE_REVISION")))
neg("analysis_question","ANALYSIS_PENDING_DECISION",
    lambda a:a["analysis_rules"][0].update(pending_decision=True))
neg("project_question","PROJECT_PENDING_DECISION",
    lambda a:a["project_rules"][0].update(pending_decision=True))
neg("l1_override","PROJECT_L1_OVERRIDE_UNAUTHORIZED",
    lambda a:a["project_rules"][0].update(modifies_l1=True))
neg("waiver_fake","PROJECT_L1_OVERRIDE_UNAUTHORIZED",
    lambda a:a["project_rules"][0].update(waives_standard=True))
neg("duplicate_a_b","RULE_ID_COLLISION",
    lambda a:a["project_rules"][0].update(id="A-01"))
neg("duplicate_catalog_a","RULE_ID_COLLISION",
    lambda a:a["analysis_rules"][0].update(id="STD-SEC-01"))
neg("unresolved_conflict","CONFLICT_UNRESOLVED_REQUIRES_DECISION",
    lambda a:a.update(conflicts=[{"status":"OPEN","evidence_ref":"fixture://conflict"}]))
neg("self_attested_conflict","CONFLICT_CLOSURE_UNATTESTED",
    lambda a:a.update(conflicts=[{"status":"INDEPENDENTLY_CLOSED","evidence_ref":"fixture://approval"}]))
neg("conflict_register_missing","CONFLICT_REGISTER_MISSING",
    lambda a:a.update(conflicts=None))
neg("unknown_rule","SELECTED_RULES_INVALID",
    lambda a:a.update(selected_rule_ids=["STD-SEC-999"]))
neg("empty_catalog_selection","SELECTED_RULES_INVALID",
    lambda a:a.update(selected_rule_ids=[]))
neg("duplicate_catalog_selection","SELECTED_RULES_INVALID",
    lambda a:a.update(selected_rule_ids=["STD-BE-01","STD-BE-01"]))
neg("unhashable_catalog_selection","SELECTED_RULES_INVALID",
    lambda a:a.update(selected_rule_ids=[{"id":"STD-BE-01"}]))
neg("null_catalog_selection","SELECTED_RULES_INVALID",
    lambda a:a.update(selected_rule_ids=None))
neg("mixed_valid_invalid_selection","SELECTED_RULES_INVALID",
    lambda a:a.update(selected_rule_ids=["STD-BE-01",None]))
assert len(cases)==23
print("PASS_PG03_C2_PRECEDENCE_CANDIDATE positive=1 negative=23 "
      "order=L1_A_B_L2 mixed_domain_fail_closed=true "
      "semantic_conflicts_verified=false precedence_verified=false "
      "authority=NONE runtime_verified=false")
