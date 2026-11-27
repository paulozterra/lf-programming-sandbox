"""CHG-0251: verified last-attempt completion must outlive prior blocked drafts."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import chain_lots as cl
import pg37_publish as pg37
from chain_contract import progress


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.lots = {"schema_version": "CP33_LOTS_CANDIDATE_V1",
                     "production_authority": False, "handoff_allowed": False,
                     "worker_invoked": False,
                     "lots": [{"id": "A", "area": "BACKEND", "depends_on": []},
                              {"id": "B", "area": "BACKEND", "depends_on": ["A"]},
                              {"id": "C", "area": "BACKEND", "depends_on": ["B"]}]}
        self.bindings = {key: {"task_name": "task" + key} for key in ("A", "B", "C")}
        self.receipts = {key: {"lot_id": key, "merge_sha": value * 40}
                         for key, value in (("A", "a"), ("B", "b"), ("C", "c"))}

    def test_three_spent_failures_then_pass_is_complete_not_blocked(self):
        result = progress(self.lots, self.receipts, {"C": [10, 11, 12]},
                          self.bindings)
        self.assertEqual(result["stage"], "CHAIN_COMPLETE_CANDIDATE")
        self.assertEqual(result["blocked_lot_ids"], [])

    def test_t32_forgiven_attempt_then_pass_is_complete(self):
        result = progress(self.lots, self.receipts, {"C": [12, 14]},
                          self.bindings)
        self.assertEqual(result["stage"], "CHAIN_COMPLETE_CANDIDATE")

    def test_verified_completion_state_removes_stale_block_reason(self):
        state = {"stage": "BLOCKED",
                 "blocked_lot_ids": ["C"], "reason_code": cl.BLOCK_CODE}
        result = cl.complete_candidate_state(state, self.receipts, self.lots)
        self.assertEqual(result["stage"], "CHAIN_COMPLETE_CANDIDATE")
        self.assertNotIn("blocked_lot_ids", result)
        self.assertNotIn("reason_code", result)
        self.assertEqual(result["completed_lot_ids"], ["A", "B", "C"])
        self.assertFalse(result["production_authority"])

    def test_incomplete_lots_cannot_publish_completion(self):
        with self.assertRaises(cl.ChainBlocked):
            cl.complete_candidate_state({"stage": "LOTS_PLANNED"},
                                        {"A": self.receipts["A"]}, self.lots)

    def test_process_skips_attempt_ledger_and_exam_requests_after_last_pass(self):
        with (patch.object(cl, "request_state", return_value=cl.OPEN),
              patch.object(cl, "completed_lots", return_value=self.receipts),
              patch.object(cl, "failed_lots", side_effect=AssertionError("ledger read")),
              patch.object(cl, "request_all_lot_exams",
                           side_effect=AssertionError("exam re-request")),
              patch.object(cl, "complete_registered_exam_requests",
                           side_effect=AssertionError("exam close")),
              patch.object(cl, "reconcile_complete_chain",
                           return_value={"status": "CHAIN_COMPLETE_DRAFT"}) as reconcile):
            result = cl.process_one_plan("req-186", self.lots,
                                         {"stage": "LOTS_PLANNED"},
                                         self.bindings, "f" * 40, "TRAIN",
                                         True, None, None, [])
        self.assertEqual(result, [{"request": "req-186",
                                   "status": "CHAIN_COMPLETE_DRAFT"}])
        reconcile.assert_called_once()

    def test_sweep_retirement_only_after_verified_completion(self):
        with (patch.object(cl, "close_stale_drafts", return_value=[267]) as close,
              patch.object(cl, "pending_draft", return_value=True)):
            result = cl.reconcile_complete_chain(
                "req-186", {"stage": "LOTS_PLANNED"},
                self.lots, self.receipts, "f" * 40, sweep=True)
        self.assertEqual(result["status"], "CHAIN_COMPLETE_DRAFT_PENDING")
        self.assertEqual(result["retired_blocked_prs"], [267])
        self.assertEqual([c.args for c in close.call_args_list],
                         [("lf/chain-blocked/req-186-", "ffffffffffff", "req-186"),
                          ("lf/chain-complete/req-186-", "ffffffffffff", "req-186")])

    def test_stale_completion_candidate_from_older_main_is_superseded(self):
        with (patch.object(cl, "close_stale_drafts", side_effect=[[], [376]]) as close,
              patch.object(cl, "pending_draft", return_value=False),
              patch.object(cl, "worktree", return_value={"status": "CHAIN_COMPLETE_DRAFT"}) as wt):
            result = cl.reconcile_complete_chain(
                "req-186", {"stage": "LOTS_PLANNED"},
                self.lots, self.receipts, "f" * 40, sweep=True)
        self.assertEqual(result["status"], "CHAIN_COMPLETE_DRAFT")
        self.assertEqual(close.call_args_list[1].args, ("lf/chain-complete/req-186-", "ffffffffffff", "req-186"))
        wt.assert_called_once()

    def test_pg37_sweep_retires_bot_draft_from_older_main(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            from pilot.config.testing import install_project_config
            install_project_config(root)
            (root / "pilot/runs/req-186").mkdir(parents=True)
            with (patch.object(pg37.chain_lots, "check_main",
                               return_value="f" * 40),
                  patch.object(pg37.chain_lots, "plans",
                               return_value=[("req-186", self.lots,
                                              {"stage": "LOTS_PLANNED"},
                                              self.bindings)]),
                  patch.object(pg37, "request_state", return_value=cl.OPEN),
                  patch.object(pg37.chain_lots, "pending_draft",
                               side_effect=[True, False]),
                  patch.object(pg37.chain_lots, "close_stale_drafts",
                               return_value=[237]) as close,
                  patch.object(pg37.chain_lots, "first_parent_merges",
                               return_value=[]),
                  patch.object(pg37.chain_lots, "completed_lots",
                               return_value={})):
                self.assertEqual(pg37.sweep(root=root),
                                 [{"status": "R1_CP37_NO_MISSING_EVIDENCE"}])
            close.assert_called_once_with("lf/evidence/req-186-", "ffffffffffff", "req-186")

    def test_pg37_sweep_does_not_override_pending_current_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            from pilot.config.testing import install_project_config
            install_project_config(root)
            (root / "pilot/runs/req-286").mkdir(parents=True)
            with (patch.object(pg37.chain_lots, "check_main",
                               return_value="f" * 40),
                  patch.object(pg37.chain_lots, "plans",
                               return_value=[("req-286", self.lots,
                                              {"stage": "LOTS_PLANNED"},
                                              self.bindings)]),
                  patch.object(pg37, "request_state", return_value=cl.OPEN),
                  patch.object(pg37.chain_lots, "pending_draft",
                               side_effect=[True, True]),
                  patch.object(pg37.chain_lots, "close_stale_drafts",
                               return_value=[]) as close,
                  patch.object(pg37.chain_lots, "first_parent_merges",
                               side_effect=AssertionError("must not scan"))):
                self.assertEqual(pg37.sweep(root=root),
                                 [{"status": "R1_CP37_NO_MISSING_EVIDENCE"}])
            close.assert_called_once()

    def test_non_sweep_does_not_retire_any_pr(self):
        with patch.object(cl, "close_stale_drafts",
                          side_effect=AssertionError("unexpected side effect")):
            self.assertEqual(cl.reconcile_complete_chain(
                "req-286", {"stage": "LOTS_PLANNED"},
                self.lots, self.receipts, "f" * 40, sweep=False),
                {"status": "CHAIN_COMPLETE_CANDIDATE"})


class TerminalCandidateTests(unittest.TestCase):
    """Acceptance model of req-652, all receipts simulated in a temporary root."""
    def setUp(self):
        from pilot.config.testing import install_project_config
        from pilot.orchestrator.lifecycle_test_support import evidence_fixture
        from pilot.orchestrator.pg37_evidence import render
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        install_project_config(self.root)
        self.slug = "req-652"
        self.ids = ["SOL-Cf376a709e8a9", "SOL-002", "SOL-K91c33077cc68", "SOL-001"]
        self.lots = {"lots": [{"id": x} for x in self.ids]}
        self.bindings = {x: {"task_name": t} for x, t in zip(self.ids, (
            "req652contrato1", "req652backend2", "req652frontend3", "req652frontend4"))}
        self.state = {"stage": "BLOCKED", "request_id": self.slug}
        self.recovery = {"original_task": "req652backend2", "successor_task": "req652backend22",
                         "original_run_ids": [101, 102, 103], "max_additional_attempts": 1}
        self.receipts = {x: {"merge_sha": sha, "task_name": self.bindings[x]["task_name"]}
                         for x, sha in [(self.ids[0], "a"*40), (self.ids[2], "b"*40)]}
        self.folder = self.root / "pilot/runs" / self.slug
        self.folder.mkdir(parents=True)
        (self.folder / "lots.json").write_text(json.dumps(self.lots))
        (self.folder / "state.json").write_text(json.dumps(self.state))
        ledger = self.root / "pilot/registry/implemented.json"
        ledger.parent.mkdir(parents=True)
        self.ledger = ledger
        ledger.write_text(json.dumps({"entries": [
            {"request": self.slug, "lot": x, "merge_sha": r["merge_sha"],
             "status": "ATTESTED" if x == self.ids[0] else "NO_DERIVABLE"}
            for x, r in self.receipts.items()]}))
        rows = [evidence_fixture(self.slug, x, r["merge_sha"]) for x, r in self.receipts.items()]
        (self.folder / "evidence").mkdir()
        for row in rows:
            (self.folder / "evidence" / (row["lot_id"] + "-" + row["merge_sha"][:12] + ".json")).write_text(json.dumps(row))
        (self.folder / "H_REPORT.md").write_text(render(self.slug, rows))

    def candidate(self, *, result="FAILED_FINAL", spent=True, completed=None):
        complete = self.receipts if completed is None else completed
        def failures(bindings, strict=False):
            return {"SOL-002": ([201] if spent else []) if strict else [101,102,103]}
        with (patch.object(cl, "ROOT", self.root),
              patch.object(cl, "first_parent_merges", return_value=[]),
              patch.object(cl, "completed_lots", return_value=complete),
              patch.object(cl, "lot_recoveries", return_value={"SOL-002": self.recovery}),
              patch.object(cl, "failed_lots", side_effect=failures)):
            return cl.terminal_candidate_state(self.slug, self.lots, self.state, self.bindings,
                                               "e"*40, result, 77)

    def test_effective_one_of_one_failure_preserves_two_integrations(self):
        from pilot.orchestrator.request_finalize import LocalView, terminal_outcome
        before = self.ledger.read_bytes()
        candidate, empty = self.candidate()
        self.assertIsNone(empty)
        self.assertEqual(candidate["stage"], "FAILED_FINAL")
        self.assertEqual(candidate["completed_merge_shas"], {x: r["merge_sha"] for x,r in self.receipts.items()})
        self.assertEqual(candidate["terminal"]["exhaustion"]["SOL-002"], {
            "task": "req652backend22", "max_attempts": 1, "run_ids": [201], "original_run_ids": [101,102,103]})
        (self.folder / "state.json").write_text(json.dumps(candidate))
        self.assertEqual(terminal_outcome(LocalView(self.root), self.slug)["stage"], "FAILED_FINAL")
        self.assertEqual(self.ledger.read_bytes(), before)
        self.assertEqual(cl.process_one_plan(self.slug, self.lots, candidate, self.bindings, "e"*40,
                                             "TRAIN", True, None, None, []),
                         [{"request": self.slug, "status": "REQUEST_CLOSED"}])

    def test_terminal_owner_proof_prevents_reopening_and_partial_audit(self):
        from pilot.orchestrator import request_lifecycle as life
        from pilot.orchestrator.request_finalize import LocalView, terminal_outcome
        from pilot.orchestrator.lifecycle_test_support import fake_api, main_response
        candidate, _ = self.candidate()
        base, head, merge = "e"*40, "b"*40, "c"*40
        (self.folder / "state.json").write_text(json.dumps(candidate))
        (self.folder / "request_meta.json").write_text(json.dumps({"issue": 652}))
        prior = self.root / "previous"
        previous = prior / "pilot/runs" / self.slug
        previous.mkdir(parents=True)
        (previous / "state.json").write_text(json.dumps(self.state))
        outcome = terminal_outcome(LocalView(self.root), self.slug)
        row = dict(slug=self.slug, issue=652, revision=merge,
                   stage=outcome["stage"], fingerprint=outcome["fingerprint"])
        def api(path, closed=False, approved=True):
            if path == "git/ref/heads/main":
                return main_response(path, self.root, merge)
            if path.startswith("contents/") and "?ref=" in path and not path.endswith("?ref=main"):
                revision = path.split("?ref=")[1]
                return main_response(path, prior if revision == base else self.root, revision)
            if path == "pulls/77":
                return {"number":77, "merged":True, "merge_commit_sha":merge,
                        "merged_at":"2026-11-27T06:00:00Z",
                        "base":{"ref":"main","repo":{"full_name":"example/sandbox"}},
                        "head":{"ref":f"lf/chain-terminal/{self.slug}-{base[:12]}",
                                "sha":head,"repo":{"full_name":"example/sandbox"}}}
            if path == f"commits/{merge}":
                return {"sha":merge, "parents":[{"sha":base},{"sha":head}],
                        "commit":{"message":"Merge PR #77 via sandbox-train"}}
            if path.startswith("pulls/77/reviews?"):
                return [{"id":1,"user":{"login":"example"},"state":"COMMENTED",
                         "commit_id":head,"submitted_at":"2026-11-27T05:59:00Z",
                         "body":life.transition_marker(self.slug,"BLOCKED","FAILED_FINAL",head)}] if approved else []
            return fake_api({}, root=self.root, issue_state="closed" if closed else "open")(path)
        self.assertEqual(life.request_state(self.slug, api, root=self.root), life.CLOSED_FAILED)
        self.assertTrue(life.require_administrative_close(row, api, root=self.root))
        with self.assertRaisesRegex(life.RequestStateError, "REQUEST_CLOSED"):
            life.require_open(self.slug, api, root=self.root)
        with self.assertRaisesRegex(life.RequestStateError, "AUDIT_REQUEST_NOT_FINALIZED"):
            life.require_finalized_audit(self.slug, lambda p: api(p, closed=True), root=self.root)
        with self.assertRaisesRegex(life.RequestStateError, "REQUEST_STATE_UNRESOLVED"):
            life.request_state(self.slug, lambda p: api(p, approved=False), root=self.root)

    def test_unspent_governed_successor_not_terminal(self):
        with self.assertRaisesRegex(cl.ChainBlocked, "TERMINAL_RECOVERY_STILL_AVAILABLE"):
            self.candidate(spent=False)

    def test_last_legitimate_merge_precedes_failure(self):
        all_lots = {x: {"merge_sha": "a"*40, "task_name": self.bindings[x]["task_name"]} for x in self.ids}
        with self.assertRaisesRegex(cl.ChainBlocked, "TERMINAL_SUCCESS_TAKES_PRECEDENCE"):
            self.candidate(completed=all_lots)

    def test_stale_report_rejected(self):
        (self.folder / "H_REPORT.md").write_text("incomplete")
        with self.assertRaises(ValueError):
            self.candidate()

    def test_formal_cancel_is_distinct(self):
        candidate, _ = self.candidate(result="CANCELLED_FINAL")
        self.assertEqual(candidate["reason_code"], "OWNER_CANCELLED")
        self.assertEqual(candidate["terminal"]["exhaustion"], {})

    def test_zero_integrated_has_truthful_report(self):
        self.ledger.write_text(json.dumps({"entries": []}))
        (self.folder / "H_REPORT.md").unlink()
        candidate, report = self.candidate(completed={})
        self.assertEqual(candidate["completed_merge_shas"], {})
        self.assertIn(b"SIN_LOTES_INTEGRADOS", report)
        self.assertNotIn(b"OBSERVED_MERGE", report)



if __name__ == "__main__":
    unittest.main()
