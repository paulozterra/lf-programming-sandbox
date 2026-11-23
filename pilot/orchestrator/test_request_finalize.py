"""T9 terminal-only close test: candidates and provisional reports do not close."""
import importlib.util
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from pilot.config.testing import install_project_config

HERE = Path(__file__).resolve().parent


def load():
    spec = importlib.util.spec_from_file_location("request_finalize_t9",
                                                  HERE / "request_finalize.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FinalizeTests(unittest.TestCase):
    def test_candidate_h_report_does_not_close(self):
        mod = load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_project_config(root)
            folder = root / "pilot/runs/req-17"
            folder.mkdir(parents=True)
            (folder / "request_meta.json").write_text(
                json.dumps({"issue": 17, "author": "owner",
                            "date": "2026-11-14T15:00:00Z"}))
            (folder / "state.json").write_text(
                json.dumps({"stage": "LOTS_PLANNED"}))
            (folder / "H_REPORT.md").write_text("# candidate")
            with patch.object(mod, "ROOT", root):
                self.assertEqual(list(mod.terminal_requests()), [])
                (folder / "state.json").write_text(
                    json.dumps({"stage": "COMPLETED"}))
                self.assertEqual(list(mod.terminal_requests())[0][2], "COMPLETED")

    def test_all_merged_lots_and_final_report_allow_closure(self):
        mod = load()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_project_config(root)
            folder = root / "pilot/runs/req-17"
            folder.mkdir(parents=True)
            ledger = root / "pilot/registry/implemented.json"
            ledger.parent.mkdir(parents=True)
            (folder / "request_meta.json").write_text(
                json.dumps({"issue": 17, "author": "owner",
                            "date": "2026-11-14T15:00:00Z"}))
            (folder / "state.json").write_text(json.dumps({"stage": "LOTS_PLANNED"}))
            (folder / "lots.json").write_text(json.dumps(
                {"lots": [{"id": "SOL-001"}, {"id": "SOL-002"}]}))
            (folder / "H_REPORT.md").write_text("# Final")
            ledger.write_text(json.dumps({"entries": [
                {"request": "req-17", "lot": "SOL-001", "merge_sha": "a" * 40,
                 "status": "ATTESTED"}]}))
            with patch.object(mod, "ROOT", root):
                self.assertEqual(list(mod.terminal_requests()), [])
                ledger.write_text(json.dumps({"entries": [
                    {"request": "req-17", "lot": n, "merge_sha": "a" * 40,
                     "status": "ATTESTED"} for n in ("SOL-001", "SOL-002")]}))
                self.assertEqual(list(mod.terminal_requests())[0][2],
                                 "CHAIN_COMPLETE_VERIFIED")
                (folder / "state.json").write_text(
                    json.dumps({"stage": "CHAIN_COMPLETE_CANDIDATE"}))
                self.assertEqual(list(mod.terminal_requests())[0][2],
                                 "CHAIN_COMPLETE_VERIFIED")
                (folder / "H_REPORT.md").unlink()
                self.assertEqual(list(mod.terminal_requests()), [])

    def test_only_explicit_terminal_states(self):
        mod = load()
        self.assertNotIn("LOTS_PLANNED", mod.TERMINAL)
        self.assertNotIn("BLOCKED", mod.TERMINAL)
        self.assertNotIn("INTEGRATION_PENDING", mod.TERMINAL)


if __name__ == "__main__":
    unittest.main()
