#!/usr/bin/env python3
"""Run the SBX-only A1-A5 chain, emitting deterministic per-stage JSON."""
import argparse
import json
from pathlib import Path
try:
    from .fixture_readback_host import run
except ImportError:
    from fixture_readback_host import run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", default="Crear la pantalla de login SBX-AUTH-LOGIN con las reglas vigentes")
    parser.add_argument("--out", type=Path, default=Path("analysis/out/sbx_auth_login"))
    args = parser.parse_args()
    result = run(args.request)
    args.out.mkdir(parents=True, exist_ok=True)
    for step, value in result.get("stages", {}).items():
        (args.out / (step.lower() + ".json")).write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
    (args.out / "run.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": result.get("status", result.get("stages", {}).get("A5", {}).get("status")),
                      "blocking_codes": result.get("blocking_codes", []),
                      "stages": list(result.get("stages", {}))}, sort_keys=True))
    return int(result.get("status") == "BLOCKED")


if __name__ == "__main__":
    raise SystemExit(main())
