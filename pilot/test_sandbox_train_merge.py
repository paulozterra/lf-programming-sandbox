"""Offline integration tests with real disposable Git repositories, no network."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sandbox_train_merge", ROOT / "pilot/sandbox_train_merge.py")
merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge)


def run(root, *args):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class RealGitSmoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        run(self.root, "init", "-b", "main")
        run(self.root, "config", "user.name", "CP02 Test")
        run(self.root, "config", "user.email", "cp02@example.invalid")
        (self.root / "standards/changes").mkdir(parents=True)
        (self.root / "standards/tools").mkdir(parents=True)
        (self.root / "standards/changes/CHG-0001.json").write_text('{"change_id":"CHG-0001"}')
        self.render_script = """import json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
ids=sorted(json.loads(p.read_text())["change_id"] for p in (root/"standards/changes").glob("CHG-*.json"))
expected="\\n".join(ids)+"\\n"
p=root/"standards/CAMBIOS.md"
if sys.argv[1]=="render":
    if len(sys.argv)>2 and sys.argv[2]=="--check":
        sys.exit(0 if p.read_text()==expected else 1)
    p.write_text(expected)
elif sys.argv[1]=="check":
    assert sys.argv[2]=="--base"
    assert (root/".git").exists()
    assert p.read_text()==expected
else:
    sys.exit(2)
"""
        (self.root / "standards/tools/changes.py").write_text(self.render_script)
        (self.root / "standards/CAMBIOS.md").write_text("CHG-0001\n")
        (self.root / "README.md").write_text("base\n")
        (self.root / "unrelated.txt").write_text("base\n")
        run(self.root, "add", ".")
        run(self.root, "commit", "-m", "baseline")
        self.initial = run(self.root, "rev-parse", "HEAD")

    def commit(self, name):
        run(self.root, "add", ".")
        run(self.root, "commit", "-m", name)
        return run(self.root, "rev-parse", "HEAD")

    def diverge(self, conflict_cambios=False, conflict_other=False):
        run(self.root, "checkout", "-b", "smoke")
        if conflict_cambios:
            (self.root / "standards/changes/CHG-0003.json").write_text('{"change_id":"CHG-0003"}')
        if conflict_cambios:
            (self.root / "standards/CAMBIOS.md").write_text("CHG-0001\nCHG-0003\n")
        if conflict_other:
            (self.root / "unrelated.txt").write_text("smoke version\n")
        else:
            (self.root / "smoke.md").write_text("inert\n")
        head = self.commit("PR branch")
        run(self.root, "checkout", "main")
        if conflict_cambios:
            (self.root / "standards/changes/CHG-0002.json").write_text('{"change_id":"CHG-0002"}')
        if conflict_cambios:
            (self.root / "standards/CAMBIOS.md").write_text("CHG-0001\nCHG-0002\n")
        if conflict_other:
            (self.root / "unrelated.txt").write_text("main version\n")
        else:
            (self.root / "README.md").write_text("main changed\n")
        main = self.commit("main advanced")
        run(self.root, "checkout", "smoke")
        return head, main

    def test_only_cambios_conflict_regenerated_and_checked(self):
        head, main = self.diverge(conflict_cambios=True)
        merged = merge.prepare_merge(self.root, main, head)
        self.assertEqual(merged, run(self.root, "rev-parse", "HEAD"))
        self.assertEqual((self.root / "standards/CAMBIOS.md").read_text(),
                         "CHG-0001\nCHG-0002\nCHG-0003\n")
        self.assertEqual(len(run(self.root, "rev-list", "--parents", "-n", "1", "HEAD").split()), 3)
        self.assertFalse(merge.check_conflicts(self.root))

    def test_merge_with_empty_home_and_no_system_git_identity(self):
        """Reproduce Actions runner with no global/system author or committer."""
        head, main = self.diverge(conflict_cambios=True)
        run(self.root, "config", "--local", "--unset", "user.name")
        run(self.root, "config", "--local", "--unset", "user.email")
        from unittest.mock import patch
        with patch.dict(os.environ, {
            "HOME": "", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }):
            for field in ("user.name", "user.email"):
                self.assertNotEqual(
                    merge.git(self.root, "config", "--get", field, check=False).returncode, 0
                )
            # Must run immediately after git init in update_branch_locally.
            merge.configure_bot_identity(self.root)
            self.assertEqual(
                merge.git(self.root, "config", "--local", "--get", "user.name").stdout.strip(),
                "sandbox-train[bot]",
            )
            self.assertEqual(
                merge.git(self.root, "config", "--local", "--get", "user.email").stdout.strip(),
                "41898282+github-actions[bot]@users.noreply.github.com",
            )
            merged = merge.prepare_merge(self.root, main, head)
            self.assertNotEqual(merged, head)
            self.assertEqual(
                (self.root / "standards/CAMBIOS.md").read_text().splitlines(),
                ["CHG-0001", "CHG-0002", "CHG-0003"],
            )
            self.assertEqual(
                len(run(self.root, "rev-list", "--parents", "-n", "1", "HEAD").split()), 3
            )

    def test_other_conflict_rejected_without_commit(self):
        head, main = self.diverge(conflict_cambios=True, conflict_other=True)
        with self.assertRaisesRegex(merge.BranchConflict, "BRANCH_CONFLICT"):
            merge.prepare_merge(self.root, main, head)
        self.assertEqual(run(self.root, "rev-parse", "HEAD"), head)

    def test_two_parallel_prs_have_disjoint_chg_files_and_train_renders(self):
        """Both PRs omit CAMBIOS; Train alone refreshes the derived view."""
        run(self.root, "checkout", "-b", "pr-a")
        (self.root / "standards/changes/CHG-0002.json").write_text(
            '{"change_id":"CHG-0002"}')
        a = self.commit("PR A CHG only")
        run(self.root, "checkout", "main")
        run(self.root, "checkout", "-b", "pr-b")
        (self.root / "standards/changes/CHG-0003.json").write_text(
            '{"change_id":"CHG-0003"}')
        b = self.commit("PR B CHG only")
        run(self.root, "checkout", "main")
        self.assertEqual(run(self.root, "diff", "--name-only", self.initial, a),
                         "standards/changes/CHG-0002.json")
        self.assertEqual(run(self.root, "diff", "--name-only", self.initial, b),
                         "standards/changes/CHG-0003.json")
        # PR A is merged to main without any PR-authored CAMBIOS change.
        run(self.root, "merge", "--no-ff", "-m", "Merge PR A", "pr-a")
        after_a = run(self.root, "rev-parse", "HEAD")
        run(self.root, "checkout", "pr-b")
        merged = merge.prepare_merge(self.root, after_a, b)
        self.assertEqual(merged, run(self.root, "rev-parse", "HEAD"))
        self.assertEqual((self.root / "standards/CAMBIOS.md").read_text(),
                         "CHG-0001\\nCHG-0002\\nCHG-0003\\n")
        self.assertFalse(merge.check_conflicts(self.root))

    def test_train_renders_when_main_already_ancestor(self):
        run(self.root, "checkout", "-b", "pr-a")
        (self.root / "standards/changes/CHG-0002.json").write_text(
            '{"change_id":"CHG-0002"}')
        head = self.commit("Add CHG without derived view")
        merged = merge.prepare_merge(self.root, self.initial, head)
        self.assertNotEqual(merged, head)
        self.assertEqual((self.root / "standards/CAMBIOS.md").read_text(),
                         "CHG-0001\\nCHG-0002\\n")
        self.assertEqual(len(run(self.root, "rev-list", "--parents",
                                 "-n", "1", "HEAD").split()), 2)
        self.assertEqual(merge.prepare_merge(self.root, self.initial, merged),
                         merged)

    def test_clean_merge_no_regeneration(self):
        head, main = self.diverge()
        merged = merge.prepare_merge(self.root, main, head)
        self.assertNotEqual(merged, head)
        self.assertEqual(len(run(self.root, "rev-list", "--parents", "-n", "1", "HEAD").split()), 3)
        self.assertEqual((self.root / "standards/CAMBIOS.md").read_text(), "CHG-0001\n")
        self.assertTrue((self.root / "smoke.md").exists())

    def test_pr_scripts_do_not_receive_write_token(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {"GH_TOKEN": "secret", "GITHUB_TOKEN": "secret2",
                                     "ACTIONS_RUNTIME_TOKEN": "secret3"}):
            child_env = merge.no_token_env()
            self.assertNotIn("GH_TOKEN", child_env)
            self.assertNotIn("GITHUB_TOKEN", child_env)
            self.assertNotIn("ACTIONS_RUNTIME_TOKEN", child_env)

    def test_changed_changes_py_blocks_before_any_merge(self):
        head, main = self.diverge(conflict_cambios=True)
        # This changes.py is now authored by the PR, not trusted main.
        run(self.root, "checkout", "smoke")
        tool = self.root / "standards/tools/changes.py"
        tool.write_text(tool.read_text() + "\\n# PR policy change\\n")
        head = self.commit("PR modifies changes.py")
        with self.assertRaisesRegex(
            merge.BranchConflict, "BRANCH_CONFLICT_TOOLING_CHANGED.*standards/tools/changes.py"
        ):
            merge.prepare_merge(self.root, main, head)
        self.assertEqual(run(self.root, "rev-parse", "HEAD"), head)
        self.assertFalse((self.root / ".git/MERGE_HEAD").exists())

    def test_changed_train_py_blocks_even_without_merge_conflict(self):
        head, main = self.diverge()
        train_file = self.root / "pilot/sandbox_train_guard.py"
        train_file.parent.mkdir(exist_ok=True)
        train_file.write_text("print('untrusted')\\n")
        head = self.commit("PR modifies Train policy")
        with self.assertRaisesRegex(
            merge.BranchConflict, "BRANCH_CONFLICT_TOOLING_CHANGED.*pilot/sandbox_train_guard.py"
        ):
            merge.prepare_merge(self.root, main, head)
        self.assertEqual(run(self.root, "rev-parse", "HEAD"), head)

    def test_adversarial_changes_script_never_sees_token(self):
        # Install a malicious-looking sentinel in the SHARED base, so the PR
        # itself does not modify tooling. It raises on any inherited token.
        script = self.root / "standards/tools/changes.py"
        original = script.read_text()
        sentinel = (
            "import os\n"
            "if any(os.getenv(k) for k in "
            "('GH_TOKEN','GITHUB_TOKEN','ACTIONS_RUNTIME_TOKEN')):\n"
            "    raise RuntimeError('TOKEN_EXPOSED')\n"
        )
        script.write_text(sentinel + original)
        self.commit("shared token sentinel")
        head, main = self.diverge(conflict_cambios=True)
        from unittest.mock import patch
        real_run = subprocess.run
        observed = []
        def scrubbed_run(*args, **kwargs):
            child_env = kwargs.get("env")
            self.assertIsNotNone(child_env, "All subprocesses must set explicit env")
            for name in ("GH_TOKEN", "GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN"):
                self.assertNotIn(name, child_env)
            observed.append(args[0])
            return real_run(*args, **kwargs)
        with patch.dict(os.environ, {"GH_TOKEN": "secret",
                                      "GITHUB_TOKEN": "other",
                                      "ACTIONS_RUNTIME_TOKEN": "third"}), \
             patch.object(merge.subprocess, "run", side_effect=scrubbed_run):
            merged = merge.prepare_merge(self.root, main, head)
        self.assertGreaterEqual(len(observed), 10)
        self.assertNotEqual(merged, head)
        self.assertEqual((self.root / "standards/CAMBIOS.md").read_text(),
                         "CHG-0001\nCHG-0002\nCHG-0003\n")

    def test_conflict_classifier_rejects_other_path(self):
        head, main = self.diverge(conflict_other=True)
        with self.assertRaisesRegex(merge.BranchConflict, "BRANCH_CONFLICT unrelated.txt"):
            merge.prepare_merge(self.root, main, head)
        self.assertEqual(run(self.root, "rev-parse", "HEAD"), head)


if __name__ == "__main__":
    unittest.main()
