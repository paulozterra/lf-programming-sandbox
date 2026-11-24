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
