"""PG-03_C2 isolated regression: canonical raw catalog -> existing C5 projector."""
import copy
import hashlib
import json

from pg03_c2_catalog_adapter_v1 import adapt_catalog_for_domain_projection, C2CatalogBlocked
from pg03_domain_judges_v1 import (
    project_rules_with_analysis, deterministic_judge_complete, DomainJudgeBlocked,
)

CATALOG = {
    "schema_version": "LF_STANDARDS_CATALOG_V1",
    "catalog_version": "0.7.0",
    "status": "BORRADOR_EN_REPO_DE_CALIFICACION",
    "domains": [
        {"id": "STD-GEN", "applies_to": ["all"]},
        {"id": "STD-BE", "applies_to": ["java-spring"]},
        {"id": "STD-FE", "applies_to": ["nextjs-typescript"]},
    ],
    "rules": [
        {"id": "STD-GEN-01", "domain": "STD-GEN", "status": "APROBADO", "rule": "Global rule"},
        {"id": "STD-BE-01", "domain": "STD-BE", "status": "APROBADO", "rule": "Backend rule"},
        {"id": "STD-FE-01", "domain": "STD-FE", "status": "APROBADO", "rule": "Frontend rule"},
    ],
}
def raw(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
def call(catalog=CATALOG, sha=None, requested=None):
    data = raw(catalog)
    return adapt_catalog_for_domain_projection(
        raw_catalog=data,
        expected_sha256=hashlib.sha256(data).hexdigest() if sha is None else sha,
        requested_domains=["STD-BE"] if requested is None else requested,
    )

before = copy.deepcopy(CATALOG)
adapter = call()
assert CATALOG == before
assert adapter["status"] == "CANDIDATE_NOT_ADMITTED" and adapter["authority"] is False
assert adapter["projected_rules_count"] == 2 and adapter["source_rules_count"] == 3
assert [r["id"] for r in adapter["catalog"]["rules"]] == ["STD-GEN-01", "STD-BE-01"]
assert adapter["catalog"]["rules"][0]["domain"] == "GLOBAL"
assert adapter["catalog"]["rules"][0]["source_domain"] == "STD-GEN"
assert all(adapter[k] is False for k in (
    "skills_selection_verified", "precedence_verified",
    "l3_type_b_verified", "catalog_release_verified",
))
assert call() == adapter

strategy = {
    "status": "CANDIDATE_NOT_ADMITTED", "production_authority": False,
    "active_domains": ["STD-BE"],
}
type_a = [{"id": "A-1", "text": "Exact business rule from Analysis",
           "domains": ["STD-BE"], "source_ref": "fixture://A9/rule"}]
inv = [{"id": "INV-1", "text": "Invariant from Analysis",
        "domains": ["GLOBAL"], "source_ref": "fixture://A9/invariant"}]
projection = project_rules_with_analysis(
    strategy=strategy, catalog=adapter["catalog"],
    requested_domains=["STD-BE"], analysis_rules=type_a,
    analysis_invariants=inv,
)
assert [r["id"] for r in projection["rules"]] == ["STD-BE-01", "STD-GEN-01"]
assert [r["id"] for r in projection["analysis_rules"]] == ["A-1", "INV-1"]
assert deterministic_judge_complete(projection=projection)["status"] == "PASS_CANDIDATE_ONLY"
assert type_a[0]["text"] == projection["analysis_rules"][0]["text"]
assert adapter["catalog_sha256"] == hashlib.sha256(raw(CATALOG)).hexdigest()

def negative(label, modified, reason, requested=None, sha=None):
    try:
        call(modified, requested=requested, sha=sha)
    except C2CatalogBlocked as exc:
        assert str(exc) == reason, (label, str(exc), reason)
    else:
        raise AssertionError("Unexpected adapter PASS: " + label)
    print("PG03_C2_CATALOG_ADAPTER_NEGATIVE_PASS=" + label)

negative("digest_drift", CATALOG, "CATALOG_DIGEST_DRIFT", sha="0"*64)
negative("schema", {**CATALOG, "schema_version": "BAD"}, "CATALOG_SCHEMA_INVALID")
negative("unknown_domain", CATALOG, "UNKNOWN_ACTIVE_DOMAIN", requested=["STD-DB"])
negative("duplicate_domain", CATALOG, "ACTIVE_DOMAINS_INVALID", requested=["STD-BE", "STD-BE"])
negative("release_claim", {**CATALOG, "status": "RELEASED"}, "CATALOG_QUALIFICATION_STATUS_INVALID")
invalid = copy.deepcopy(CATALOG)
invalid["rules"][0]["id"] = invalid["rules"][1]["id"]
negative("duplicate_rule", invalid, "CATALOG_RULE_INVALID")
invalid = copy.deepcopy(CATALOG)
invalid["rules"][1]["rule"] = ""
negative("missing_text", invalid, "CATALOG_RULE_TEXT_MISSING")
invalid = copy.deepcopy(CATALOG)
invalid["rules"][1]["domain"] = "UNKNOWN"
negative("unknown_rule_domain", invalid, "CATALOG_RULE_INVALID")

# Existing C5 judge owns pending-rule decision, not a second rule engine.
pending = copy.deepcopy(CATALOG)
pending["rules"][1]["status"] = "PENDIENTE_REVISION"
pending_adapter = call(pending)
try:
    project_rules_with_analysis(
        strategy=strategy, catalog=pending_adapter["catalog"],
        requested_domains=["STD-BE"], analysis_rules=type_a,
        analysis_invariants=inv,
    )
except DomainJudgeBlocked as exc:
    assert str(exc) == "RULE_STATUS_NOT_ADMITTED"
else:
    raise AssertionError("Pending catalog rule bypassed existing judge")

print("PASS_PG03_C2_CATALOG_ADAPTER positive=1 negative=8 "
      "type_a_preserved=2 backend_only=true global_l1=true "
      "pending_rule_blocked=true existing_projector_reused=true "
      "skills_selection_verified=false precedence_verified=false "
      "catalog_release_verified=false authority=NONE runtime_verified=false")
