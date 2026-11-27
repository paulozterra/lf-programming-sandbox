"""T26: affected project tests enter the lot's scope; pending lots are refreshed.

Synthetic projects only use invented names. The real-case check runs on a
copy of the repository's own committed request data, read-only.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import affected_tests as at  # noqa: E402
import generate_chain  # noqa: E402
import pending_plan_refresh as ppr  # noqa: E402
from intake import canonical  # noqa: E402

TEST_DIR = "apps/time-service/src/test/java/demo/widget"


def project(tmp: Path) -> Path:
    tests = tmp / TEST_DIR
    tests.mkdir(parents=True)
    (tests / "GadgetControllerTest.java").write_text('get("/api/gadgets")\n', "utf-8")
    (tests / "GadgetSearchTest.java").write_text('mvc.perform(get("/api/gadgets").param("q","x"))\n', "utf-8")
    (tests / "GadgetItemTest.java").write_text('get("/api/gadgets/7")\n', "utf-8")
    (tests / "GadgetStatsTest.java").write_text('get("/api/gadgets-stats")\n', "utf-8")
    (tests / "ClockTest.java").write_text('get("/api/clock")\n', "utf-8")
    return tmp


SRC = "apps/time-service/src/main/java/demo/widget/GadgetController.java"


def extend_row(endpoints, path=SRC, req="REQ-X-1"):
    return {"decision": "EXTEND", "path": path, "requirement_id": req,
            "reused_endpoints": endpoints, "write_paths": [path]}


def test_route_tests_and_paired_test_are_affected(tmp_path):
    root = project(tmp_path)
    found = at.affected_behavior_tests(root, SRC, ["GET /api/gadgets"])
    assert found == {f"{TEST_DIR}/GadgetControllerTest.java", f"{TEST_DIR}/GadgetSearchTest.java"}


def test_longer_routes_and_unrelated_tests_are_not_affected(tmp_path):
    root = project(tmp_path)
    found = at.affected_behavior_tests(root, "x/Other.java", ["GET /api/gadgets"])
    assert f"{TEST_DIR}/GadgetItemTest.java" not in found
    assert f"{TEST_DIR}/GadgetStatsTest.java" not in found
    assert f"{TEST_DIR}/ClockTest.java" not in found


def test_no_changed_endpoint_means_nothing_to_adapt(tmp_path):
    assert at.affected_behavior_tests(project(tmp_path), SRC, []) == set()


@pytest.mark.parametrize("bad", [["/api/gadgets"], [3], ["GET api/gadgets"]])
def test_malformed_endpoints_fail_closed(tmp_path, bad):
    with pytest.raises(at.AffectedTestsBlocked, match="LOTE_PRUEBAS_AFECTADAS_INDETERMINADAS"):
        at.affected_behavior_tests(project(tmp_path), SRC, bad)


def test_symlinked_test_tree_fails_closed(tmp_path):
    root = project(tmp_path)
    (root / TEST_DIR / "Link.java").symlink_to(root / TEST_DIR / "ClockTest.java")
    with pytest.raises(at.AffectedTestsBlocked):
        at.affected_behavior_tests(root, SRC, ["GET /api/gadgets"])


def test_lot_scope_gains_only_its_own_extend_tests(tmp_path):
    root = project(tmp_path)
    lot = {"id": "SOL-002", "area": "BACKEND", "write_paths": [SRC], "requirement_ids": ["REQ-X-1"]}
    other = {"id": "SOL-003", "area": "FRONTEND", "write_paths": ["frontend/src/app/g/page.tsx"],
             "requirement_ids": ["REQ-X-2"]}
    rows = [extend_row(["GET /api/gadgets"])]
    scopes = {"REQ-X-1": "S1", "REQ-X-2": "S2"}
    assert at.affected_for_lot(root, lot, rows, scopes) == {
        f"{TEST_DIR}/GadgetControllerTest.java", f"{TEST_DIR}/GadgetSearchTest.java"}
    assert at.affected_for_lot(root, other, rows, scopes) == set()
    # REUSE_AS_IS never makes tests writable: unchanged behaviour stays protected.
    reuse_only = [dict(extend_row(["GET /api/gadgets"]), decision="REUSE_AS_IS")]
    assert at.affected_for_lot(root, lot, reuse_only, scopes) == set()


def test_every_other_project_test_stays_protected(tmp_path):
    root = project(tmp_path)
    affected = {f"{TEST_DIR}/GadgetControllerTest.java"}
    protected = generate_chain._unprotect_affected(
        root, ["pilot/**", "apps/time-service/src/test/**",
               "apps/time-service/visible-tests/**"], affected)
    assert "apps/time-service/src/test/**" not in protected
    assert "apps/time-service/visible-tests/**" in protected  # examiner-owned, never affected
    assert f"{TEST_DIR}/ClockTest.java" in protected
    assert f"{TEST_DIR}/GadgetSearchTest.java" in protected
    assert f"{TEST_DIR}/GadgetControllerTest.java" not in protected


def test_project_test_classifier():
    assert at.is_project_test("apps/time-service/src/test/java/a/BTest.java")
    assert not at.is_project_test("apps/time-service/visible-tests/x/run_visible.py")
    assert not at.is_project_test("apps/time-service/src/main/java/a/B.java")


# --- real committed request, refreshed read-only on a copy ---------------------------------

REAL_CASE_SNAPSHOT = "13609483de4398ad87e0eee80b864c6bad1bcb9f"


def _real_request(tmp_path) -> tuple[Path, str] | None:
    candidates = []
    # Most recent request first: older discarded runs may predate later analysis fixes.
    for folder in sorted((ROOT / "pilot/runs").glob("req-*"),
                         key=lambda f: int(f.name[4:]) if f.name[4:].isdigit() else -1,
                         reverse=True):
        assessment = folder / "reuse_assessment.json"
        lots = folder / "lots.json"
        if not (assessment.is_file() and lots.is_file()):
            continue
        # T33.1: the case is read from the pinned snapshot, so a request
        # admitted after it (e.g. a new EXTEND request) is not a candidate.
        import subprocess
        if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e",
                           f"{REAL_CASE_SNAPSHOT}:pilot/runs/{folder.name}/lots.json"],
                          capture_output=True).returncode != 0:
            continue
        rows = json.loads(assessment.read_text("utf-8")).get("obligations", [])
        if any(r.get("decision") == "EXTEND" and r.get("reused_endpoints") for r in rows):
            candidates.append(folder.name)
    if not candidates:
        return None
    copy = tmp_path / "repo"
    shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(
        ".git", "node_modules", "target", ".next", "__pycache__"), symlinks=True)
    # T29: product code and request data come from a pinned snapshot, so later
    # integrated lots (which change the live tree) do not break this fixture.
    import io, subprocess, tarfile
    for tree in ("apps/time-service", "pilot/runs/" + candidates[0]):
        shutil.rmtree(copy / tree, ignore_errors=True)
        raw = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar",
                              REAL_CASE_SNAPSHOT, tree],
                             check=True, capture_output=True).stdout
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            archive.extractall(copy, filter="data")
    return copy, candidates[0]


def test_real_request_pending_backend_lot_gets_affected_tests_and_current_generator(tmp_path):
    found = _real_request(tmp_path)
    if found is None:
        pytest.skip("no committed request with an EXTEND obligation")
    root, request = found
    lots = json.loads((root / f"pilot/runs/{request}/lots.json").read_text("utf-8"))
    integrated = [lot for lot in lots["lots"] if lot["area"] == "CONTRATO"]
    completed = {lot["id"]: {"expected_files": lot["write_paths"]} for lot in integrated}
    before = {lot["id"]: lot for lot in lots["lots"]}
    changed = ppr.refresh(root, request, completed)
    after = json.loads((root / f"pilot/runs/{request}/lots.json").read_text("utf-8"))
    state = json.loads((root / f"pilot/runs/{request}/state.json").read_text("utf-8"))
    assert state["lots_sha256"] == hashlib.sha256(canonical(after)).hexdigest()
    for lot in after["lots"]:
        if lot["id"] in completed:
            assert lot == before[lot["id"]]  # integrated lots are never touched
    # Whether main already carries the refreshed plan or not, after refresh
    # every pending EXTEND lot holds exactly its affected project tests.
    rows, scopes = at.load_reuse(root, request)
    assert any(at.affected_for_lot(root, lot, rows, scopes) for lot in after["lots"]
               if lot["id"] not in completed), "the request must have an EXTEND lot with tests"
    for lot in after["lots"]:
        if lot["id"] in completed:
            continue
        expected = at.affected_for_lot(root, lot, rows, scopes)
        assert expected <= set(lot["write_paths"])
        gained = set(lot["write_paths"]) - set(before[lot["id"]]["write_paths"])
        assert all(at.is_project_test(p) for p in gained)
    for plan_rel in (f"pilot/runs/{request}/chain_plan.json",):
        if (root / plan_rel).exists():
            plan = json.loads((root / plan_rel).read_text("utf-8"))
            assert plan["lots_sha256"] == state["lots_sha256"]
    for path in changed:
        if path.endswith(".task.json"):
            spec = json.loads((root / path).read_text("utf-8"))["task_spec"]
            assert all(c["argv"][0] != "python3" for c in spec["acceptance_commands"])
            writable = set(spec["write_path_patterns"])
            assert not (writable & set(spec["protected_path_patterns"]))
    # Idempotent: a second refresh against the refreshed plan changes nothing.
    assert ppr.refresh(root, request, completed) == []


def test_refreshed_plan_keeps_every_chain_plan_valid(tmp_path):
    found = _real_request(tmp_path)
    if found is None:
        pytest.skip("no committed request with an EXTEND obligation")
    root, request = found
    lots = json.loads((root / f"pilot/runs/{request}/lots.json").read_text("utf-8"))
    completed = {lot["id"]: {"expected_files": lot["write_paths"]}
                 for lot in lots["lots"] if lot["area"] == "CONTRATO"}
    ppr.refresh(root, request, completed)
    from chain_contract import validate_plan
    plan = json.loads((root / f"pilot/runs/{request}/chain_plan.json").read_text("utf-8"))
    validate_plan(plan, json.loads((root / f"pilot/runs/{request}/lots.json").read_text("utf-8")),
                  request)


def test_cp36_retires_plan_drafts_from_an_older_main():
    source = (HERE / "chain_lots.py").read_text("utf-8")
    body = source.split("def publish_pending_plan_refresh(", 1)[1].split("\ndef ", 1)[0]
    assert body.index("close_stale_drafts(") < body.index("pending_draft(")


def test_cp36_refreshes_before_registering_and_plan_branch_is_auxiliary():
    source = (HERE / "chain_lots.py").read_text("utf-8")
    body = source.split("def prepare_successor(", 1)[1].split("\ndef ", 1)[0]
    assert body.index("publish_pending_plan_refresh(") < body.index("prepare_native_lot.py")
    sys.path.insert(0, str(ROOT / "pilot"))
    from native_registration_family import registration_family
    assert registration_family("lf/native-registration/plan-demotask2-0123456789ab") == (
        "auxiliary", "demotask2")


# --- T26.3: registration accepts planned affected tests; small context --------------

def test_registration_accepts_only_existing_backend_project_tests(tmp_path):
    from native_lot_binding import real_write_paths, NativeLotBlocked
    root = project(tmp_path)
    (root / "apps/time-service/src/main/java/demo/widget").mkdir(parents=True)
    existing = f"{TEST_DIR}/GadgetControllerTest.java"
    assert real_write_paths(root, "BACKEND", [SRC, existing]) == sorted([SRC, existing])
    with pytest.raises(NativeLotBlocked):
        real_write_paths(root, "BACKEND", [SRC, f"{TEST_DIR}/InventedTest.java"])
    with pytest.raises(NativeLotBlocked):
        real_write_paths(root, "FRONTEND", [existing])


def test_task_context_classifies_project_tests_as_backend():
    sys.path.insert(0, str(ROOT / "pilot/worker_v08"))
    from register_task_context import classify_path
    assert classify_path("apps/time-service/src/test/java/demo/GadgetTest.java") == "BACKEND"


def test_large_analysis_anchor_only_when_context_would_be_empty():
    source = (HERE / "generate_chain.py").read_text("utf-8")
    block = source.split('if not context_paths:', 1)
    assert len(block) == 2 and '/analysis.json' in block[1].split("\n", 2)[1]


def test_completed_characterization_is_preserved_during_pending_refresh(tmp_path):
    """T26 regression: a verified completed suite is not a new CREATE."""
    from test_chain_lots import configure_root
    from chain_contract import validate_plan
    configure_root(tmp_path)
    request = "req-1"
    folder = tmp_path / "pilot/runs" / request
    folder.mkdir(parents=True)
    suite = "frontend/visible-tests/sol-k0123456789ab.json"
    char = {"id": "SOL-K0123456789ab", "area": "FRONTEND",
            "lot_kind": "CHARACTERIZATION", "requirement_ids": [],
            "characterized_requirement_ids": ["REQ-KEEP"],
            "characterized_files": ["frontend/src/app/x/page.tsx"],
            "write_paths": [suite], "depends_on": []}
    backend = {"id": "SOL-002", "area": "BACKEND", "requirement_ids": ["REQ-B"],
               "write_paths": [SRC], "depends_on": []}
    frontend = {"id": "SOL-001", "area": "FRONTEND", "requirement_ids": ["REQ-F"],
                "write_paths": ["frontend/src/app/x/page.tsx"],
                "depends_on": [char["id"], backend["id"]]}
    lots = {"schema_version": "CP33_LOTS_CANDIDATE_V1",
            "production_authority": False, "handoff_allowed": False,
            "worker_invoked": False, "lots": [backend, char, frontend]}
    before = generate_chain.generate(tmp_path, request, lots, persist=False)
    bindings = validate_plan(before["plan"], lots, request)
    for path, template in before["templates"].items():
        generate_chain.save(tmp_path / path, template)
    (folder / "lots.json").write_bytes(canonical(lots))
    (folder / "state.json").write_bytes(canonical({
        "lots_sha256": hashlib.sha256(canonical(lots)).hexdigest()}))
    char_template = tmp_path / bindings[char["id"]]["template_path"]
    original_template = char_template.read_bytes()
    original_lots = (folder / "lots.json").read_bytes()
    suite_file = tmp_path / suite
    suite_file.parent.mkdir(parents=True, exist_ok=True)
    suite_file.write_text('{"covers":["REQ-KEEP"],"cases":[]}\n', encoding="utf-8")
    original_suite = suite_file.read_bytes()
    receipt = {"lot_id": char["id"], "expected_files": [suite],
               "merge_sha": "a" * 40, "integration_pr": 123,
               "task_name": bindings[char["id"]]["task_name"]}
    completed = {char["id"]: receipt}

    # No proof, wrong lot or wrong file must never authorize existing suite.
    with pytest.raises(ValueError, match="CARACTERIZACION_ALCANCE_INVALIDO"):
        generate_chain.generate(tmp_path, request, lots, persist=False,
                                allow_source_drift={suite})
    for bad in (dict(receipt, lot_id=backend["id"]),
                dict(receipt, expected_files=["frontend/visible-tests/other.json"])):
        with pytest.raises(ValueError, match="CARACTERIZACION_ALCANCE_INVALIDO"):
            generate_chain.generate(tmp_path, request, lots, persist=False,
                                    allow_source_drift={suite},
                                    completed={char["id"]: bad})

    refreshed = generate_chain.generate(tmp_path, request, lots, persist=False,
                                         allow_source_drift={suite}, completed=completed)
    assert refreshed["plan"] == before["plan"]
    assert refreshed["templates"][bindings[char["id"]]["template_path"]] == before["templates"][bindings[char["id"]]["template_path"]]
    assert refreshed["templates"][bindings[backend["id"]]["template_path"]] == before["templates"][bindings[backend["id"]]["template_path"]]
    changed = ppr.refresh(tmp_path, request, completed)
    assert bindings[char["id"]]["template_path"] not in changed
    assert ppr.refresh(tmp_path, request, completed) == []
    assert char_template.read_bytes() == original_template
    assert suite_file.read_bytes() == original_suite
    assert (folder / "lots.json").read_bytes() == original_lots

    # Completed evidence cannot be used for initial generation or a lost suite.
    with pytest.raises(ValueError, match="T1_COMPLETED_REGENERATION_ONLY"):
        generate_chain.generate(tmp_path, request, lots, completed=completed)
    suite_file.unlink()
    with pytest.raises(ValueError, match="CARACTERIZACION_ALCANCE_INVALIDO"):
        ppr.refresh(tmp_path, request, completed)
