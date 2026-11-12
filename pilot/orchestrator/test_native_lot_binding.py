"""Visible CP3.4 tests: no model, no oracle, no pinned-source edits."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_lot_binding import NativeLotBlocked, map_profile, real_write_paths, next_ready


@pytest.mark.parametrize("code,area,native", [
    ("PERFIL-PROG-BACKEND-SPRING-EXP", "BACKEND", "PERFIL-PROG-BACKEND-EXP"),
    ("PERFIL-PROG-FRONTEND-EXP", "FRONTEND", "PERFIL-PROG-FRONTEND-EXP"),
    ("PERFIL-PROG-DATA-EXP", "DATA", "PERFIL-PROG-DATA-EXP"),
])
def test_explicit_profile_alias(code, area, native):
    assert map_profile(code, area)["native_profile_code"] == native


def test_profile_unknown_or_area_confusion_fails_closed():
    for code, area in [
        ("PERFIL-PROG-BACKEND-SPRING-EXP", "FRONTEND"),
        ("PERFIL-PROG-BACKEND-SPRING-EXP-FAKE", "BACKEND"),
        ("PERFIL-PROG-BACKEND-EXP", "BACKEND"),
    ]:
        with pytest.raises(NativeLotBlocked):
            map_profile(code, area)


def test_real_paths_and_historical_fake_paths(tmp_path):
    (tmp_path / "apps/time-service").mkdir(parents=True)
    (tmp_path / "apps/web").mkdir(parents=True)
    (tmp_path / "db").mkdir()
    assert real_write_paths(tmp_path, "BACKEND", [
        "apps/time-service/src/main/java/lf/sandbox/time/LoginController.java"
    ])
    assert real_write_paths(tmp_path, "FRONTEND", ["apps/web/src/app/login/page.tsx"])
    assert real_write_paths(tmp_path, "DATA", ["db/migration/V001__auth.sql"])
    for area, path in [
        ("BACKEND", "src/main/java/com/lf/Login.java"),
        ("FRONTEND", "web/src/app/login/page.tsx"),
        ("BACKEND", "apps/time-service/../../secret.java"),
        ("DATA", "vendor/a.sql"),
        ("FRONTEND", ".env.local"),
    ]:
        with pytest.raises(NativeLotBlocked):
            real_write_paths(tmp_path, area, [path])


def test_unknown_project_root_fails_closed(tmp_path):
    with pytest.raises(NativeLotBlocked, match="PROJECT_ROOT_MISSING"):
        real_write_paths(tmp_path, "FRONTEND", ["apps/web/src/app/page.tsx"])


def test_two_lots_handoff_simulated_without_model():
    lots = {
        "schema_version": "CP33_LOTS_CANDIDATE_V1",
        "production_authority": False, "handoff_allowed": False, "worker_invoked": False,
        "lots": [
            {"id": "L1", "area": "DATA", "depends_on": []},
            {"id": "L2", "area": "BACKEND", "depends_on": ["L1"]},
        ],
    }
    assert [x["id"] for x in next_ready(lots, set())] == ["L1"]
    assert [x["id"] for x in next_ready(lots, {"L1"})] == ["L2"]
    assert next_ready(lots, {"L1", "L2"}) == []
    with pytest.raises(NativeLotBlocked):
        next_ready(lots, {"INVENTED"})


def test_never_promote_authority():
    lots = {"schema_version": "CP33_LOTS_CANDIDATE_V1",
            "production_authority": True, "handoff_allowed": False,
            "worker_invoked": False, "lots": []}
    with pytest.raises(NativeLotBlocked, match="LOTS_NOT_CANDIDATE"):
        next_ready(lots, set())
