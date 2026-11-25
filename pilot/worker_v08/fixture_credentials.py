"""Fictitious sandbox credentials for Worker and exam commands.

An exam that must sign in as the sandbox demo user cannot carry the password in
its argv (the Worker rejects probable secrets there). The trusted bridge exposes
the fictitious values as SBX_FIXTURE_* environment variables instead. Each value
must already be published verbatim in its declared source document, so this
channel can never carry a real secret. Read from the trusted checkout, never
from the Worker workspace.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path("pilot/config/fixture_credentials.json")
ENV_NAME = re.compile(r"SBX_FIXTURE_[A-Z0-9_]{1,48}")


def fixture_environment(root: Path = ROOT) -> dict[str, str]:
    path = root / CONFIG
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("credentials"), list):
        raise ValueError("FIXTURE_CREDENTIALS_INVALID")
    env: dict[str, str] = {}
    for item in data["credentials"]:
        name, value, source = item.get("env"), item.get("value"), item.get("source")
        if not (isinstance(name, str) and ENV_NAME.fullmatch(name) and name not in env):
            raise ValueError("FIXTURE_CREDENTIALS_INVALID:env")
        if not (isinstance(value, str) and value and isinstance(source, str)):
            raise ValueError(f"FIXTURE_CREDENTIALS_INVALID:{name}")
        doc = root / source
        if ".." in Path(source).parts or not doc.is_file() or value not in doc.read_text(encoding="utf-8"):
            raise ValueError(f"FIXTURE_CREDENTIALS_UNPUBLISHED:{name}")
        env[name] = value
    return env
