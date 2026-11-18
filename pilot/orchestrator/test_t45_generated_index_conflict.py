"""T45: generated-index-only conflicts are kept; offline injected boundaries."""
import json
import subprocess

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
    assert result == [{"status": "KEPT", "pr": PR, "branch": BRANCH,
                       "sha": HEAD,
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


def test_t45_cp36_kept_receipt_never_enters_regenerator():
    from unittest.mock import patch
    from pilot.orchestrator import chain_lots

    kept = {"status": "KEPT", "pr": PR, "branch": BRANCH,
            "sha": HEAD, "reason": "CONFLICT_ONLY_GENERATED_CHANGES_INDEX"}
    with patch.object(chain_lots, "check_main", return_value=MAIN), \
         patch.object(chain_lots, "main_ci_decision", return_value="GREEN"), \
         patch.object(chain_lots, "retire_conflicted_generated",
                      return_value=[kept]), \
         patch.object(chain_lots, "plans", return_value=[]), \
         patch.object(chain_lots, "retry_failed_bot_prs", return_value=[]), \
         patch.object(chain_lots, "retry_native_infra", return_value=[]), \
         patch.object(chain_lots, "recover_native_feedback", return_value=[]), \
         patch.object(chain_lots, "recover_route_defects", return_value=[]), \
         patch.object(chain_lots, "regenerate_conflicted",
                      side_effect=AssertionError("KEPT must not regenerate")):
        outcomes = chain_lots.process(sweep=True, base_sha=MAIN)
    assert kept in outcomes


@pytest.mark.parametrize("extra_conflict", [False, True])
def test_t45_real_git_merge_tree_and_published_pull_ref(tmp_path, extra_conflict):
    """Exercise real Git porcelain, merge-tree messages and a bare PR remote."""
    work = tmp_path / "work"
    remote = tmp_path / "origin.git"
    work.mkdir()

    def git(*argv):
        return subprocess.run(["git", "-C", str(work), *argv],
                              text=True, capture_output=True, check=True).stdout.strip()

    subprocess.run(["git", "init", "--bare", str(remote)],
                   check=True, text=True, capture_output=True)
    git("init", "-q")
    git("config", "user.name", "T45 test")
    git("config", "user.email", "t45@example.invalid")
    git("remote", "add", "origin", str(remote))
    generated = work / GENERATED_CHANGES_INDEX
    generated.parent.mkdir(parents=True)
    generated.write_text("base\n", encoding="utf-8")
    other = work / "src/other.py"
    other.parent.mkdir(parents=True)
    other.write_text("base\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    git("switch", "-qc", "proposed")
    generated.write_text("proposed\n", encoding="utf-8")
    if extra_conflict:
        other.write_text("proposed\n", encoding="utf-8")
    git("commit", "-qam", "proposed")
    proposed_sha = git("rev-parse", "HEAD")
    git("push", "-q", "origin", f"HEAD:refs/pull/{PR}/head")
    git("switch", "-qc", "main", base)
    generated.write_text("main\n", encoding="utf-8")
    if extra_conflict:
        other.write_text("main\n", encoding="utf-8")
    git("commit", "-qam", "main")
    main_sha = git("rev-parse", "HEAD")

    probe = subprocess.run(
        ["git", "-C", str(work), "merge-tree", "--write-tree",
         "--name-only", "--messages", main_sha, proposed_sha],
        text=True, capture_output=True)
    if probe.returncode == 129 and (
        "unknown option" in probe.stderr or "usage:" in probe.stderr.lower()
    ):
        pytest.skip("Installed Git lacks merge-tree --write-tree support")
    assert probe.returncode == 1, (probe.returncode, probe.stdout, probe.stderr)

    def command(*args):
        if args[:3] == ("gh", "pr", "list"):
            row, _ = fixtures()
            return json.dumps([{**row, "headRefOid": proposed_sha}])
        if args[:3] == ("gh", "pr", "close"):
            return ""
        result = subprocess.run(args, cwd=work, capture_output=True, text=True)
        if result.returncode:
            raise OSError(f"git command failed: {args[0:3]}, code={result.returncode}")
        return result.stdout.strip()

    def api(path):
        assert path == f"pulls/{PR}"
        _, detail = fixtures()
        detail["head"]["sha"] = proposed_sha
        return detail

    receipt = retire_conflicted_generated(main_sha, command, api, REPO,
                                           api_list=lambda _: [])
    if extra_conflict:
        assert len(receipt) == 1
        assert receipt[0]["number"] == PR
        assert receipt[0]["reason"] == "GitHub mergeable_state=dirty"
    else:
        assert receipt == [{
            "status": "KEPT", "pr": PR, "branch": BRANCH, "sha": proposed_sha,
            "reason": "CONFLICT_ONLY_GENERATED_CHANGES_INDEX",
        }]
