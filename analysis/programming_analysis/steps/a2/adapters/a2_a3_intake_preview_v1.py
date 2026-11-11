"""A2→A3 preview adapter, SOURCE-ONLY. Does not dispatch A3 or attest a judge.

Consumes A2's existing proposed Golden v0.3 handoff without altering the
canonical A3 input contracts. Every returned payload is untrusted draft data.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import importlib.util
from pathlib import Path
from typing import Any

SCHEMA = 'PROGRAMMING_ANALYSIS_A2_TO_A3_PREVIEW_V1'
A3_SOURCE = ('sandbox/lf_contract_gate_test/programming_agent_four_stage/'
             'wave1_boundary_contracts/analysis_targeted_evidence_contract_v1.json')
A3_BLOB = '97d06e88b963690202424a2936ae2b7bf597cea7'
A2_BLOB = '0f07d3603c1bf3e4d2a4b9de5d6c3a3968bb4051'
CATALOG_SHA = '67c235e0b855086176a5f6b0f348095bdb96f711187c5772fd48987d2d1ef6ba'
SIGNALS = {'materiality_level','scope_bounded','authority_state',
 'reversibility_state','currentness_decision','material_contradiction',
 'known_cross_scope_impact','unresolved_material_signal_count',
 'required_specialist_count'}

def digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def blocked(code: str) -> dict:
    return {'schema_version':SCHEMA,'status':'BLOCKED','blocking_codes':[code],
      'a3_input_preview':None,'a3_resolution_plan_preview':None,
      'preview_digest_sha256':None,'source_authenticated':False,
      'judge_verified':False,'run_verified':False,'dispatch_attempted':False,
      'a3_allowed':False,'next_step':None,'no_write_performed':True}

def prepare_preview(a1_result:Any,a2_result:Any,signal_bundle:Any,golden:Any) -> dict:
    if not all(isinstance(x,dict) for x in (a1_result,a2_result,signal_bundle,golden)):
        return blocked('A2_A3_TYPED_INPUT_REQUIRED')
    a1_mode = a1_result.get('interpretation_state')
    if (a1_result.get('schema_version')!='A1_INTERNAL_STEP_CANDIDATE_RESULT_V1'
       or a1_result.get('status')!='VALID_OUTPUT'
       or a1_result.get('semantic_review_required') is not False
       or a1_mode not in ('PRESTRUCTURED_UNATTESTED','SEMANTIC_REVIEWED_CANDIDATE')
       or not isinstance(a1_result.get('payload'),dict)):
        return blocked('A2_A3_A1_NOT_ELIGIBLE')
    business=a1_result.get('business')
    if not isinstance(business,str) or not 2<=len(business)<=32 or business.strip()!=business:
        return blocked('A2_A3_A1_BUSINESS_INVALID')
    # This preview belongs to PROGRAMMING_ANALYSIS_LF, not SALY admission.
    if business != 'LF':
        return blocked('A2_A3_BUSINESS_NOT_ENABLED_FOR_SKILL')
    if (a2_result.get('schema_version')!='A2_INTERNAL_STEP_CANDIDATE_RESULT_V1'
        or a2_result.get('status') not in ('CANDIDATE_UNATTESTED','NEED_MORE_EVIDENCE')
        or signal_bundle.get('schema_version')!='ANALYSIS_A2_TYPED_SIGNAL_CANDIDATE_V1'):
        return blocked('A2_A3_A2_CLASSIFICATION_UNAVAILABLE')
    if business != a2_result.get('business') or business!=signal_bundle.get('business'):
        return blocked('A2_A3_BUSINESS_CROSS_SCOPE')
    if a1_mode == 'SEMANTIC_REVIEWED_CANDIDATE':
        # Integrity-only guard; cannot attest native semantic judge identity.
        guard_path = Path(__file__).resolve().with_name('a2_semantic_input_integrity_v1.py')
        guard_spec = importlib.util.spec_from_file_location('a2_semantic_binding_guard', guard_path)
        if guard_spec is None or guard_spec.loader is None:
            return blocked('A2_A3_SEMANTIC_GUARD_UNAVAILABLE')
        guard_module = importlib.util.module_from_spec(guard_spec)
        try:
            guard_spec.loader.exec_module(guard_module)
            check = guard_module.check(a1_result,a2_result,signal_bundle)
        except (OSError, ValueError, TypeError, AttributeError):
            return blocked('A2_A3_SEMANTIC_GUARD_UNAVAILABLE')
        if check.get('status') != 'CHECKED_SOURCE_ONLY':
            return blocked('A2_A3_SEMANTIC_BINDING_INVALID')
    if any(a2_result.get(k) is True for k in ('source_attested','independent_judge_verified',
                                             'operationally_integrated','effects_executed')) or a2_result.get('next_step') is not None:
        return blocked('A2_A3_A2_FALSE_AUTHORITY')
    c=a2_result.get('classification')
    if not isinstance(c,dict) or c.get('schema_version')!='ANALYSIS_CHANGE_CLASSIFICATION_V1':
        return blocked('A2_A3_CANONICAL_CLASSIFICATION_INVALID')
    context=a1_result['payload']
    if c.get('target_ref') not in context.get('target_hints',[]):
        return blocked('A2_A3_TARGET_NOT_IN_A1')
    if (c.get('target_ref')!=signal_bundle.get('target_ref') or
        c.get('target_granularity')!=signal_bundle.get('target_granularity') or
        c.get('change_type')!=signal_bundle.get('change_type') or
        c.get('nested_parent_ref')!=signal_bundle.get('nested_parent_ref')):
        return blocked('A2_A3_TARGET_OR_CHANGE_MISMATCH')
    if not isinstance(signal_bundle.get('depth_signals'),dict) or set(signal_bundle['depth_signals'])!=SIGNALS:
        return blocked('A2_A3_NINE_SIGNALS_REQUIRED')
    if c.get('signals_sha256')!=digest(signal_bundle):
        return blocked('A2_A3_SIGNALS_DIGEST_MISMATCH')
    if (not isinstance(c.get('evidence_refs'),list) or not c['evidence_refs'] or
        c.get('evidence_refs')!=signal_bundle.get('evidence_refs') or
        not all(isinstance(x,str) for x in c['evidence_refs'])):
        return blocked('A2_A3_SOURCE_REF_CONFLICT')
    if (golden.get('schema_version')!='A2_GOLDEN_HANDOFF_PROPOSAL_V0_3' or
        golden.get('contract_status')!='DESIGN_CANDIDATE_NOT_ADMITTED' or
        golden.get('processing_state')!=a2_result.get('status') or
        golden.get('canonical_classification')!=c):
        return blocked('A2_A3_GOLDEN_CLASSIFICATION_CONFLICT')
    bind=golden.get('source_binding')
    if not isinstance(bind,dict) or (bind.get('a1_output_sha256')!=digest(a1_result)
       or bind.get('signal_bundle_sha256')!=digest(signal_bundle)
       or bind.get('a2_policy_blob_sha1')!=A2_BLOB
       or bind.get('a3_contract_blob_sha1')!=A3_BLOB
       or bind.get('a3_contract_ref')!=A3_SOURCE
       or bind.get('catalog_sha256')!=CATALOG_SHA):
        return blocked('A2_A3_SOURCE_BINDING_DRIFT')
    assertion=golden.get('producer_assertions')
    if not isinstance(assertion,dict) or any(assertion.get(k) is not False for k in
          ('source_attested','independent_judge_verified','effects_executed','operationally_integrated')) or assertion.get('next_step') is not None:
        return blocked('A2_A3_GOLDEN_FALSE_AUTHORITY')
    dims=golden.get('dimension_results')
    if not isinstance(dims,list) or len(dims)!=12 or any(not isinstance(d,dict) or not isinstance(d.get('elements'),list) for d in dims):
        return blocked('A2_A3_DIMENSIONS_INCOMPLETE')
    elems=[e for d in dims for e in d['elements']]
    ids=[e.get('element_id') for e in elems if isinstance(e,dict)]
    if len(elems)!=59 or len(ids)!=59 or len(set(ids))!=59:
        return blocked('A2_A3_ELEMENTS_MISSING_OR_DUPLICATED')
    if any(e.get('fulfilment')!='PENDING_EVIDENCE' or e.get('applicability') not in
        ('REQUIRED','CONDITIONAL_REQUIRED','UNRESOLVED_TRIGGER') for e in elems):
        return blocked('A2_A3_ELEMENT_FALSE_COMPLETION')
    sm=golden.get('signal_evidence_map')
    if not isinstance(sm,list) or len(sm)!=9 or {s.get('signal_name') for s in sm if isinstance(s,dict)}!=SIGNALS:
        return blocked('A2_A3_SIGNAL_LINEAGE_INCOMPLETE')
    if any(s.get('attestation_state')!='DECLARED_UNATTESTED' or
       s.get('declared_value')!=signal_bundle['depth_signals'][s['signal_name']]
       for s in sm if isinstance(s,dict)):
        return blocked('A2_A3_SIGNAL_LINEAGE_FALSE_AUTHORITY')
    plan=golden.get('a3_resolution_plan')
    if not isinstance(plan,dict) or (plan.get('expected_a3_output_contract')!='TARGETED_EVIDENCE_SET_V1'
        or plan.get('consumer_state')!='PENDING_NATIVE_REVIEW'
        or plan.get('target_ref')!=c['target_ref']
        or plan.get('target_granularity')!=c['target_granularity']
        or plan.get('depth_level')!=c.get('depth_level')
        or plan.get('source_refs')!=c['evidence_refs']):
        return blocked('A2_A3_RESOLUTION_PLAN_INVALID')
    needs=plan.get('source_resolution_requests')
    tneeds=plan.get('target_resolution_requests')
    if not isinstance(needs,list) or len(needs)!=26 or not isinstance(tneeds,list) or len(tneeds)<1:
        return blocked('A2_A3_RESEARCH_REQUEST_COVERAGE_MISSING')
    needids=[n.get('need_id') for n in needs if isinstance(n,dict)]
    if len(needids)!=26 or len(set(needids))!=26 or set(needids)!={f'GOLDEN-{e["element_id"]}' for e in elems if e.get('applicability')!='REQUIRED'}:
        return blocked('A2_A3_RESEARCH_REQUEST_ID_MISMATCH')
    if any(not isinstance(n.get('source_refs'),list) or not n['source_refs']
       or not isinstance(n.get('material_question'),str) or not n['material_question'].strip()
       for n in needs):
        return blocked('A2_A3_RESEARCH_REQUEST_NOT_EVIDENCED')
    if any(t.get('expected_evidence')!='CANONICAL_TARGET_AUTHORITY_AND_IMPLEMENTATION_STATE' for t in tneeds if isinstance(t,dict)):
        return blocked('A2_A3_TARGET_AUTHORITY_QUERY_MISSING')
    # Human-first A2 interpretation; isolated from canonical A2/A3 contracts.
    # It never sends questions to the owner or opens an A3 RUN.
    brief_path = Path(__file__).resolve().with_name('intent_brief_v1.py')
    brief_spec = importlib.util.spec_from_file_location('a2_human_intent_brief_candidate',brief_path)
    if brief_spec is None or brief_spec.loader is None:
        return blocked('A2_A3_INTENT_BRIEF_SOURCE_MISSING')
    brief_module = importlib.util.module_from_spec(brief_spec)
    brief_spec.loader.exec_module(brief_module)
    human_brief = brief_module.build_brief(a1_result,a2_result,signal_bundle,golden)
    if human_brief.get('status') != 'HUMAN_BRIEF_CANDIDATE_UNATTESTED':
        return blocked('A2_A3_INTENT_BRIEF_UNQUALIFIED')
    # EXACT A3 input contracts. No runtime credential is carried in the preview.
    candidate={'REQUEST_CONTEXT_V1':deepcopy(context),
               'ANALYSIS_CHANGE_CLASSIFICATION_V1':deepcopy(c)}
    return {'schema_version':SCHEMA,'status':'PREVIEW_PREPARED_NOT_DISPATCHABLE',
     'blocking_codes':['A2_A3_A1_SOURCE_JUDGE_AND_NATIVE_RUN_PENDING'],
     'business':business,'a3_input_preview':candidate,
     'a3_resolution_plan_preview':deepcopy(plan),
     'human_intent_brief':deepcopy(human_brief),
     'preview_digest_sha256':digest({'a3_input':candidate,'research_plan':plan,'human_intent_brief':human_brief}),
     'source_binding':deepcopy(bind),'source_authenticated':False,
     'judge_verified':False,'run_verified':False,'dispatch_attempted':False,
     'a3_allowed':False,'next_step':None,'no_write_performed':True}
