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
    from programming_agent_runner import worker_commands
    from programming_agent_runner.worker_spec import AcceptanceCommand

    approved = {
        "DB_URL": "jdbc:postgresql://127.0.0.1:5432/pilot",
        "DB_USERNAME": "pilot", "DB_PASSWORD": "job-only",
    }
    derived = {
        "PGHOST": "127.0.0.1", "PGPORT": "5432", "PGDATABASE": "pilot",
        "PGUSER": approved["DB_USERNAME"], "PGPASSWORD": approved["DB_PASSWORD"],
    }
    forbidden = ("GITHUB_TOKEN", "GH_TOKEN", "ANTHROPIC_API_KEY",
                 "OPENAI_API_KEY", "PGSERVICE", "PGPASSFILE")
    for key, value in approved.items():
        monkeypatch.setenv(key, value)
    for key in (*derived, *forbidden):
        monkeypatch.setenv(key, "not-exported")
    with worker_database_environment():
        env = worker_commands._command_environment(tmp_path / "runtime")
        assert {k: v for k, v in env.items() if k.startswith("DB_")} == approved
        assert {k: v for k, v in env.items() if k.startswith("PG")} == derived
        assert all(k not in env for k in forbidden)
        # Check the actual subprocess, not just the environment factory.
        script = (
            "import os,sys;"
            f"expected={dict(approved, **derived)!r};"
            f"forbidden={forbidden!r};"
            "sys.exit(0 if all(os.environ.get(k)==v for k,v in expected.items()) "
            "and all(k not in os.environ for k in forbidden) "
            "and not any(k.startswith(('DB_','PG')) and k not in expected "
            "for k in os.environ) else 1)"
        )
        cmd = AcceptanceCommand("db-env", (sys.executable, "-c", script), 10, 1024)
        result = worker_commands.run_acceptance_command(tmp_path, cmd)
        assert result.status == "PASS", result.reason
    env = worker_commands._command_environment(tmp_path / "after")
    assert not any(k.startswith(("DB_", "PG")) for k in env)
    assert all(k not in env for k in forbidden)


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
