"""PG-10_C2: source-only precedence and legacy-rename guard.

No real source authentication, migration approval, or execution authority.
C1 is an untrusted typed declaration, not a verified source-of-truth.
"""
import hashlib
import json
import re
from copy import deepcopy

SHA = re.compile(r"^[0-9a-f]{64}$")
ALLOWED = {"PRESERVE_EXISTING", "DEFER_PRECEDENCE", "RETURN_PHASE1_A3",
           "QUERY_EXACT_MISSING_EVIDENCE"}
C1_SCHEMA = "PG10_C1_CONFLICT_INVENTORY_CANDIDATE_V1"

class PG10C2Blocked(ValueError):
    pass

def _fail(code):
    raise PG10C2Blocked(code)

def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()

def _ref(value):
    return isinstance(value, str) and bool(value.strip())

def prepare_pg10_c2(*, pg10_c1, precedence_observations):
    """One observation per C1 solution.

    observation: solution_id, conflict_actions (id -> action), legacy_changes
    legacy_change: change_id, kind (RENAME|PRESERVE), legacy_ref, target_ref,
                   migration_approval_ref, migration_approval_authenticated
    Only PRESERVE is an eligible candidate; RENAME is always held pending an
    externally verified approval (even caller asserts approval).
    """
    if not isinstance(pg10_c1, dict) or pg10_c1.get("schema_version") != C1_SCHEMA:
        _fail("PG10_C2_C1_SCHEMA_INVALID")
    expected = _digest({k: v for k, v in pg10_c1.items() if k != "candidate_sha256"})
    if pg10_c1.get("candidate_sha256") != expected:
        _fail("PG10_C2_C1_DIGEST_INVALID")
    if (pg10_c1.get("status") != "CANDIDATE_NOT_ADMITTED" or
        pg10_c1.get("pg10_c1_pass") is not False or
        pg10_c1.get("pg10_c1_admitted") is not False or
        pg10_c1.get("production_authority") is not False or
        pg10_c1.get("handoff_allowed") is not False or
        pg10_c1.get("precedence_decided") is not False):
        _fail("PG10_C2_C1_AUTHORITY_INVALID")
    solutions = pg10_c1.get("solutions")
    if not isinstance(solutions, list) or not solutions:
        _fail("PG10_C2_C1_SOLUTIONS_INVALID")
    ids = [s.get("solution_id") for s in solutions if isinstance(s, dict)]
    if len(ids) != len(solutions) or not all(map(_ref, ids)) or len(set(ids)) != len(ids):
        _fail("PG10_C2_C1_SOLUTION_IDS_INVALID")
    if not isinstance(precedence_observations, list) or len(precedence_observations) != len(ids):
        _fail("PG10_C2_OBSERVATION_COVERAGE_INVALID")
    obs = {}
    for row in precedence_observations:
        if not isinstance(row, dict) or set(row) != {"solution_id", "conflict_actions", "legacy_changes"}:
            _fail("PG10_C2_OBSERVATION_SHAPE_INVALID")
        sid = row["solution_id"]
        if not _ref(sid) or sid in obs or not isinstance(row["conflict_actions"], list) or not isinstance(row["legacy_changes"], list):
            _fail("PG10_C2_OBSERVATION_INVALID")
        obs[sid] = row
    if set(obs) != set(ids):
        _fail("PG10_C2_OBSERVATION_COVERAGE_DRIFT")
    output = []
    for s in sorted(solutions, key=lambda x: x["solution_id"]):
        sid = s["solution_id"]
        conflicts = s.get("conflicts")
        if not isinstance(conflicts, list):
            _fail("PG10_C2_CONFLICTS_INVALID")
        expected_ids = set()
        for c in conflicts:
            if not isinstance(c, dict) or not _ref(c.get("conflict_id")) or c["conflict_id"] in expected_ids:
                _fail("PG10_C2_CONFLICT_ID_INVALID")
            expected_ids.add(c["conflict_id"])
        actions = {}
        for item in obs[sid]["conflict_actions"]:
            if not isinstance(item, dict) or set(item) != {"conflict_id", "action"}:
                _fail("PG10_C2_ACTION_SHAPE_INVALID")
            cid, action = item["conflict_id"], item["action"]
            if not _ref(cid) or cid in actions or action not in ALLOWED:
                _fail("PG10_C2_ACTION_INVALID")
            actions[cid] = action
        if set(actions) != expected_ids:
            _fail("PG10_C2_CONFLICT_ACTION_COVERAGE_DRIFT")
        rows = []
        for c in sorted(conflicts, key=lambda x: x["conflict_id"]):
            kind, cid = c.get("issue_kind_reported"), c["conflict_id"]
            action = actions[cid]
            if kind == "REQUIREMENT_GAP" and action != "RETURN_PHASE1_A3":
                _fail("PG10_C2_REQUIREMENT_GAP_CANNOT_OVERRIDE")
            if kind == "EVIDENCE_GAP" and action != "QUERY_EXACT_MISSING_EVIDENCE":
                _fail("PG10_C2_EVIDENCE_GAP_CANNOT_OVERRIDE")
            if kind == "CONFLICT" and action not in {"PRESERVE_EXISTING", "DEFER_PRECEDENCE"}:
                _fail("PG10_C2_CONFLICT_CANNOT_REDEFINE")
            rows.append({"conflict_id": cid, "action_candidate": action,
                         "precedence_authenticated": False,
                         "requirement_redefined": False,
                         "conflict_resolved": False})
        legacy = []
        seen = set()
        for item in obs[sid]["legacy_changes"]:
            fields = {"change_id", "kind", "legacy_ref", "target_ref",
                      "migration_approval_ref", "migration_approval_authenticated"}
            if not isinstance(item, dict) or set(item) != fields:
                _fail("PG10_C2_LEGACY_SHAPE_INVALID")
            cid = item["change_id"]
            if not _ref(cid) or cid in seen or item["kind"] not in {"RENAME", "PRESERVE"}:
                _fail("PG10_C2_LEGACY_ID_INVALID")
            seen.add(cid)
            if not _ref(item["legacy_ref"]) or not _ref(item["target_ref"]):
                _fail("PG10_C2_LEGACY_REFERENCE_INVALID")
            if item["migration_approval_authenticated"] is not False:
                _fail("PG10_C2_UNVERIFIED_APPROVAL_CLAIM")
            approval = item["migration_approval_ref"]
            if approval is not None and not _ref(approval):
                _fail("PG10_C2_MIGRATION_REFERENCE_INVALID")
            rename = item["kind"] == "RENAME"
            legacy.append({"change_id": cid, "kind_reported": item["kind"],
                           "legacy_ref_reported": item["legacy_ref"],
                           "target_ref_reported": item["target_ref"],
                           "migration_approval_ref_reported": approval,
                           "migration_approval_verified": False,
                           "rename_allowed": False,
                           "diagnostic": "BLOCK_UNAPPROVED_LEGACY_RENAME" if rename
                               else "PRESERVE_LEGACY_CANDIDATE"})
        output.append({"solution_id": sid, "conflict_actions": rows,
                       "legacy_changes": sorted(legacy, key=lambda x: x["change_id"]),
                       "requires_review": bool(rows) or any(x["kind_reported"] == "RENAME" for x in legacy),
                       "no_unilateral_redefinition": True,
                       "precedence_applied": False, "legacy_modified": False,
                       "decision_authorized": False})
    result = {"schema_version": "PG10_C2_PRECEDENCE_LEGACY_GUARD_CANDIDATE_V1",
              "status": "CANDIDATE_NOT_ADMITTED", "source_pg10_c1_sha256": expected,
              "observations_sha256": _digest(precedence_observations),
              "run_ref": pg10_c1.get("run_ref"), "solutions": output,
              "analysis_modified": False, "real_sources_compared": False,
              "approved_migration_verified": False, "precedence_decided": False,
              "legacy_rename_executed": False, "pg10_c2_pass": False,
              "pg10_c2_admitted": False, "handoff_allowed": False,
              "production_authority": False,
              "next_gate": "REAL_SOURCE_PRECEDENCE_AND_MIGRATION_APPROVAL_VERIFICATION"}
    result["candidate_sha256"] = _digest(result)
    return deepcopy(result)
