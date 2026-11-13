#!/usr/bin/env python3
"""Run the fixture-provided simulated request through real A1..A5.

No language model, Supabase, production authority, or PG-04 dispatch.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
try:
    from .fixture_readback_host import FixtureHost, FixtureBlocked, DEFAULT_FIXTURES
except ImportError:
    from fixture_readback_host import FixtureHost, FixtureBlocked, DEFAULT_FIXTURES

REQUEST = json.loads((DEFAULT_FIXTURES / "semantic_signals.json").read_text(encoding="utf-8"))["request_text"]


def encoded(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n").encode("utf-8")


def execute(request=REQUEST, fixtures=None, output_dir=None):
    host = FixtureHost(fixtures) if fixtures is not None else FixtureHost()
    result = host.run(request)
    if output_dir is not None:
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        for stage, value in result["stages"].items():
            (directory / (stage.lower() + ".json")).write_bytes(encoded(value))
        (directory / "source_provenance.json").write_bytes(encoded({
            "simulation": True, "source_attested": False,
            "fixture_provenance": result["fixture_provenance"],
        }))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", default=REQUEST)
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = execute(args.request, args.fixtures, args.output_dir)
    except FixtureBlocked as exc:
        parser.exit(2, "BLOCKED:" + exc.code + "\n")
    print(json.dumps({
        "simulation": True, "stages": {
            key: value.get("status") for key, value in result["stages"].items()
        },
        "output_dir": str(args.output_dir),
    }, sort_keys=True))
