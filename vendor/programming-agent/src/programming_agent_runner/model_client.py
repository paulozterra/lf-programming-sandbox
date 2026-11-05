from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ModelError(RuntimeError):
    """Base class for fail-closed model transport and response errors."""


class ModelRefusal(ModelError):
    """The model explicitly refused the requested programming operation."""


class ModelClient(Protocol):
    provider: str
    model: str

    def generate(self, system_instruction: str, user_payload: dict[str, Any]) -> "ModelResponse": ...


@dataclass(frozen=True)
class ModelResponse:
    response_id: str
    requested_model: str
    resolved_model: str
    output_text: str
    usage: dict[str, int]
