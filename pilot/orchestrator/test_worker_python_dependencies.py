"""T13: all generated acceptance areas have pinned Python imports."""
from pathlib import Path
import pytest
from pilot.orchestrator.worker_python_dependencies import (
    all_generated_commands, check_commands, pinned_modules, verify,
)

ROOT = Path(__file__).resolve().parents[2]


def test_all_areas_generate_only_isolated_python_commands():
    assert {area for area, _ in all_generated_commands()} == {
        "CONTRATO", "BACKEND", "FRONTEND", "INFRA", "DATA"}
    for _, commands in all_generated_commands():
        for command in commands:
            if command["argv"][1:2] and command["argv"][1].endswith(".py"):
                assert command["argv"][0] == "lf-python"
    verify()


def test_missing_import_fails_closed_for_every_area(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("PyYAML==6.0.3\n")
    script = tmp_path / "probe.py"
    script.write_text("import third_party_unpinned\n")
    with pytest.raises(ValueError, match=r"WORKER_DEPENDENCIA_FALTANTE:probe.py:third_party_unpinned"):
        check_commands([{"argv": ["lf-python", "probe.py"]}], root=tmp_path,
                       requirements=requirements)


def test_runtime_has_required_direct_imports():
    assert {"yaml", "jsonschema", "openapi_spec_validator", "playwright"} <= pinned_modules()
