"""T52: main CI after a Train merge reuses the exact-SHA push run.

Dispatch is only a bounded fallback (no push run, e.g. a GITHUB_TOKEN merge,
CHG-0113). A failed push CI blocks and is never replaced by a new dispatch.
Every required job must have run and succeeded; skipped never counts.
"""
import importlib.util
from pathlib import Path
import unittest

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SHA = "a" * 40
OTHER = "b" * 40
REPO = "paulozterra/lf-programming-sandbox"


def module(name):
    spec = importlib.util.spec_from_file_location(name + "_t52", HERE / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


handoff = module("train_handoff")
GATE = handoff.main_ci_gate_config()
CFG = {**GATE, "push_wait_seconds": 60, "poll_seconds": 15, "wait_seconds": 60}


def run(event="push", conclusion="success", status="completed", sha=SHA,
        run_id=500, attempt=1):
    return {"id": run_id, "head_sha": sha, "head_branch": "main", "event": event,
            "run_attempt": attempt, "path": ".github/workflows/ci.yml",
            "repository": {"full_name": REPO}, "status": status,
            "conclusion": conclusion, "created_at": f"2026-11-19T10:00:{run_id % 60:02d}Z",
            "html_url": f"https://github.com/{REPO}/actions/runs/{run_id}"}


def jobs(overrides=None, drop=(), extra=()):
    rows = []
    for name in GATE["required_jobs"]:
        if name in drop:
            continue
        row = {"name": name, "status": "completed", "conclusion": "success"}
        row.update((overrides or {}).get(name, {}))
        rows.append(row)
    rows.extend(extra)
    return {"total_count": len(rows), "jobs": rows}


class API:
    """Scripted GitHub: each ci.yml runs listing returns the next snapshot."""

    def __init__(self, snapshots, job_rows=None):
        self.snapshots = list(snapshots)
        self.job_rows = job_rows or jobs()
        self.calls = []

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "GET" and path == "/git/ref/heads/main":
            return {"object": {"sha": SHA}}
        if method == "GET" and path.startswith("/actions/workflows/ci.yml/runs?"):
            assert f"head_sha={SHA}" in path
            rows = self.snapshots.pop(0) if len(self.snapshots) > 1 else self.snapshots[0]
            return {"workflow_runs": list(rows), "total_count": len(rows)}
        if method == "GET" and "/jobs?filter=latest" in path:
            return self.job_rows
        if method == "POST":
            return {}
        raise AssertionError((method, path, body))

    def posts(self):
        return [p for m, p, _ in self.calls if m == "POST"]


def ensure(api, cfg=CFG, required=True):
    return handoff.ensure_main_ci(api, SHA, required=required, config=cfg,
                                  sleep=lambda _: None)


class Tests(unittest.TestCase):
    def test_green_push_ci_is_reused_without_dispatch(self):
        api = API([[run()]])
        result = ensure(api)
        self.assertEqual(result["status"], "MAIN_CI_GREEN")
        self.assertEqual(result["event"], "push")
        self.assertEqual(api.posts(), [])

    def test_push_ci_appearing_later_is_awaited_not_replaced(self):
        api = API([[], [run(status="in_progress", conclusion=None)], [run()]])
        self.assertEqual(ensure(api)["run_id"], 500)
        self.assertEqual(api.posts(), [])

    def test_no_push_ci_dispatches_once_and_requires_new_dispatch_run(self):
        # 4 push probes (60s / 15s) see nothing; previous lookup; then dispatch run.
        api = API([[], [], [], [], [], [run("workflow_dispatch", run_id=601)]])
        result = ensure(api)
        self.assertEqual(result["event"], "workflow_dispatch")
        self.assertEqual(result["run_id"], 601)
        self.assertEqual(api.posts(), ["/actions/workflows/ci.yml/dispatches"])

    def test_failed_push_ci_blocks_after_one_rerun_and_never_dispatches(self):
        failed = run(conclusion="failure")
        failed_again = run(conclusion="failure", attempt=2)
        api = API([[failed], [failed], [failed_again]])
        with self.assertRaisesRegex(handoff.HandoffBlocked, "BASE_NO_VERDE:.*runs/500"):
            ensure(api)
        self.assertEqual(api.posts(), ["/actions/runs/500/rerun-failed-jobs"])

    def test_transient_push_failure_rerun_green_is_accepted(self):
        api = API([[run(conclusion="failure")], [run(conclusion="failure")],
                   [run(attempt=2)]])
        self.assertEqual(ensure(api)["status"], "MAIN_CI_GREEN")
        self.assertNotIn("/actions/workflows/ci.yml/dispatches", api.posts())

    def test_skipped_required_job_never_approves(self):
        name = GATE["required_jobs"][0]
        api = API([[run()]], jobs({name: {"conclusion": "skipped"}}))
        with self.assertRaisesRegex(handoff.HandoffBlocked, "REQUIRED_JOBS"):
            ensure(api)
        self.assertEqual(api.posts(), [])

    def test_missing_or_duplicated_required_job_never_approves(self):
        name = GATE["required_jobs"][1]
        for rows in (jobs(drop=(name,)),
                     jobs(extra=({"name": name, "status": "completed",
                                  "conclusion": "success"},))):
            api = API([[run()]], rows)
            with self.assertRaisesRegex(handoff.HandoffBlocked, "REQUIRED_JOBS"):
                ensure(api)

    def test_inconsistent_job_listing_never_approves(self):
        rows = jobs()
        rows["total_count"] += 1
        api = API([[run()]], rows)
        with self.assertRaisesRegex(handoff.HandoffBlocked, "REQUIRED_JOBS"):
            ensure(api)

    def test_dispatch_run_also_needs_required_jobs(self):
        name = GATE["required_jobs"][2]
        api = API([[], [], [], [], [], [run("workflow_dispatch", run_id=601)]],
                  jobs({name: {"conclusion": "skipped"}}))
        with self.assertRaisesRegex(handoff.HandoffBlocked, "REQUIRED_JOBS"):
            ensure(api)

    def test_push_ci_of_another_sha_is_ignored(self):
        foreign = run(sha=OTHER, run_id=400)
        api = API([[foreign]] * 5 + [[foreign, run("workflow_dispatch", run_id=601)]])
        self.assertEqual(ensure(api)["run_id"], 601)
        self.assertEqual(api.posts(), ["/actions/workflows/ci.yml/dispatches"])

    def test_old_dispatch_run_cannot_stand_in_for_new_one(self):
        old = run("workflow_dispatch", run_id=300)
        api = API([[old], [old], [old], [old], [old], [old], [old], [old], [old]])
        with self.assertRaisesRegex(handoff.HandoffBlocked, "BASE_NO_VERDE"):
            ensure(api)
        self.assertEqual(api.posts(), ["/actions/workflows/ci.yml/dispatches"])

    def test_non_required_mode_observes_push_or_dispatches(self):
        api = API([[run()]])
        self.assertEqual(ensure(api, required=False)["status"], "MAIN_CI_PUSH_OBSERVED")
        self.assertEqual(api.posts(), [])
        api = API([[]])
        self.assertEqual(ensure(api, required=False)["status"], "MAIN_CI_DISPATCHED")
        self.assertEqual(api.posts(), ["/actions/workflows/ci.yml/dispatches"])

    def test_gate_config_rejects_legacy_or_unsafe_values(self):
        import json
        import tempfile
        base = json.loads((HERE / "train_main_ci_gate_v1.json").read_text(encoding="utf-8"))
        bad = [{**base, "required_event": "workflow_dispatch"},
               {**base, "accepted_events": ["push"]},
               {**base, "push_wait_seconds": 901},
               {**base, "required_jobs": []},
               {**base, "required_jobs": ["x", "x"]}]
        for config in bad:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "gate.json"
                path.write_text(json.dumps(config), encoding="utf-8")
                with self.assertRaises(handoff.HandoffBlocked):
                    handoff.main_ci_gate_config(path)

    def test_required_jobs_are_unconditional_ci_jobs(self):
        """A required job that ci.yml may skip by event/branch would block or lie."""
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
        unconditional = {job.get("name", key) for key, job in workflow["jobs"].items()
                         if "if" not in job and "strategy" not in job}
        self.assertTrue(set(GATE["required_jobs"]) <= unconditional,
                        set(GATE["required_jobs"]) - unconditional)
        by_name = {job.get("name", key): job for key, job in workflow["jobs"].items()}
        for name in GATE["required_jobs"]:
            self.assertNotIn("needs", by_name[name], name)  # no skip cascade
        push = workflow[True]["push"]  # PyYAML parses `on:` as True
        self.assertEqual(push, {"branches": ["main"]})  # no paths filter on main


if __name__ == "__main__":
    unittest.main()
