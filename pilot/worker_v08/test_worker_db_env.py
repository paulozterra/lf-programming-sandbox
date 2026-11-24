"""Bridge regression: real isolated Worker commands, with disposable DB in CI."""
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vendor/programming-agent/src"))
from programming_agent_runner import worker_commands
from programming_agent_runner.worker_spec import AcceptanceCommand
from pilot.worker_v08.worker_db_env import worker_database_environment


def test_only_approved_database_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_URL", "jdbc:postgresql://127.0.0.1:5432/synthetic_db")
    monkeypatch.setenv("DB_USERNAME", "synthetic_user")
    monkeypatch.setenv("DB_PASSWORD", "synthetic_password")
    for name in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD",
                 "PGSERVICE", "GITHUB_TOKEN", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(name, "ambient-do-not-pass")
    with worker_database_environment():
        env = worker_commands._command_environment(tmp_path)
        assert {k: v for k, v in env.items() if k.startswith("PG")} == {
            "PGHOST": "127.0.0.1", "PGPORT": "5432", "PGDATABASE": "synthetic_db",
            "PGUSER": "synthetic_user", "PGPASSWORD": "synthetic_password"}
        assert env["DB_PASSWORD"] == "synthetic_password"
        assert "GITHUB_TOKEN" not in env and "ANTHROPIC_API_KEY" not in env
        assert env["HOME"] == str(tmp_path / "home")
    assert "PGPASSWORD" not in worker_commands._command_environment(tmp_path)


@pytest.mark.parametrize("url", [
    "jdbc:postgresql://remote:5432/pilot",
    "jdbc:postgresql://127.0.0.1:5432/",
    "jdbc:postgresql://127.0.0.1:5432/db?sslmode=disable",
    "jdbc:postgresql://127.0.0.1:5432/db/extra",
])
def test_untrusted_url_blocks(url, monkeypatch):
    monkeypatch.setenv("DB_URL", url)
    monkeypatch.setenv("DB_USERNAME", "user")
    monkeypatch.setenv("DB_PASSWORD", "password")
    with pytest.raises(ValueError, match="WORKER_DB_URL_UNTRUSTED"):
        with worker_database_environment():
            pytest.fail("untrusted DB reached Worker")


def test_absent_or_partial_db_environment(tmp_path, monkeypatch):
    for key in ("DB_URL", "DB_USERNAME", "DB_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    with worker_database_environment():
        assert "PGHOST" not in worker_commands._command_environment(tmp_path)
    monkeypatch.setenv("DB_USERNAME", "user")
    with pytest.raises(ValueError, match="WORKER_DB_ENV_INCOMPLETE"):
        with worker_database_environment():
            pytest.fail("partial DB reached Worker")


@pytest.mark.skipif(os.getenv("LF_TEST_REAL_WORKER_DB") != "YES",
                    reason="Requires dedicated disposable PostgreSQL service")
def test_generated_data_command_applies_in_isolated_worker(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "pilot/orchestrator"))
    from pilot.orchestrator.generate_chain import acceptance
    from uuid import uuid4

    path = "apps/time-service/src/main/resources/db/migration/V1__synthetic.sql"
    migration = tmp_path / path
    migration.parent.mkdir(parents=True)
    table = "worker_db_" + uuid4().hex
    migration.write_text(f"CREATE TABLE {table} (id integer PRIMARY KEY);\n"
                         f"INSERT INTO {table} VALUES (1);\n", encoding="utf-8")
    spec = next(c for c in acceptance("DATA", [path])
                if c["name"] == "data-migration-visible")
    command = AcceptanceCommand(spec["name"], tuple(spec["argv"]),
                                spec["timeout_seconds"], spec["max_output_bytes"])
    monkeypatch.setenv("PGHOST", "invalid-ambient-host")
    monkeypatch.setenv("PGPASSWORD", "invalid-ambient-password")
    with worker_database_environment():
        result = worker_commands.run_acceptance_command(tmp_path, command)
        assert result.status == "PASS", result.stderr
        check = AcceptanceCommand("check", ("psql", "-X", "-At", "-v",
            "ON_ERROR_STOP=1", "-c", f"SELECT count(*) FROM {table}"), 15, 1024)
        observed = worker_commands.run_acceptance_command(tmp_path, check)
        assert observed.status == "PASS" and observed.stdout.strip() == "1"
        cleanup = AcceptanceCommand("cleanup", ("psql", "-X", "-v",
            "ON_ERROR_STOP=1", "-c", f"DROP TABLE {table}"), 15, 1024)
        assert worker_commands.run_acceptance_command(tmp_path, cleanup).status == "PASS"


def test_reset_only_approved_database_and_no_ambient_secrets(monkeypatch):
    from pilot.worker_v08 import worker_db_env as bridge
    from unittest.mock import Mock
    monkeypatch.setenv("DB_URL", "jdbc:postgresql://127.0.0.1:5432/pilot")
    monkeypatch.setenv("DB_USERNAME", "pilot")
    monkeypatch.setenv("DB_PASSWORD", "job-only")
    monkeypatch.setenv("PGPASSWORD", "ambient")
    monkeypatch.setenv("GITHUB_TOKEN", "ambient")
    run = Mock()
    monkeypatch.setattr(bridge.subprocess, "run", run)
    bridge.reset_disposable_database()
    assert run.call_count == 2
    for call in run.call_args_list:
        assert call.kwargs["env"]["PGPASSWORD"] == "job-only"
        assert call.kwargs["env"]["PGDATABASE"] == "postgres"
        assert "GITHUB_TOKEN" not in call.kwargs["env"]
        assert "job-only" not in str(call.args)
    assert run.call_args_list[0].args[0][-1] == 'DROP DATABASE "pilot" WITH (FORCE)'
    assert run.call_args_list[1].args[0][-1] == 'CREATE DATABASE "pilot" TEMPLATE template0'
    monkeypatch.setenv("DB_URL", "jdbc:postgresql://127.0.0.1:5432/postgres")
    with pytest.raises(ValueError, match="WORKER_DB_RESET_TARGET_UNTRUSTED"):
        bridge.reset_disposable_database()
    assert run.call_count == 2


@pytest.mark.skipif(os.getenv("LF_TEST_REAL_WORKER_DB") != "YES",
                    reason="Requires dedicated disposable PostgreSQL service")
def test_reference_runs_on_clean_database_and_preserves_attempt(tmp_path, monkeypatch):
    # Use a separate disposable database from CI's Maven service database.
    import subprocess
    from types import SimpleNamespace
    from pilot.worker_v08.worker_db_env import reset_disposable_database
    from pilot.worker_v08 import worker_db_env
    monkeypatch.syspath_prepend(str(ROOT / "pilot/worker_v08"))
    monkeypatch.syspath_prepend(str(ROOT / "pilot/orchestrator"))
    import native_run
    import native_exam_control as control
    import programming_agent_runner.verified_worker as verified
    import json

    # The CI service is lf_ci; use a distinct pilot database for this test.
    original = os.environ["DB_URL"]
    assert original == "jdbc:postgresql://127.0.0.1:5432/lf_ci"
    env = {"PATH": "/usr/bin:/bin", "PGHOST": "127.0.0.1", "PGPORT": "5432",
           "PGDATABASE": "postgres", "PGUSER": os.environ["DB_USERNAME"],
           "PGPASSWORD": os.environ["DB_PASSWORD"]}
    subprocess.run(["psql", "-X", "-w", "-v", "ON_ERROR_STOP=1", "-c",
                    "CREATE DATABASE pilot TEMPLATE template0"], env=env, check=True,
                   capture_output=True)
    monkeypatch.setenv("DB_URL", "jdbc:postgresql://127.0.0.1:5432/pilot")
    command = AcceptanceCommand("migration", ("psql", "-X", "-v", "ON_ERROR_STOP=1",
        "-c", "CREATE TABLE synthetic_attempt (id integer)"), 15, 1024)
    try:
        reset_disposable_database()
        with worker_database_environment():
            assert worker_commands.run_acceptance_command(tmp_path, command).status == "PASS"
        # A second CREATE would fail without the reference reset.
        def reference(source, spec, client, oracle, *, work_parent):
            result = worker_commands.run_acceptance_command(work_parent, command)
            return SimpleNamespace(receipt={"status": result.status, "reason": result.reason})
        monkeypatch.setattr(verified, "run_verified_worker", reference)
        monkeypatch.setattr(control, "load_reference", lambda *args: "synthetic")
        public = tmp_path / "public"
        public.mkdir()
        proof = public / "attempt-proof.json"
        proof.write_text("{}")
        feedback = public / "feedback.json"
        feedback.write_text(json.dumps(native_run._visible_feedback(None, 1)))
        before = feedback.read_bytes()
        assert not native_run._examiner_control(tmp_path, None, None, tmp_path,
            public, "synthetic", 123, "a" * 64, 1, None,
            {"proposal_sha256": "b" * 64, "task_pack_sha256": "c" * 64})
        assert proof.exists()
        assert feedback.read_bytes() == before
        assert not (public / "no-attempt.json").exists()
    finally:
        subprocess.run(["psql", "-X", "-w", "-v", "ON_ERROR_STOP=1", "-c",
                        "DROP DATABASE pilot WITH (FORCE)"], env=env, check=True,
                       capture_output=True)
