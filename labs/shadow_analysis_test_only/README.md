# SHADOW_ANALYSIS / TEST_ONLY / NO_AUTHORITY

**Isolated diagnostic in paulozterra/lf-programming-sandbox.** This is NOT the original Analysis skill, not a clone of its production runtime and not operational A2–A9. Do not confuse it with a full A9 producer. The official sources in cristhianlujan/claude-persona-lf-patch remain read-only and untouched.

Source references:
- skills/programming_analysis/SKILL.md (single A1–A15 skill)
- skills/programming_analysis/contracts/analysis_skill_manifest_v1.json
- sandbox/lf_contract_gate_test/programming_agent_four_stage/wave1_boundary_contracts/analysis_procedure_v1.json
- private.lf_decision_context_asof_v1.context_payload (user-exported JSON, no direct SQL writes)

This first stage uses only fields *already present* in an exported A9 snapshot. When scope_readiness references Fxx and material_front_coverage lists Fxx, it proposes a **derived** matrix candidate. The source matrix is never overwritten. A6 typed fields, PG04 obligations, authentic receipts and authority remain BLOCKED.

Usage:
```sh
python shadow_a9_replay.py context_payload.json --output shadow_result.json
python -m unittest -v test_shadow_a9_replay.py
```

Outputs must retain: `simulation_only=true`, `production_authority=false`, `pg01_admitted=false`, `handoff_allowed=false`.

**Next independent increments**: pin the original A1 code in the sandbox, connect read-only source adapters, implement A2–A9 exploratory processors with explicit missing-evidence codes, and feed diagnostic outputs into PG01 without declaring authenticity. This is NOT authority to change or deploy Analysis, Supabase, Router, or Product.
