from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .anthropic_messages import AnthropicMessagesClient
from .hashutil import strict_json_loads
from .model_client import ModelError, ModelResponse
from .openai_responses import OpenAIResponsesClient
from .programming_quality_hardening_v7_runtime import (
    load_quality_plan,
    load_readback_manifest,
    readback_source_paths,
    run_programming_quality_worker_hardened,
)
from .worker_oracle import OracleError, load_hidden_oracle
from .worker_spec import TaskSpecError, parse_worker_task


class _UnavailableModelClient:
    def __init__(self, provider: str, model: str, reason: str) -> None:
        self.provider = provider
        self.model = model
        self.reason = reason

    def generate(self, system_instruction: str, user_payload: dict[str, Any]) -> ModelResponse:
        raise ModelError(self.reason)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description=(
            "Programming Agent Worker: causal risk evidence, declared-target fixture preflight, "
            "pre/post source-of-truth readback, visible+hidden acceptance, and post-green quality"
        )
    )
    value.add_argument("--repo-path", type=Path, required=True)
    value.add_argument("--task-spec", type=Path, required=True)
    value.add_argument(
        "--quality-plan",
        type=Path,
        required=True,
        help="Owner-pinned risk profile, fixture preflight, and semantic target plan outside the repository",
    )
    value.add_argument(
        "--quality-plan-sha256",
        required=True,
        help="Owner-pinned raw SHA-256 of the quality plan",
    )
    value.add_argument(
        "--hidden-oracle-manifest",
        type=Path,
        required=True,
        help="Pinned hidden holdout manifest outside the repository and outside Builder context",
    )
    value.add_argument(
        "--hidden-oracle-sha256",
        required=True,
        help="Owner-pinned SHA-256 of the hidden oracle manifest",
    )
    value.add_argument(
        "--readback-manifest",
        type=Path,
        required=True,
        help="Owner-pinned source-of-truth readback contract outside the repository",
    )
    value.add_argument(
        "--readback-manifest-sha256",
        required=True,
        help="Owner-pinned SHA-256 of the readback contract",
    )
    value.add_argument(
        "--provider",
        choices=("openai", "anthropic"),
        default="openai",
        help="Explicit model provider. Provider selection never changes verification authority.",
    )
    value.add_argument("--model", required=True, help="Explicit provider model identifier")
    value.add_argument("--api-timeout-seconds", type=float, default=120.0)
    value.add_argument("--max-output-tokens", type=int, default=20_000)
    value.add_argument("--output", type=Path, required=True, help="Quality-gated receipt JSON path outside the repository")
    value.add_argument("--patch-output", type=Path, required=True, help="Final patch path outside the repository")
    return value


def _outside_repository(path: Path, repository: Path) -> bool:
    resolved = path.resolve()
    return resolved != repository and not resolved.is_relative_to(repository)


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _model_client(args: argparse.Namespace) -> Any:
    provider = args.provider
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return _UnavailableModelClient(provider, args.model, "OPENAI_API_KEY_MISSING")
        return OpenAIResponsesClient(
            api_key=api_key,
            model=args.model,
            timeout_seconds=args.api_timeout_seconds,
            max_output_tokens=args.max_output_tokens,
        )
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return _UnavailableModelClient(provider, args.model, "ANTHROPIC_API_KEY_MISSING")
        return AnthropicMessagesClient(
            api_key=api_key,
            model=args.model,
            timeout_seconds=args.api_timeout_seconds,
            max_output_tokens=args.max_output_tokens,
        )
    raise ValueError("provider is unsupported")


def main() -> int:
    args = parser().parse_args()
    repository = args.repo_path.resolve()
    output_paths = {args.output.resolve(), args.patch_output.resolve()}
    protected_inputs = {
        args.task_spec.resolve(),
        args.quality_plan.resolve(),
        args.hidden_oracle_manifest.resolve(),
        args.readback_manifest.resolve(),
    }
    if len(output_paths) != 2 or output_paths & protected_inputs:
        print("WORKER_OUTPUT_PATHS_CONFLICT", file=sys.stderr)
        return 2
    external_paths = (
        *output_paths,
        args.quality_plan.resolve(),
        args.hidden_oracle_manifest.resolve(),
        args.readback_manifest.resolve(),
    )
    for path in external_paths:
        if not _outside_repository(path, repository):
            print("WORKER_EXTERNAL_PATH_INSIDE_SOURCE_REPOSITORY", file=sys.stderr)
            return 2
    try:
        raw_task = strict_json_loads(args.task_spec.read_text(encoding="utf-8"))
        spec = parse_worker_task(raw_task)
    except (OSError, UnicodeError, ValueError, TaskSpecError) as exc:
        print(f"WORKER_TASK_INVALID: {exc}", file=sys.stderr)
        return 2
    try:
        quality_plan = load_quality_plan(args.quality_plan, args.quality_plan_sha256)
    except ValueError as exc:
        print(f"WORKER_QUALITY_PLAN_INVALID: {exc}", file=sys.stderr)
        return 2
    try:
        oracle = load_hidden_oracle(args.hidden_oracle_manifest, args.hidden_oracle_sha256)
    except OracleError as exc:
        print(f"WORKER_HIDDEN_ORACLE_INVALID: {exc}", file=sys.stderr)
        return 2
    try:
        readback_manifest = load_readback_manifest(args.readback_manifest, args.readback_manifest_sha256)
    except (OSError, ValueError) as exc:
        print(f"WORKER_READBACK_MANIFEST_INVALID: {exc}", file=sys.stderr)
        return 2
    for source_path in readback_source_paths(readback_manifest):
        if not source_path.is_absolute() or not _outside_repository(source_path, repository):
            print("WORKER_READBACK_SOURCE_INSIDE_SOURCE_REPOSITORY", file=sys.stderr)
            return 2
    try:
        client = _model_client(args)
    except ValueError as exc:
        print(f"WORKER_MODEL_CONFIGURATION_INVALID: {exc}", file=sys.stderr)
        return 2
    result = run_programming_quality_worker_hardened(
        repository,
        spec,
        client,
        oracle,
        quality_plan,
        readback_manifest,
    )
    _atomic_text(
        args.output,
        json.dumps(result.receipt, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n",
    )
    _atomic_text(args.patch_output, result.patch)
    print(
        f"WORKER_STATUS={result.receipt['status']} RECEIPT_SHA256={result.receipt['receipt_sha256']} "
        f"PATCH_SHA256={result.receipt['patch_sha256']} ORACLE_FAMILY={oracle.family} "
        f"ORACLE_SHA256={oracle.manifest_sha256} QUALITY_PLAN_SHA256={quality_plan.sha256} "
        f"READBACK_SHA256={readback_manifest.sha256}"
    )
    return 0 if result.receipt["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
