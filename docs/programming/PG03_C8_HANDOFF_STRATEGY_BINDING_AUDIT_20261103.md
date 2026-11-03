# PG-03_C8 — Handoff boundary strategy-binding audit (2026-11-03)

**Scope:** technical PG-03_C8, not Supabase operational statuses. Sandbox-only documentation; no upstream edit, merge or authority changes.

## Existing implementation (reused)

- PR #3509: `cristhianlujan/claude-persona-lf-patch`, HEAD `6067db67e39cd0d29fdda7205b206f250f7ed8bf`, DRAFT.
- Original `pg03_handoff_boundary_v1.py` Git blob `d824f3c61021ada7ebb6aec2e6b1fa984f69ec57`.
- Original `test_pg03_handoff_boundary_v1.py` Git blob `0cf6223f0494805b0177c4737e5fc91a2e027925`.
- Current tests have 15 cases; the PR describes these as unverified independently. No test execution of C8 was performed in this work segment.

## Verified source-level gap

`prepare_pg04_handoff()` checks only that every solution's `strategy_ref` is non-empty. Its original fixture sets `strategy_ref='pg03:strategy'` while the strategy's `candidate_sha256='sha-test'`. A distinct non-empty strategy ref is not required to match the strategy bound through C6. In addition, C8 checks `source_strategy_sha256==strategy.candidate_sha256` but never recomputes the digest of the strategy object.

**Risk:** a self-consistent but stale/forged strategy pointer could be embedded in the resulting PG-04 candidate. Does **not** establish operational exploitation, since `dispatch_allowed=false` and `handoff_allowed=false`.

## Minimal patch prepared

Sandbox file `docs/programming/patches/PG03_C8_HANDOFF_STRATEGY_REF_DIGEST_20261103.patch`:

1. Recomputes `candidate_sha256` over canonical C3 JSON excluding the digest field, rejecting `STRATEGY_DIGEST_MISMATCH`.
2. Requires `row['strategy_ref']==strategy['candidate_sha256']` for every solution, rejecting `PARTITION_STRATEGY_REF_DRIFT`.
3. Updates C8 test fixture to use a real synthetic SHA and binds both solution rows to it; adds two regression cases (wrong ref, mutated strategy with old digest).
4. Maintains owner assignment, DAG validation, zero authority and existing PG-04 partition contract.

**Verification:** all patch hunk counts and original-line contexts were checked against both files returned by GitHub at the stated HEAD: `PATCH_STRUCTURAL_PASS`. **No C8 Python test run or CI was performed** in this segment. Therefore status is `C8_SOURCE_GAP_IDENTIFIED / PATCH_STRUCTURALLY_VERIFIED / C8_REGRESSION_NOT_EXECUTED`, not `C8_TECHNICAL_PASS`.

## Relationship to prior PG-03 work

- PG-03_C1–C7 source-only/local checks do not imply integrated or productive checkpoint closure.
- The bridge C1→C2→C3 is still not jointly executed and mandatory binding of C2 receipt to C3 is not shown.
- Earlier C4/C6/C7 candidate_sha256 hardenings have been prepared as local patches in this sandbox, not installed in upstream.
- Exact-HEAD CI and independent review are required before promotion.

**Next:** execute existing 15 C8 tests and the extended 17-case suite in a local isolated checkout, then audit C9 original without creating a new review engine.

No Supabase writes, no modifications to Cristhian repository.
