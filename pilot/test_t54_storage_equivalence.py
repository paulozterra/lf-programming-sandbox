"""T54 phase 2: equivalence of every migrated storage-path consumer.

The sandbox baseline is an independent literal contract, not computed from the
new helper. Test signatures are pinned for audit trigger public functions.
"""
import inspect
import json
from pathlib import Path
import re
import unittest

from config.project_config import storage, storage_path, template_path_pattern

ROOT = Path(__file__).resolve().parents[1]
BASE = {
    "requests_root": "pilot/runs",
    "registrations_root": "pilot/worker_v08/native_tasks",
    "chain_plans_root": "pilot/orchestrator/chain_plans",
    "task_template_pattern": "pilot/runs/{request}/templates/{task}.task.json",
}


class StorageEquivalence(unittest.TestCase):
    def test_exact_baseline(self):
        self.assertEqual(storage(), BASE)

    def test_paths_for_each_migrated_consumer(self):
        # Each function has its own fixture, even where roots are shared.
        cases = {
            "chain_lots.plans.legacy": ("chain_plans_root", (), "pilot/orchestrator/chain_plans"),
            "chain_lots.plans.runs": ("requests_root", (), "pilot/runs"),
            "chain_lots.plans.folder": ("requests_root", ("req-286",), "pilot/runs/req-286"),
            "chain_lots.failed_lots": ("registrations_root", ("req286backend2.json",), "pilot/worker_v08/native_tasks/req286backend2.json"),
            "chain_lots.exam_key.registration": ("registrations_root", ("req286backend2.json",), "pilot/worker_v08/native_tasks/req286backend2.json"),
            "chain_lots.complete_registered_exam_requests": ("registrations_root", ("x.json",), "pilot/worker_v08/native_tasks/x.json"),
            "chain_lots.request_missing_exam": ("registrations_root", ("x.json",), "pilot/worker_v08/native_tasks/x.json"),
            "chain_lots.regenerate_template": ("requests_root", ("req-286",), "pilot/runs/req-286"),
            "chain_lots.prepare_successor": ("requests_root", ("req-286", "proposal_requests"), "pilot/runs/req-286/proposal_requests"),
            "chain_lots.route_request_metadata": ("requests_root", ("req-286", "request_meta.json"), "pilot/runs/req-286/request_meta.json"),
            "chain_lots.publish_missing_registered_pack": ("requests_root", ("req-286", "proposal_requests"), "pilot/runs/req-286/proposal_requests"),
            "chain_lots.publish_legacy_submission_contract": ("requests_root", ("req-286", "proposal_requests", "x.proposal-request.json"), "pilot/runs/req-286/proposal_requests/x.proposal-request.json"),
            "chain_lots.block_request": ("requests_root", ("req-286", "state.json"), "pilot/runs/req-286/state.json"),
            "chain_lots.verify_new_plan": ("requests_root", ("req-286", "chain_plan.json"), "pilot/runs/req-286/chain_plan.json"),
            "chain_lots.process_one_plan": ("registrations_root", ("x.json",), "pilot/worker_v08/native_tasks/x.json"),
            "plan_lots.plan": ("requests_root", ("req-286",), "pilot/runs/req-286"),
            "request_trigger.close_done": ("requests_root", ("req-286", "audit", "report.json"), "pilot/runs/req-286/audit/report.json"),
            "request_trigger.candidates": ("requests_root", ("req-286", "audit"), "pilot/runs/req-286/audit"),
            "request_trigger.main": ("requests_root", ("req-286", "analysis.json"), "pilot/runs/req-286/analysis.json"),
        }
        for consumer, (kind, parts, expected) in cases.items():
            with self.subTest(consumer=consumer):
                self.assertEqual(storage_path(kind, *parts, root=ROOT), ROOT / expected)

    def test_regex_exact_equivalence_and_security(self):
        req = "req-286"
        old = re.compile(
            rf"pilot/runs/{re.escape(req)}/templates/[a-z][a-z0-9_-]{{0,31}}[.]task[.]json"
        )
        new = template_path_pattern(req)
        samples = [
            "pilot/runs/req-286/templates/abc.task.json",
            "pilot/runs/req-286/templates/a.task.json",
            "pilot/runs/req-286/templates/a_b-0.task.json",
            "pilot/runs/req-287/templates/a.task.json",
            "pilot/runs/req-286/templates/A.task.json",
            "pilot/runs/req-286/templates/../a.task.json",
            "pilot/runs/req-286/templates/a.task.json/evil",
            "pilot/runs/req-286/templates/a.task.json\n",
            "pilot/runs/req-286/templates/.task.json",
            "pilot/runs/req-286/templates/" + "a" * 33 + ".task.json",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(bool(old.fullmatch(sample)), bool(new.fullmatch(sample)))

    def test_public_signatures_unchanged(self):
        import audit.request_trigger as trigger
        self.assertEqual(str(inspect.signature(trigger.close_done)), "(repo: 'str', root: 'Path' = ROOT) -> 'list[dict]'".replace("ROOT", repr(trigger.ROOT)))
        self.assertEqual(list(inspect.signature(trigger.candidates).parameters),
                         ["config", "plans", "root", "repository", "api"])
        self.assertEqual(list(inspect.signature(trigger.issue_body).parameters),
                         ["request", "data", "config"])

    def test_invalid_storage_keys_and_segments(self):
        from config.project_config import ProjectConfigError
        for kind, parts in [("unknown", ()), ("requests_root", ("..",)),
                            ("requests_root", ("x/y",)), ("requests_root", (".",))]:
            with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                storage_path(kind, *parts)


if __name__ == "__main__":
    unittest.main()
