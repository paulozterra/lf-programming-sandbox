"""T54 2b: active-project fail-closed, exact Worker regex and storage audit."""
from __future__ import annotations

import json
import re
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

from config.project_config import (
    ProjectConfigError, active_project, load, storage, storage_path,
    template_path_any_request, template_path_pattern,
    request_context_pattern, reuse_assessment_pattern,
)
import sys
project_config = sys.modules[storage_path.__module__]  # the module these names came from


ROOT = Path(__file__).resolve().parents[1]
# Explicit, individually justified exceptions only. No blanket directories.
EXCEPTIONS: dict[str, set[str]] = {}


class Phase2b(unittest.TestCase):
    def test_active_project_and_root_are_authoritative(self):
        self.assertEqual(active_project(root=ROOT), "sandbox")
        self.assertEqual(storage(root=ROOT), load("sandbox", root=ROOT)["storage"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                active_project(root=root)
            # A data root never supplies configuration: paths resolve under it
            # with the repository's validated config.
            self.assertEqual(storage_path("requests_root", "req-1", root=root),
                             root / storage(root=ROOT)["requests_root"] / "req-1")
            # A broken configuration repository is denied (CONFIG_ROOT).
            with patch.object(project_config, "CONFIG_ROOT", root):
                with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                    storage_path("requests_root", root=root)
            (root / "pilot/config").mkdir(parents=True)
            selector = root / "pilot/config/active_project.json"
            for value in ({}, {"schema_version": "LF_ACTIVE_PROJECT_V1", "project_id": "../sandbox"},
                          {"schema_version": "LF_ACTIVE_PROJECT_V1", "project_id": "missing"}):
                selector.write_text(json.dumps(value))
                with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                    active_project(root=root)
            # An explicit project still needs its config under the supplied root.
            with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                storage(root=root, project="sandbox")
            import shutil
            (root / "pilot/config/projects").mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "pilot/config/projects/sandbox.json",
                         root / "pilot/config/projects/sandbox.json")
            selector.write_text(json.dumps({"schema_version": "LF_ACTIVE_PROJECT_V1",
                                            "project_id": "sandbox"}))
            self.assertEqual(active_project(root=root), "sandbox")
            self.assertEqual(storage_path("requests_root", "req-901", root=root),
                             root / "pilot/runs/req-901")
            self.assertTrue(template_path_any_request(root=root).fullmatch(
                "pilot/runs/req-901/templates/task202.task.json"))

    def test_unconfigured_config_repo_is_denied_even_with_real_config_available(self):
        from pilot.config.testing import install_project_config
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                storage(root=root)
            with patch.object(project_config, "CONFIG_ROOT", root):
                with self.assertRaisesRegex(ProjectConfigError, "PROJECT_CONFIG_INVALID"):
                    template_path_any_request(root=root)
            install_project_config(root)
            self.assertEqual(storage(root=root)["requests_root"], storage(root=ROOT)["requests_root"])

    def test_exact_worker_template_regex(self):
        old = re.compile(r"pilot/runs/req-[1-9][0-9]*/templates/[a-z][a-z0-9_-]{0,31}[.]task[.]json")
        new = template_path_any_request(root=ROOT, project="sandbox")
        for value in (
            "pilot/runs/req-1/templates/a.task.json",
            "pilot/runs/req-901/templates/task202.task.json",
            "pilot/runs/req-0/templates/a.task.json",
            "pilot/runs/req-01/templates/a.task.json",
            "pilot/runs/req-1/templates/A.task.json",
            "pilot/runs/req-1/templates/../a.task.json",
            "pilot/runs/req-1/templates/a.task.json/evil",
            "pilot/runs/req-1/templates/a.task.json\n",
            "pilot/runs/req-1/templates/" + "a"*33 + ".task.json",
        ):
            with self.subTest(value=value):
                self.assertEqual(bool(old.fullmatch(value)), bool(new.fullmatch(value)))

    def test_equivalence_for_every_migrated_function(self):
        cases = {
            "request_lifecycle._finalized": ("requests_root", ("req-1",), "pilot/runs/req-1"),
            "request_lifecycle.request_for_task.registration": ("registrations_root", ("task202.json",), "pilot/worker_v08/native_tasks/task202.json"),
            "request_lifecycle.request_for_task.plans": ("chain_plans_root", (), "pilot/orchestrator/chain_plans"),
            "request_lifecycle.request_for_task.per_request": ("requests_root", (), "pilot/runs"),
            "t4_admission._legacy_template_matches": ("requests_root", ("req-901", "chain_plan.json"), "pilot/runs/req-901/chain_plan.json"),
            "t4_admission.registration_variant": ("registrations_root", (), "pilot/worker_v08/native_tasks"),
            "native_run.load_registration": ("registrations_root", ("task202.json",), "pilot/worker_v08/native_tasks/task202.json"),
            "native_run.registration_holdout_ref": ("registrations_root", ("task202.json",), "pilot/worker_v08/native_tasks/task202.json"),
            "native_run.execute.route_retry": ("registrations_root", ("task202.json",), "pilot/worker_v08/native_tasks/task202.json"),
            "request_finalize.terminal_requests": ("requests_root", (), "pilot/runs"),
            "chain_lots.conflicted_request": ("requests_root", (), "pilot/runs"),
            "chain_lots.publish_legacy_submission_contract": ("requests_root", ("req-901", "proposal_requests"), "pilot/runs/req-901/proposal_requests"),
        }
        for name, (kind, parts, expected) in cases.items():
            with self.subTest(name=name):
                self.assertEqual(storage_path(kind, *parts, root=ROOT, project="sandbox"), ROOT / expected)

    def test_request_and_reuse_regex_exact(self):
        old = re.compile(r"pilot/runs/(req-[1-9][0-9]*)/")
        new = request_context_pattern(root=ROOT, project="sandbox")
        for s in ("pilot/runs/req-1/lots.json", "pilot/runs/req-0/lots.json",
                  "pilot/runs/req-01/lots.json", "pilot/runs/req-1x/lots.json"):
            self.assertEqual(bool(old.match(s)), bool(new.match(s)))
        old_reuse = re.compile(r"pilot/runs/[a-z][a-z0-9_-]{0,63}/reuse_assessment[.]json")
        new_reuse = reuse_assessment_pattern(root=ROOT, project="sandbox")
        for s in ("pilot/runs/req-1/reuse_assessment.json", "pilot/runs/A/reuse_assessment.json",
                  "pilot/runs/a/reuse_assessment.json", "pilot/runs/a/reuse_assessment.json/evil"):
            self.assertEqual(bool(old_reuse.fullmatch(s)), bool(new_reuse.fullmatch(s)))

    def test_no_hardcoded_storage_literals_outside_config(self):
        forbidden = ('"pilot/runs"', '"pilot/worker_v08/native_tasks"',
                     '"pilot/orchestrator/chain_plans"')
        found = []
        for path in sorted((ROOT / "pilot").rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            if path.name.startswith("test_") or "/test_" in relative or relative.startswith("pilot/config/"):
                continue
            text = path.read_text(encoding="utf-8")
            for literal in forbidden:
                if literal in text and literal not in EXCEPTIONS.get(relative, set()):
                    found.append(f"{relative}: {literal}")
        self.assertEqual(found, [], "\n".join(found))


if __name__ == "__main__":
    unittest.main()
