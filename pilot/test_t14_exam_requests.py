"""T14: select the legitimate exam request and close only after main registration."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "orchestrator"))
from pilot.orchestrator import chain_lots
from pilot.orchestrator.lifecycle_test_support import fake_api


TASK = "lotexample1"
REQUEST = "req-901"


def issue(number, *, state="open", reason=None):
    return {
        "number": number, "title": "EXAM_REQUEST: " + TASK,
        "body": f"- Pedido: `{REQUEST}`\n- Task ID: `{TASK}`\n"
                + chain_lots.exam_issue_marker(TASK),
        "state": state, "state_reason": reason,
    }


def fixture(root):
    import shutil
    source_config = Path(__file__).resolve().parents[1] / "pilot/config"
    target_config = root / "pilot/config"
    (target_config / "projects").mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_config / "active_project.json", target_config / "active_project.json")
    shutil.copy2(source_config / "projects/sandbox.json", target_config / "projects/sandbox.json")
    source = root / "pilot/runs/req-901/templates/lotexample1.task.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(json.dumps({"task_spec": {
        "write_path_patterns": ["contracts/sample.openapi.yaml"],
        "context_path_patterns": [], "protected_path_patterns": []}}))
    return ({"task_name": TASK, "template_path": "pilot/runs/req-901/templates/lotexample1.task.json"},
            {"id": "SOL-1", "area": "CONTRATO", "requirement_ids": ["REQ-ONE"]})


class GitMock:
    def __init__(self, rows):
        self.rows = list(rows)
        self.created = 0
        self.closed = []
    def __call__(self, *argv, **kwargs):
        if argv[:3] == ("gh", "label", "list"):
            return json.dumps([{"name": "exam-request"}])
        if argv[:2] == ("gh", "api"):
            return json.dumps(self.rows)
        if argv[:3] == ("gh", "issue", "create"):
            self.created += 1
            return "https://github.com/example/repo/issues/new"
        if argv[:3] == ("gh", "issue", "comment"):
            return ""
        if argv[:3] == ("gh", "issue", "close"):
            self.closed.append((int(argv[3]), argv))
            return ""
        raise AssertionError(argv)


class T14ExamRequestTests(unittest.TestCase):
    def setUp(self):
        chain_lots._EXAM_RUN_CACHE.clear()

    def test_open_wins_over_closed_duplicate_regardless_of_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binding, lot = fixture(root)
            git = GitMock([issue(195, state="closed", reason="not_planned"),
                           issue(194, state="open")])
            with patch.object(chain_lots, "ROOT", root), patch.object(
                    chain_lots, "api", side_effect=fake_api({})), patch.object(
                    chain_lots, "run", side_effect=git):
                result = chain_lots.request_missing_exam(REQUEST, binding, lot)
            self.assertEqual(result["exam_issue"], 194)
            self.assertEqual(result["reason_code"], "EXAMEN_PENDIENTE")
            self.assertEqual(git.created, 0)

    def test_completed_closure_with_main_registration_is_terminal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binding, lot = fixture(root)
            registered = root / "pilot/worker_v08/native_tasks" / (TASK + ".json")
            registered.parent.mkdir(parents=True)
            registered.write_text("{}")
            git = GitMock([issue(195, state="closed", reason="not_planned"),
                           issue(194, state="open"),
                           issue(196, state="closed", reason="completed")])
            with patch.object(chain_lots, "ROOT", root), patch.object(
                    chain_lots, "api", side_effect=fake_api({})), patch.object(
                    chain_lots, "run", side_effect=git):
                result = chain_lots.request_missing_exam(REQUEST, binding, lot)
            self.assertEqual(result, {"status": "EXAM_ALREADY_REGISTERED",
                                      "task": TASK, "exam_issue": 196})
            registered.unlink()
            chain_lots._EXAM_RUN_CACHE.clear()
            with patch.object(chain_lots, "ROOT", root), patch.object(
                    chain_lots, "api", side_effect=fake_api({})), patch.object(
                    chain_lots, "run", side_effect=git):
                self.assertEqual(chain_lots.request_missing_exam(
                    REQUEST, binding, lot)["exam_issue"], 194)

    def test_only_closed_duplicates_block_without_new_request(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binding, lot = fixture(root)
            git = GitMock([issue(195, state="closed", reason="not_planned"),
                           issue(193, state="closed", reason="duplicate")])
            with patch.object(chain_lots, "ROOT", root), patch.object(
                    chain_lots, "api", side_effect=fake_api({})), patch.object(
                    chain_lots, "run", side_effect=git):
                result = chain_lots.request_missing_exam(REQUEST, binding, lot)
            self.assertEqual(result["reason_code"], "EXAM_REQUEST_PREVIOUSLY_DISCARDED")
            self.assertEqual(git.created, 0)

    def test_only_unverified_closed_remains_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binding, lot = fixture(root)
            git = GitMock([issue(195, state="closed", reason="not_planned"),
                           issue(194, state="closed", reason="completed")])
            with patch.object(chain_lots, "ROOT", root), patch.object(
                    chain_lots, "api", side_effect=fake_api({})), patch.object(
                    chain_lots, "run", side_effect=git):
                result = chain_lots.request_missing_exam(REQUEST, binding, lot)
                self.assertEqual(result["reason_code"], "EXAM_REQUEST_CLOSED_UNVERIFIED")
            self.assertEqual(git.created, 0)

    def test_exam_on_main_allows_preparation_then_main_registration_closes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binding, lot = fixture(root)
            encrypted = root / "pilot/holdouts" / (TASK + ".oracle.json.age")
            encrypted.parent.mkdir(parents=True)
            encrypted.write_bytes(b"opaque-fixture-not-an-oracle")
            git = GitMock([issue(194, state="open"),
                           issue(195, state="closed", reason="not_planned")])
            with patch.object(chain_lots, "ROOT", root), patch.object(
                    chain_lots, "api", side_effect=fake_api({})), patch.object(
                    chain_lots, "run", side_effect=git), patch.object(
                    chain_lots, "require_green_base"), patch.object(
                    chain_lots, "protected_test_conflict"):
                self.assertIsNone(chain_lots.admit_registration(
                    REQUEST, binding, lot, "a" * 40))
                self.assertEqual(chain_lots.complete_registered_exam_requests(
                    REQUEST, {"SOL-1": binding}), [])
                self.assertEqual(git.closed, [])
                registered = root / "pilot/worker_v08/native_tasks" / (TASK + ".json")
                registered.parent.mkdir(parents=True)
                registered.write_text("{}")
                self.assertEqual(chain_lots.complete_registered_exam_requests(
                    REQUEST, {"SOL-1": binding}), [194])
                self.assertEqual(git.closed[0][0], 194)
                self.assertEqual(git.closed[0][1][-2:], ("--reason", "completed"))


if __name__ == "__main__":
    unittest.main()
