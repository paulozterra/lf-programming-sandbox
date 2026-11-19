"""Explicit fixture installer for disposable LF project checkouts.

Never called by production configuration resolution.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from pilot.config.project_config import ROOT, PROJECT_ID, ProjectConfigError, validate


def install_project_config(tmp_root: Path, project: str = "sandbox") -> None:
    """Copy a validated project definition and select it in a temporary root."""
    root = Path(tmp_root)
    if not isinstance(project, str) or not PROJECT_ID.fullmatch(project):
        raise ProjectConfigError("PROJECT_CONFIG_INVALID")
    source = ROOT / "pilot/config/projects" / (project + ".json")
    if not source.is_file() or source.is_symlink():
        raise ProjectConfigError("PROJECT_CONFIG_INVALID")
    try:
        data = json.loads(source.read_text("utf-8"))
        validate(data, root=root, project=project)
    except (OSError, ValueError, TypeError) as exc:
        raise ProjectConfigError("PROJECT_CONFIG_INVALID") from exc
    target = root / "pilot/config/projects"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target / (project + ".json"))
    (root / "pilot/config/active_project.json").write_text(
        json.dumps({"schema_version": "LF_ACTIVE_PROJECT_V1", "project_id": project},
                   sort_keys=True, indent=2) + "\n", encoding="utf-8")
