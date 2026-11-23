"""CHG-0251: reconstruct historical T7 registry from exact request-local bindings."""
import unittest
from pathlib import Path
from unittest.mock import patch

from pilot.orchestrator import implemented_registry as registry

MERGE = "a" * 40
TASK = "req286backend2"
PR = {"merged": True, "merge_commit_sha": MERGE,
      "head": {"ref": "lf/native-integration/req286backend2-run-44167628590"},
      "base": {"ref": "main"}}


def lot(name="SOL-002", paths=("apps/a.java", "apps/b.java")):
    return {"id": name, "area": "BACKEND", "write_paths": list(paths),
            "requirement_ids": ["REQ-1"]}


def fixture_command(root, *args):
    if args[:3] == ("git", "rev-list", "--parents"):
        return MERGE + " " + "b" * 40 + " " + "c" * 40
    if args[:3] == ("git", "diff", "--name-only"):
        return "apps/a.java"
    raise AssertionError(args)


class RegistryMappingTests(unittest.TestCase):
    def _run(self, plans, local_plan, *, legacy_plan=None):
        def json_from_tree(root, commit, path):
            if path == "pilot/runs/req-286/chain_plan.json":
                return local_plan
            if path == "pilot/orchestrator/chain_plans/req-286.json":
                return legacy_plan
            return None

        with (patch.object(registry, "command", side_effect=fixture_command),
              patch.object(registry, "_plans", return_value=plans),
              patch.object(registry, "json_at", side_effect=json_from_tree),
              patch.object(registry, "git_file", return_value=b"source")):
            return registry.record_merge(Path("/tmp"), MERGE, PR,
                                         current_sha=MERGE)

    def test_local_plan_maps_partial_changed_files_with_full_tree(self):
        binding = {"bindings": [{"lot_id": "SOL-002", "task_name": TASK}]}
        result = self._run([("req-286", {"lots": [lot()]}, {})], binding)
        self.assertEqual(result["request"], "req-286")
        self.assertEqual(result["lot"], "SOL-002")
        self.assertEqual({file["path"] for file in result["files"]},
                         {"apps/a.java", "apps/b.java"})

    def test_explicit_binding_outweighs_legacy_path_collision(self):
        binding = {"bindings": [{"lot_id": "SOL-002", "task_name": TASK}]}
        # The fallback-only row matches the same registered write pattern.
        other = ("other-req", {"lots": [lot("SOL-003", ("apps/a.java",))]}, {})
        with (patch.object(registry, "command", side_effect=fixture_command),
              patch.object(registry, "_plans",
                           return_value=[other, ("req-286", {"lots": [lot()]}, {})]),
              patch.object(registry, "git_file", return_value=b"source"),
              patch.object(registry, "json_at",
                           side_effect=lambda root, commit, path:
                           binding if path == "pilot/runs/req-286/chain_plan.json"
                           else {"task_spec": {"write_path_patterns": ["apps/a.java"]}}
                           if path.endswith("/native_tasks/" + TASK + ".json")
                           else None)):
            result = registry.record_merge(Path("/tmp"), MERGE, PR,
                                           current_sha=MERGE)
        self.assertEqual((result["request"], result["lot"]),
                         ("req-286", "SOL-002"))

    def test_no_changed_file_does_not_claim_lot(self):
        binding = {"bindings": [{"lot_id": "SOL-002", "task_name": TASK}]}
        with patch.object(registry, "command",
                          side_effect=lambda root, *args:
                          "unrelated/path" if args[:3] == ("git", "diff", "--name-only")
                          else fixture_command(root, *args)):
            # _run installs its own command mock, so use a lot with no
            # intersection against the standard integration diff.
            result = self._run([("req-286", {"lots": [
                lot(paths=("unrelated/a.java", "unrelated/b.java"))]}, {})],
                binding)
        self.assertEqual(result["reasons"], ["LOT_MAPPING_MISSING"])

    def test_conflicting_legacy_and_local_plans_fail_closed(self):
        binding = {"bindings": [{"lot_id": "SOL-002", "task_name": TASK}]}
        with self.assertRaisesRegex(registry.RegistryBlocked,
                                    "REGISTRY_PLAN_AMBIGUOUS"):
            self._run([("req-286", {"lots": [lot()]}, {})], binding,
                      legacy_plan={"bindings": []})


if __name__ == "__main__":
    unittest.main()
