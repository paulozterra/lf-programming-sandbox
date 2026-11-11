"""Sandbox-only pytest path adapter; upstream A1-A5 and test bodies remain byte-exact."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "analysis" / "programming_analysis"
COMPAT = ROOT / "skills" / "programming_analysis"
if not COMPAT.exists() and not COMPAT.is_symlink():
    COMPAT.parent.mkdir(parents=True, exist_ok=True)
    COMPAT.symlink_to(SOURCE, target_is_directory=True)
elif COMPAT.resolve() != SOURCE.resolve():
    raise RuntimeError("ANALYSIS_COMPAT_PATH_CONFLICT")
for relative in ("steps/a2/adapters",):
    candidate = str(SOURCE / relative)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)
