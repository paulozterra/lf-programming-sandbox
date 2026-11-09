"""Offline model-client adapter. Worker owns proposal and patch validation.

Envelope is data, never instructions; the client does not call an API.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from programming_agent_runner.hashutil import canonical_json_bytes, strict_json_loads
from programming_agent_runner.model_client import ModelError, ModelResponse
from native_capture_client import task_pack_sha256

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_PROPOSAL_BYTES = 1_000_000


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def read_proposal_envelope(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_PROPOSAL_BYTES:
        raise ModelError("NATIVE_PROPOSAL_FILE_INVALID")
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ModelError("NATIVE_PROPOSAL_JSON_INVALID") from exc
    if not isinstance(value, dict) or set(value) != {
        "task_pack_sha256", "proposal_sha256", "proposal", "author"
    }:
        raise ModelError("NATIVE_PROPOSAL_ENVELOPE_INVALID")
    if not _is_sha(value["task_pack_sha256"]) or not _is_sha(value["proposal_sha256"]):
        raise ModelError("NATIVE_PROPOSAL_SHA_INVALID")
    if value["author"] != "GPT_NATIVE":
        raise ModelError("NATIVE_AUTHOR_INVALID")
    # Preserve the submitted JSON value; the original Worker validates its schema.
    proposal_bytes = canonical_json_bytes(value["proposal"])
    if hashlib.sha256(proposal_bytes).hexdigest() != value["proposal_sha256"]:
        raise ModelError("NATIVE_PROPOSAL_SHA_MISMATCH")
    return value


class NativeProposalClient:
    provider = "native-subscription"
    model = "gpt-native"

    def __init__(self, proposal_path: Path) -> None:
        self.proposal_path = Path(proposal_path)
        self.calls = 0

    def generate(self, system_instruction: str, user_payload: dict[str, Any]) -> ModelResponse:
        self.calls += 1
        if self.calls != 1:
            raise ModelError("NATIVE_SINGLE_ATTEMPT_ONLY")
        value = read_proposal_envelope(self.proposal_path)
        if task_pack_sha256(system_instruction, user_payload) != value["task_pack_sha256"]:
            raise ModelError("NATIVE_PACK_MISMATCH")
        return ModelResponse(
            response_id=value["proposal_sha256"],
            requested_model=self.model,
            resolved_model="gpt-native:chat-subscription",
            output_text=canonical_json_bytes(value["proposal"]).decode("utf-8"),
            usage={},
        )
