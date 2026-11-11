# A1 semantic producer / reviewer protocol — SOURCE_CANDIDATE

Purpose: model-provider-neutral semantic reasoning protocol for A1. It does not create a model call, verify provider identity, or authorize downstream actions. No literal keyword dictionary.



### Mandatory A1 route identity (no Profile Updater crossover)

Every A1 Native authoring handoff MUST bind the versioned source contract
`skills/programming_analysis/steps/a1/contracts/a1_native_semantic_route_v1.json`:
- contract_code: `A1_NATIVE_SEMANTIC_ROUTE_V1`
- route_code: `PROGRAMMING_ANALYSIS_LF/A1/SEMANTIC_NATIVE_AUTHORING`
- owner_skill_code: `PROGRAMMING_ANALYSIS_LF`
- owner_step_code: `A1`
- runtime_operation_code: null (source-only authoring)
- A1 output: `A1_INTERNAL_STEP_CANDIDATE_RESULT_V1` with canonical payload `REQUEST_CONTEXT_V1` and separate semantic candidate annex.
- A2 internal handoff: `A1_A2_SEMANTIC_TRANSPORT_CANDIDATE_V1`, NOT an autonomous A2 run.

The Profile Updater's `ACTUALIZACION_PERFIL_LF`,
`LF_PE10_V02_SAME_CHAT_NATIVE_HANDOFF_V1`,
`LF_PE10_V02_SAME_CHAT_RAW_CAPTURE_V1`, and its profile-plan bindings
are **precedents, NOT callable routes for A1**. Reject any re-signed
handoff/capture carrying these fields or wrong owner/route identifiers.
A matched executor mode (GPT_NATIVE/CLAUDE_NATIVE) is NOT sufficient
to identify an A1 request. The contract binding must match as well.

No fallback to Profile Updater, Llama, REMOTE_API, `EJECUCION_PERFIL_LF`,
or `EJECUCION_SKILL_LF`. This boundary remains fixed while A1's
semantic reasoning and the A1→A2 data schema can evolve independently.

## Native executor transport — canonical mode selection

The semantic author executes through the **existing native conversation**, with
executor_mode chosen by its calling context: GPT_NATIVE / OPENAI_CHATGPT_NATIVE /
CHATGPT_CURRENT_CONVERSATION or CLAUDE_NATIVE / ANTHROPIC_CLAUDE_NATIVE /
CLAUDE_CURRENT_CONVERSATION. These are modes of the same LF generic Native
pattern, **not new model engines**. Never create or call LlamaHTTPClient or any
REMOTE_API alternative for this A1 implementation.

The source-only A1 transport adapter freezes prompt bytes, protocol/schema
hashes and mode/provider pairs; the native conversation authors raw candidate
content and a separate reviewer must review it. The adapter itself does NOT
invoke either GPT or Claude, authenticate author identity, prove independent
review, open an execution, or authorize the next governed stage.

Cross-provider captures are rejected. A source-bound candidate is
SOURCE_BOUND_NATIVE_CHAT_RAW_UNATTESTED, even if its content later passes
local deterministic validation. A callback supplied in tests is never
evidence of a real native execution.

## Semantic producer
Input: original user sentence (unaltered), authenticated business context from caller, schema intent_analysis_candidate_v1.schema.json, and optionally approved prior-scope references.
Output: ONLY JSON satisfying that schema. Do not hardcode catalog entries to login, auth, UI, or example phrases.

Interpret the requested operation by meaning rather than verb match. Distinguish IMPLEMENT (delivery of an as-yet-unverified capability), CREATE (explicit create new artifact), MODIFY, REBUILD, REPAIR, REUSE (user requires using an existing artifact without implying new creation or modification), REMOVE and REVIEW. A stated assumption that code does not exist is a user hypothesis, NOT verified repository state.
When an input asks to use an existing artifact and forbids creating another, emit REUSE, preserve the literal prohibition in explicit_constraints, and bind a full NEGATION evidence span. If the function of that artifact is unspecified, set canonical_capability=UNKNOWN with a MATERIAL ambiguity and keep the request at REQUIRES_DECISION. The legacy REQUEST_CONTEXT_V1 declared_intent_kind remains UNKNOWN for REUSE, not CREATE or EVOLVE; do not auto-promote it into A2.
When the user requests merely entering, opening or navigating to a destination without expressly specifying authentication, do not silently turn the desired capability into credential authentication. Keep the broader access/navigation capability and a MATERIAL ambiguity about the mechanism until prior definitions or the user resolve it. Security/session reviews may be research questions, not declared requirements. This is a generic semantic rule, not a keyword-triggered classification.
Identify artifact kind and functional archetype separately. Infer canonical capability as a proposal, not an authoritative registry result. Separate business/actor scope from artifact name. Never manufacture repository IDs or source authorities.
Keep raw mentions solely for subsequent inventory lookup. Provide exact verbatim text spans with Python code-point start/end offsets for OPERATION, ARTIFACT, CAPABILITY, and actor/assumption when applicable. An inferential capability may be supported by a whole descriptive clause, not necessarily a keyword.
Preserve explicitly stated restrictions verbatim as constraints, each literally present in the user text and supported by a CONSTRAINT or NEGATION evidence span. Do not interpret an explicitly negated verb as a positive requested operation. Capture negation scope and mutually incompatible requests as material ambiguities when not resolvable from the input.
List dimensions to investigate based on capabilities and impacts, not on a screen-specific fixed checklist. The fact that the user did not specify a policy is a reason to SEARCH existing definitions, never proof that the policy is absent.
Do not mark code NEW, deployed, verified, CURRENT, READY, authority SUFFICIENT, or materially LOW without source resolution.
If operation or target is genuinely unclear, use UNKNOWN/material_ambiguities; do not invent certainty. Context may be inferred but source/authority remains candidate.

## Independent semantic reviewer
Read original text and proposed candidate independently; do not trust the producer's explanation or self-declared confidence.
Check semantic fidelity including negation, request type (implement vs create from zero), actor context, artifact-vs-capability, expressed constraints, invented requirements or repository truth, and whether proposed missing dimensions are research tasks rather than claims of missing policies.
A valid substring and numeric offset establish only text provenance, NOT correctness of interpretation.
Return verdict PASS/FAIL and issues. Separate deterministic host code binds the reviewer decision to candidate SHA-256; the model must NOT invent the digest or its own verified identity.
FAIL on unsupported interpretations, ignored material ambiguity, negation drift, or materially altered scope. No fabricated review PASS if no actual reviewer call occurred.

## Safety and qualifications
Two callback functions may be different objects and still be controlled by the same actor. Therefore reviewer identity, model independence, and external attestation remain FALSE until a governed receipt verifies them.
The nine A2 depth signals are evidence-derived from appropriate authorities; hints from A1 do not replace or auto-grade them.
QA corpus must include paraphrases, implied intent without keyword, unrelated archetypes, negation, mixed operations, previously documented but not implemented work, and insufficient requests.
Do not touch Router, RUN, parent/child operations, Supabase, source-of-truth rules or A3/A9 in this development phase.