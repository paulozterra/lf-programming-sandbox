"""T20: reject floating or dynamic GitHub Actions runner labels."""
from __future__ import annotations
from pathlib import Path
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
PINNED = "ubuntu-24.04"


def verify_runner_pins(folder: Path = WORKFLOWS) -> list[str]:
    failures = []
    for file in sorted([*folder.glob("*.yml"), *folder.glob("*.yaml")]):
        try:
            doc = yaml.safe_load(file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError):
            failures.append(f"WORKFLOW_RUNNER_FLOTANTE:{file.name}:__WORKFLOW__")
            continue
        jobs = doc.get("jobs") if isinstance(doc, dict) else None
        if not isinstance(jobs, dict) or not jobs:
            failures.append(f"WORKFLOW_RUNNER_FLOTANTE:{file.name}:__WORKFLOW__")
            continue
        for job, row in jobs.items():
            if isinstance(row, dict) and "uses" in row and "runs-on" not in row:
                continue  # Reusable workflow executes its own pinned jobs.
            label = row.get("runs-on") if isinstance(row, dict) else None
            if label != PINNED:
                failures.append(f"WORKFLOW_RUNNER_FLOTANTE:{file.name}:{job}")
    return failures


class RunnerPins(unittest.TestCase):
    def test_all_22_workflows_pinned(self):
        self.assertEqual(len(list(WORKFLOWS.glob("*.yml"))), 22)
        self.assertEqual(verify_runner_pins(), [])

    def test_floating_and_dynamic_labels_emit_precise_codes(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.yml"
            path.write_text("jobs:\n  a:\n    runs-on: ubuntu-latest\n"
                            "  b:\n    runs-on: ubuntu-26.04-latest\n"
                            "  c:\n    runs-on: unknown-dynamic\n")
            self.assertEqual(verify_runner_pins(Path(tmp)), [
                "WORKFLOW_RUNNER_FLOTANTE:test.yml:a",
                "WORKFLOW_RUNNER_FLOTANTE:test.yml:b",
                "WORKFLOW_RUNNER_FLOTANTE:test.yml:c",
            ])


if __name__ == "__main__":
    result = verify_runner_pins()
    if result:
        raise SystemExit("\n".join(result))
    unittest.main()
