"""T21: install an executable trampoline without losing pyvenv.cfg discovery."""
from __future__ import annotations

import argparse
from pathlib import Path

RUNTIME = Path("/tmp/lf-python-runtime")
HEADER = "#!/bin/sh\n"


def write_wrapper(destination: Path, interpreter: Path = RUNTIME / "bin/python") -> None:
    if not interpreter.is_absolute() or not interpreter.is_file():
        raise ValueError("LF_PYTHON_INTERPRETER_MISSING")
    if destination.is_symlink():
        destination.unlink()
    destination.write_text(
        HEADER + 'exec "' + str(interpreter) + '" "$@"\n', encoding="utf-8"
    )
    destination.chmod(0o755)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interpreter", type=Path, default=RUNTIME / "bin/python")
    args = parser.parse_args()
    write_wrapper(args.output, args.interpreter)


if __name__ == "__main__":
    main()
