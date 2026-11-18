"""T45: generated-index-only conflicts are kept; offline injected boundaries."""
import json

import pytest

from pilot.orchestrator.generated_conflict_recovery import (
    GENERATED_CHANGES_INDEX, retire_conflicted_generated,
)

MAIN = "a" * 40
HEAD = "b" * 40
REPO = "paulozterra/lf-programming-sandbox"
BRANCH = "lf/native-registration/req186contrato1-2f384485df66"
PR = 440


def fixtures(dirty=True):
    row = {"number": PR, "headRefName": BRANCH, "headRefOid": HEAD,
           "author": {"login": "github-actions[bot]"}}
    detail = {"number": PR, "state": "open", "merged": False,
              "mergeable_state": "dirty" if dirty else "blocked",
              "user": {"login": "github-actions[bot]"},
              "labels": [{"name": "ready-to-merge"}],
              "base": {"ref": "main"},
              "head": {"sha": HEAD, "ref": BRANCH, "repo": {"full_name": REPO}}}
    return row, detail


def merge_tree(*paths, malformed=False):
    if malformed:
        return "unparseable\nT45_MERGE_EXIT=1"
    messages = ["Auto-merging " + path for path in paths]
    messages += ["CONFLICT (content): Merge conflict in " + path
                 for path in paths]
    return ("c" * 40 + "\n" + "\n".join(paths) + "\n\n"
            + "\n".join(messages) + "\n\nT45_MERGE_EXIT=1")


def exercise(paths=(), *, git_error=False, malformed=False, dirty=True):
    row, detail = fixtures(dirty=dirty)
    calls = []

    def command(*args):
        calls.append(args)
        if args[:3] == ("gh", "pr", "list"):
            return json.dumps([row])
        if args[:3] == ("gh", "pr", "close"):
            return ""
        if args[:3] == ("git", "fetch", "--no-tags"):
            if git_error:
                raise OSError("git is unavailable")
            assert args[-1] == f"refs/pull/{PR}/head"
            return ""
        if args[:3] == ("git", "rev-parse", "FETCH_HEAD"):
            return HEAD
        if args[:2] == ("bash", "-c"):
            if git_error:
                raise OSError("merge-tree failed")
            return merge_tree(*paths, malformed=malformed)
        if args[:3] == ("git", "worktree", "add"):
            raise OSError("fallback unavailable")
        if args[:3] == ("gh", "run", "view"):
            return ('{"event": "local_merge_and_render", "pr": 440, '
                    '"head": "' + HEAD + '"}\nTRAIN_BLOCKED BRANCH_CONFLICT')
        raise AssertionError(args)

    def api(path):
        if path == f"pulls/{PR}":
            return detail
        if path.startswith("actions/workflows/sandbox-train.yml/runs?"):
            return {"workflow_runs": [{
                "id": 100, "event": "workflow_dispatch", "head_branch": "main",
                "status": "completed", "conclusion": "failure",
                "created_at": "2026-11-18T00:00:00Z",
            }]}
        raise AssertionError(path)

    result = retire_conflicted_generated(MAIN, command, api, REPO,
                                         api_list=lambda _: [])
    return result, calls


def test_t45_only_generated_changes_index_kept():
    result, calls = exercise([GENERATED_CHANGES_INDEX])
    assert result == [{"status": "KEPT", "pr": PR,
                       "reason": "CONFLICT_ONLY_GENERATED_CHANGES_INDEX"}]
    assert not any(c[:3] == ("gh", "pr", "close") for c in calls)


@pytest.mark.parametrize("paths", [
    [GENERATED_CHANGES_INDEX, "src/other.py"],
    ["src/other.py"],
])
def test_t45_other_conflicts_retired(paths):
    result, calls = exercise(paths)
    assert len(result) == 1 and result[0]["number"] == PR
    assert any(c[:3] == ("gh", "pr", "close") for c in calls)


@pytest.mark.parametrize("options", [
    {"git_error": True}, {"malformed": True},
])
def test_t45_git_failure_or_unreadable_output_retired(options):
    result, calls = exercise([GENERATED_CHANGES_INDEX], **options)
    assert len(result) == 1 and result[0]["number"] == PR
    assert any(c[:3] == ("gh", "pr", "close") for c in calls)


def test_t45_train_failure_non_dirty_keeps_prior_logic():
    result, calls = exercise(dirty=False)
    assert len(result) == 1 and "Train BRANCH_CONFLICT" in result[0]["reason"]
    assert any(c[:3] == ("gh", "pr", "close") for c in calls)
    assert not any(c[0] == "git" for c in calls)
