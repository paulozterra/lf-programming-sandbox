"""EX6-only PG04..PG14 source-bound candidate chain.

Each stage uses the ORIGINAL producer where the independently supplied EX6
inputs suffice. No EX5C fixtures, no fabricated PG01 currentness or PG06
build receipts. First exact rejection stops downstream: no fabricated PASS.
The caller-side data is installed/uninstalled without touching producer code.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ex6_source_truth_v1 import source_truth, SPEC_REF, RUN_REF, TASK_REF
from ex6_real_world_v1 import BASE_SHA, REPO

_UNDO = []
STAGE_ORDER = tuple(f"PG-{n:02d}" for n in range(4, 15))
REQUIREMENTS = ("REM-D1", "REM-D2", "REM-D3", "REM-D4")
ACCEPTANCE = ("time-service-package", "ex6-visible-check")
WRITE_SCOPE = "apps/time-service/src/main/java/lf/sandbox/time/reminder"


def install():
    """Add only EX6 tool directories to sys.path; preserve original order."""
    if _UNDO:
        raise RuntimeError("EX6_ALREADY_INSTALLED")
    folders = [ROOT / name / sub
               for name in ("pg04_semantic_partition_candidate",
                            "pg05_target_binding_candidate",
                            "pg06_preflight_candidate",
                            "pg07_worker_candidate",
                            "pg08_build_candidate",
                            "pg09_iteration_candidate",
                            "pg10_decision_candidate",
                            "pg11_integrity_candidate")
               for sub in ("tools", "tests")]
    folders += [x for x in sorted(ROOT.iterdir()) if x.is_dir()
                and x.name.startswith(("pg04_", "pg05_", "pg06_", "pg07_",
                                       "pg08_", "pg09_", "pg10_", "pg11_",
                                       "pg12_", "pg13_", "pg14_"))]
    # Some modules are imported by filename from sibling candidate directories.
    for d in list(folders):
        if d.is_dir():
            for sub in ("tools", "tests"):
                if (d / sub).is_dir():
                    folders.append(d / sub)
    for d in folders:
        if d.is_dir() and str(d) not in sys.path:
            sys.path.insert(0, str(d))
            _UNDO.append(str(d))
    return len(_UNDO)


def uninstall():
    """No monkeypatching producers or synthetic test fixtures."""
    while _UNDO:
        path = _UNDO.pop()
        if path in sys.path:
            sys.path.remove(path)


def _digest(obj):
    return hashlib.sha256(json.dumps(
        obj, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    ).encode()).hexdigest()


def authorize_from_real_hunks(truth=None):
    """Exactly 3 new files, one batch+scope per file, from original EX6 ZIP."""
    truth = truth or source_truth()
    hunks = truth["hunks"]
    if len(hunks) != 3 or sorted(h["path"] for h in hunks) != truth["write_paths"]:
        raise ValueError("EX6_REAL_HUNK_SCOPE_MISMATCH")
    changed, authorized, traces = [], [], []
    for hunk in sorted(hunks, key=lambda x: x["path"]):
        path = hunk["path"]
        ref = "ex6://scope/" + path
        batch = "ex6://batch/EX6-SOL-001"
        changed.append({"path": path, "change_type": "ADDED", "old_path": None})
        links = [{"requirement_ref": SPEC_REF + "#" + req,
                  "batch_ref": batch, "scope_ref": ref}
                 for req in hunk["requirements"]]
        if not links or len(set(x["requirement_ref"] for x in links)) != len(links):
            raise ValueError("EX6_REAL_HUNK_REQUIREMENT_DRIFT")
        authorized.append({**changed[-1], "authorized_links": links})
        traces.append({"path": path, "status_reported": "LINKED",
                       "links": [{**link,
                                  "evidence_ref": hunk["header_ref"],
                                  "change_reason_ref": RUN_REF}
                                 for link in links]})
    return changed, authorized, traces


def make_pg04(truth=None):
    truth = truth or source_truth()
    from pg04_semantic_partition_candidate_v1 import partition_by_semantic_outcome
    from pg04_c7_coverage_dossier_v1 import build_coverage_dossier
    from pg04_definition_of_done_candidate_v1 import prepare_dod
    from pg04_independent_review_request_v1 import prepare_partition_review_request
    from pg04_pg05_exit_candidate_v1 import assemble_pg04_exit_candidate
    from test_pg04_semantic_partition_candidate_v1 import POLICY

    strategy = {"status": "CANDIDATE_NOT_ADMITTED",
                "production_authority": False, "handoff_allowed": False,
                "scope_ids": ["EX6"], "requirement_ids": list(REQUIREMENTS),
                "acceptance_ids": list(ACCEPTANCE)}
    strategy["candidate_sha256"] = _digest(strategy)
    outcomes = [{"outcome_id": "REMINDER_STATS",
                 "business_outcome": "REM-D1..D4 reminder statistics",
                 "evidence_ref": SPEC_REF}]
    def atom(identifier, requirements, acceptance, depends):
        return {
            "atom_id": identifier, "outcome_id": "REMINDER_STATS",
            "source_ref": SPEC_REF + "#" + requirements[0],
            "scope_id": "EX6", "risk_level": "MEDIUM",
            "semantic_rationale": "Lote D public contract; repository remains read-only",
            "write_scope_reason": "Only three new reminder-statistics Java files",
            "write_scope": [WRITE_SCOPE],
            "shared_contract_refs": ["ex6://contract/existing-reminder-repository"],
            "implementation_state": "NEW",
            "bounded_reuse_assessment_ref": SPEC_REF + "#no-existing-files-modified",
            "requirement_ids": requirements, "acceptance_ids": acceptance,
            "depends_on": depends, "coimplement_with": [],
        }
    atoms = [
        atom("STATS-CORE", ["REM-D1", "REM-D2"], ["ex6-visible-check"], []),
        atom("STATS-REST", ["REM-D3", "REM-D4"], ["time-service-package"], ["STATS-CORE"]),
    ]
    partition = partition_by_semantic_outcome(
        strategy=strategy, partition_contract=copy.deepcopy(POLICY),
        obligations=atoms, outcome_registry=outcomes)
    dossier = build_coverage_dossier(
        partition=partition, strategy=strategy, original_obligations=atoms)
    checks = ([{"check_id": "EX6-SPEC", "kind": "STANDARD",
                "validation_code": "PROGRAMMING_GITHUB_FILE_TEXT_ASSERT_V1",
                "input_ref": SPEC_REF, "requirement_ids": [],
                "acceptance_ids": [], "standard_code": "STD-EX6-LOTE-D"}]
              + [{"check_id": req, "kind": "REQUIREMENT",
                  "validation_code": "PROGRAMMING_GITHUB_FILE_TEXT_ASSERT_V1",
                  "input_ref": SPEC_REF + "#" + req,
                  "requirement_ids": [req], "acceptance_ids": []}
                 for req in REQUIREMENTS]
              + [{"check_id": acc, "kind": "ACCEPTANCE",
                  "validation_code": "PROGRAMMING_GITHUB_FILE_TEXT_ASSERT_V1",
                  "input_ref": "ex6://run/42674262914/public-visible/" + acc,
                  "requirement_ids": [], "acceptance_ids": [acc]}
                 for acc in ACCEPTANCE])
    dod = prepare_dod(
        partition=partition,
        standards_catalog_version="EX6-BASE-" + BASE_SHA[:12],
        standards=[{"standard_code": "STD-EX6-LOTE-D",
                    "source_ref": SPEC_REF,
                    "source_sha256": truth["source_snapshot_sha256"],
                    "applies_to_write_scopes": [WRITE_SCOPE]}],
        validation_registry=[{"validation_code": "PROGRAMMING_GITHUB_FILE_TEXT_ASSERT_V1",
                              "status": "ACTIVE", "source_ref": SPEC_REF}],
        solution_plans=[{"solution_id": s["id"],
                         "standard_codes": ["STD-EX6-LOTE-D"], "checks": checks}
                        for s in partition["solutions"]])
    # EX6 has no independently attested A9/PG03 package. These are explicitly
    # caller-side candidates, NOT authenticated source manifests.
    sources = {
        k: {"ref": "ex6://unattested/" + k,
            "sha256": truth["task_pack_sha256"]}
        for k in ("a9_package", "pg03_strategy",
                  "pg04_partition_contract", "outcome_registry", "typed_obligations")
    }
    sources["pg03_strategy"]["sha256"] = partition["strategy_sha256"]
    sources["source_head_sha"] = BASE_SHA
    review = prepare_partition_review_request(
        partition=partition, sources=sources,
        producer_execution_id=RUN_REF + "/pg04-source-only",
        coverage_dossier=dossier)
    exit_obj = assemble_pg04_exit_candidate(
        partition=partition, dod=dod, coverage_dossier=dossier,
        review_request=review,
        target_binding={"repo_full_name": REPO, "base_head_sha": BASE_SHA,
                        "target_binding_ref": TASK_REF})
    assert all(not x["production_authority"] for x in
               (partition, dossier, dod, review, exit_obj))
    return {"partition": partition, "dossier": dossier, "dod": dod,
            "review": review, "exit": exit_obj}


def make_pg05(pg04=None, truth=None):
    truth = truth or source_truth()
    pg04 = pg04 or make_pg04(truth)
    exit_obj = pg04["exit"]
    from pg05_c1_target_binding_preflight_v1 import prepare_pg05_c1
    from pg05_c2_write_scope_candidate_v1 import prepare_pg05_c2
    from pg05_c3_collision_lock_plan_candidate_v1 import prepare_pg05_c3
    from pg05_c4_write_boundary_preflight_v1 import prepare_pg05_c4
    from pg05_c5_independent_assurance_request_v1 import prepare_pg05_assurance_request
    from pg05_pg06_exit_candidate_v1 import assemble_pg05_pg06_candidate
    c1 = prepare_pg05_c1(pg04_exit=exit_obj, work_code="EX6", slug="stats")
    rows = []
    for sol in exit_obj["solutions"]:
        rows.append({
            "solution_id": sol["solution_id"],
            "resolved_scopes": [{
                "scope_token": scope,
                "derivation_ref": TASK_REF + "#write_path_patterns",
                "resources": [
                    {"kind": "REPO_PATH", "identity": path,
                     "source_ref": "ex6://source/proposal/" +
                                   truth["proposal_sha256"] + "#" + path}
                    for path in truth["write_paths"]]
            } for scope in sol["write_scope_candidates"]],
            "shared_read_refs": [{
                "contract_ref": ref,
                "derivation_ref": SPEC_REF + "#REM-D3",
                "resource": {
                    "kind": "REPO_PATH",
                    "identity": WRITE_SCOPE + "/ReminderRepository.java",
                    "source_ref": SPEC_REF + "#read-only-repository",
                }} for ref in sol["shared_contract_refs"]],
            "l3_structure_ref": TASK_REF + "#base-head",
        })
    c2 = prepare_pg05_c2(pg04_exit=exit_obj, pg05_c1=c1, scope_resolutions=rows)
    c3 = prepare_pg05_c3(pg04_exit=exit_obj, pg05_c2=c2)
    proposals = [{
        "solution_id": sol["solution_id"],
        "source_head_sha": BASE_SHA,
        "proposal_ref": "ex6://source/proposal/" + truth["proposal_sha256"],
        "changes": [{"operation": "ADD", "resource": copy.deepcopy(entry),
                     "change_ref": RUN_REF + "/native-verified-patch#" +
                                   entry["identity"]}
                    for entry in sol["write_resource_keys"]],
    } for sol in c2["solution_scopes"]]
    c4 = prepare_pg05_c4(
        pg04_exit=exit_obj, pg05_c2=c2, pg05_c3=c3,
        change_proposals=proposals)
    parts = {"pg04_exit": exit_obj, "pg05_c1": c1, "pg05_c2": c2,
             "pg05_c3": c3, "pg05_c4": c4}
    manifest = {"source_head_sha": BASE_SHA, **{
        key: {"ref": "ex6://source/" + key,
              "sha256": value["candidate_sha256"]}
        for key, value in parts.items()}}
    c5 = prepare_pg05_assurance_request(
        pg04_exit=exit_obj, pg05_c1=c1, pg05_c2=c2,
        pg05_c3=c3, pg05_c4=c4, source_manifest=manifest,
        producer_execution_id=RUN_REF + "/pg05-source-only")
    handoff = assemble_pg05_pg06_candidate(
        pg04_exit=exit_obj, pg05_c1=c1, pg05_c2=c2,
        pg05_c3=c3, pg05_c4=c4, pg05_c5=c5)
    assert all(not x["production_authority"] for x in
               (c1, c2, c3, c4, c5, handoff))
    return {"pg04": pg04, "c1": c1, "c2": c2,
            "c3": c3, "c4": c4, "c5": c5, "handoff": handoff}


PG01_FIXTURE_STATUS = "FIXTURE_UNATTESTED"
PG01_FIXTURE_ALLOWED_REF = "fixture://pg01/currentness"


def official_pg01_fixture():
    """Import official PG06 test fixture unmodified; sole EX6 non-source input."""
    from test_pg06_c1_c5_chain_v1 import pg01
    binding = pg01()
    if binding.get("pg01_decision_ref") != PG01_FIXTURE_ALLOWED_REF:
        raise ValueError("EX6_PG01_FIXTURE_IDENTITY_DRIFT")
    return binding


def make_pg06(pg05=None):
    from pg06_c1_currentness_reuse_candidate_v1 import prepare_pg06_c1
    pg05 = pg05 or make_pg05()
    binding = official_pg01_fixture()
    c1 = prepare_pg06_c1(
        pg05_exit=pg05["handoff"], pg01_currentness_binding=binding)
    return {"c1": c1, "pg01_binding": binding,
            "pg01_status": PG01_FIXTURE_STATUS,
            "production_authority": False, "handoff_allowed": False}


# Explicit per-stage boundaries. No caller may treat a placeholder as a PASS.
# These functions are deliberately fail-closed until the preceding real
# producer has been admitted with source-backed EX6 inputs.
def _missing(stage: int, predecessor: str):
    raise RuntimeError(f"EX6_PG{stage:02d}_UPSTREAM_UNATTESTED:{predecessor}")


def make_pg07(pg06=None):
    _missing(7, "ex6://pending-execution/pg06-real-preflight")


def make_pg08(pg07=None):
    _missing(8, "ex6://pending-execution/pg07-real-worker-dispatch")


def make_pg09(pg08=None):
    _missing(9, "ex6://pending-execution/pg08-real-build-evidence")


def make_pg10(pg09=None):
    _missing(10, "ex6://pending-execution/pg09-real-budget")


def make_pg11(pg10=None):
    _missing(11, "ex6://pending-execution/pg10-real-conflict-review")


def make_pg12(pg11=None):
    _missing(12, "ex6://pending-execution/pg11-real-diff-trace")


def make_pg13(pg12=None):
    _missing(13, "ex6://pending-execution/pg12-real-identity")


def make_pg14(pg13=None):
    _missing(14, "ex6://pending-execution/pg13-real-freeze")


def _code(exc):
    reason = str(exc).splitlines()[0]
    return reason if reason else type(exc).__name__


def run_v1():
    """First exact original-producer rejection, then dependent stages blocked."""
    install()
    results = []
    try:
        truth = source_truth()
        authorize_from_real_hunks(truth)
        state = {}
        current_block = None
        for i in range(4, 15):
            if current_block:
                results.append({"stage": f"PG-{i:02d}", "before_v2": "NOT_RUN_UPSTREAM_BLOCKED",
                                "code": "UPSTREAM_BLOCKED:" + current_block,
                                "producer_invoked": False})
                continue
            try:
                if i == 4:
                    state[4] = make_pg04(truth)
                elif i == 5:
                    state[5] = make_pg05(state[4], truth)
                elif i == 6:
                    state[6] = make_pg06(state[5])
                    # C1: official PG01 fixture, unchanged and unattested.
                    # C2: actual EX6 POM and pinned native-run Java 21 log.
                    from ex6_pg06_evidence_v1 import c2_inputs, c4_partial_baseline
                    from pg06_c2_toolchain_environment_candidate_v1 import prepare_pg06_c2
                    from pg06_c3_reversibility_plan_candidate_v1 import prepare_pg06_c3
                    catalog, observation = c2_inputs(state[5]["handoff"])
                    state[6]["c2"] = prepare_pg06_c2(
                        pg05_exit=state[5]["handoff"], pg06_c1=state[6]["c1"],
                        toolchain_catalog=catalog, environment_observations=observation)
                    # Retain an independently sourced *partial* C4 baseline,
                    # but never claim a missing lint result or full output SHA.
                    state[6]["c4_partial"] = c4_partial_baseline(state[5]["handoff"])
                    # EX6 receipts have no A7 material-front coverage. Do not
                    # reuse EX5C or official synthetic A7 fixtures as evidence.
                    state[6]["c3"] = prepare_pg06_c3(
                        pg05_exit=state[5]["handoff"], pg06_c1=state[6]["c1"],
                        pg06_c2=state[6]["c2"],
                        a7_material_front_coverage=None,
                        solution_reversibility_plans=[])
                else:
                    raise RuntimeError("EX6_PRODUCER_UNWIRED_AFTER_PG06")
                results.append({"stage": f"PG-{i:02d}", "before_v2": "PASS_SOURCE_ONLY",
                                "code": None, "producer_invoked": True,
                                "pg01_status": PG01_FIXTURE_STATUS if i >= 6 else "NOT_USED"})
            except (Exception,) as exc:
                current_block = f"PG-{i:02d}:" + _code(exc)
                results.append({"stage": f"PG-{i:02d}", "before_v2": "BLOCK",
                                "code": _code(exc), "producer_invoked": True,
                                "pg01_status": PG01_FIXTURE_STATUS if i >= 6 else "NOT_USED"})
        return results
    finally:
        uninstall()


if __name__ == "__main__":
    print(json.dumps({"authority": False, "stages": run_v1()},
                     indent=2, sort_keys=True))
