"""T16 security regression: rule examples cannot bypass vendored secret checks."""
from __future__ import annotations

import pytest

from pilot.worker_v08.worker_context_safety import (
    safe_rule_context, WorkerContextUnsafe,
)
from pilot.worker_v08.lf_rule_context import material
from programming_agent_runner.worker_secrets import secret_text_reason


def test_assignment_examples_are_safely_redacted_without_dropping_rule_text():
    source = (
        '# STD-GEN-03\n'
        'Nunca usar valores reales en ejemplos:\n'
        'password = "0123456789abcdef012345"\n'
        'api_key: "0123456789abcdef012345"\n'
    ).encode()
    assert secret_text_reason(source.decode()) == "ASSIGNMENT_SECRET"
    output, count = safe_rule_context(source)
    assert count == 2
    assert b"STD-GEN-03" in output
    assert b"Nunca usar" in output
    assert b"0123456789abcdef" not in output
    assert b'password = "REDACTED"' in output
    assert secret_text_reason(output.decode()) is None


def test_non_assignment_secrets_never_get_silently_redacted():
    source = b"Conectar con valor sk-proj-" + b"A" * 30
    assert secret_text_reason(source.decode()) == "OPENAI_API_KEY"
    with pytest.raises(WorkerContextUnsafe, match="LF_RULE_CONTEXT_SECRET"):
        safe_rule_context(source)


@pytest.mark.parametrize("area", ["CONTRATO", "INFRA", "DATA", "BACKEND", "FRONTEND"])
def test_real_assigned_lf_rules_are_safe_for_unmodified_vendor_worker(area):
    raw, receipt = material(area)
    safe, count = safe_rule_context(raw)
    assert receipt["rule_ids"]
    assert count >= 0
    assert secret_text_reason(safe.decode()) is None
    assert safe


def test_worker_commands_receive_disposable_db_env_only_inside_trusted_bridge(
        tmp_path, monkeypatch):
    import sys
    from pilot.worker_v08.worker_db_env import worker_database_environment
    from programming_agent_runner.worker_commands import (
        _command_environment, run_acceptance_command,
    )
    from programming_agent_runner.worker_spec import AcceptanceCommand

    monkeypatch.setenv("DB_URL", "jdbc:postgresql://127.0.0.1:5432/pilot")
    monkeypatch.setenv("DB_USERNAME", "pilot")
    monkeypatch.setenv("DB_PASSWORD", "pilot")
    monkeypatch.setenv("GITHUB_TOKEN", "not-exported")
    monkeypatch.setenv("PGPASSWORD", "not-exported")
    with worker_database_environment():
        env = _command_environment(tmp_path / "runtime")
        # Imported reference before monkeypatch remains the strict vendor
        # function; read the module attribute that subprocesses actually call.
        from programming_agent_runner import worker_commands
        env = worker_commands._command_environment(tmp_path / "runtime2")
        assert {k: env[k] for k in ("DB_URL", "DB_USERNAME", "DB_PASSWORD")} == {
            "DB_URL": "jdbc:postgresql://127.0.0.1:5432/pilot",
            "DB_USERNAME": "pilot", "DB_PASSWORD": "pilot",
        }
        assert "GITHUB_TOKEN" not in env and "PGPASSWORD" not in env
        cmd = AcceptanceCommand(
            "db-env", (sys.executable, "-c",
                       "import os,sys;sys.exit(0 if all(os.environ.get(k) "
                       "for k in ('DB_URL','DB_USERNAME','DB_PASSWORD')) "
                       "and 'GITHUB_TOKEN' not in os.environ "
                       "and 'PGPASSWORD' not in os.environ else 1)"),
            10, 1024,
        )
        result = run_acceptance_command(tmp_path, cmd)
        assert result.status == "PASS", result.reason
    from programming_agent_runner import worker_commands
    assert "DB_PASSWORD" not in worker_commands._command_environment(
        tmp_path / "after")


def test_worker_db_bridge_refuses_partial_or_remote_env(tmp_path, monkeypatch):
    from pilot.worker_v08.worker_db_env import worker_database_environment
    monkeypatch.setenv("DB_URL", "jdbc:postgresql://127.0.0.1:5432/pilot")
    monkeypatch.setenv("DB_USERNAME", "pilot")
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="WORKER_DB_ENV_INCOMPLETE"):
        with worker_database_environment():
            pass
    monkeypatch.setenv("DB_PASSWORD", "job-only")
    monkeypatch.setenv("DB_URL", "jdbc:postgresql://remote.example:5432/pilot")
    with pytest.raises(ValueError, match="WORKER_DB_URL_UNTRUSTED"):
        with worker_database_environment():
            pass
