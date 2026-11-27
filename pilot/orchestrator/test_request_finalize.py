"""F1.B/T9: use existing terminal evidence and administrative-only closure."""
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from pilot.config.testing import install_project_config
from pilot.orchestrator import request_finalize as mod, request_lifecycle as life
from pilot.orchestrator.lifecycle_test_support import fake_api, evidence_fixture, TEST_MAIN
from pilot.orchestrator.pg37_evidence import render

SLUG = "req-17"

def fixture(root, *, lots=("A", "B"), merged=("A",), report=True):
    install_project_config(root)
    folder = root / "pilot/runs" / SLUG
    folder.mkdir(parents=True)
    (folder / "request_meta.json").write_text(json.dumps({"issue": 17}))
    (folder / "state.json").write_text(json.dumps({"stage": "LOTS_PLANNED", "request_id": SLUG}))
    (folder / "lots.json").write_text(json.dumps({"lots": [{"id": x} for x in lots]}))
    ledger = root / "pilot/registry/implemented.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps({"entries": [
        {"request": SLUG, "lot": x, "merge_sha": "a"*40,
         "status": "NO_DERIVABLE" if x == "A" else "ATTESTED"} for x in merged]}))
    records = [evidence_fixture(SLUG, x, "a"*40) for x in merged]
    (folder / "evidence").mkdir()
    for row in records:
        (folder / "evidence" / (row["lot_id"] + "-" + "a"*12 + ".json")).write_text(json.dumps(row))
    if report:
        (folder / "H_REPORT.md").write_text(render(SLUG, records))
    return folder


class FinalizeTests(unittest.TestCase):
    def test_candidate_and_exhaustion_without_decision_do_not_close(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = fixture(root)
            for stage in ("LOTS_PLANNED", "BLOCKED", "CHAIN_COMPLETE_CANDIDATE"):
                (folder / "state.json").write_text(json.dumps({"stage": stage}))
                with patch.object(mod, "ROOT", root):
                    self.assertEqual(list(mod.terminal_requests()), [])
            (folder / "state.json").write_text(json.dumps({"stage": "FAILED_FINAL"}))
            with self.assertRaises(mod.FinalizationError):
                mod.terminal_outcome(mod.LocalView(root), SLUG)

    def test_all_merged_lots_and_current_report_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = fixture(root, merged=("A", "B"))
            with patch.object(mod, "ROOT", root):
                self.assertEqual(list(mod.terminal_requests())[0][2], "CHAIN_COMPLETE_VERIFIED")
                (folder / "H_REPORT.md").write_text(render(SLUG, [evidence_fixture(SLUG, "A", "a"*40)]))
                self.assertEqual(list(mod.terminal_requests()), [])
                (folder / "H_REPORT.md").unlink()
                self.assertEqual(list(mod.terminal_requests()), [])

    def test_administrative_gate_is_distinct_and_live(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = fixture(root, merged=("A", "B"))
            outcome = mod.terminal_outcome(mod.LocalView(root), SLUG)
            row = dict(slug=SLUG, issue=17, revision=TEST_MAIN,
                       stage=outcome["stage"], fingerprint=outcome["fingerprint"])
            api = fake_api({}, root=root)
            self.assertEqual(life.request_state(SLUG, api, root=root), life.CLOSED_FINALIZED)
            with self.assertRaisesRegex(life.RequestStateError, "REQUEST_CLOSED"):
                life.require_open(SLUG, api, root=root)
            self.assertTrue(life.require_administrative_close(row, api, root=root))
            paused = fake_api({SLUG: {"state": life.SUSPENDING, "authorization_pr": 77}}, root=root)
            with self.assertRaisesRegex(life.RequestStateError, "REQUEST_SUSPENDED"):
                life.require_administrative_close(row, paused, root=root)
            for bad in (dict(row, revision="b"*40), dict(row, fingerprint="0"*64)):
                with self.assertRaises(life.RequestStateError):
                    life.require_administrative_close(bad, api, root=root)
            (folder / "H_REPORT.md").write_text("tampered")
            with self.assertRaises(life.RequestStateError):
                life.require_administrative_close(row, api, root=root)

    def test_close_revalidates_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root, merged=("A", "B"))
            outcome = mod.terminal_outcome(mod.LocalView(root), SLUG)
            row = dict(slug=SLUG, issue=17, revision=TEST_MAIN, stage=outcome["stage"],
                       fingerprint=outcome["fingerprint"], intervencion_manual=False)
            (root / "manifest.json").write_text(json.dumps([row]))
            class APIStub:
                def __init__(self):
                    self.ops, self.comments = [], []
                    self.state, self.blocked = "open", True
                def issue(self, number):
                    return {"number": number, "state": self.state,
                            "labels": [{"name": "lf-request-blocked"}] if self.blocked else []}
                def comment(self, number, body):
                    self.ops.append(("COMMENT", number))
                    self.comments.append({"id": 1, "user": {"login": mod.BOT}, "body": body})
                def call(self, method, path, payload=None):
                    if method == "GET":
                        if path == "/issues/17":
                            return self.issue(17)
                        if path.startswith("/issues/17/comments?"):
                            return self.comments
                        return fake_api({}, issue_state=self.state, root=root)(path.lstrip("/"))
                    self.ops.append((method, path))
                    if method == "PATCH":
                        self.state = "closed"
                    if method == "DELETE":
                        self.blocked = False
            api = APIStub()
            with patch.object(mod, "ROOT", root), patch.object(mod, "API", return_value=api), patch.dict("os.environ", {"GH_TOKEN": "offline", "GITHUB_RUN_ID": "123", "GITHUB_REPOSITORY": "example/sandbox"}):
                mod.close(root)
                mod.close(root)
            self.assertEqual(api.ops, [("COMMENT",17),("PATCH","/issues/17"),("DELETE","/issues/17/labels/lf-request-blocked")])

    def test_only_explicit_terminal_states(self):
        self.assertFalse({"LOTS_PLANNED", "BLOCKED", "INTEGRATION_PENDING"} & mod.TERMINAL)
        self.assertIn("FAILED_FINAL", mod.TERMINAL)
        self.assertIn("CANCELLED_FINAL", mod.TERMINAL)

if __name__ == "__main__":
    unittest.main()
