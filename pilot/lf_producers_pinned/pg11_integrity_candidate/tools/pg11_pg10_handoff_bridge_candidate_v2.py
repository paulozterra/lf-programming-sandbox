"""Non-authoritative PG10_C5 -> PG11_C1 exact-source bridge.

The bridge requires a real PG10 C5 producer envelope (not a fabricated
direct PG11 start), PG09 C4 for run continuity, PG08 final for target base
and PG11 C1 for the same exact base/head. Caller inputs are untrusted.
"""
import hashlib
import json
import re

SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class PG10PG11BridgeBlocked(ValueError):
    pass


def _block(code):
    raise PG10PG11BridgeBlocked(code)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _freeze(obj, schema):
    if not isinstance(obj, dict) or obj.get("schema_version") != schema:
        _block("PG10_PG11_SOURCE_SCHEMA_INVALID")
    digest = obj.get("candidate_sha256")
    if (not isinstance(digest, str) or not SHA256.fullmatch(digest)
            or digest != _digest({k: v for k, v in obj.items()
                                  if k != "candidate_sha256"})):
        _block("PG10_PG11_SOURCE_DIGEST_DRIFT")
    if (obj.get("status") != "CANDIDATE_NOT_ADMITTED"
            or obj.get("production_authority") is not False
            or obj.get("handoff_allowed") is not False):
        _block("PG10_PG11_SOURCE_AUTHORITY_INVALID")
    return digest


def _freeze_pg08_c1(candidate):
    if not isinstance(candidate, dict) or candidate.get("schema_version") != "PG08_C1_BUILD_COMPILATION_CANDIDATE_V1":
        _block("PG10_PG11_V2_HEAD_LINEAGE_DRIFT")
    actual = candidate.get("candidate_sha256")
    if actual != _digest({k:v for k,v in candidate.items() if k != "candidate_sha256"}):
        _block("PG10_PG11_V2_HEAD_LINEAGE_DRIFT")
    if candidate.get("production_authority") is not False or candidate.get("handoff_allowed") is not False:
        _block("PG10_PG11_SOURCE_AUTHORITY_INVALID")
    return actual


def bridge_pg10_c5_to_pg11_c1(*, pg10_c5, pg10_c4, pg09_c4,
                             pg08_final, pg08_c1, lineage_solution_ids, pg11_c1, run_binding):
    """Return source-only linkage; do not authenticate real Git or execute gates.

    run_binding must be {run_ref,target_repo,base_head_sha,expected_head_sha}.
    Its values MUST match PG10 C5 / PG09 C4, PG08 final, PG11 C1.
    """
    h10 = _freeze(pg10_c5, "PG10_C5_NEGATIVE_ASSURANCE_CANDIDATE_V1")
    h4 = _freeze(pg10_c4, "PG10_C4_HUMAN_DECISION_PACKETS_CANDIDATE_V1")
    h9 = _freeze(pg09_c4, "PG09_C4_TYPED_ESCALATION_CANDIDATE_V1")
    h11 = _freeze(pg11_c1, "PG11_C1_DIFF_HYGIENE_CANDIDATE_V2")
    if not isinstance(pg08_final, dict) or pg08_final.get("schema_version") != (
            "PG08_C6_C7_C8_FINAL_FEEDBACK_CANDIDATE_V1"):
        _block("PG10_PG11_PG08_SCHEMA_INVALID")
    h8 = pg08_final.get("candidate_sha256")
    if (not isinstance(h8, str) or not SHA256.fullmatch(h8)
            or h8 != _digest({k: v for k, v in pg08_final.items()
                              if k != "candidate_sha256"})):
        _block("PG10_PG11_PG08_DIGEST_DRIFT")
    if (pg08_final.get("status") != "SOURCE_ONLY_NOT_ADMITTED"
            or pg08_final.get("production_authority") is not False
            or pg08_final.get("handoff_allowed") is not False
            or pg08_final.get("feedback_only") is not True
            or pg08_final.get("final_verdict_issued") is not False):
        _block("PG10_PG11_PG08_AUTHORITY_INVALID")
    if (pg10_c5.get("source_candidate_sha256", {}).get("pg10_c4") != h4
            or pg10_c5.get("run_ref") != pg10_c4.get("run_ref")
            or pg10_c5.get("run_ref") != pg09_c4.get("run_ref")
            or not isinstance(pg10_c5.get("scenarios"), list)
            or pg10_c5.get("required_case_count") != 12
            or pg10_c5.get("executed_case_count") != 0
            or pg10_c5.get("independent_verdict_issued") is not False
            or pg11_c1.get("real_git_diff_readback_verified") is not False):
        _block("PG10_PG11_UPSTREAM_CHAIN_INVALID")
    if not isinstance(run_binding, dict) or set(run_binding) != {
            "run_ref", "target_repo", "base_head_sha", "expected_head_sha"}:
        _block("PG10_PG11_BINDING_INVALID")
    run = run_binding["run_ref"]
    repo = run_binding["target_repo"]
    base = run_binding["base_head_sha"]
    head = run_binding["expected_head_sha"]
    if (not isinstance(run, str) or not run.strip()
            or not isinstance(repo, str) or not repo.strip()
            or not isinstance(base, str) or not GIT_SHA.fullmatch(base)
            or not isinstance(head, str) or not GIT_SHA.fullmatch(head)
            or base == head):
        _block("PG10_PG11_BINDING_SHAPE_INVALID")
    if run != pg10_c5.get("run_ref") or run != pg09_c4.get("run_ref"):
        _block("PG10_PG11_RUN_DRIFT")
    if repo != pg08_final.get("target_repo"):
        _block("PG10_PG11_TARGET_REPO_DRIFT")
    if (base != pg08_final.get("base_head_sha")
            or base != pg11_c1.get("expected_base_sha")):
        _block("PG10_PG11_BASE_COMMIT_DRIFT")
    if head != pg11_c1.get("expected_head_sha"):
        _block("PG10_PG11_CANDIDATE_HEAD_DRIFT")
    # Exact PG08 lineage: no caller-supplied final head can supersede PG08.
    h8c1 = _freeze_pg08_c1(pg08_c1)
    rows = pg08_c1.get("solutions")
    if (not isinstance(rows, list) or not isinstance(lineage_solution_ids, list)
            or not lineage_solution_ids or len(lineage_solution_ids) != len(set(lineage_solution_ids))):
        _block("PG10_PG11_V2_HEAD_LINEAGE_DRIFT")
    observed = {}
    for item in rows:
        if not isinstance(item, dict) or item.get("solution_id") in observed:
            _block("PG10_PG11_V2_HEAD_LINEAGE_DRIFT")
        observed[item.get("solution_id")] = item.get("candidate_head_sha_reported")
    if (set(lineage_solution_ids) != set(observed)
            or any(not isinstance(observed[sid], str) or not GIT_SHA.fullmatch(observed[sid])
                   for sid in lineage_solution_ids)
            or observed[lineage_solution_ids[-1]] != head):
        _block("PG10_PG11_V2_HEAD_LINEAGE_DRIFT")
    if pg08_c1.get("target_repo") != repo or pg08_c1.get("base_head_sha") != base:
        _block("PG10_PG11_V2_HEAD_LINEAGE_DRIFT")
    if (pg11_c1.get("clean_diff_verified") is not False
            or pg11_c1.get("pg11_c1_pass") is not False):
        _block("PG10_PG11_PREMATURE_DIFF_VERDICT")
    out = {
        "schema_version": "PG10_C5_TO_PG11_C1_HANDOFF_CANDIDATE_V2",
        "status": "CANDIDATE_NOT_ADMITTED",
        "source_pg10_c5_sha256": h10,
        "source_pg10_c4_sha256": h4,
        "source_pg09_c4_sha256": h9,
        "source_pg08_final_sha256": h8,
        "source_pg08_c1_sha256": h8c1,
        "lineage": [{"solution_id": sid, "head": observed[sid]} for sid in lineage_solution_ids],
        "source_pg11_c1_sha256": h11,
        "run_ref": run, "target_repo": repo,
        "base_head_sha": base, "expected_head_sha": head,
        "pg10_pg11_chain_shape_verified": True,
        "real_execution_source_authenticated": False,
        "real_git_diff_readback_verified": False,
        "independent_review_executed": False,
        "production_authority": False, "handoff_allowed": False,
        "next_gate": "REAL_RUN_BINDING_EXACT_GIT_DIFF_AND_AUTHORITY_READBACK",
    }
    out["candidate_sha256"] = _digest(out)
    return out
