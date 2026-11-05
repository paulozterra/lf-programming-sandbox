from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any

from .discovery import (
    architecture_inventory,
    configuration_inventory,
    dependency_inventory,
    migration_inventory,
    public_api_inventory,
    relative_files,
    test_inventory,
)
from .models import ContextPack


def build_context_pack(root: Path, ekb_snapshot: dict[str, Any] | None = None) -> ContextPack:
    files = relative_files(root)
    return ContextPack(
        repository_inventory={"files": files, "file_count": len(files)},
        dependency_inventory=dependency_inventory(root),
        architecture_inventory=architecture_inventory(root),
        configuration_inventory=configuration_inventory(root),
        test_inventory=test_inventory(root),
        migration_inventory=migration_inventory(root),
        public_api_inventory=public_api_inventory(root),
        ekb_snapshot=ekb_snapshot or {"status": "MISSING_CONTEXT", "required_for_effective_pass": True},
        provenance={
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "builder": "programming_agent_runner.context_builder",
        },
    )
