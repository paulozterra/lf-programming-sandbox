"""T46: per-project configuration of the route's audit stage.

The audit stage is generic: nothing project-specific lives in code. Each
project declares, in pilot/audit/projects/<project>.json, which audit skill it
uses (repository, pinned commit, path and a per-file SHA-256 manifest), where
its error-knowledge base (EKB) is read from, and how the stage runs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECTS = ROOT / "pilot/audit/projects"
PROJECT = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
REPO = re.compile(r"[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}\Z")
REL = re.compile(r"[A-Za-z0-9._/-]{1,300}\Z")
IDENT = re.compile(r"[a-z_][a-z0-9_]{0,62}(?:\.[a-z_][a-z0-9_]{0,62})?\Z")
SECRET = re.compile(r"[A-Z][A-Z0-9_]{0,99}\Z")
MODES = {"SHADOW", "GATE"}
TRIGGERS = {"REQUEST_CLOSED"}
AUDITORS = {"CLAUDE_ROUTINE"}
EKB_SOURCES = {"NONE", "POSTGRES_READONLY"}


class AuditConfigError(ValueError):
    pass


def _rel(value: object, code: str) -> str:
    if not isinstance(value, str) or not REL.fullmatch(value) or ".." in value.split("/") \
            or value.startswith("/"):
        raise AuditConfigError(code)
    return value


def load(project: str, root: Path = ROOT) -> dict:
    if not isinstance(project, str) or not PROJECT.fullmatch(project):
        raise AuditConfigError("AUDIT_PROJECT_INVALID")
    file = root / "pilot/audit/projects" / (project + ".json")
    if file.is_symlink() or not file.is_file():
        raise AuditConfigError("AUDIT_CONFIG_MISSING")
    try:
        data = json.loads(file.read_text("utf-8"))
    except (OSError, ValueError):
        raise AuditConfigError("AUDIT_CONFIG_UNREADABLE") from None
    if not isinstance(data, dict) or data.get("schema_version") != "LF_ROUTE_AUDIT_CONFIG_V1" \
            or data.get("project") != project or not isinstance(data.get("audit"), dict):
        raise AuditConfigError("AUDIT_CONFIG_INVALID")
    audit = data["audit"]
    skill, ekb = audit.get("skill"), audit.get("ekb")
    if (audit.get("enabled") not in (True, False) or audit.get("mode") not in MODES
            or audit.get("trigger") not in TRIGGERS or audit.get("auditor") not in AUDITORS
            or not isinstance(skill, dict) or not isinstance(ekb, dict)
            or type(audit.get("sample_n")) is not int or not 1 <= audit["sample_n"] <= 100):
        raise AuditConfigError("AUDIT_CONFIG_INVALID")
    since = audit.get("since_commit")
    if since is not None and (not isinstance(since, str) or not SHA40.fullmatch(since)):
        raise AuditConfigError("AUDIT_CONFIG_INVALID")
    if (not isinstance(skill.get("repository"), str) or not REPO.fullmatch(skill["repository"])
            or not isinstance(skill.get("commit"), str) or not SHA40.fullmatch(skill["commit"])):
        raise AuditConfigError("AUDIT_SKILL_CONFIG_INVALID")
    _rel(skill.get("path"), "AUDIT_SKILL_CONFIG_INVALID")
    _rel(skill.get("manifest"), "AUDIT_SKILL_CONFIG_INVALID")
    if ekb.get("source") not in EKB_SOURCES or ekb.get("store_content") is not False:
        raise AuditConfigError("AUDIT_EKB_CONFIG_INVALID")
    if ekb["source"] == "POSTGRES_READONLY" and not (
            isinstance(ekb.get("secret"), str) and SECRET.fullmatch(ekb["secret"])
            and isinstance(ekb.get("table"), str) and IDENT.fullmatch(ekb["table"])
            and isinstance(ekb.get("code_column"), str) and IDENT.fullmatch(ekb["code_column"])
            and "." not in ekb["code_column"]):
        raise AuditConfigError("AUDIT_EKB_CONFIG_INVALID")
    return data


def manifest(config: dict, root: Path = ROOT) -> dict:
    skill = config["audit"]["skill"]
    file = root / skill["manifest"]
    try:
        data = json.loads(file.read_text("utf-8"))
    except (OSError, ValueError):
        raise AuditConfigError("AUDIT_SKILL_MANIFEST_UNREADABLE") from None
    files = data.get("files") if isinstance(data, dict) else None
    if (data.get("schema_version") != "LF_AUDIT_SKILL_MANIFEST_V1"
            or data.get("repository") != skill["repository"] or data.get("commit") != skill["commit"]
            or data.get("path") != skill["path"] or not isinstance(files, dict) or not files
            or not all(isinstance(k, str) and REL.fullmatch(k) and isinstance(v, str)
                       and SHA64.fullmatch(v) for k, v in files.items())):
        raise AuditConfigError("AUDIT_SKILL_MANIFEST_INVALID")
    return files
