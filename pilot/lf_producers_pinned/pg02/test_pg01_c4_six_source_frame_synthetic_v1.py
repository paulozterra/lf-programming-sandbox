#!/usr/bin/env python3
"""PG-01_C4 synthetic positive composition and strict fail-closed boundaries.

This is *not* an authority check: the existing V3 preflight is the source of
truth and deliberately returns verified=False until six trusted readbacks exist.
"""
import copy
import hashlib
import json

from pg01_technical_frame_v3_candidate_v1 import CONTRACT, preflight

EXPECTED_SIX = (
    "standards_catalog_version", "l3_manifest", "control_qualification",
    "d15_architecture", "d17_optimization_policy",
    "d17_approved_request_budget",
)
assert tuple(CONTRACT["required_evidence"]) == EXPECTED_SIX
assert CONTRACT["rules"]["all_six_must_verify"] is True
assert CONTRACT["rules"]["activation"] is False

# Entirely invented fixture values are visibly synthetic, never production refs.
binding = {
    "context_id": "SYNTHETIC-CONTEXT-ID",
    "context_sha256": "a" * 64,
    "binding_key_sha256": "b" * 64,
    "receipt_record_id": "SYNTHETIC-RECEIPT-ID",
    "target_repo": "fixture/example-product",
    "target_head_sha": "1" * 40,
}
assert set(binding) == set(CONTRACT["frame_binding"])
rows = {
    name: {
        "source_ref": "synthetic://" + name,
        "source_digest_sha256": hashlib.sha256(name.encode()).hexdigest(),
        "authority_receipt_ref": "synthetic://receipt/" + name,
        "verified_by": "INDEPENDENT_TRUSTED_READBACK",
        "currentness": "CURRENT",
        "target_repo": binding["target_repo"],
        "target_head_sha": binding["target_head_sha"],
    }
    for name in EXPECTED_SIX
}

# A complete candidate composes a stable hash while ALWAYS withholding verified
# because these source claims are not proven against real authoritative readers.
result = preflight(binding, rows)
assert result["reason"] == "PG01_V3_PROVENANCE_UNAVAILABLE", result
assert result["verified"] is False
assert result["hash_note"] == "PYTHON_CANDIDATE_NOT_PG_JSONB_DIGEST"
expected_hash = hashlib.sha256(json.dumps(
    {"binding": binding, "evidence": rows}, sort_keys=True,
    separators=(",", ":"),
).encode()).hexdigest()
assert result["candidate_frame_sha256"] == expected_hash
assert preflight(copy.deepcopy(binding), dict(reversed(list(rows.items())))) == result

# Six source-by-source omissions and six independent stale/unauthenticated
# failures. The destination must not infer an omitted D15, L3 or D17 binding.
for name in EXPECTED_SIX:
    missing = copy.deepcopy(rows)
    del missing[name]
    assert preflight(binding, missing) == {
        "verified": False, "reason": "PG01_V3_EVIDENCE_MISSING",
        "evidence": name,
    }
    stale = copy.deepcopy(rows)
    stale[name]["currentness"] = "STALE"
    assert preflight(binding, stale) == {
        "verified": False, "reason": "PG01_V3_EVIDENCE_NOT_VERIFIED",
        "evidence": name,
    }
    wrong_repo = copy.deepcopy(rows)
    wrong_repo[name]["target_repo"] = "fixture/other-product"
    assert preflight(binding, wrong_repo) == {
        "verified": False, "reason": "PG01_V3_TARGET_DRIFT",
        "evidence": name,
    }

# Synthetic L3 must be project-bound, and D15 must match the exact target
# commit; the immutable binding digest is mandatory even in the dry-run.
bad = copy.deepcopy(binding)
bad["context_sha256"] = "not-a-digest"
assert preflight(bad, rows)["reason"] == "PG01_V3_CONTEXT_DIGEST_INVALID"

print(
    "PASS_PG01_C4_SIX_SOURCE_SYNTHETIC "
    "four_core=4 optimization=1 budget=1 "
    "candidate_positive=1 six_missing=6 six_stale=6 "
    "six_target_drift=6 invalid_context=1 "
    "deterministic=true authority=NONE pg01_runtime_verified=false"
)
