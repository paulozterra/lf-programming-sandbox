"""T9.4: workflow YAML entrypoint extraction and fresh-process smoke regression."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pilot import workflow_python_commands as tool

ROOT = Path(__file__).resolve().parents[1]


def make(root, name, content):
    path = root / ".github/workflows" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class WorkflowPythonCommandsTests(unittest.TestCase):
    def test_extracts_multiline_bash_and_module_forms(self):
        with tempfile.TemporaryDirectory() as td:
            p = make(Path(td), "sample.yml", """on: workflow_dispatch
jobs:
  sample:
    runs-on: ubuntu-latest
    steps:
      - run: |
          # python3 pilot/ignored.py
          python3 pilot/orchestrator/t7_entry.py --root .
          result="$(python3 -m pilot.orchestrator.issue_intake)"
          python3 -m pytest --help
""")
            self.assertEqual(tool.commands(p), [
                ("module", "pilot.orchestrator.issue_intake"),
                ("script", "pilot/orchestrator/t7_entry.py")
            ])

    def test_old_script_form_blocks_before_smoke(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make(root, "bad.yml", """jobs:
  one:
    steps:
      - run: python3 pilot/orchestrator/t7_entry.py --root .
""")
            with patch.object(tool, "smoke", side_effect=AssertionError("must not import")):
                self.assertEqual(tool.scan(root),
                                 ["WORKFLOW_COMANDO_NO_EJECUTABLE:bad.yml:pilot/orchestrator/t7_entry.py"])

    def test_missing_module_exposes_precise_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make(root, "missing.yml", """jobs:
  one:
    steps:
      - run: python3 -m pilot.definitely_nonexistent
""")
            self.assertEqual(tool.scan(root),
                             ["WORKFLOW_COMANDO_NO_EJECUTABLE:missing.yml:pilot.definitely_nonexistent"])

    def test_wrapper_command_extraction(self):
        with tempfile.TemporaryDirectory() as td:
            path = make(Path(td), "wrapped.yml", """jobs:
  route:
    steps:
      - run: python3 -m pilot.workflow_entrypoint pilot/orchestrator/t7_entry.py --root .
""")
            self.assertEqual(tool.commands(path), [
                ("wrapper", "pilot/orchestrator/t7_entry.py")])

    def test_runtime_checkout_scripts_need_declared_checkout_and_import(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            local = root / "pilot/worker_v08/probe.py"
            local.parent.mkdir(parents=True)
            local.write_text("value = 1\n")
            wf = make(root, "external.yml", """jobs:
  probe:
    steps:
      - uses: actions/checkout@v5
        with:
          path: source
      - run: python3 source/pilot/worker_v08/probe.py
""")
            self.assertEqual(tool.scan(root), [])
            wf.write_text("""jobs:
  probe:
    steps:
      - run: python3 source/pilot/worker_v08/probe.py
""")
            self.assertEqual(tool.scan(root), [
                "WORKFLOW_COMANDO_NO_EJECUTABLE:external.yml:source/pilot/worker_v08/probe.py"])

    def test_wrapped_command_in_shell_substitution(self):
        with tempfile.TemporaryDirectory() as td:
            wf = make(Path(td), "substitution.yml", """jobs:
  probe:
    steps:
      - run: result="$(python3 -m pilot.workflow_entrypoint pilot/orchestrator/issue_intake.py)"
""")
            self.assertEqual(tool.commands(wf), [
                ("wrapper", "pilot/orchestrator/issue_intake.py")])

    def test_smoke_does_not_inherit_pythonpath(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pkg = root / "pilot"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")
            (pkg / "probe.py").write_text(
                "import os\nassert 'PYTHONPATH' not in os.environ\n")
            with patch.dict("os.environ", {"PYTHONPATH": "/tmp/fake-injected-path"}):
                self.assertEqual(tool.smoke(root, "module", "pilot.probe")[0], True)

    def test_real_t7_command_is_shared_launcher(self):
        path = ROOT / ".github/workflows/t7-request.yml"
        self.assertIn(("wrapper", "pilot/orchestrator/t7_entry.py"), tool.commands(path))
        self.assertNotIn(("script", "pilot/orchestrator/t7_entry.py"), tool.commands(path))


if __name__ == "__main__":
    unittest.main()
