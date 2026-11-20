"""T9.2 stage timeout tests: next run, no run, notification, discard safety."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import json
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "request_stage_watchdog", HERE / "request_stage_watchdog.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
CONFIG = mod.stage_config()
MERGE_SHA = "a" * 40
MERGED = "2026-11-14T16:00:00Z"


class API:
    def __init__(self, branch="lf/request/req-987", seen=False, open_issue=True):
        self.branch, self.seen, self.open_issue = branch, seen, open_issue

    def api(self, method, path, body=None):
        if path == "/pulls/777":
            return {"number": 777, "merged": True, "merge_commit_sha": MERGE_SHA,
                    "merged_at": MERGED, "base": {"ref": "main"},
                    "head": {"ref": self.branch, "repo": {"full_name": mod.REPO}}}
        if path == "/actions/runs/12345":
            return {"id": 12345, "conclusion": "success",
                    "html_url": f"https://github.com/{mod.REPO}/actions/runs/12345",
                    "path": ".github/workflows/sandbox-train.yml",
                    "repository": {"full_name": mod.REPO}}
        if path == "/issues/987":
            return {"number": 987, "state": "open" if self.open_issue else "closed"}
        if path.startswith("/actions/workflows/"):
            is_t7 = "t7-request" in path
            title = "T7 req-987" if is_t7 else "CP3.6 PR 777"
            return {"workflow_runs": [{"name": CONFIG["REQUEST_MERGED" if is_t7
                                   else "ANALYSIS_MERGED"]["expected_workflow"],
                                     "display_title": title,
                                     "status": "completed", "conclusion": "success",
                                     "created_at": "2026-11-14T16:01:00Z"}]
                    if self.seen else []}
        raise AssertionError((method, path))


class Stages(unittest.TestCase):
    def test_request_merge_without_t7_stalls_after_threshold(self):
        api = API()
        before = datetime(2026, 11, 14, 16, 10, tzinfo=timezone.utc)
        after = datetime(2026, 11, 14, 16, 40, tzinfo=timezone.utc)
        self.assertEqual(mod.evaluate(api, 777, MERGE_SHA, 12345, before, CONFIG)[0],
                         "STAGE_AWAITING_NEXT_RUN")
        with patch.object(mod, "emit", return_value="RUTA_NOTIFIED") as notify:
            self.assertEqual(mod.evaluate(api, 777, MERGE_SHA, 12345, after, CONFIG)[0],
                             "STAGE_STALLED_NOTIFIED")
            run = notify.call_args.args[1]
            self.assertEqual(run["failure_code"], "PEDIDO_ESTANCADO:REQUEST_MERGED")
            self.assertTrue(run["html_url"].endswith("/actions/runs/12345"))

    def test_real_next_run_never_notifies(self):
        with patch.object(mod, "emit") as notify:
            result = mod.evaluate(API(seen=True), 777, MERGE_SHA, 12345,
                                  datetime(2026, 11, 14, 17, tzinfo=timezone.utc), CONFIG)
            self.assertEqual(result[0], "STAGE_NEXT_RUN_FOUND")
            notify.assert_not_called()

    def test_cancelled_expected_title_does_not_count_as_seen(self):
        class Cancelled(API):
            def api(self, method, path, body=None):
                result = super().api(method, path, body)
                if path.startswith("/actions/workflows/"):
                    for row in result["workflow_runs"]:
                        row["status"] = "completed"
                        row["conclusion"] = "cancelled"
                return result
        with patch.object(mod, "emit", return_value="RUTA_NOTIFIED") as notify:
            result = mod.evaluate(Cancelled(seen=True), 777, MERGE_SHA, 12345,
                                  datetime(2026, 11, 14, 17, tzinfo=timezone.utc), CONFIG)
            self.assertEqual(result[0], "STAGE_STALLED_NOTIFIED")
            notify.assert_called_once()

    def test_skipped_does_not_count_but_queued_does(self):
        class Variant(API):
            def __init__(self, status, conclusion):
                super().__init__(seen=True)
                self.status, self.conclusion = status, conclusion

            def api(self, method, path, body=None):
                result = super().api(method, path, body)
                if path.startswith("/actions/workflows/"):
                    for row in result["workflow_runs"]:
                        row.update(status=self.status, conclusion=self.conclusion)
                return result
        self.assertFalse(mod.next_run_seen(Variant("completed", "skipped"),
                                           "REQUEST_MERGED", 777, "req-987", MERGED, CONFIG))
        self.assertTrue(mod.next_run_seen(Variant("queued", None),
                                          "REQUEST_MERGED", 777, "req-987", MERGED, CONFIG))

    def test_discarded_issue_is_never_touched(self):
        with patch.object(mod, "emit") as notify:
            self.assertEqual(mod.evaluate(
                API(open_issue=False), 777, MERGE_SHA, 12345,
                datetime(2026, 11, 14, 17, tzinfo=timezone.utc), CONFIG)[0],
                "STAGE_NEXT_RUN_FOUND")
            notify.assert_not_called()

    def test_generated_merge_uses_chain_and_stage_specific_code(self):
        api = API(branch="lf/generated-t7/" + "d" * 12)
        with patch.object(mod, "git", return_value="pilot/runs/req-987/state.json"), \
             patch.object(mod, "emit", return_value="RUTA_NOTIFIED") as notify:
            result = mod.evaluate(api, 777, MERGE_SHA, 12345,
                                  datetime(2026, 11, 14, 17, tzinfo=timezone.utc), CONFIG)
            self.assertEqual(result[0], "STAGE_STALLED_NOTIFIED")
            self.assertEqual(notify.call_args.args[1]["failure_code"],
                             "PEDIDO_ESTANCADO:ANALYSIS_MERGED")

    def test_native_integration_retry_maps_to_existing_chain(self):
        with tempfile.TemporaryDirectory() as td:
            import shutil
            target = Path(td) / "pilot/config"
            (target / "projects").mkdir(parents=True, exist_ok=True)
            shutil.copy2(HERE.parent / "pilot/config/active_project.json", target / "active_project.json")
            shutil.copy2(HERE.parent / "pilot/config/projects/sandbox.json", target / "projects/sandbox.json")
            folder = Path(td) / "pilot/runs/req-987"
            folder.mkdir(parents=True)
            (folder / "chain_plan.json").write_text(
                json.dumps({"bindings": [{"task_name": "demo"}]}), encoding="utf-8")
            api = API(branch="lf/native-integration/demo2-run-123")
            with patch.object(mod, "SRC", Path(td)), \
                 patch.object(mod, "git", return_value="apps/time-service/Reminder.java"), \
                 patch.object(mod, "emit", return_value="RUTA_NOTIFIED") as notify:
                result = mod.evaluate(
                    api, 777, MERGE_SHA, 12345,
                    datetime(2026, 11, 14, 17, tzinfo=timezone.utc), CONFIG)
                self.assertEqual(result[0], "STAGE_STALLED_NOTIFIED")
                self.assertEqual(notify.call_args.args[1]["failure_code"],
                                 "PEDIDO_ESTANCADO:INTEGRATION_MERGED")

    def test_wait_exits_when_next_run_exists(self):
        result = mod.watch(API(seen=True), 777, MERGE_SHA, 12345, CONFIG,
                           sleep=lambda seconds: self.fail("unexpected sleep"),
                           clock=lambda: datetime(2026, 11, 14, 17, tzinfo=timezone.utc))
        self.assertEqual(result, "STAGE_NEXT_RUN_FOUND")


if __name__ == "__main__":
    unittest.main()
