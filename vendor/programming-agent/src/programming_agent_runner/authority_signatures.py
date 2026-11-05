from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .hashutil import canonical_json_bytes


class AuthoritySignatureError(ValueError):
    """Raised when an external authority receipt cannot be cryptographically verified."""


def _required_text(value: Any, field: str, maximum: int = 8192) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > maximum:
        raise AuthoritySignatureError(f"{field} is required")
    return value


def _decode_b64(value: Any, field: str, expected_length: int) -> bytes:
    text = _required_text(value, field, maximum=4096)
    try:
        decoded = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AuthoritySignatureError(f"{field} is not valid base64") from exc
    if len(decoded) != expected_length:
        raise AuthoritySignatureError(f"{field} must decode to {expected_length} bytes")
    return decoded


def signed_authority_payload(receipt: Any) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise AuthoritySignatureError("authority receipt must be an object")
    if receipt.get("schema_version") != 1:
        raise AuthoritySignatureError("authority receipt schema_version must be 1")
    if "signature_ed25519_b64" not in receipt:
        raise AuthoritySignatureError("authority receipt signature is required")
    return {key: value for key, value in receipt.items() if key != "signature_ed25519_b64"}


def verify_authority_receipt(
    receipt: Any,
    trusted_public_keys: Mapping[str, str],
    *,
    expected_kind: str,
    expected_head_sha: str | None = None,
    expected_subject_sha256: str | None = None,
) -> dict[str, Any]:
    payload = signed_authority_payload(receipt)
    kind = _required_text(payload.get("kind"), "authority receipt kind", 128)
    if kind != expected_kind:
        raise AuthoritySignatureError(f"authority receipt kind must be {expected_kind}")

    key_id = _required_text(payload.get("key_id"), "authority receipt key_id", 256)
    public_key_b64 = trusted_public_keys.get(key_id)
    if public_key_b64 is None:
        raise AuthoritySignatureError("authority receipt key_id is not trusted")

    public_key_bytes = _decode_b64(public_key_b64, "trusted Ed25519 public key", 32)
    signature = _decode_b64(receipt.get("signature_ed25519_b64"), "signature_ed25519_b64", 64)
    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(signature, canonical_json_bytes(payload))
    except (InvalidSignature, ValueError) as exc:
        raise AuthoritySignatureError("authority receipt signature verification failed") from exc

    if expected_head_sha is not None and payload.get("head_sha") != expected_head_sha:
        raise AuthoritySignatureError("authority receipt HEAD mismatch")
    if expected_subject_sha256 is not None and payload.get("subject_sha256") != expected_subject_sha256:
        raise AuthoritySignatureError("authority receipt subject mismatch")
    return receipt
