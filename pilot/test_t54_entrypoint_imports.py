"""T54: all migrated direct-script imports must work without cwd PYTHONPATH."""
import ast
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MIGRATED = (
    "pilot/auto_integrate.py",
    "pilot/audit/auditor_job.py",
    "pilot/audit/build_input.py",
    "pilot/exam_issue_lifecycle.py",
    "pilot/orchestrator/affected_tests.py",
    "pilot/orchestrator/analysis_report.py",
    "pilot/orchestrator/chain_lots.py",
    "pilot/orchestrator/generate_chain.py",
    "pilot/orchestrator/implemented_registry.py",
    "pilot/orchestrator/intake.py",
    "pilot/orchestrator/native_integration_replay.py",
    "pilot/orchestrator/native_lot_registration.py",
    "pilot/orchestrator/native_route_recovery.py",
    "pilot/orchestrator/package_to_lots.py",
    "pilot/orchestrator/pending_plan_refresh.py",
    "pilot/orchestrator/publish_exam.py",
    "pilot/orchestrator/request_finalize.py",
    "pilot/orchestrator/request_lifecycle.py",
    "pilot/orchestrator/reuse_assessment.py",
    "pilot/orchestrator/route_tool_defect.py",
    "pilot/orchestrator/t4_admission.py",
    "pilot/orchestrator/t7_entry.py",
    "pilot/request_failure_notify.py",
    "pilot/request_stage_watchdog.py",
    "pilot/train_handoff.py",
    "pilot/worker_v08/api_lot.py",
    "pilot/worker_v08/business_context.py",
    "pilot/worker_v08/exam_rehearsal.py",
    "pilot/worker_v08/native_feedback_delivery.py",
    "pilot/worker_v08/native_push_failure_notify.py",
    "pilot/worker_v08/native_run.py",
    "pilot/worker_v08/native_run_history.py",
    "pilot/worker_v08/register_task_context.py",
)


class MigratedEntrypointTest(unittest.TestCase):
    def test_bootstrap_precedes_package_import_in_every_migrated_script(self):
        for rel in MIGRATED:
            with self.subTest(script=rel):
                source = (ROOT / rel).read_text("utf-8")
                tree = ast.parse(source, filename=rel)
                first_pilot = min(
                    (n.lineno for n in ast.walk(tree)
                     if isinstance(n, ast.ImportFrom)
                     and n.module and n.module.startswith("pilot.")),
                    default=10**9)
                marker = "_project_sys.path.insert(0, str(_project_Path(__file__)"
                index = source.find(marker)
                self.assertGreaterEqual(index, 0, rel)
                self.assertLess(source[:index].count("\n") + 1, first_pilot, rel)
                self.assertIn(".parents[" + str(len(Path(rel).parts) - 1) + "]",
                              source[index:index + 140], rel)
                self.assertNotIn("import conftest", source)
                self.assertNotIn("from pilot.conftest", source)

    def test_isolated_entrypoint_imports(self):
        # python -I disables cwd and PYTHONPATH injection; only the script's
        # own directory is on sys.path, matching python3 pilot/<script>.py.
        for rel in ("pilot/auto_integrate.py",
                    "pilot/orchestrator/chain_lots.py",
                    "pilot/worker_v08/native_run.py",
                    "pilot/audit/build_input.py"):
            with self.subTest(script=rel):
                script = ROOT / rel
                code = ("import runpy,sys;"
                        "sys.path.insert(0," + repr(str(script.parent)) + ");"
                        "runpy.run_path(" + repr(str(script)) +
                        ",run_name='t54_import_probe')")
                proc = subprocess.run([sys.executable, "-I", "-c", code],
                                      cwd=ROOT, text=True, capture_output=True,
                                      timeout=25)
                self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
