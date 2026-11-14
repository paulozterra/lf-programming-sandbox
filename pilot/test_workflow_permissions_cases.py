"""T9.1 offline permission checks and synthetic missing-permission workflows."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("workflow_permissions", HERE / "test_workflow_permissions.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
MAPPING = json.loads((HERE / "workflow_permission_map_v1.json").read_text(encoding="utf-8"))


class PermissionTests(unittest.TestCase):
    def verify(self, text, expected):
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / "synthetic.yml"
            file.write_text(text, encoding="utf-8")
            self.assertEqual(policy.check_workflow(file, MAPPING), expected)

    def test_missing_actions_permission(self):
        self.verify("""name: synthetic
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: gh workflow run ci.yml --ref main
""", ["WORKFLOW_PERMISO_FALTANTE:synthetic.yml:actions"])

    def test_all_mappings_and_job_override(self):
        self.verify("""name: synthetic
permissions: write-all
jobs:
  fail:
    permissions:
      contents: read
    runs-on: ubuntu-latest
    steps:
      - run: |
          gh workflow run ci.yml
          gh pr create --title test
          gh pr edit --add-label blocked
          gh issue comment 160 --body bad
""", [f"WORKFLOW_PERMISO_FALTANTE:synthetic.yml:{p}"
      for p in ("actions", "issues", "pull-requests")])

    def test_valid_permissions_and_unexecuted_comments(self):
        self.verify("""permissions:
  actions: write
  pull-requests: write
  issues: write
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: |
          # gh workflow run ci.yml
          gh workflow run ci.yml
          gh pr create --title test
          gh issue comment 160 --body hello
""", [])

    def test_http_api_equivalent_missing_permission(self):
        self.verify("""permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: |
          gh api -X POST repos/o/r/actions/workflows/ci.yml/dispatches
          gh api -X POST repos/o/r/issues/160/comments
""", ["WORKFLOW_PERMISO_FALTANTE:synthetic.yml:actions",
      "WORKFLOW_PERMISO_FALTANTE:synthetic.yml:issues"])

    def test_repo_workflows(self):
        self.assertEqual(policy.scan(HERE.parent, MAPPING), [])


if __name__ == "__main__":
    unittest.main()
