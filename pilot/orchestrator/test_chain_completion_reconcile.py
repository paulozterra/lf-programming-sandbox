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


if __name__ == "__main__":
    unittest.main()
