"""Capture the exact model input produced by the unmodified vendored Worker.

No model request is made. Capture is deliberately a terminal ModelError.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from programming_agent_runner.hashutil import canonical_json_bytes
from programming_agent_runner.model_client import ModelError


def task_pack_bytes(system_instruction: str, user_payload: dict[str, Any]) -> bytes:
    return canonical_json_bytes({
        "system_instruction": system_instruction,
        "user_payload": user_payload,
    })


def task_pack_sha256(system_instruction: str, user_payload: dict[str, Any]) -> str:
    return hashlib.sha256(task_pack_bytes(system_instruction, user_payload)).hexdigest()


class NativeCaptureClient:
    provider = "native-capture"
    model = "capture-only"

    def __init__(self, output_path: Path) -> None:
        self.output_path = Path(output_path)
        self.called = False
        self.captured_sha256: str | None = None

    def generate(self, system_instruction: str, user_payload: dict[str, Any]):
        if self.called or self.output_path.exists() or self.output_path.is_symlink():
            raise ModelError("NATIVE_CAPTURE_ALREADY_EXISTS")
        self.called = True
        raw = task_pack_bytes(system_instruction, user_payload)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("xb") as output:
            output.write(raw)
        self.output_path.chmod(0o600)
        self.captured_sha256 = hashlib.sha256(raw).hexdigest()
        raise ModelError("NATIVE_CAPTURE_ONLY")
