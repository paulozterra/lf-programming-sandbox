"""PG03_C2: synthetic output of original C6 skills.select, not a new selector."""
import copy
import hashlib
import json

from pg03_c2_skill_receipt_binding_v1 import validate_skill_selection_receipt

source = {
    "schema_version": "LF_STACK_SKILL_V1",
    "skill_id": "spring-boot",
    "skill_version": "0.3.0",
    "catalog_compat": "0.7",
    "domains": ["STD-BE", "STD-API", "STD-GEN"],
    "exclude_rule_ids": [],
}
raw = json.dumps(source, sort_keys=True).encode()
selection = {
    "status": "CANDIDATE_NOT_ADMITTED",
    "run_id": "SYNTHETIC-PG03-RUN",
    "stack_commit": "a"*40,
    "catalog_sha256": "b"*64,
    "selector_repo": "paulozterra/lf-programming-sandbox",
    "selector_path": "standards/tools/skills.py",
    "selector_commit": "ab361cf947fb9a34c874bf3e786b7f7478c85aa9",
    "active_domains": ["STD-API", "STD-BE"],
    "skills": [{"skill": "spring-boot", "skill_version": "0.3.0",
                "skill_json_sha256": hashlib.sha256(raw).hexdigest()}],
}
params = dict(selection=selection,source_skill_jsons={"spring-boot":raw},
    expected_run_id="SYNTHETIC-PG03-RUN",expected_domains=["STD-API","STD-BE"],
    expected_stack_commit="a"*40,expected_catalog_sha256="b"*64,
    expected_selector_commit="ab361cf947fb9a34c874bf3e786b7f7478c85aa9")
ok = validate_skill_selection_receipt(**params)
assert ok["status"] == "CANDIDATE_NOT_ADMITTED" and ok["authority"] is False
assert ok["skills"] == ["spring-boot"] and ok["selector_execution_verified"] is False
assert ok["dispatch_allowed"] is False
assert validate_skill_selection_receipt(**copy.deepcopy(params)) == ok

cases = []
def neg(label, code, change):
    args = copy.deepcopy(params)
    change(args)
    out = validate_skill_selection_receipt(**args)
    assert out["status"] == "BLOCKED" and out["code"] == code, (label,out)
    assert out["dispatch_allowed"] is False and out["authority"] is False
    cases.append(label)
    print("PG03_C2_SKILL_RECEIPT_NEGATIVE_PASS=" + label)

neg("wrong_run","RUN_OR_STACK_DRIFT",lambda a:a["selection"].update(run_id="OTHER"))
neg("wrong_stack","RUN_OR_STACK_DRIFT",lambda a:a["selection"].update(stack_commit="c"*40))
neg("wrong_catalog","CATALOG_PIN_DRIFT",lambda a:a["selection"].update(catalog_sha256="c"*64))
neg("wrong_selector_commit","SELECTOR_PROVENANCE_DRIFT",lambda a:a["selection"].update(selector_commit="c"*40))
neg("wrong_selector_path","SELECTOR_PROVENANCE_DRIFT",lambda a:a["selection"].update(selector_path="forged.py"))
neg("missing_source","SKILL_SOURCE_MISSING",lambda a:a.update(source_skill_jsons={}))
neg("tampered_source","SKILL_DIGEST_DRIFT",lambda a:a.update(source_skill_jsons={"spring-boot":raw+b" "}))
neg("wrong_version","SKILL_VERSION_DRIFT",lambda a:a["selection"]["skills"][0].update(skill_version="0.2.0"))
neg("duplicate_skill","SKILL_DUPLICATE",lambda a:a["selection"]["skills"].append(copy.deepcopy(a["selection"]["skills"][0])))
neg("coverage_missing","ACTIVE_DOMAIN_SKILL_COVERAGE_MISSING",lambda a:a.update(expected_domains=["STD-API","STD-BE","STD-DB"]) or a["selection"].update(active_domains=["STD-API","STD-BE","STD-DB"]))
neg("other_domain","UNNEEDED_SKILL_FOR_ACTIVE_DOMAINS",lambda a:a.update(expected_domains=["STD-DB"]) or a["selection"].update(active_domains=["STD-DB"]))
neg("invalid_status","SELECTION_CANDIDATE_REQUIRED",lambda a:a["selection"].update(status="ACCEPT"))
neg("untrusted_exclusion","SKILL_EXCLUSIONS_REQUIRE_REVIEW",lambda a: (
 a.update(source_skill_jsons={"spring-boot":json.dumps({**source,"exclude_rule_ids":[{"rule_id":"STD-BE-01","reason":"test"}]},sort_keys=True).encode()}),
 a["selection"]["skills"][0].update(skill_json_sha256=hashlib.sha256(a["source_skill_jsons"]["spring-boot"]).hexdigest())))
assert len(cases)==13
print("PASS_PG03_C2_SKILL_RECEIPT_BINDING positive=1 negatives=13 "
      "source_digests=true run_bound=true domain_cover=true "
      "selector_reused_by_contract=true selector_execution_verified=false "
      "authority=NONE runtime_verified=false")
