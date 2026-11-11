"""PG-12_C4 source-only persistence/readback intent and comparison contract.

No database writes, reads or signatures. In particular, no caller-provided
'stored' or 'reloaded' values can make an actual persistence claim true.
"""
import hashlib
import json
from copy import deepcopy

SCHEMA = "PG12_C3_CHECK_RESULTS_LINK_CANDIDATE_V1"

class PG12C4Blocked(ValueError):
    pass

def fail(reason):
    raise PG12C4Blocked(reason)

def digest(obj):
    return hashlib.sha256(json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")).hexdigest()

def ref(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()

def prepare_pg12_c4(*, pg12_c3, storage_contract_ref,
                    authorized_writer_ref, readback_contract_ref,
                    record_key_ref, expected_store_namespace):
    """Freeze a proposed persistence payload and typed expected readback.

    Only emits a request to a future governed writer/readback verifier.
    Never returns persisted=true or supplies a synthetic storage receipt.
    """
    if not isinstance(pg12_c3, dict) or pg12_c3.get("schema_version") != SCHEMA:
        fail("PG12_C4_UPSTREAM_SCHEMA_INVALID")
    sha = digest({k: v for k, v in pg12_c3.items() if k != "candidate_sha256"})
    if sha != pg12_c3.get("candidate_sha256"):
        fail("PG12_C4_UPSTREAM_DIGEST_INVALID")
    if (pg12_c3.get("status") != "CANDIDATE_NOT_ADMITTED"
        or pg12_c3.get("pg12_c3_pass") is not False
        or pg12_c3.get("pg12_c3_admitted") is not False
        or pg12_c3.get("handoff_allowed") is not False
        or pg12_c3.get("production_authority") is not False
        or pg12_c3.get("all_check_results_verified") is not False):
        fail("PG12_C4_PREMATURE_AUTHORITY")
    if not all(ref(x) for x in (
            storage_contract_ref, authorized_writer_ref,
            readback_contract_ref, record_key_ref, expected_store_namespace)):
        fail("PG12_C4_PERSISTENCE_REFERENCE_INVALID")
    identity = pg12_c3.get("source_pg12_c1_sha256")
    if not isinstance(identity, str) or len(identity) != 64 or any(
        c not in "0123456789abcdef" for c in identity):
        fail("PG12_C4_IDENTITY_INVALID")
    checks = pg12_c3.get("check_results")
    if not isinstance(checks, list) or len(checks) != 13:
        fail("PG12_C4_CHECK_COVERAGE_INVALID")
    seen = set()
    for check in checks:
        if not isinstance(check, dict):
            fail("PG12_C4_CHECK_ENTRY_INVALID")
        code = check.get("checkpoint_code")
        if not ref(code) or code in seen or check.get("candidate_identity_sha256") != identity:
            fail("PG12_C4_CHECK_IDENTITY_DRIFT")
        seen.add(code)
        if (check.get("result_verified") is not False
            or check.get("receipt_authenticated") is not False
            or check.get("check_pass_qualified") is not False):
            fail("PG12_C4_UNTRUSTED_CHECK_AUTHORITY")
    expected = {f"PG-08_C{i}" for i in range(1, 9)} | {
        f"PG-11_C{i}" for i in range(1, 6)}
    if seen != expected:
        fail("PG12_C4_CHECK_SET_DRIFT")
    payload = {
        "source_pg12_c3_sha256": sha,
        "source_pg12_c1_sha256": identity,
        "source_pg12_c2_sha256": pg12_c3.get("source_pg12_c2_sha256"),
        "candidate_check_results": deepcopy(checks),
        "target_schema": "PG12_C4_PERSISTENCE_SUBJECT_CANDIDATE_V1",
    }
    payload_sha = digest(payload)
    result = {
        "schema_version": "PG12_C4_PERSISTENCE_READBACK_REQUEST_CANDIDATE_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "source_pg12_c3_sha256": sha,
        "source_pg12_c1_sha256": identity,
        "storage_contract_ref_reported": storage_contract_ref,
        "authorized_writer_ref_reported": authorized_writer_ref,
        "readback_contract_ref_reported": readback_contract_ref,
        "record_key_ref_reported": record_key_ref,
        "expected_store_namespace_reported": expected_store_namespace,
        "payload_candidate": payload,
        "payload_candidate_sha256": payload_sha,
        "readback_comparison_plan": {
            "record_key_expected": record_key_ref,
            "payload_sha256_expected": payload_sha,
            "candidate_identity_sha256_expected": identity,
            "check_count_expected": len(checks),
            "require_authenticated_writer_receipt": True,
            "require_independent_storage_readback": True,
            "require_exact_stored_payload_digest": True,
            "require_exact_candidate_identity": True,
        },
        "writer_contract_authenticated": False,
        "write_attempted": False,
        "persisted": False,
        "writer_receipt_ref": None,
        "storage_readback_attempted": False,
        "readback_payload_sha256": None,
        "readback_matched": False,
        "readback_authenticated": False,
        "pg12_c4_pass": False,
        "pg12_c4_admitted": False,
        "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "GOVERNED_WRITER_RECEIPT_AND_INDEPENDENT_STORAGE_READBACK",
    }
    result["candidate_sha256"] = digest(result)
    return deepcopy(result)
