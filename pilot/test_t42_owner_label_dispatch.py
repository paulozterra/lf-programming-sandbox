"""T42: an owner's ready-to-merge label on a bot integration PR dispatches the
Train once (GitHub runs no pull_request workflow for bot-created PRs)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auto_integrate as ai  # noqa: E402

LABEL_AT = "2026-11-17T22:03:29Z"


class Api:
    def __init__(self, actor="paulozterra", permission="admin", runs=()):
        self.actor, self.permission, self.runs, self.posted = actor, permission, list(runs), []

    def pages(self, path, field):
        assert path == "/issues/319/events"
        return [{"event": "labeled", "label": {"name": "ready-to-merge"},
                 "actor": {"login": self.actor}, "created_at": LABEL_AT}]

    def request(self, method, path, data=None, **_):
        if path.startswith("/collaborators/"):
            return {"permission": self.permission}
        if path.startswith("/actions/workflows/sandbox-train.yml/runs"):
            return {"workflow_runs": self.runs}
        if method == "POST":
            self.posted.append((path, data))
            return {}
        raise AssertionError(path)


def test_owner_label_is_dispatched():
    assert ai.owner_labeled_after_last_train(Api(), 319) is True


def test_bot_or_non_admin_label_is_not():
    assert ai.owner_labeled_after_last_train(Api(actor=ai.BOT), 319) is False
    assert ai.owner_labeled_after_last_train(Api(permission="write"), 319) is False


def test_only_once_per_label():
    done = [{"created_at": "2026-11-17T22:10:00Z", "display_title": "sandbox-train PR #319"}]
    assert ai.owner_labeled_after_last_train(Api(runs=done), 319) is False
    older = [{"created_at": "2026-11-17T21:00:00Z", "display_title": "sandbox-train PR #319"}]
    assert ai.owner_labeled_after_last_train(Api(runs=older), 319) is True
    other = [{"created_at": "2026-11-17T22:10:00Z", "display_title": "sandbox-train PR #3190"}]
    assert ai.owner_labeled_after_last_train(Api(runs=other), 319) is True


def test_train_run_name_carries_pr_number():
    wf = (Path(__file__).resolve().parents[1] / ".github/workflows/sandbox-train.yml").read_text()
    assert "format('sandbox-train PR #{0}', inputs.pr_number)" in wf
