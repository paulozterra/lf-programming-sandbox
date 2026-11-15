"""T20: reject floating or dynamic GitHub Actions runner labels."""
from __future__ import annotations
from pathlib import Path
import re
import subprocess
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
PINNED = "ubuntu-24.04"


def _train_exception_allowed(folder: Path) -> bool:
    # Only while the trusted main still has the old Train runner.
    if folder.resolve() != WORKFLOWS.resolve():
        return False
    try:
        raw = subprocess.run(
            ["git", "-C", str(ROOT), "show",
             "refs/remotes/origin/main:.github/workflows/sandbox-train.yml"],
            capture_output=True, text=True, check=True,
        ).stdout
        return yaml.safe_load(raw)["jobs"]["merge"]["runs-on"] == "ubuntu-latest"
    except (OSError, subprocess.CalledProcessError, KeyError, TypeError,
            yaml.YAMLError):
        return False


def verify_runner_pins(folder: Path = WORKFLOWS) -> list[str]:
    failures = []
    train_pending = _train_exception_allowed(folder)
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
            if label != PINNED and not (
                train_pending and file.name == "sandbox-train.yml"
                and job == "merge" and label == "ubuntu-latest"
            ):
                failures.append(f"WORKFLOW_RUNNER_FLOTANTE:{file.name}:{job}")
    return failures


class RunnerPins(unittest.TestCase):
    def test_all_22_workflows_pinned(self):
        self.assertEqual(len(list(WORKFLOWS.glob("*.yml"))), 22)
        self.assertEqual(verify_runner_pins(), [])

    def test_train_exception_not_granted_to_other_folders_or_pinned_main(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / "sandbox-train.yml"
            file.write_text("jobs:\n  merge:\n    runs-on: ubuntu-latest\n")
            self.assertEqual(verify_runner_pins(Path(tmp)), [
                "WORKFLOW_RUNNER_FLOTANTE:sandbox-train.yml:merge"])
        with patch(__name__ + "._train_exception_allowed", return_value=False):
            self.assertIn("WORKFLOW_RUNNER_FLOTANTE:sandbox-train.yml:merge",
                          verify_runner_pins())

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
