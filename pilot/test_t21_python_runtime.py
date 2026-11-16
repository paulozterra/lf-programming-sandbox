"""T21 real runtime regression: same pinned dependencies, clean environment."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

from pilot.worker_v08.install_lf_python import write_wrapper

ROOT = Path(__file__).resolve().parents[1]
IMPORTS = "import yaml, jsonschema, openapi_spec_validator, playwright.sync_api"


def check() -> None:
    with tempfile.TemporaryDirectory(prefix="lf-t21-") as tmp:
        root = Path(tmp)
        venv = root / "lf-python-runtime"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        python = venv / "bin/python"
        subprocess.run([str(python), "-m", "pip", "install",
                        "--disable-pip-version-check", "--no-input",
                        "-r", str(ROOT / "pilot/worker_v08/python_runtime_requirements.txt")],
                       check=True)
        # Check a private site-packages sentinel as well as the real imports.
        site = subprocess.check_output(
            [str(python), "-c", "import site; print(site.getsitepackages()[0])"],
            text=True).strip()
        (Path(site) / "lf_t21_venv_only.py").write_text("VERIFIED = True\\n")
        bin_dir = root / "bin"
        bin_dir.mkdir()
        shim = bin_dir / "lf-python"
        shim.symlink_to(python)
        isolated = {"PATH": str(bin_dir) + ":/usr/local/bin:/usr/bin:/bin"}
        command = ["lf-python", "-c", IMPORTS + ", lf_t21_venv_only"]
        bad = subprocess.run(command, env=isolated, capture_output=True, text=True)
        if bad.returncode == 0 or "ModuleNotFoundError" not in bad.stderr:
            raise AssertionError("T21_SYMLINK_MUST_FAIL_ISOLATED_IMPORT")
        write_wrapper(shim, python)
        good = subprocess.run(command, env=isolated, capture_output=True, text=True)
        if good.returncode != 0:
            raise AssertionError("T21_WRAPPER_IMPORT_FAILED: " + good.stderr[-800:])
        prefix = subprocess.check_output(
            ["lf-python", "-c", "import sys; print(sys.prefix)"],
            env=isolated, text=True).strip()
        if prefix != str(venv):
            raise AssertionError("T21_WRAPPER_NOT_USING_EXPECTED_VENV")
        print("T21_REAL_ISOLATED_RUNTIME_PASS")


if __name__ == "__main__":
    check()
