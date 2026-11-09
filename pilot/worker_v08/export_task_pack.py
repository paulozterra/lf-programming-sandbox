#!/usr/bin/env python3
"""Use run_worker itself to export its exact system instruction and user payload.

Run with an owner-approved WorkerTaskSpec. No hidden oracle, API key or model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

PILOT = Path(__file__).resolve().parent
ROOT = PILOT.parents[1]
sys.path.insert(0, str(ROOT / "vendor" / "programming-agent" / "src"))

from programming_agent_runner.hashutil import strict_json_loads  # noqa: E402
from programming_agent_runner.worker import run_worker  # noqa: E402
from programming_agent_runner.worker_spec import parse_worker_task  # noqa: E402
from native_capture_client import NativeCaptureClient  # noqa: E402


def export(repo: Path, spec_path: Path, output_path: Path) -> str:
    raw = strict_json_loads(spec_path.read_text(encoding="utf-8"))
    spec = replace(parse_worker_task(raw), max_attempts=1)
    client = NativeCaptureClient(output_path)
    result = run_worker(repo, spec, client)
    if (not client.called or client.captured_sha256 is None
        or result.receipt.get("status") != "BLOCKED"
        or result.receipt.get("reason") != "NATIVE_CAPTURE_ONLY"
        or result.patch):
        raise RuntimeError("NATIVE_CAPTURE_FAILED_OR_PREFLIGHT_BLOCKED")
    actual = hashlib.sha256(output_path.read_bytes()).hexdigest()
    if actual != client.captured_sha256:
        raise RuntimeError("NATIVE_PACK_SHA_MISMATCH")
    return actual


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--task-spec", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sha = export(args.repo, args.task_spec, args.out)
    # The digest is public; the pack never includes a hidden oracle.
    print(json.dumps({"task_pack_sha256": sha}, sort_keys=True))


if __name__ == "__main__":
    main()
