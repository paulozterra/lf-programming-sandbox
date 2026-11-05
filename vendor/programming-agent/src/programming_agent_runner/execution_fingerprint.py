from __future__ import annotations

import re
from typing import Any

from .hashutil import sha256_evidence_envelope, sha256_json
from .models import Evidence, GateResult, RunnerInput, Status

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VALID_EXECUTION_MODES = {"legacy", "deterministic", "probabilistic"}


def _valid_sha256(value: str | None) -> bool:
    return value is not None and SHA256_RE.fullmatch(value) is not None


def _payload(input_: RunnerInput, context_pack_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "repo_full_name": input_.repo_full_name,
        "ref": input_.ref,
        "head_sha": input_.head_sha,
        "source_snapshot_sha256": input_.source_snapshot_sha256,
        "scope": list(input_.scope),
        "version_code": input_.version_code,
        "profile_code": input_.profile_code,
        "context_pack_sha256": context_pack_sha256,
        "execution_mode": input_.execution_mode,
        "model_provider": input_.model_provider,
        "model_identifier": input_.model_identifier,
        "instruction_sha256": input_.instruction_sha256,
        "toolchain_sha256": input_.toolchain_sha256,
    }


def evaluate_execution_fingerprint(
    input_: RunnerInput,
    context_pack_sha256: str,
) -> tuple[GateResult, Evidence]:
    payload = _payload(input_, context_pack_sha256)
    fingerprint = sha256_json(payload)
    problems: list[str] = []

    if input_.execution_mode not in VALID_EXECUTION_MODES:
        problems.append("execution_mode_invalid")
    if input_.instruction_sha256 is not None and not _valid_sha256(input_.instruction_sha256):
        problems.append("instruction_sha256_invalid")
    if input_.toolchain_sha256 is not None and not _valid_sha256(input_.toolchain_sha256):
        problems.append("toolchain_sha256_invalid")
    if input_.expected_execution_fingerprint_sha256 is not None and not _valid_sha256(
        input_.expected_execution_fingerprint_sha256
    ):
        problems.append("expected_execution_fingerprint_sha256_invalid")

    v06_contract = input_.version_code.startswith("v0.6")
    if v06_contract:
        if input_.execution_mode == "legacy":
            problems.append("execution_mode_required")
        if input_.toolchain_sha256 is None:
            problems.append("toolchain_sha256_required")

    if input_.execution_mode == "probabilistic":
        if not input_.model_provider.strip() or input_.model_provider.strip().lower() == "none":
            problems.append("model_provider_required")
        if not input_.model_identifier.strip() or input_.model_identifier.strip().lower() == "none":
            problems.append("model_identifier_required")
        if input_.instruction_sha256 is None:
            problems.append("instruction_sha256_required")
    elif input_.execution_mode == "deterministic":
        if input_.model_provider.strip().lower() != "none":
            problems.append("deterministic_runtime_model_provider_conflict")
        if input_.model_identifier.strip().lower() != "none":
            problems.append("deterministic_runtime_model_identifier_conflict")
    elif input_.execution_mode == "legacy" and not v06_contract:
        probabilistic_legacy = input_.model_provider.strip().lower() != "none"
        if probabilistic_legacy:
            if not input_.model_identifier.strip() or input_.model_identifier.strip().lower() == "none":
                problems.append("model_identifier_required")
            if input_.instruction_sha256 is None:
                problems.append("instruction_sha256_required")

    if problems:
        status: Status = "BLOCKED"
        reason = "EXECUTION_IDENTITY_INCOMPLETE"
    elif (
        input_.expected_execution_fingerprint_sha256 is not None
        and input_.expected_execution_fingerprint_sha256 != fingerprint
    ):
        status = "FAIL"
        reason = "EXECUTION_FINGERPRINT_DRIFT"
    else:
        status = "PASS"
        reason = (
            "EXECUTION_FINGERPRINT_MATCHED"
            if input_.expected_execution_fingerprint_sha256
            else "EXECUTION_FINGERPRINT_PINNED"
        )

    metadata = {
        "execution_fingerprint_sha256": fingerprint,
        "expected_execution_fingerprint_sha256": input_.expected_execution_fingerprint_sha256,
        "identity": payload,
        "problems": problems,
    }
    code = "E_EXECUTION_FINGERPRINT"
    source_system = "RUNNER"
    source_ref = f"{input_.repo_full_name}@{input_.head_sha}"
    producer = "RUNNER_EXECUTION_FINGERPRINT"
    evidence = Evidence(
        code=code,
        status=status,
        source_system=source_system,
        source_ref=source_ref,
        sha256=sha256_evidence_envelope(
            code=code,
            status=status,
            source_system=source_system,
            source_ref=source_ref,
            head_sha=input_.head_sha,
            producer=producer,
            metadata=metadata,
        ),
        head_sha=input_.head_sha,
        producer=producer,
        metadata=metadata,
    )
    gate = GateResult(
        "G_RUNNER_EXECUTION_FINGERPRINT",
        status,
        reason,
        (code,),
        metadata,
    )
    return gate, evidence
