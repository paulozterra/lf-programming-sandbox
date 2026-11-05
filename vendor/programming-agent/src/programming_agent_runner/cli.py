from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .github_reader import GitHubReader
from .hashutil import strict_json_loads
from .models import RunnerInput
from .runner import run_reference


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Programming Agent Runner v0.6 reference implementation")
    p.add_argument("--repo-path", type=Path, required=True)
    p.add_argument("--repo-full-name", required=True)
    p.add_argument("--ref", required=True)
    p.add_argument("--head-sha", required=True)
    p.add_argument("--source-snapshot-sha256", required=True)
    p.add_argument("--scope", action="append", default=[])
    p.add_argument("--worker-task-spec", type=Path, help="WorkerTaskSpec v2 JSON; required when --execute-commands is used")
    p.add_argument("--execution-mode", choices=("deterministic", "probabilistic"), required=True)
    p.add_argument("--model-provider", default="none")
    p.add_argument("--model-identifier", default="none")
    p.add_argument("--instruction-sha256")
    p.add_argument("--toolchain-sha256", required=True)
    p.add_argument("--expected-execution-fingerprint-sha256")
    p.add_argument("--ekb-snapshot", type=Path)
    p.add_argument("--github", action="store_true", help="Reconcile GitHub using GITHUB_TOKEN")
    p.add_argument("--execute-commands", action="store_true", help="Execute only commands explicitly discovered from repository configuration")
    p.add_argument("--output", type=Path, required=True)
    return p


def _load_json_object(path: Path, label: str) -> dict:
    try:
        loaded = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"{label}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"{label}: root must be an object")
    return loaded


def main() -> int:
    args = parser().parse_args()
    ekb = None
    if args.ekb_snapshot:
        try:
            ekb = _load_json_object(args.ekb_snapshot, "EKB_SNAPSHOT_INVALID")
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    worker_task_spec = None
    if args.worker_task_spec:
        try:
            worker_task_spec = _load_json_object(args.worker_task_spec, "WORKER_TASK_SPEC_INVALID")
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    github = GitHubReader.from_environment() if args.github else None
    result = run_reference(
        RunnerInput(
            repo_path=args.repo_path.resolve(),
            repo_full_name=args.repo_full_name,
            ref=args.ref,
            head_sha=args.head_sha,
            source_snapshot_sha256=args.source_snapshot_sha256,
            scope=tuple(args.scope),
            version_code="v0.6-local-reference",
            execution_mode=args.execution_mode,
            model_provider=args.model_provider,
            model_identifier=args.model_identifier,
            instruction_sha256=args.instruction_sha256,
            toolchain_sha256=args.toolchain_sha256,
            expected_execution_fingerprint_sha256=args.expected_execution_fingerprint_sha256,
            worker_task_spec=worker_task_spec,
        ),
        ekb_snapshot=ekb,
        github=github,
        execute_commands=args.execute_commands,
    )
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
