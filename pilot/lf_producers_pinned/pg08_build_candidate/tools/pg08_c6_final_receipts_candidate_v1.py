"""Late C6 feedback consolidation: C6 -> C7 -> C8, not a cyclic dependency.

C6 captures C1-C5. C7 needs C6, C8 needs C7. The final manifest MUST be
a post-C8 projection; it never overwrites the upstream C6 object. All
checks and fingerprints remain reported/unverified until a trusted runner
provides independently read-back evidence.
"""
import hashlib
import json
import re
from copy import deepcopy

SHA=re.compile(r"^[0-9a-f]{64}$")
HEAD=re.compile(r"^[0-9a-f]{40}$")
class PG08FinalReceiptBlocked(ValueError):pass

def block(code):raise PG08FinalReceiptBlocked(code)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def valid(v):return isinstance(v,str) and bool(v.strip())
def frozen(obj,schema):
    if not isinstance(obj,dict) or obj.get("schema_version")!=schema:
        block("PG08_FINAL_SOURCE_SCHEMA_INVALID")
    sha=obj.get("candidate_sha256")
    if not isinstance(sha,str) or not SHA.fullmatch(sha) or sha!=digest({k:v for k,v in obj.items() if k!="candidate_sha256"}):
        block("PG08_FINAL_SOURCE_DIGEST_DRIFT")
    if (obj.get("status")!="SOURCE_ONLY_NOT_ADMITTED"
        or obj.get("handoff_allowed") is not False
        or obj.get("production_authority") is not False):
        block("PG08_FINAL_SOURCE_AUTHORITY_FORBIDDEN")
    return sha

def indexed(rows):
    if not isinstance(rows,list) or not rows:block("PG08_FINAL_SOLUTION_ROWS_INVALID")
    result={}
    for row in rows:
        if not isinstance(row,dict) or not valid(row.get("solution_id")) or row["solution_id"] in result:
            block("PG08_FINAL_SOLUTION_ID_INVALID")
        result[row["solution_id"]]=row
    return result

def consolidate_pg08_c6_c7_c8(*,pg08_c6,pg08_c7,pg08_c8):
    h6=frozen(pg08_c6,"PG08_C6_CHECK_RECEIPT_FEEDBACK_CANDIDATE_V1")
    h7=frozen(pg08_c7,"PG08_C7_ARCH_BOUNDARY_CANDIDATE_V1")
    h8=frozen(pg08_c8,"PG08_C8_IAC_CONTAINER_CANDIDATE_V1")
    if (pg08_c7.get("source_pg08_c6_sha256")!=h6
        or pg08_c8.get("source_pg08_c7_sha256")!=h7
        or pg08_c7.get("source_pg08_c1_sha256")!=pg08_c6.get("source_digests",{}).get("c1")
        or pg08_c8.get("source_pg08_c1_sha256")!=pg08_c6.get("source_digests",{}).get("c1")):
        block("PG08_FINAL_UPSTREAM_DIGEST_LINK_INVALID")
    if pg08_c6.get("feedback_only") is not True or any(
        pg08_c6.get(k) is not False for k in ("pg08_c6_pass","pg08_c6_admitted","receipts_authenticated","tool_execution_verified")
    ) or any(pg08_c7.get(k) is not False for k in ("pg08_c7_pass","pg08_c7_admitted","receipts_authenticated")
    ) or any(pg08_c8.get(k) is not False for k in ("pg08_c8_pass","pg08_c8_admitted","receipts_authenticated")):
        block("PG08_FINAL_PREMATURE_PASS_OR_RECEIPT")
    repo=pg08_c6.get("target_repo")
    head=pg08_c6.get("base_head_sha")
    if not valid(repo) or not isinstance(head,str) or not HEAD.fullmatch(head):
        block("PG08_FINAL_TARGET_MISSING")
    if any(x.get("target_repo")!=repo or x.get("base_head_sha")!=head for x in (pg08_c7,pg08_c8)):
        block("PG08_FINAL_TARGET_DRIFT")
    s6,s7,s8=[indexed(x.get("solutions")) for x in (pg08_c6,pg08_c7,pg08_c8)]
    if not (set(s6)==set(s7)==set(s8)):
        block("PG08_FINAL_SOLUTION_COVERAGE_DRIFT")
    results=[]
    for sid in sorted(s6):
        a,b,c=s6[sid],s7[sid],s8[sid]
        for field in ("candidate_head_sha_reported","diff_sha256_reported","executor_mode_reported"):
            if a.get(field)!=b.get(field) or a.get(field)!=c.get(field):
                block("PG08_FINAL_HEAD_DIFF_EXECUTOR_DRIFT")
        checks=[]
        original=a.get("checks")
        if not isinstance(original,list) or not original:
            block("PG08_FINAL_C1_C5_RECEIPTS_MISSING")
        for row in original:
            if not isinstance(row,dict) or row.get("checkpoint") not in {
                "PG-08_C1","PG-08_C2","PG-08_C3","PG-08_C4","PG-08_C5"}:
                block("PG08_FINAL_C6_CHECK_INVALID")
            checks.append(deepcopy(row))
        for stage,src,required in (("PG-08_C7",b,{"SPRING_MODULITH_VERIFY","ARCHUNIT"}),
                                    ("PG-08_C8",c,{"TERRAFORM_FMT","TERRAFORM_VALIDATE","IAC_LINT",
                                     "FLOCI_PLAN","FLOCI_APPLY","CONTAINER_BUILD","DOCKER_COMPOSE_UP",
                                     "CONTAINER_HEALTHCHECK"})):
            observed=src.get("checks_reported")
            if not isinstance(observed,list) or {row.get("kind") for row in observed if isinstance(row,dict)}!=required or len(observed)!=len(required):
                block("PG08_FINAL_C7_C8_CHECK_COVERAGE_DRIFT")
            for row in observed:
                check={
                    "check_id":stage+":"+row["kind"],
                    "checkpoint":stage,
                    "kind":row["kind"],
                    "reported_result":row.get("reported_result"),
                    "source_check_sha256":digest(row),
                    "command_id_reported":row.get("command_id_reported"),
                    "command_ref_reported":row.get("command_ref_reported"),
                    "tool_name_reported":row.get("tool_name_reported"),
                    "tool_version_reported":row.get("tool_version_reported"),
                    "config_sha256_reported":row.get("config_sha256_reported"),
                    "stdout_sha256_reported":row.get("stdout_sha256_reported"),
                    "stderr_sha256_reported":row.get("stderr_sha256_reported"),
                    "execution_receipt_ref_reported":row.get("execution_receipt_ref_reported"),
                    "receipt_authenticated":False,
                    "tool_execution_verified":False,
                    "feedback_only":True
                }
                if check["reported_result"] not in ("PASS","FAIL","BLOCKED","NOT_RUN"):
                    block("PG08_FINAL_REPORTED_RESULT_INVALID")
                if check["reported_result"]=="PASS":
                    if not all(valid(check.get(k)) for k in (
                        "command_id_reported","command_ref_reported","tool_name_reported",
                        "tool_version_reported","execution_receipt_ref_reported")) or any(
                        not isinstance(check.get(k),str) or not SHA.fullmatch(check[k])
                        for k in ("config_sha256_reported","stdout_sha256_reported","stderr_sha256_reported")):
                        block("PG08_FINAL_C7_C8_PASS_INSUFFICIENT_DIGESTS")
                checks.append(check)
        if {x["checkpoint"] for x in checks}!={"PG-08_C1","PG-08_C2","PG-08_C3","PG-08_C4","PG-08_C5","PG-08_C7","PG-08_C8"}:
            block("PG08_FINAL_STAGE_COVERAGE_INCOMPLETE")
        results.append({
            "solution_id":sid,
            "candidate_head_sha_reported":a["candidate_head_sha_reported"],
            "diff_sha256_reported":a["diff_sha256_reported"],
            "executor_mode_reported":a["executor_mode_reported"],
            "feedback_checks":sorted(checks,key=lambda x:x["check_id"]),
            "checkpoint_coverage":["PG-08_C1","PG-08_C2","PG-08_C3","PG-08_C4",
                "PG-08_C5","PG-08_C7","PG-08_C8"],
            "authentic_receipts_verified":False,"quality_verdict_issued":False})
    result={
        "schema_version":"PG08_C6_C7_C8_FINAL_FEEDBACK_CANDIDATE_V1",
        "status":"SOURCE_ONLY_NOT_ADMITTED",
        "source_pg08_c6_sha256":h6,
        "source_pg08_c7_sha256":h7,
        "source_pg08_c8_sha256":h8,
        "target_repo":repo,"base_head_sha":head,
        "solutions":results,
        "receipt_completeness_verified":False,
        "tool_execution_verified":False,
        "stdout_stderr_readback_verified":False,
        "feedback_only":True,"final_verdict_issued":False,
        "production_authority":False,"handoff_allowed":False,
        "next_gate":"EXACT_HEAD_AUTHENTIC_RECEIPTS_FOR_C1_C8"}
    result["candidate_sha256"]=digest(result)
    return result

def reject_falsified_pass_fingerprint(*,reported_check,independent_observation):
    """Pure diagnostic; the caller must independently acquire observation.
    Does not run commands and never labels the observation authenticated.
    """
    if not isinstance(reported_check,dict) or reported_check.get("reported_result")!="PASS":
        block("PG08_FINGERPRINT_ONLY_FOR_CLAIMED_PASS")
    required={"command_text","stdout_text","stderr_text","command_sha256",
              "stdout_sha256","stderr_sha256","exit_code"}
    if not isinstance(independent_observation,dict) or set(independent_observation)!=required:
        block("PG08_FINGERPRINT_OBSERVATION_INVALID")
    obs=independent_observation
    if any(not isinstance(obs[k],str) for k in ("command_text","stdout_text","stderr_text")) or type(obs["exit_code"]) is not int:
        block("PG08_FINGERPRINT_TEXT_OR_EXIT_INVALID")
    for key,body in (("command_sha256","command_text"),("stdout_sha256","stdout_text"),
                     ("stderr_sha256","stderr_text")):
        actual=hashlib.sha256(obs[body].encode("utf-8")).hexdigest()
        if obs[key]!=actual:
            block("PG08_FINGERPRINT_INDEPENDENT_OBSERVATION_INCONSISTENT")
    if obs["exit_code"]!=0:
        block("PG08_FINGERPRINT_PASS_EXIT_NONZERO")
    fields=(("command_sha256","command_sha256_reported"),
            ("stdout_sha256","stdout_sha256_reported"),
            ("stderr_sha256","stderr_sha256_reported"))
    for obskey,reportkey in fields:
        if reported_check.get(reportkey)!=obs[obskey]:
            block("PG08_FINGERPRINT_REPORTED_PASS_MISMATCH")
    return {"status":"REPORTED_FINGERPRINT_MATCH_UNVERIFIED",
            "independent_observer_authenticated":False,
            "command_executed_by_this_component":False,
            "receipt_authenticated":False,"final_pass":False}
