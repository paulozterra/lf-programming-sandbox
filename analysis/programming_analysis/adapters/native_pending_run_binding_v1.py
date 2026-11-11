"""Candidate-only replacement for completed-invocation A2 binding.

The previous guard requires lf_skill_invocation_v1.status=COMPLETED even
though A2 executes before the independent judge, 70/80 and final completion.
This source-only guard requires IN_PROGRESS and the child RUN/step0.
Rows are untrusted: this cannot issue readback_authenticated or A3 PASS.
"""
from __future__ import annotations

import re
from typing import Any

SKILL = 'PROGRAMMING_ANALYSIS_LF'
OP = 'EJECUCION_SKILL_LF'
REPO = 'cristhianlujan/claude-persona-lf-patch'
PATH = 'skills/programming_analysis/SKILL.md'
SCHEMA = 'A2_GOLDEN_PENDING_RUN_BUSINESS_CANDIDATE_V1'
H64 = re.compile(r'^[a-f0-9]{64}$')
H40 = re.compile(r'^[a-f0-9]{40}$')


def block(code):
    return {'schema_version': SCHEMA,'status':'BLOCKED','blocking_codes':[code],
            'business':None,'execution_id':None,'skill_run_id':None,
            'readback_authenticated':False,'native_judge_verified':False,'a3_allowed':False}


def _is_dict(x):
    return isinstance(x, dict)


def verify_pending(parent: Any, invocation: Any, child: Any, step0: Any, actor_parent_execution_id: Any):
    if not all(_is_dict(x) for x in (parent,invocation,child,step0)):
        return block('PENDING_READBACK_REQUIRED')
    pid = parent.get('execution_id')
    if not isinstance(pid,str) or not pid or pid != actor_parent_execution_id:
        return block('PENDING_PARENT_ACTOR_MISMATCH')
    if parent.get('operation_code')!='EJECUCION_PERFIL_LF' or parent.get('status')!='IN_PROGRESS' or parent.get('target_type')!='PERFIL':
        return block('PENDING_PARENT_NOT_ACTIVE')
    manifest = parent.get('manifest')
    if not _is_dict(manifest):return block('PENDING_PARENT_MANIFEST_INVALID')
    business = manifest.get('business')
    if not isinstance(business,str) or not 2<=len(business)<=32 or business!=business.strip():
        return block('PENDING_PARENT_BUSINESS_MISSING')
    handoff = manifest.get('router_profile_handoff')
    receipt = handoff.get('router_authorization_receipt') if _is_dict(handoff) else None
    if not _is_dict(receipt):return block('PENDING_ROUTER_RECEIPT_MISSING')
    profile = parent.get('target_code')
    request = parent.get('request_sha256')
    if not isinstance(request,str) or not H64.fullmatch(request):return block('PENDING_REQUEST_HASH_INVALID')
    if (handoff.get('business')!=business or receipt.get('business')!=business or
        handoff.get('profile_code')!=profile or receipt.get('profile_code')!=profile or
        handoff.get('request_sha256')!=request or receipt.get('request_sha256')!=request):
        return block('PENDING_PROFILE_BUSINESS_OR_REQUEST_CONFLICT')
    if (receipt.get('schema_version')!='LF_ROUTER_PROFILE_AUTHORIZATION_RECEIPT_V1' or
        receipt.get('router')!='ACT-0001' or receipt.get('action_code')!='PROFILE_EXECUTION' or
        receipt.get('operation_code')!='EJECUCION_PERFIL_LF' or receipt.get('asset_type')!='PERFIL' or
        receipt.get('profile_execution_allowed') is not True or receipt.get('effect_authority') is not False):
        return block('PENDING_ROUTER_NOT_AUTHORIZED')
    srid = invocation.get('skill_run_id')
    cid = invocation.get('child_execution_id')
    if (invocation.get('status')!='IN_PROGRESS' or
        not isinstance(srid,str) or not srid or not isinstance(cid,str) or not cid or
        invocation.get('skill_code')!=SKILL or invocation.get('parent_execution_id')!=pid or
        invocation.get('profile_code')!=profile or
        not isinstance(invocation.get('input_sha256'),str) or not H64.fullmatch(invocation['input_sha256'])):
        return block('PENDING_INVOCATION_NOT_EXACT_OR_PREMATURELY_CLOSED')
    cm = child.get('manifest')
    if (child.get('execution_id')!=cid or child.get('operation_code')!=OP or child.get('target_type')!='SKILL' or
        child.get('target_code')!=SKILL or child.get('status')!='IN_PROGRESS' or
        child.get('created_by_execution_id')!=pid or child.get('request_sha256')!=request or
        not _is_dict(cm)):
        return block('PENDING_CHILD_RUN_MISMATCH')
    if (child.get('target_repo')!=REPO or child.get('target_path')!=PATH or
        parent.get('target_repo')!=REPO):
        return block('PENDING_REPOSITORY_OR_TARGET_MISMATCH')
    if cm.get('skill_input_sha256')!=invocation.get('input_sha256'):
        return block('PENDING_INPUT_DIGEST_MISMATCH')
    ph = cm.get('profile_handoff')
    if not _is_dict(ph) or ph.get('source_execution_id')!=pid or ph.get('skill_run_id')!=srid or ph.get('business')!=business or cm.get('business')!=business:
        return block('PENDING_CHILD_CROSS_BUSINESS')
    source = cm.get('skill_source')
    if not _is_dict(source) or source.get('path')!=PATH or source.get('repository')!=REPO or not H40.fullmatch(str(source.get('commit_sha',''))) or not H40.fullmatch(str(source.get('blob_sha',''))):
        return block('PENDING_CURRENT_SOURCE_NOT_BOUND')
    if (step0.get('evidence_ref')!='supabase://public.lf_operation_execution/'+cid):
        return block('PENDING_INIT_STEP_EVIDENCE_REF_INVALID')
    if (step0.get('execution_id')!=cid or step0.get('step_id')!='init_execution' or step0.get('step_order')!=0 or
        step0.get('status')!='STEP_PASS_WITH_EVIDENCE' or not _is_dict(step0.get('evidence_payload')) or
        step0['evidence_payload'].get('execution_id_created') is not True or
        step0['evidence_payload'].get('mini_judge_code')!='JUDGE-EJECUCION-SKILL-LF-v0.1' or
        step0['evidence_payload'].get('mini_judge_result')!='STEP_PASS_WITH_EVIDENCE' or
        step0['evidence_payload'].get('step_result')!='STEP_PASS_WITH_EVIDENCE'):
        return block('PENDING_INIT_STEP_NOT_CLEAN')
    return {'schema_version':SCHEMA,'status':'CANDIDATE_PENDING_RUN_CONSISTENT',
            'blocking_codes':[],'business':business,'execution_id':cid,'skill_run_id':srid,
            'readback_authenticated':False,'native_judge_verified':False,'a3_allowed':False}
