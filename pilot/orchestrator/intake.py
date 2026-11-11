#!/usr/bin/env python3
"""CP3.2 — deterministic, offline intake; never grants production authority.

The Analysis payload follows LF's ANALYSIS_IMPLEMENTATION_PACKAGE_V1 candidate
shape, with CP3.2's explicit simulation marker and request-byte binding.
PG-01 uses the unmodified pinned C4/V3 preflight and remains UNATTESTED.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
PG01 = ROOT / "pilot/lf_producers_pinned/pg02"
REQ = re.compile(r"REQ-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
SLUG = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
STAGES = [f"A{i}" for i in range(1, 10)]
READINESS = {"READY_CANDIDATE", "NEED_MORE_EVIDENCE", "REQUIRES_DECISION", "BLOCKED"}
AUTHORITY = {"production_authority", "handoff_allowed", "merge_allowed",
             "deploy_allowed", "downstream_authorized", "pg01_consumer_verified"}


class IntakeBlocked(ValueError):
    pass


def block(reason: str) -> None:
    raise IntakeBlocked(reason)


def canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def normalized_request_bytes(raw: bytes) -> bytes:
    try:
        value = raw.decode("utf-8")
    except UnicodeDecodeError:
        block("REQUEST_UTF8_INVALID")
    if not value.strip() or "\x00" in value:
        block("REQUEST_INVALID")
    return value.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _reject_authority(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in AUTHORITY and item is not False:
                block("INTAKE_AUTHORITY_FORBIDDEN")
            if key.endswith("_authority") and item is True:
                block("INTAKE_AUTHORITY_FORBIDDEN")
            _reject_authority(item)
    elif isinstance(value, list):
        for item in value:
            _reject_authority(item)


def validate(package: dict, request_raw: bytes) -> tuple[dict, str]:
    if not isinstance(package, dict):
        block("ANALYSIS_FIELDS_MISSING")
    if package.get("analysis_mode") != "SIMULATED_ANALYSIS":
        block("ANALYSIS_SIMULATION_MARK_MISSING")
    digest = hashlib.sha256(normalized_request_bytes(request_raw)).hexdigest()
    if not isinstance(package.get("request_sha256"), str) or package["request_sha256"] != digest:
        block("ANALYSIS_REQUEST_SHA_MISMATCH")
    required = {
        "schema_version", "candidate_only", "request_context", "classification",
        "stage_trace", "material_unknowns", "decisions_pending", "requirements",
        "material_fronts", "scope_proposals", "research_stop",
        "package_readiness_candidate", "analysis_mode", "request_sha256",
    }
    if not required.issubset(package):
        block("ANALYSIS_FIELDS_MISSING")
    if package["schema_version"] != "ANALYSIS_IMPLEMENTATION_PACKAGE_V1" or package["candidate_only"] is not True:
        block("ANALYSIS_SCHEMA_INVALID")
    _reject_authority(package)
    ctx, classification = package["request_context"], package["classification"]
    if not isinstance(ctx, dict) or not all(isinstance(ctx.get(k), str) and ctx[k] for k in ("intent", "target_ref")):
        block("ANALYSIS_FIELDS_MISSING")
    if not isinstance(classification, dict) or any(k not in classification for k in
        ("target_granularity", "depth", "authority_state", "implementation_state")):
        block("ANALYSIS_FIELDS_MISSING")
    if (classification["depth"] not in ("L1", "L2", "L3")
            or classification["authority_state"] not in ("EXISTING", "NEW", "UNKNOWN")
            or classification["implementation_state"] not in ("EXISTING", "NEW", "UNKNOWN")):
        block("ANALYSIS_SCHEMA_INVALID")
    stages = package["stage_trace"]
    if not isinstance(stages, list) or [s.get("stage") if isinstance(s, dict) else None for s in stages] != STAGES:
        block("ANALYSIS_FIELDS_MISSING")
    for field in ("material_unknowns", "decisions_pending", "requirements", "material_fronts", "scope_proposals"):
        if not isinstance(package[field], list):
            block("ANALYSIS_FIELDS_MISSING")
    if not package["requirements"] or not package["material_fronts"] or not package["scope_proposals"]:
        block("ANALYSIS_FIELDS_MISSING")
    if not isinstance(package["research_stop"], dict) or not isinstance(package["package_readiness_candidate"], str):
        block("ANALYSIS_FIELDS_MISSING")
    scope_ids = []
    for scope in package["scope_proposals"]:
        if not isinstance(scope, dict) or not isinstance(scope.get("scope_id"), str):
            block("ANALYSIS_FIELDS_MISSING")
        if not isinstance(scope.get("material_front_refs"), list) or scope.get("readiness_candidate") not in READINESS:
            block("ANALYSIS_FIELDS_MISSING")
        scope_ids.append(scope["scope_id"])
    if len(set(scope_ids)) != len(scope_ids):
        block("ANALYSIS_SCOPE_DUPLICATED")
    req_ids, scopes_with_reqs = [], set()
    for req in package["requirements"]:
        if not isinstance(req, dict) or any(not isinstance(req.get(k), str) or not req[k]
                for k in ("requirement_id", "scope_id", "outcome", "acceptance_signal")):
            block("ANALYSIS_FIELDS_MISSING")
        name = req["requirement_id"]
        if not REQ.fullmatch(name):
            block("ANALYSIS_REQUIREMENT_INVALID")
        if req["scope_id"] not in scope_ids or not isinstance(req.get("evidence_refs"), list):
            block("ANALYSIS_REQUIREMENT_SCOPE_INVALID")
        req_ids.append(name)
        scopes_with_reqs.add(req["scope_id"])
    if len(set(req_ids)) != len(req_ids):
        block("ANALYSIS_REQUIREMENT_DUPLICATED")
    front_ids, covered = [], set()
    for front in package["material_fronts"]:
        if not isinstance(front, dict) or not isinstance(front.get("front_id"), str) or not front["front_id"]:
            block("ANALYSIS_FIELDS_MISSING")
        if not isinstance(front.get("scope_ids"), list) or not front["scope_ids"]:
            block("ANALYSIS_FIELDS_MISSING")
        if any(s not in scope_ids for s in front["scope_ids"]):
            block("ANALYSIS_FRONT_UNKNOWN_SCOPE")
        if front.get("obligation_mode") not in ("REQUIRED", "REUSE_AS_IS", "NOT_APPLICABLE"):
            block("ANALYSIS_FIELDS_MISSING")
        if front.get("closure") not in ("CLOSED", "BLOCKED"):
            block("ANALYSIS_FIELDS_MISSING")
        for field in ("blockers", "evidence_refs"):
            if not isinstance(front.get(field), list):
                block("ANALYSIS_FIELDS_MISSING")
        if not isinstance(front.get("reason"), str) or not front["reason"]:
            block("ANALYSIS_FIELDS_MISSING")
        front_ids.append(front["front_id"])
        covered.update(front["scope_ids"])
    if len(set(front_ids)) != len(front_ids):
        block("ANALYSIS_FRONT_DUPLICATED")
    for scope in package["scope_proposals"]:
        sid = scope["scope_id"]
        if sid not in scopes_with_reqs or sid not in covered:
            block("ANALYSIS_FRONT_WITHOUT_REQUIREMENT")
        expected = {f["front_id"] for f in package["material_fronts"] if sid in f["scope_ids"]}
        if set(scope["material_front_refs"]) != expected:
            block("ANALYSIS_FRONT_SCOPE_MISMATCH")
    return package, digest


def _pg01_fixture_readback(package: dict, digest: str) -> dict:
    """Call the pinned PG-01 preflight, never issue a trusted admission."""
    if not PG01.is_dir():
        block("PG01_PRODUCER_MISSING")
    sys.path.insert(0, str(PG01))
    try:
        from pg01_technical_frame_v3_candidate_v1 import preflight
        binding = {
            "context_id": "fixture://cp3-2/" + digest[:16],
            "context_sha256": digest,
            "binding_key_sha256": hashlib.sha256(canonical(package)).hexdigest(),
            "receipt_record_id": "fixture://pg01/unattested",
            "target_repo": "fixture://sandbox",
            "target_head_sha": "0" * 40,
        }
        response = preflight(binding, {})
    finally:
        sys.path.remove(str(PG01))
    if response.get("verified") is not False:
        block("PG01_FIXTURE_AUTHORITY_DRIFT")
    return {"status": "FIXTURE_UNATTESTED", "verified": False,
            "reason": response["reason"],
            "producer": "pg01_technical_frame_v3_candidate_v1.preflight"}


def accept(root: Path, slug: str) -> dict:
    if not SLUG.fullmatch(slug):
        block("RUN_ID_INVALID")
    directory = root / "pilot/runs" / slug
    if directory.is_symlink():
        block("RUN_PATH_INVALID")
    request = directory / "request.md"
    analysis = directory / "analysis.json"
    if any(p.is_symlink() or not p.is_file() for p in (request, analysis)):
        block("INTAKE_INPUT_MISSING")
    raw = normalized_request_bytes(request.read_bytes())
    try:
        package = json.loads(analysis.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        block("ANALYSIS_JSON_INVALID")
    obj, sha = validate(package, raw)
    readback = _pg01_fixture_readback(obj, sha)
    state = {
        "schema_version": "LF_ORCHESTRATOR_STATE_V1",
        "stage": "INTAKE_ACCEPTED", "request_id": slug,
        "request_sha256": sha,
        "analysis_sha256": hashlib.sha256(canonical(obj)).hexdigest(),
        "analysis_schema_version": "ANALYSIS_IMPLEMENTATION_PACKAGE_V1",
        "analysis_mode": "SIMULATED_ANALYSIS",
        "pg01": readback,
        "production_authority": False, "handoff_allowed": False,
        "downstream_authorized": False, "pg01_consumer_verified": False,
    }
    target = directory / "state.json"
    data = canonical(state)
    if target.exists() or target.is_symlink():
        if target.is_symlink() or target.read_bytes() != data:
            block("INTAKE_STATE_DRIFT")
    else:
        with target.open("xb") as out:
            out.write(data)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--request-id", required=True)
    args = parser.parse_args()
    try:
        result = accept(args.root, args.request_id)
    except (IntakeBlocked, OSError) as exc:
        print("INTAKE_BLOCKED:" + (str(exc) if isinstance(exc, IntakeBlocked) else "IO_ERROR"))
        return 1
    print("INTAKE_ACCEPTED " + result["request_id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
