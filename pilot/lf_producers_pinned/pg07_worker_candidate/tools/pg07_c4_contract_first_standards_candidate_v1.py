"""PG-07_C4: contract-first policy selection and pre-patch formatter plan.

Candidate-only binding: reuse current C6 Skills/STD catalog, C3 selected
material references and existing governed formatter toolchain. No rule
inference, STD-API-06 text fabrication, formatter invocation or patch delivery.
"""
import hashlib
import json
import re

class StandardsPlanBlocked(ValueError):
    pass

_SHA=re.compile(r"^[0-9a-f]{64}$")
_ALLOWED={"STD","SKILL","CONTRACT"}
def _fail(code):raise StandardsPlanBlocked(code)
def _hash(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def _ref(value):return isinstance(value,str) and bool(value.strip())
def _frozen(value,schema):
    if not isinstance(value,dict) or value.get("schema_version")!=schema:_fail("PG07_C4_SOURCE_SCHEMA_INVALID")
    digest=value.get("candidate_sha256")
    if not isinstance(digest,str) or not _SHA.fullmatch(digest) or digest!=_hash({k:v for k,v in value.items() if k!="candidate_sha256"}):
        _fail("PG07_C4_SOURCE_DIGEST_INVALID")
    return digest
def _list(value,empty=False):
    return isinstance(value,list) and (empty or bool(value)) and all(_ref(x) for x in value) and len(value)==len(set(value))

def prepare_pg07_c4(*,pg07_c1,pg07_c2,pg07_c3,standards_catalog_selection,solution_policy_plans):
    c1=_frozen(pg07_c1,"PG07_C1_WORKER_DISPATCH_PLAN_CANDIDATE_V1")
    c2=_frozen(pg07_c2,"PG07_C2_WORKER_TASK_BATCH_CANDIDATE_V1")
    c3=_frozen(pg07_c3,"PG07_C3_CONTEXT_PROJECTION_CANDIDATE_V1")
    if (pg07_c2.get("source_pg07_c1_sha256")!=c1
        or pg07_c3.get("source_pg07_c1_sha256")!=c1
        or pg07_c3.get("source_pg07_c2_sha256")!=c2
        or any(x.get("production_authority") is not False or x.get("handoff_allowed") is not False
               or x.get("dispatch_allowed") is not False or x.get("worker_invoked") is not False
               for x in (pg07_c1,pg07_c2,pg07_c3))):
        _fail("PG07_C4_SOURCE_CHAIN_OR_AUTHORITY_INVALID")
    if not isinstance(standards_catalog_selection,dict) or set(standards_catalog_selection)!={
        "catalog_ref","catalog_sha256","catalog_version","selection_ref","entries"}:
        _fail("PG07_C4_CATALOG_SHAPE_INVALID")
    catalog=standards_catalog_selection
    if (not _ref(catalog["catalog_ref"]) or not _ref(catalog["catalog_version"])
        or not _ref(catalog["selection_ref"]) or not isinstance(catalog["catalog_sha256"],str)
        or not _SHA.fullmatch(catalog["catalog_sha256"])):
        _fail("PG07_C4_CATALOG_SOURCE_INVALID")
    entries=catalog["entries"]
    if not isinstance(entries,list) or not entries:_fail("PG07_C4_CATALOG_ENTRIES_MISSING")
    standards={}
    for e in entries:
        if not isinstance(e,dict) or set(e)!={
            "rule_id","kind","source_ref","source_sha256","version",
            "ok_example_ref","no_example_ref","applies_to_solution_ids"}:
            _fail("PG07_C4_ENTRY_SHAPE_INVALID")
        rid=e["rule_id"]
        if (not _ref(rid) or rid in standards or e["kind"] not in _ALLOWED
            or not _ref(e["source_ref"]) or not _ref(e["version"])
            or not isinstance(e["source_sha256"],str) or not _SHA.fullmatch(e["source_sha256"])
            or not _list(e["applies_to_solution_ids"])):
            _fail("PG07_C4_ENTRY_INVALID")
        # OK and NO examples must be present for STD/SKILL; contract-only
        # references can carry examples but do not require invented ones.
        if e["kind"] in ("STD","SKILL") and (not _ref(e["ok_example_ref"]) or not _ref(e["no_example_ref"])):
            _fail("PG07_C4_STD_EXAMPLES_MISSING")
        if e["kind"]=="CONTRACT" and any(v is not None and not _ref(v) for v in (e["ok_example_ref"],e["no_example_ref"])):
            _fail("PG07_C4_CONTRACT_EXAMPLE_INVALID")
        standards[rid]=e
    payload=pg07_c2.get("worker_payloads")
    c3rows=pg07_c3.get("solutions")
    if not isinstance(payload,list) or not isinstance(c3rows,list):_fail("PG07_C4_TASK_SET_MISSING")
    task={}
    for row in payload:
        if not isinstance(row,dict) or not _ref(row.get("solution_id")) or row["solution_id"] in task:
            _fail("PG07_C4_TASK_ID_INVALID")
        task[row["solution_id"]]=row
    budget={}
    for row in c3rows:
        if not isinstance(row,dict) or row.get("solution_id") not in task or row["solution_id"] in budget:
            _fail("PG07_C4_BUDGET_ID_INVALID")
        budget[row["solution_id"]]=row
    if not task or set(budget)!=set(task):_fail("PG07_C4_BUDGET_TASK_COVERAGE_DRIFT")
    for entry in standards.values():
        if not set(entry["applies_to_solution_ids"]).issubset(task):
            _fail("PG07_C4_CATALOG_SOLUTION_UNKNOWN")
    if not isinstance(solution_policy_plans,list) or len(solution_policy_plans)!=len(task):
        _fail("PG07_C4_PLANS_INCOMPLETE")
    plans={}
    for plan in solution_policy_plans:
        if not isinstance(plan,dict) or set(plan)!={
            "solution_id","required_rule_ids","contract_first_ref","contract_first_rule_id",
            "formatter_commands","formatter_plan_ref"}:
            _fail("PG07_C4_PLAN_SHAPE_INVALID")
        sid=plan["solution_id"]
        if sid not in task or sid in plans:_fail("PG07_C4_PLAN_SOLUTION_DRIFT")
        if (not _list(plan["required_rule_ids"]) or not _ref(plan["contract_first_ref"])
            or not _ref(plan["formatter_plan_ref"])):
            _fail("PG07_C4_PLAN_REQUIRED_FIELDS_MISSING")
        if not isinstance(plan["formatter_commands"],list) or not plan["formatter_commands"]:
            _fail("PG07_C4_FORMATTER_PLAN_REQUIRED")
        cmds=set()
        for command in plan["formatter_commands"]:
            if not isinstance(command,dict) or set(command)!={
                "command_id","formatter_tool_ref","command_ref","scope_ref","expected_artifact_ref"}:
                _fail("PG07_C4_FORMATTER_SHAPE_INVALID")
            if (any(not _ref(command[k]) for k in command) or command["command_id"] in cmds):
                _fail("PG07_C4_FORMATTER_BINDING_INVALID")
            cmds.add(command["command_id"])
        plans[sid]=plan
    reports=[]
    for sid in sorted(task):
        plan=plans[sid]
        required=plan["required_rule_ids"]
        applicable={rid for rid,e in standards.items() if sid in e["applies_to_solution_ids"]}
        if not set(required).issubset(applicable) or set(required)!=applicable:
            _fail("PG07_C4_CATALOG_APPLICABILITY_DRIFT")
        contract_id=plan["contract_first_rule_id"]
        if not _ref(contract_id) or contract_id not in required or standards[contract_id]["kind"] not in ("STD","CONTRACT"):
            _fail("PG07_C4_CONTRACT_FIRST_BINDING_INVALID")
        c3row=budget[sid]
        if not isinstance(c3row.get("required_ref_ids"),list) or not isinstance(c3row.get("eager_ref_ids"),list) or not isinstance(c3row.get("jit_ref_ids"),list):
            _fail("PG07_C4_CONTEXT_SELECTION_INVALID")
        selected=set(c3row["required_ref_ids"])|set(c3row["eager_ref_ids"])|set(c3row["jit_ref_ids"])
        # The catalog record must be represented in C3 context by exact refs.
        missing=[rid for rid in required if rid not in selected]
        if missing:_fail("PG07_C4_MATERIAL_RULE_NOT_SELECTED_IN_C3")
        context_blocked=c3row.get("diagnostic_status")=="BLOCK_CONTEXT_BUDGET"
        rules=[{"rule_id":rid,"kind":standards[rid]["kind"],
                "version":standards[rid]["version"],"source_ref":standards[rid]["source_ref"],
                "source_sha256":standards[rid]["source_sha256"],
                "ok_example_ref":standards[rid]["ok_example_ref"],
                "no_example_ref":standards[rid]["no_example_ref"],
                "rule_runtime_verified":False} for rid in sorted(required)]
        reports.append({
            "solution_id":sid,
            "contract_first_rule_id":contract_id,
            "contract_first_ref":plan["contract_first_ref"],
            "required_rules":rules,
            "formatter_commands":plan["formatter_commands"],
            "formatter_plan_ref":plan["formatter_plan_ref"],
            "diagnostic_status":("BLOCK_CONTEXT_BUDGET" if context_blocked
                                 else "POLICY_AND_FORMATTER_PLAN_DECLARED_UNVERIFIED"),
            "formatter_execution_receipts":[],
            "formatters_executed":False,
            "patch_delivered":False,
            "dispatch_allowed":False})
    result={
        "schema_version":"PG07_C4_CONTRACT_FIRST_STANDARDS_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg07_c1_sha256":c1,
        "source_pg07_c2_sha256":c2,
        "source_pg07_c3_sha256":c3,
        "catalog_manifest_sha256":_hash(catalog),
        "catalog_ref":catalog["catalog_ref"],
        "catalog_version":catalog["catalog_version"],
        "catalog_selection_ref":catalog["selection_ref"],
        "solution_plans":reports,
        "catalog_currentness_verified":False,
        "applicability_verified_against_real_task":False,
        "std_api_06_authenticity_verified":False,
        "ok_no_examples_readback_verified":False,
        "formatter_toolchain_verified":False,
        "formatters_executed":False,
        "patch_delivered":False,
        "worker_invoked":False,
        "dispatch_allowed":False,
        "write_allowed":False,
        "production_authority":False,
        "handoff_allowed":False,
        "next_gate":"LIVE_C6_STD_RULE_READBACK_AND_POST_WORKER_FORMATTER_RECEIPTS"
    }
    result["candidate_sha256"]=_hash(result)
    return result
