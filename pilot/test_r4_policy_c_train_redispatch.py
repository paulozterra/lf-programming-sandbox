"""R4 (CHG-0250): policy C recovers a bot ready-to-merge label whose Train run
was replaced in the sandbox-train concurrency group or never dispatched."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auto_integrate as ai  # noqa: E402

LABEL_AT = "2026-11-20T20:00:00Z"


def run(i, status="completed", conclusion="cancelled", at="2026-11-20T20:01:00Z", n=371):
    return {"id": i, "status": status, "conclusion": conclusion, "created_at": at,
            "display_title": f"sandbox-train PR #{n}"}


class Api:
    def __init__(self, actor=ai.BOT, runs=(), labeled=True):
        self.actor, self.runs, self.labeled, self.posted = actor, list(runs), labeled, []

    def pages(self, path, field):
        assert path == "/issues/371/events"
        if not self.labeled:
            return []
        return [{"event": "labeled", "label": {"name": ai.READY_LABEL},
                 "actor": {"login": self.actor}, "created_at": LABEL_AT}]

    def request(self, method, path, data=None, **_):
        if path.startswith("/actions/workflows/sandbox-train.yml/runs"):
            return {"workflow_runs": self.runs}
        if method == "POST":
            self.posted.append((path, data))
            return {}
        raise AssertionError(path)


class R4Tests(unittest.TestCase):
    def decide(self, api):
        return ai.labeled_train_recovery(api, 371)

    def test_missing_train_is_dispatched_once(self):
        api = Api()
        self.assertEqual(self.decide(api), "TRAIN_REDISPATCHED_MISSING")
        self.assertEqual(api.posted, [("/actions/workflows/sandbox-train.yml/dispatches",
                                       {"ref": "main", "inputs": {"pr_number": "371"}})])

    def test_replaced_pending_train_is_redispatched(self):
        api = Api(runs=[run(10)])
        self.assertEqual(self.decide(api), "TRAIN_REDISPATCHED_CANCELLED")
        self.assertEqual(len(api.posted), 1)

    def test_active_train_waits(self):
        for status in ("queued", "in_progress", "waiting", "pending"):
            api = Api(runs=[run(10), run(11, status=status, conclusion=None)])
            self.assertEqual(self.decide(api), "ALREADY_LABELED")
            self.assertEqual(api.posted, [])

    def test_failed_train_requires_review(self):
        api = Api(runs=[run(10, conclusion="failure")])
        with self.assertRaisesRegex(ai.PolicyBlocked, "TRAIN_FAILED_REQUIRES_REVIEW"):
            self.decide(api)
        self.assertEqual(api.posted, [])

    def test_success_with_open_pr_is_blocked(self):
        with self.assertRaisesRegex(ai.PolicyBlocked, "TRAIN_SUCCEEDED_PR_STILL_OPEN"):
            self.decide(Api(runs=[run(10, conclusion="success")]))

    def test_redispatch_is_bounded(self):
        runs = [run(i) for i in range(10, 10 + ai.TRAIN_REDISPATCH_LIMIT)]
        api = Api(runs=runs)
        with self.assertRaisesRegex(ai.PolicyBlocked, "TRAIN_REDISPATCH_LIMIT"):
            self.decide(api)
        self.assertEqual(api.posted, [])

    def test_runs_before_label_or_other_pr_are_ignored(self):
        api = Api(runs=[run(1, conclusion="failure", at="2026-11-20T19:00:00Z"),
                        run(2, conclusion="failure", n=3710)])
        self.assertEqual(self.decide(api), "TRAIN_REDISPATCHED_MISSING")

    def test_latest_run_by_id_decides(self):
        api = Api(runs=[run(12, status="in_progress", conclusion=None), run(11)])
        self.assertEqual(self.decide(api), "ALREADY_LABELED")

    def test_human_label_keeps_owner_path(self):
        api = Api(actor="paulozterra")
        self.assertEqual(self.decide(api), "ALREADY_LABELED")
        self.assertEqual(api.posted, [])

    def test_no_label_event(self):
        self.assertEqual(self.decide(Api(labeled=False)), "ALREADY_LABELED")


if __name__ == "__main__":
    unittest.main()
