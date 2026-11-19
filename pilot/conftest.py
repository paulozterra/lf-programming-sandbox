"""Synthetic project fixture for pilot pytest tests.

Every test using tmp_path receives an explicit, validated project configuration
at that checkout root. Production paths never fall back when config is missing.
"""
from pathlib import Path
import shutil

import pytest


@pytest.fixture(autouse=True)
def configured_pilot_checkout(request):
    if "tmp_path" not in request.fixturenames:
        return
    root = request.getfixturevalue("tmp_path")
    source = Path(__file__).resolve().parent / "config"
    target = root / "pilot/config"
    (target / "projects").mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "active_project.json", target / "active_project.json")
    shutil.copy2(source / "projects/sandbox.json", target / "projects/sandbox.json")
