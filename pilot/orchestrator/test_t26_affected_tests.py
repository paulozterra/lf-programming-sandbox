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
        rows = json.loads(assessment.read_text("utf-8")).get("obligations", [])
        if any(r.get("decision") == "EXTEND" and r.get("reused_endpoints") for r in rows):
            candidates.append(folder.name)
    if not candidates:
        return None
    copy = tmp_path / "repo"
    shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(
        ".git", "node_modules", "target", ".next", "__pycache__"), symlinks=True)
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
    gained = {lot["id"]: set(lot["write_paths"]) - set(before[lot["id"]]["write_paths"])
              for lot in after["lots"]}
    assert any(gained.values()), "an EXTEND lot must gain its affected project tests"
    for lot_id, paths in gained.items():
        assert all(at.is_project_test(p) for p in paths)
    for path in changed:
        if path.endswith(".task.json"):
            spec = json.loads((root / path).read_text("utf-8"))["task_spec"]
            assert all(c["argv"][0] != "python3" for c in spec["acceptance_commands"])
            writable = set(spec["write_path_patterns"])
            assert not (writable & set(spec["protected_path_patterns"]))
    # Idempotent: a second refresh against the refreshed plan changes nothing.
    assert ppr.refresh(root, request, completed) == []


def test_cp36_refreshes_before_registering_and_plan_branch_is_auxiliary():
    source = (HERE / "chain_lots.py").read_text("utf-8")
    body = source.split("def prepare_successor(", 1)[1].split("\ndef ", 1)[0]
    assert body.index("publish_pending_plan_refresh(") < body.index("prepare_native_lot.py")
    sys.path.insert(0, str(ROOT / "pilot"))
    from native_registration_family import registration_family
    assert registration_family("lf/native-registration/plan-demotask2-0123456789ab") == (
        "auxiliary", "demotask2")
