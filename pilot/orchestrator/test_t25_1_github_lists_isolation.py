"""T25.1: real GitHub collection shapes, paginated API and isolated sweep."""
from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pilot.orchestrator import chain_lots
from pilot.orchestrator import generated_conflict_recovery as recovery

ROOT = Path(__file__).resolve().parents[2]
HEAD = "a" * 40
SHA = "b" * 40
RUN = 43797847761
BRANCH = "lf/native-integration/req186contrato1-run-" + str(RUN)
REPO = chain_lots.REPO


def test_github_object_and_collection_types_do_not_mix():
    def run(*args):
        path = args[-1]
        if path.endswith("/pulls/227/files"):
            return json.dumps([{"filename": "contracts/sbx-rem-list.openapi.yaml"}])
        if path.endswith("/issues/901"):
            return json.dumps({"number": 901})
        raise AssertionError(path)
    with patch.object(chain_lots, "run", side_effect=run):
        assert chain_lots.api("issues/901") == {"number": 901}
        with pytest.raises(chain_lots.ChainBlocked, match="GITHUB_RESPONSE_INVALID"):
            chain_lots.api("pulls/227/files")
    assert chain_lots.api_list is not chain_lots.api


def test_paginated_github_files_and_comments_use_actual_list_shape():
    calls = []
    page_one = [{"filename": f"contracts/contract-{n}.openapi.yaml"} for n in range(100)]
    second = [{"filename": "frontend/src/lib/api/generated/index.ts"}]
    def run(*args):
        path = args[-1]
        calls.append(path)
        if path.endswith("/pulls/227/files?per_page=100&page=1"):
            return json.dumps(page_one)
        if path.endswith("/pulls/227/files?per_page=100&page=2"):
            return json.dumps(second)
        if path.endswith("/issues/901/comments?per_page=100&page=1"):
            return json.dumps([{"id": 1, "body": "example"}])
        raise AssertionError(path)
    with patch.object(chain_lots, "run", side_effect=run):
        files = chain_lots.api_list("pulls/227/files")
        comments = chain_lots.api_list("issues/901/comments")
    assert files == page_one + second
    assert comments == [{"id": 1, "body": "example"}]
    assert len(calls) == 3


@pytest.mark.parametrize("bad", [{"items": []}, "not JSON", ["bad element"], [0], None])
def test_collection_shape_is_never_coerced_to_object(bad):
    def run(*args):
        return bad if isinstance(bad, str) else json.dumps(bad)
    with patch.object(chain_lots, "run", side_effect=run):
        with pytest.raises(chain_lots.ChainBlocked, match="GITHUB_LIST_RESPONSE_INVALID"):
            chain_lots.api_list("pulls/227/files")


def test_collection_pagination_fails_closed_on_repeated_or_unbounded_pages():
    page = [{"id": n} for n in range(100)]
    with patch.object(chain_lots, "run", return_value=json.dumps(page)):
        with pytest.raises(chain_lots.ChainBlocked, match="GITHUB_LIST_PAGINATION_INVALID"):
            chain_lots.api_list("issues/901/comments")
    def run(*args):
        n = int(args[-1].rsplit("page=", 1)[1])
        return json.dumps([{"page": n, "row": i} for i in range(100)])
    with patch.object(chain_lots, "run", side_effect=run):
        with pytest.raises(chain_lots.ChainBlocked, match="GITHUB_LIST_PAGINATION_LIMIT"):
            chain_lots.api_list("pulls/227/files", max_pages=2)
    with pytest.raises(chain_lots.ChainBlocked, match="GITHUB_LIST_PAGINATION_INVALID"):
        chain_lots.api_list("pulls/227/files?per_page=100")


def test_real_227_bot_metadata_and_files_list_triggers_retirement_without_worker():
    identity = {"number": 227, "headRefName": BRANCH, "headRefOid": SHA,
                "author": {"login": "github-actions[bot]"}}
    detail = {"number": 227, "state": "open", "merged": False,
              "mergeable_state": "blocked", "labels": [],
              "user": {"login": "github-actions[bot]"},
              "base": {"ref": "main"},
              "head": {"sha": SHA, "ref": BRANCH,
                       "repo": {"full_name": REPO}}}
    rows = [{"filename": "contracts/sbx-rem-list.openapi.yaml", "status": "added"},
            {"filename": "standards/changes/CHG-0141.json", "status": "added"},
            {"filename": "standards/CAMBIOS.md", "status": "modified"}]
    calls = []
    def run(*args):
        calls.append(args)
        if args[:3] == ("gh", "pr", "list"):
            return json.dumps([identity])
        if args[:3] == ("gh", "pr", "close"):
            return ""
        raise AssertionError(args)
    def obj_api(path):
        assert path == "pulls/227"
        return detail
    def list_api(path):
        assert path == "pulls/227/files"
        return rows
    retired = recovery.retire_conflicted_generated(
        HEAD, run, obj_api, REPO, list_api)
    assert len(retired) == 1 and retired[0]["number"] == 227
    assert retired[0]["reason"] == "CI_DERIVED_GEN_API_STALE"
    assert len([c for c in calls if c[:3] == ("gh", "pr", "close")]) == 1
    assert not any(c[:3] == ("gh", "workflow", "run") for c in calls)


def test_bad_pr_collection_does_not_prevent_other_pr_retirement():
    def row(n):
        return {"number": n, "headRefName":
                "lf/native-integration/req186contrato1-run-" + str(n),
                "headRefOid": SHA,
                "author": {"login": "github-actions[bot]"}}
    def api(path):
        n = int(path.split("/")[1])
        return {"number": n, "state": "open", "merged": False,
                "mergeable_state": "blocked",
                "user": {"login": "github-actions[bot]"}, "labels": [],
                "head": {"sha": SHA, "ref": row(n)["headRefName"],
                         "repo": {"full_name": REPO}},
                "base": {"ref": "main"}}
    def list_api(path):
        if path == "pulls/227/files":
            raise ValueError("PR_FILES_GITHUB_BAD_GATEWAY")
        if path == "pulls/228/files":
            return [{"filename": "contracts/new.openapi.yaml", "status": "added"}]
        raise AssertionError(path)
    calls = []
    def run(*args):
        calls.append(args)
        if args[:3] == ("gh", "pr", "list"):
            return json.dumps([row(227), row(228)])
        if args[:3] == ("gh", "pr", "close"):
            return ""
        raise AssertionError(args)
    result = recovery.retire_conflicted_generated(
        HEAD, run, api, REPO, list_api)
    assert any(r.get("pr") == 227 and r.get("status") == "BLOCKED" for r in result)
    assert any(r.get("number") == 228 and r.get("reason") ==
               "CI_DERIVED_GEN_API_STALE" for r in result)


def test_full_sweep_isolates_t17_4_and_t23_errors_and_processes_healthy_request():
    plans = [("req-901", {"lots": []}, {"stage": "BLOCKED"},
              {"L1": {"task_name": "goodtask"}})]
    processed = []
    def process_one(request, *_args):
        processed.append(request)
        return [{"request": request, "status": "CHAIN_OK"}]
    with patch.object(chain_lots, "check_main", return_value=HEAD), \
         patch.object(chain_lots, "main_ci_decision", return_value="GREEN"), \
         patch.object(chain_lots, "plans", return_value=plans), \
         patch.object(chain_lots, "retire_conflicted_generated",
                      side_effect=ValueError("GITHUB_LIST_RESPONSE_INVALID")), \
         patch.object(chain_lots, "retry_failed_bot_prs", return_value=[]), \
         patch.object(chain_lots, "retry_native_infra", return_value=[]), \
         patch.object(chain_lots, "recover_native_feedback", return_value=[]), \
         patch.object(chain_lots, "recover_route_defects",
                      side_effect=ValueError("LOCAL_ROUTE_BAD_READBACK")), \
         patch.object(chain_lots, "replay_native_integration", return_value=[]), \
         patch.object(chain_lots, "route_request_metadata", return_value=True), \
         patch.object(chain_lots, "publish_missing_registered_pack", return_value=None), \
         patch.object(chain_lots, "publish_legacy_submission_contract", return_value=None), \
         patch.object(chain_lots, "first_parent_merges", return_value=[]), \
         patch.object(chain_lots, "process_one_plan", side_effect=process_one):
        results = chain_lots.process(sweep=True, base_sha=HEAD)
    assert processed == ["req-901"]
    assert any(r.get("phase") == "T17_4_RETIRE" and
               r.get("status") == "BLOCKED" for r in results)
    assert any(r.get("phase") == "T23_ROUTE" and
               r.get("status") == "BLOCKED" for r in results)
    assert any(r.get("request") == "req-901" and r.get("status") == "CHAIN_OK"
               for r in results)


def test_global_integrity_still_blocks_other_work():
    with pytest.raises(chain_lots.ChainBlocked, match="MAIN_DRIFT"):
        chain_lots.sweep_recovery_block("T23_ROUTE",
                                        chain_lots.ChainBlocked("MAIN_DRIFT"))


def test_static_no_github_collection_fed_into_object_api():
    offenders = []
    for source in (ROOT / "pilot/orchestrator").rglob("*.py"):
        if source.name.startswith("test_"):
            continue
        body = source.read_text("utf-8")
        tree = ast.parse(body)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (
                fn.attr if isinstance(fn, ast.Attribute) else "")
            if name not in ("api", "api_list", "gh_api"):
                continue
            if not node.args:
                continue
            path = node.args[0]
            fragments = [item.value for item in ast.walk(path)
                         if isinstance(item, ast.Constant)
                         and isinstance(item.value, str)]
            joined = "".join(fragments)
            is_list = ("/files" in joined and "pulls/" in joined
                       or "/comments" in joined and "issues/" in joined
                       or "pulls?" in joined)
            if is_list and name != "api_list":
                offenders.append(f"{source.relative_to(ROOT)}:{node.lineno}:{name}")
    assert not offenders, "GITHUB_COLLECTION_USED_WITH_OBJECT_API:" + ",".join(offenders)
