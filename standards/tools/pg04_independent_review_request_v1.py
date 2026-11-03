"""PG-04_C7 source-only review-request preflight for existing INDEPENDENT_ASSURANCE.

Does not dispatch a reviewer, fetch evidence, attest provenance, or grant authority.
"""
import hashlib
import json
import re

SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")

class ReviewRequestBlocked(ValueError):
    pass

def _sha(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()).hexdigest()

def _block(reason):
    raise ReviewRequestBlocked(reason)

def prepare_partition_review_request(*, partition, sources, producer_execution_id):
    """Freeze the exact candidate and its caller-supplied source manifest.

    The returned packet is a REVIEW PREPARATION, not an assurance receipt.
    """
    if not isinstance(partition, dict) or (
        partition.get("schema_version") != "PG04_SEMANTIC_PARTITION_CANDIDATE_V1"
        or partition.get("status") != "CANDIDATE_NOT_ADMITTED"
        or partition.get("production_authority") is not False
        or partition.get("dispatch_allowed") is not False
        or partition.get("handoff_allowed") is not False
        or partition.get("semantic_judge_executed") is not False
        or partition.get("source_authenticity") != "UNVERIFIED"
    ):
        _block("PARTITION_NOT_UNTRUSTED_CANDIDATE")
    expected = partition.get("candidate_sha256")
    if not isinstance(expected, str) or not SHA256.fullmatch(expected):
        _block("PARTITION_DIGEST_INVALID")
    unsigned = {k: v for k, v in partition.items() if k != "candidate_sha256"}
    if _sha(unsigned) != expected:
        _block("PARTITION_DIGEST_DRIFT")
    strategy_sha = partition.get("strategy_sha256")
    if not isinstance(strategy_sha, str) or not SHA256.fullmatch(strategy_sha):
        _block("PARTITION_STRATEGY_SHA_INVALID")
    rows = partition.get("solutions")
    if not isinstance(rows, list) or not rows:
        _block("PARTITION_SOLUTIONS_MISSING")
    if any(not isinstance(row, dict) or row.get("strategy_ref") != strategy_sha
           or not isinstance(row.get("id"), str) or not row["id"].strip()
           for row in rows):
        _block("PARTITION_SOLUTION_BINDING_DRIFT")
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        _block("PARTITION_SOLUTION_ID_DUPLICATE")
    required = (
        "a9_package", "pg03_strategy", "pg04_partition_contract",
        "outcome_registry", "typed_obligations"
    )
    if not isinstance(sources, dict) or set(sources) != set(required) | {"source_head_sha"}:
        _block("REVIEW_SOURCE_MANIFEST_INCOMPLETE")
    head = sources["source_head_sha"]
    if not isinstance(head, str) or not GIT_SHA.fullmatch(head):
        _block("REVIEW_SOURCE_HEAD_INVALID")
    for key in required:
        entry = sources[key]
        if not isinstance(entry, dict) or set(entry) != {"ref", "sha256"} or (
            not isinstance(entry["ref"], str) or not entry["ref"].strip()
            or not isinstance(entry["sha256"], str)
            or not SHA256.fullmatch(entry["sha256"])
        ):
            _block("REVIEW_SOURCE_BINDING_INVALID")
    if sources["pg03_strategy"]["sha256"] != strategy_sha:
        _block("REVIEW_STRATEGY_SOURCE_DRIFT")
    if not isinstance(producer_execution_id, str) or not producer_execution_id.strip():
        _block("PRODUCER_ID_MISSING")
    criteria = [
        "A9_REQUIREMENT_AND_ACCEPTANCE_BIDIRECTIONAL_COVERAGE",
        "SOURCE_OUTCOME_FIDELITY_AND_NO_FALSE_SEMANTIC_MERGE",
        "COIMPLEMENT_JUSTIFICATION_AND_ATOMICITY",
        "PARTITION_DEPENDENCY_AND_RISK_BOUNDARIES",
        "IMPLEMENTATION_STATE_AS_IS_DELTA_OR_REUSE",
        "SHARED_CONTRACT_REFS_NOT_INLINE_COPIES",
        "WRITE_SCOPE_AND_MATERIAL_CONTEXT_PRESERVATION",
        "INDEPENDENT_REVIEWER_AND_CURRENT_SOURCE_ATTESTATION",
    ]
    packet = {
        "schema_version": "PG04_C7_PARTITION_REVIEW_REQUEST_CANDIDATE_V1",
        "subject_type": "PG04_SOLUTION_PARTITION_CANDIDATE",
        "subject_sha256": _sha(partition),
        "candidate_sha256": expected,
        "source_manifest_sha256": _sha(sources),
        "strategy_sha256": strategy_sha,
        "source_manifest": sources,
        "solution_ids": sorted(ids),
        "producer_execution_id": producer_execution_id,
        "reviewer_execution_id": None,
        "independent_review_capability": "INDEPENDENT_ASSURANCE",
        "intended_review_operation": "REVISION_INDEPENDIENTE_ESTRATEGIA_LF",
        "required_assertions": criteria,
        "status": "CANDIDATE_NOT_ADMITTED",
        "semantic_judge_executed": False,
        "source_readback_verified": False,
        "ledger_receipt_verified": False,
        "reviewer_independence_attested": False,
        "review_execution_allowed": False,
        "production_authority": False,
        "handoff_allowed": False,
        "reason": "AUTHENTIC_A9_AND_INDEPENDENT_REVIEW_BINDING_REQUIRED",
    }
    packet["request_sha256"] = _sha(packet)
    return packet
