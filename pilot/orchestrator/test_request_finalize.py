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
                    if method == "POST":
                        return self.comment(17, payload["body"])
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

    def test_late_suspension_prevents_issue_patch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root, merged=("A", "B"))
            outcome = mod.terminal_outcome(mod.LocalView(root), SLUG)
            row = dict(slug=SLUG, issue=17, revision=TEST_MAIN, stage=outcome["stage"],
                       fingerprint=outcome["fingerprint"], intervencion_manual=False)
            (root / "manifest.json").write_text(json.dumps([row]))
            class APIStub:
                def __init__(self):
                    self.paused = False
                    self.ops = []
                def issue(self, number):
                    return {"number": number, "state": "open", "labels": []}
                def comment(self, number, body):
                    self.ops.append(("COMMENT", number))
                    self.paused = True
                def call(self, method, path, payload=None):
                    if method == "POST":
                        return self.comment(17, payload["body"])
                    if method != "GET":
                        self.ops.append((method, path))
                        return {}
                    if path.startswith("/issues/17/comments?"):
                        return []
                    ledger = {SLUG: {"state": life.SUSPENDING,
                                      "authorization_pr": 77}} if self.paused else {}
                    return fake_api(ledger, root=root)(path.lstrip("/"))
            api = APIStub()
            with patch.object(mod, "ROOT", root), patch.object(mod, "API", return_value=api), patch.dict("os.environ", {"GH_TOKEN": "offline", "GITHUB_RUN_ID": "123", "GITHUB_REPOSITORY": "example/sandbox"}):
                mod.close(root)
            self.assertEqual(api.ops, [("COMMENT", 17)])

    def test_guard_rejects_observed_main_control_and_issue_drift(self):
        from pilot.orchestrator.lifecycle_test_support import CONTROL, content, main_response
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root, merged=("A", "B"))
            outcome = mod.terminal_outcome(mod.LocalView(root), SLUG)
            row = dict(slug=SLUG, issue=17, revision=TEST_MAIN,
                       stage=outcome["stage"], fingerprint=outcome["fingerprint"])
            ledger = root / "pilot/registry/implemented.json"
            original = ledger.read_bytes()
            for effect in ("admission", "administrative"):
                if effect == "admission":
                    entries = json.loads(original)
                    entries["entries"] = entries["entries"][:1]
                    ledger.write_text(json.dumps(entries))
                    self.assertEqual(life.request_state(SLUG, fake_api({}, root=root), root=root), life.OPEN)
                else:
                    ledger.write_bytes(original)
                    self.assertTrue(life.require_administrative_close(row, fake_api({}, root=root), root=root))
                for fault in ("main_after_first_control", "main_during_last_control",
                              "control_during_outcome", "issue_during_outcome"):
                    with self.subTest(effect=effect, fault=fault):
                        state = {"sha": TEST_MAIN, "controls": 0, "issues": 0}
                        def api(path):
                            if path == "git/ref/heads/main":
                                return main_response(path, root, state["sha"])
                            if path == f"contents/{CONTROL}?ref=main":
                                state["controls"] += 1
                                if fault == "main_after_first_control" and state["controls"] == 1:
                                    state["sha"] = "b"*40
                                if fault == "main_during_last_control" and state["controls"] == 2:
                                    state["sha"] = "b"*40
                                if fault == "control_during_outcome" and state["controls"] >= 2:
                                    return fake_api({SLUG: {"state":life.SUSPENDING,"authorization_pr":77}}, root=root)(path)
                                return content({})
                            if path == "issues/17":
                                state["issues"] += 1
                                return {"number":17,"state":"closed" if fault == "issue_during_outcome" and state["issues"] > 1 else "open"}
                            if path.startswith("contents/") and path.endswith("?ref="+TEST_MAIN):
                                return main_response(path, root)
                            return fake_api({SLUG: {"state":life.SUSPENDING,"authorization_pr":77}}, root=root)(path)
                        with self.assertRaises(life.RequestStateError):
                            if effect == "admission":
                                life.request_state(SLUG, api, root=root)
                            else:
                                life.require_administrative_close(row, api, root=root)

    def test_reopen_during_delete_guard_prevents_label_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root, merged=("A", "B"))
            outcome = mod.terminal_outcome(mod.LocalView(root), SLUG)
            row = dict(slug=SLUG, issue=17, revision=TEST_MAIN, stage=outcome["stage"],
                       fingerprint=outcome["fingerprint"], intervencion_manual="NO")
            (root / "manifest.json").write_text(json.dumps([row]))
            class APIStub:
                def __init__(self):
                    self.ops, self.closed_reads = [], 0
                    self.closed = False
                def call(self, method, path, payload=None):
                    if method == "GET":
                        if path == "/issues/17":
                            if self.closed:
                                self.closed_reads += 1
                            # First post-PATCH read and guard initial read see
                            # closed, final read sees reopened.
                            return {"number":17, "state":"closed" if self.closed and self.closed_reads < 3 else "open",
                                    "labels":[{"name":"lf-request-blocked"}]}
                        if "/comments?" in path:
                            return []
                        return fake_api({}, root=root)(path[1:])
                    self.ops.append((method,path))
                    if method == "PATCH":
                        self.closed = True
            api = APIStub()
            with patch.object(mod,"ROOT",root), patch.object(mod,"API",return_value=api), patch.dict("os.environ", {"GH_TOKEN":"offline","GITHUB_RUN_ID":"123","GITHUB_REPOSITORY":"example/sandbox"}):
                mod.close(root)
            self.assertEqual(api.ops, [("POST","/issues/17/comments"),("PATCH","/issues/17")])
            self.assertGreaterEqual(api.closed_reads, 3)

    def test_local_report_error_continues_but_global_git_error_surfaces(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root, merged=("A", "B"))
            rows = [("req-17", {"issue":17}, "CHAIN_COMPLETE_VERIFIED"),
                    ("req-18", {"issue":18}, "CHAIN_COMPLETE_VERIFIED")]
            def result(slug, **_kw):
                if slug == "req-17":
                    raise ValueError("invalid local evidence")
                return {"intervencion_manual":"NO"}
            with patch.object(mod,"ROOT",root), patch.object(mod,"terminal_requests",return_value=rows), patch.object(mod,"terminal_outcome",return_value={"fingerprint":"a"*64}), patch.object(mod.subprocess,"check_output",return_value=TEST_MAIN), patch.object(mod,"report",side_effect=result), patch.object(mod,"markdown",return_value="report"):
                prepared = mod.prepare(root)
                self.assertEqual([r["slug"] for r in prepared], ["req-18"])
                with patch.object(mod,"report",side_effect=subprocess.CalledProcessError(128,["git"])):
                    with self.assertRaises(subprocess.CalledProcessError):
                        mod.prepare(root)
            (root / "pilot/registry/implemented.json").write_text("{")
            with patch.object(mod,"ROOT",root), patch.object(mod.subprocess,"check_output",return_value=TEST_MAIN):
                with self.assertRaises(mod.GlobalCloseError):
                    mod.prepare(root)

    def test_local_issue_failure_continues_global_api_failure_does_not(self):
        from urllib.error import HTTPError
        from pilot.orchestrator.issue_intake import Blocked
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [dict(slug=f"req-{n}",issue=n,stage="FAILED_FINAL",revision=TEST_MAIN,
                         fingerprint="a"*64,intervencion_manual="NO") for n in (17,18)]
            (root / "manifest.json").write_text(json.dumps(rows))
            for where in ("issue","comments","post","patch"):
                for status in (404,422,403,429,500):
                    with self.subTest(where=where,status=status):
                        class APIStub:
                            def __init__(self):
                                self.ops = []
                            def call(self, method, path, payload=None):
                                failing = {"issue":("GET","/issues/17"),
                                           "comments":("GET","/issues/17/comments?per_page=100&page=1"),
                                           "post":("POST","/issues/17/comments"),
                                           "patch":("PATCH","/issues/17")}[where]
                                if (method,path) == failing:
                                    raise Blocked("PEDIDO_API_FAILED") from HTTPError(path,status,"error",{},None)
                                if method == "GET":
                                    if "/comments?" in path:
                                        return []
                                    return {"number":int(path.rsplit("/",1)[-1]),"state":"open","labels":[]}
                                self.ops.append((method,path))
                        api = APIStub()
                        with patch.object(mod,"API",return_value=api), patch.object(life,"require_administrative_close",return_value=True), patch.dict("os.environ", {"GH_TOKEN":"offline","GITHUB_RUN_ID":"123","GITHUB_REPOSITORY":"example/sandbox"}):
                            if status in (404,422):
                                mod.close(root)
                                self.assertIn(("PATCH","/issues/18"),api.ops)
                            else:
                                with self.assertRaises(mod.GlobalCloseError):
                                    mod.close(root)
                                self.assertNotIn(("PATCH","/issues/18"),api.ops)

    def test_only_explicit_terminal_states(self):
        self.assertFalse({"LOTS_PLANNED", "BLOCKED", "INTEGRATION_PENDING"} & mod.TERMINAL)
        self.assertIn("FAILED_FINAL", mod.TERMINAL)
        self.assertIn("CANCELLED_FINAL", mod.TERMINAL)

if __name__ == "__main__":
    unittest.main()
