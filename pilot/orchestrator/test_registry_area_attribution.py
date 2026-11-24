"""INFRA/CONTRATO lots never claim business rules; INFRA/DATA expose no API."""
import unittest
from pathlib import Path
from unittest.mock import patch

from pilot.orchestrator import implemented_registry as registry

MERGE = "a" * 40
PR = {"merged": True, "merge_commit_sha": MERGE,
      "head": {"ref": "lf/native-integration/req9task1-run-1"},
      "base": {"ref": "main"}}


def command(root, *args):
    if args[:3] == ("git", "rev-list", "--parents"):
        return MERGE + " " + "b" * 40 + " " + "c" * 40
    if args[:3] == ("git", "diff", "--name-only"):
        return "x/file"
    raise AssertionError(args)


class AreaAttributionTests(unittest.TestCase):
    def _record(self, area):
        lots = {"lots": [{"id": "SOL-1", "area": area, "write_paths": ["x/file"],
                          "requirement_ids": ["REQ-UI", "REQ-DATA"]}]}
        plan = {"bindings": [{"lot_id": "SOL-1", "task_name": "req9task1"}]}

        def json_at(root, commit, path):
            return plan if path == "pilot/runs/req-9/chain_plan.json" else None

        with (patch.object(registry, "command", side_effect=command),
              patch.object(registry, "_plans", return_value=[("req-9", lots, {})]),
              patch.object(registry, "json_at", side_effect=json_at),
              patch.object(registry, "_rules", return_value=["RULE-UI", "RULE-DATA"]),
              patch.object(registry, "_contract_endpoints", return_value=None),
              patch.object(registry, "git_file", return_value=b"x")):
            return registry.record_merge(Path("/tmp"), MERGE, PR, current_sha=MERGE)

    def test_infra_claims_no_rules_and_no_api(self):
        row = self._record("INFRA")
        self.assertEqual(row["rule_codes"], [])
        self.assertEqual(row["endpoints"], [])
        self.assertEqual(row["status"], "ATTESTED")
        self.assertEqual(row["requirement_ids"], ["REQ-UI", "REQ-DATA"])

    def test_contract_claims_no_rules_but_still_needs_its_contract(self):
        row = self._record("CONTRATO")
        self.assertEqual(row["rule_codes"], [])
        self.assertIn("CONTRACT_ENDPOINTS_NOT_DERIVABLE", row["reasons"])

    def test_data_keeps_rules_and_has_no_api(self):
        row = self._record("DATA")
        self.assertEqual(row["rule_codes"], ["RULE-UI", "RULE-DATA"])
        self.assertEqual(row["endpoints"], [])
        self.assertEqual(row["status"], "ATTESTED")

    def test_backend_unchanged(self):
        row = self._record("BACKEND")
        self.assertEqual(row["rule_codes"], ["RULE-UI", "RULE-DATA"])
        self.assertIn("CONTRACT_ENDPOINTS_NOT_DERIVABLE", row["reasons"])


if __name__ == "__main__":
    unittest.main()
