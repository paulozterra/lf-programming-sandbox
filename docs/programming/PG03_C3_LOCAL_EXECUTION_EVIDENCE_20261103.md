# PG-03 — Execution evidence and exact limit (2026-11-03)

Scope: technical route PG-03_C3 and prospective C1→C2→C3. No Supabase writes, no merge, no modification to upstream repository.

## Attempt at actual cross-repository execution

A `git ls-remote https://github.com/paulozterra/lf-programming-sandbox.git HEAD` from the local execution container failed:
```
fatal: unable to access 'https://github.com/paulozterra/lf-programming-sandbox.git/': Could not resolve host: github.com
```
Therefore the cross-repo Python probe `standards/tools/pg03_cross_repo_chain_probe_v1.py` could not be exercised with its required pinned upstream checkout. **Do not mark C1→C2→C3 as CHAIN_PASS.**

## Actually executed locally

Available files: `/mnt/data/pg03_c3_verify/pg03_strategy_v1.py` and `test_pg03_strategy_v1.py`, previous local copy of original C3 with scope guard patch applied. Files SHA-256:
- strategy: `9088c3fa3b2f4d8010c8afb3d6e2d53e5534b141633975f32b292e235f7c2571`
- test: `a30af569413d29d6ddd60525d2b138559c96d36f83bee20dc3cac5ea52f7e9bd`

```sh
cd /mnt/data/pg03_c3_verify
python3 test_pg03_strategy_v1.py
# PG03_C3_STRATEGY_CANDIDATE_PASS positive=1 deterministic=1 negatives=11 authority=0
```

Additional inline Python replay imported the patched strategy, invoked synthetic valid classification+stack source+partition policy, verified exact active domains, stack commit, determinism and authority=false, then tested duplicate scopes, null scope, missing stack status, non-ready scope:

```
LOCAL_C3_POSITIVE_SYNTHETIC_PASS=true deterministic=true authority=false
LOCAL_C3_NEGATIVE_PASS=scope_duplicate
LOCAL_C3_NEGATIVE_PASS=scope_null
LOCAL_C3_NEGATIVE_PASS=missing_stack
LOCAL_C3_NEGATIVE_PASS=nonready_scope
C2_RECEIPT_BINDING_IN_C3=false
FULL_C1_C2_C3_CHAIN_EXECUTED=false
```

These are **C3 local tests**. Synthetic stack shape was supplied in the inline replay; `resolve_stack()` and `select_and_assemble()` were NOT jointly executed in the same process.

## Existing CI result, separate from cross-repo chain

Sandbox #19 run [41686925349](https://github.com/paulozterra/lf-programming-sandbox/actions/runs/41686925349) was read back with 5 completed SUCCESS jobs on commit `b57f709d3b1e47f7a6bf3cceae9316b123252b9c`. That CI does not invoke the opt-in cross-repo probe.

## Next admissible technical execution

In a local or CI environment where both checkouts are available, pin sandbox to the reviewed commit and upstream to `1a3dfe22a8ceaed4306a719e9391694d122342a2`, then run:

```sh
LF_PG03_UPSTREAM_REPO=/absolute/path/to/claude-persona-lf-patch python3 standards/tools/pg03_cross_repo_chain_probe_v1.py
```

The probe itself reports that C3 does not enforce C2 receipt binding; even a function-chain positive run must be qualified as `SYNTHETIC_FUNCTION_CHAIN`, not product/runtime integration. Future implementation should reuse the existing #3519 receipt validator and source binding, not introduce a second selector or strategy.

**State:** `PG03_C3_LOCAL_PASS / CROSS_REPO_CHAIN_NOT_EXECUTED / C2_C3_ENFORCEMENT_UNVERIFIED`.
