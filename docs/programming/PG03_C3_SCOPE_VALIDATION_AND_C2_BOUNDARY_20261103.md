# PG-03_C3 — Exact-source scope validation and C2→C3 boundary · 2026-11-03

**Mode:** TECHNICAL / local reproduction; no upstream modification, no Supabase writes, no merge, no operational authority.

## Pinned sources and prior-work check

- Existing C3 owner implementation: `cristhianlujan/claude-persona-lf-patch` PR #3498, HEAD `1a3dfe22a8ceaed4306a719e9391694d122342a2`.
- Existing C3 source: `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_strategy_v1.py`, Git blob SHA `4bbebe3d4d7cd7b48645b3033366122b0c8183d1`.
- Existing test: `test_pg03_strategy_v1.py`, Git blob SHA `469365d6b31c029d9809c0a6062aa82a6e55e018`.
- Existing C2: sandbox #19, `standards/tools/skills.py::select_and_assemble`, HEAD `3bdedf43575cde773e1a958bd0fcc75a3fda1dae`, CI #41682026113 5/5 SUCCESS.
- Searched existing C3 and PG-03 PRs before preparing fix. Do not create second C3 strategy component.

## Patch and reproducible local proof

The minimal upstream patch is `docs/programming/patches/PG03_C3_SCOPE_ID_GUARD_20261103.patch`, commit `4717cbb7e00a8a417638e74254b867fc4784d765`. It adds validation to original `prepare_strategy()` after READY-state check and before the existing stack check; introduces 5 regressions. The patch was **not applied to upstream**.

The two original source files were reconstructed locally from the GitHub connector response. Running `git hash-object` on each yielded **exactly** the existing Git blob SHA listed above, thus confirming byte-for-byte identity before patch.

Execution (local Python checkout copy of the two exact source blobs):
```sh
python test_pg03_strategy_v1.py
# PG03_C3_STRATEGY_CANDIDATE_PASS positive=1 deterministic=1 negatives=6 authority=0
# Apply the minimal patch to the two files.
python test_pg03_strategy_v1.py
# PG03_C3_STRATEGY_CANDIDATE_PASS positive=1 deterministic=1 negatives=11 authority=0
```

New cases: duplicate IDs → `SCOPE_IDS_DUPLICATED`; empty string, `None`, integer, or mixed valid/`None` → `SCOPE_IDS_INVALID`. Patch context was checked against pinned GitHub source and both hunks matched (`PATCH_STRUCTURAL_PASS`).

**Result:** `PG03_C3_SCOPE_GUARD_LOCAL_PASS`, **not** owner-repository CI PASS or official checkpoint closure.

## C2→C3 compatibility observation

C2 `select_and_assemble` returns a context and a receipt containing `selection_status=CANDIDATE_NOT_ADMITTED`, `production_authority=false`, and `pg02_source_verified=false`. C3 `prepare_strategy` expects a different `stack_evidence` envelope with `status=CANDIDATE_NOT_ADMITTED`, `authority=false`, `commit_sha`, and `sources`. A synthetic receipt retaining the published C2 receipt fields was supplied directly as C3 `stack_evidence`; the original C3 function blocked:

```text
PG03_C2_C3_DIRECT_RECEIPT_BOUNDARY_PASS reason=STACK_EVIDENCE_INVALID direct_compatible=false dispatch_allowed=false
```

**Meaning:** the failure is correct fail-closed behavior, not a reason to create a second strategy engine. A separate, explicitly source-bound contract mapping is needed to combine authenticated PG-02/C1 stack provenance with the Skills receipt before using C3. It must not infer authority, source SHA, or commit from caller-provided C2 receipt. Search for an already implemented binding before writing one.

## Next

1. Preserve patch in sandbox; apply upstream only by an agreed owner-controlled integration route.
2. Find the existing PG-03_C1 / PG-02 and C2 skill-receipt binding and establish the exact C2→C3 contract without copying C3.
3. Run exact-HEAD CI in the owning repository when that integration is approved.
4. Keep checkpoint `PARCIAL`; production authority and official closure outside current technical mode.
