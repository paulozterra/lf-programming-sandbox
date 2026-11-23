"""CHG-0252: GitHub API budget — batched PR reads and failure-only watchdog."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pilot/orchestrator"))
from pilot.orchestrator.implemented_registry import (  # noqa: E402
    RegistryBlocked, batched_pr_reader)

SHA = "b" * 40


def listed(n, merged=True):
    return {"number": n, "head": {"ref": f"lf/native-integration/t{n}"},
            "base": {"ref": "main"}, "merge_commit_sha": SHA,
            "merged_at": "2026-11-20T00:00:00Z" if merged else None}


class BatchedReaderTests(unittest.TestCase):
    def setUp(self):
        self.list_calls, self.single = 0, []

    def reader(self, rows):
        def list_closed():
            self.list_calls += 1
            return rows
        def one(n):
            self.single.append(n)
            return {"number": n, "merged": True, "source": "single"}
        return batched_pr_reader(list_closed, one)

    def test_one_listing_serves_every_merged_pr(self):
        read = self.reader([listed(n) for n in range(1, 250)])
        for n in range(1, 250):
            row = read(n)
            self.assertTrue(row["merged"])
            self.assertEqual(row["merge_commit_sha"], SHA)
        self.assertEqual(self.list_calls, 1)
        self.assertEqual(self.single, [])

    def test_missing_or_unmerged_falls_back_to_exact_read(self):
        read = self.reader([listed(1), listed(2, merged=False)])
        self.assertEqual(read(2)["source"], "single")
        self.assertEqual(read(9)["source"], "single")
        self.assertEqual(self.single, [2, 9])

    def test_invalid_listing_fails_closed(self):
        with self.assertRaises(RegistryBlocked):
            self.reader({"message": "x"})(1)


class WatchdogBudgetTests(unittest.TestCase):
    SOURCES = ("auto-integrate", "chain-lots", "native-verified-integration",
               "pg37-evidence", "request-finalize", "t7-request", "train-handoff")

    def test_dispatch_wake_only_on_failure_or_cancel(self):
        for name in self.SOURCES:
            lines = (ROOT / ".github/workflows" / (name + ".yml")).read_text().splitlines()
            i = next(k for k, l in enumerate(lines)
                     if "gh workflow run request-failure-watchdog.yml" in l)
            guard = [l.strip() for l in lines[max(0, i - 5):i] if l.strip().startswith("if:")]
            self.assertTrue(guard and guard[-1].startswith("if: failure() || cancelled()"), name)

    def test_workflow_run_job_skips_successful_sources(self):
        text = (ROOT / ".github/workflows/request-failure-watchdog.yml").read_text()
        self.assertIn("github.event.workflow_run.conclusion == 'failure'", text)
        self.assertIn("github.event.workflow_run.conclusion == 'timed_out'", text)
        self.assertIn("cron: '*/10 * * * *'", text)  # recovery sweep kept


if __name__ == "__main__":
    unittest.main()
