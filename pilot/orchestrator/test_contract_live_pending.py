"""Integration CI may defer a live contract operation only while the BACKEND
lot that owns its requirement is planned and not yet integrated."""
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from pilot.orchestrator.contract_validate import (
    ContractBlocked, compare_live, pending_backend_requirements)

LIVE = {"paths": {"/api/auth/login": {"post": {}}}}


def _contract(tmp_path: Path) -> Path:
    spec = {"openapi": "3.0.3", "info": {"title": "x", "version": "1"},
            "paths": {
                "/api/auth/login": {"post": {"x-requirement-ids": ["REQ-LOGIN"],
                                             "responses": {"200": {"description": "ok"}}}},
                "/api/auth/logout": {"post": {"x-requirement-ids": ["REQ-SESSIONS"],
                                              "responses": {"204": {"description": "ok"}}}}}}
    path = tmp_path / "c.openapi.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return path


def _git(root, *argv):
    subprocess.run(["git", *argv], cwd=root, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def _root(tmp_path: Path, *, backend_ids, integrated=False) -> Path:
    root = tmp_path / "repo"
    runs = root / "pilot/runs/req-1"
    runs.mkdir(parents=True)
    lots = {"lots": [{"id": "SOL-1", "area": "CONTRATO", "requirement_ids": ["REQ-SESSIONS"]},
                     {"id": "SOL-2", "area": "BACKEND", "requirement_ids": backend_ids}]}
    (runs / "lots.json").write_text(json.dumps(lots), encoding="utf-8")
    plan = {"bindings": [{"lot_id": "SOL-1", "task_name": "req1contrato1"},
                         {"lot_id": "SOL-2", "task_name": "req1backend2"}]}
    (runs / "chain_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "plan")
    if integrated:
        _git(root, "commit", "-q", "--allow-empty", "-m", "Merge PR #9 via sandbox-train",
             "-m", "[DRAFT][CP3.5][CHG-0001] Verified native req1backend2 run 7")
    return root


def test_strict_by_default(tmp_path):
    with pytest.raises(ContractBlocked, match="CONTRACT_LIVE_OPERATION_MISSING:POST /api/auth/logout"):
        compare_live(_contract(tmp_path), LIVE)


def test_operation_owned_by_pending_backend_is_deferred(tmp_path):
    pending = pending_backend_requirements(_root(tmp_path, backend_ids=["REQ-SESSIONS"]))
    assert compare_live(_contract(tmp_path), LIVE, pending) == ["POST /api/auth/logout"]


def test_operation_without_responsible_backend_blocks(tmp_path):
    pending = pending_backend_requirements(_root(tmp_path, backend_ids=["REQ-OTHER"]))
    with pytest.raises(ContractBlocked, match="CONTRACT_LIVE_OPERATION_MISSING"):
        compare_live(_contract(tmp_path), LIVE, pending)


def test_integrated_backend_is_no_longer_deferred(tmp_path):
    pending = pending_backend_requirements(
        _root(tmp_path, backend_ids=["REQ-SESSIONS"], integrated=True))
    assert "REQ-SESSIONS" not in pending
    with pytest.raises(ContractBlocked, match="CONTRACT_LIVE_OPERATION_MISSING"):
        compare_live(_contract(tmp_path), LIVE, pending)


def test_shallow_history_denies(tmp_path):
    root = _root(tmp_path, backend_ids=["REQ-SESSIONS"], integrated=True)
    clone = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", root.as_uri(), str(clone)],
                   check=True, capture_output=True)
    with pytest.raises(ContractBlocked, match="CONTRACT_LIVE_PENDING_EVIDENCE_INCOMPLETE"):
        pending_backend_requirements(clone)


def test_request_without_chain_plan_never_widens(tmp_path):
    root = _root(tmp_path, backend_ids=["REQ-SESSIONS"])
    (root / "pilot/runs/req-1/chain_plan.json").unlink()
    assert pending_backend_requirements(root) == frozenset()


def test_malformed_backend_requirements_deny(tmp_path):
    root = _root(tmp_path, backend_ids="REQ-SESSIONS")
    with pytest.raises(ContractBlocked, match="CONTRACT_LIVE_PENDING_EVIDENCE_INCOMPLETE"):
        pending_backend_requirements(root)
