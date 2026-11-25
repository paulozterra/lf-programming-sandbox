import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/programming-agent/src"))
from programming_agent_runner import worker_commands
from programming_agent_runner.worker_secrets import secret_text_reason
from pilot.worker_v08.fixture_credentials import fixture_environment
from pilot.worker_v08.worker_db_env import worker_database_environment


def _write(root, credentials, doc="Credenciales ficticias: `demo` / `Sandbox-Demo-2026`.\n"):
    (root / "pilot/config").mkdir(parents=True, exist_ok=True)
    (root / "spec.md").write_text(doc, encoding="utf-8")
    (root / "pilot/config/fixture_credentials.json").write_text(
        json.dumps({"schema_version": 1, "credentials": credentials}), encoding="utf-8")


def test_repo_fixtures_are_published_and_safe_names():
    env = fixture_environment()
    assert set(env) == {"SBX_FIXTURE_DEMO_USERNAME", "SBX_FIXTURE_DEMO_PASSWORD"}
    # An argv that reads the variable is not a probable secret; a literal would be.
    assert secret_text_reason('import os; p=os.environ["SBX_FIXTURE_DEMO_PASSWORD"]') is None


def test_value_must_be_published_in_its_source(tmp_path):
    _write(tmp_path, [{"env": "SBX_FIXTURE_X", "value": "not-in-the-doc", "source": "spec.md"}])
    with pytest.raises(ValueError, match="FIXTURE_CREDENTIALS_UNPUBLISHED"):
        fixture_environment(tmp_path)


@pytest.mark.parametrize("name", ["GITHUB_TOKEN", "DB_PASSWORD", "sbx_fixture_x", "SBX_FIXTURE_"])
def test_only_sbx_fixture_names(tmp_path, name):
    _write(tmp_path, [{"env": name, "value": "demo", "source": "spec.md"}])
    with pytest.raises(ValueError, match="FIXTURE_CREDENTIALS_INVALID"):
        fixture_environment(tmp_path)


def test_source_cannot_escape_root(tmp_path):
    _write(tmp_path, [{"env": "SBX_FIXTURE_X", "value": "demo", "source": "../spec.md"}])
    with pytest.raises(ValueError, match="FIXTURE_CREDENTIALS_UNPUBLISHED"):
        fixture_environment(tmp_path)


def test_worker_commands_receive_fixtures_without_db(tmp_path, monkeypatch):
    for key in ("DB_URL", "DB_USERNAME", "DB_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "ambient-do-not-pass")
    with worker_database_environment():
        env = worker_commands._command_environment(tmp_path)
        assert env["SBX_FIXTURE_DEMO_USERNAME"] == "demo"
        assert "SBX_FIXTURE_DEMO_PASSWORD" in env
        assert "GITHUB_TOKEN" not in env and "PGHOST" not in env
    assert "SBX_FIXTURE_DEMO_PASSWORD" not in worker_commands._command_environment(tmp_path)
