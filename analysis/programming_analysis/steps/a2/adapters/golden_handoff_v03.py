"""A2 Golden source-only projection to the pre-existing v0.3 proposed handoff.

Read-only, preserves canonical ANALYSIS_CHANGE_CLASSIFICATION_V1 without
changing its schema. Schema v0.3 is local proposal, NOT runtime admission.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import importlib.util
from typing import Any

from jsonschema import Draft202012Validator

A2_BASE=Path(__file__).resolve().parents[1]
DEFAULT_CATALOG=A2_BASE/'catalog/A2_GOLDEN_CATALOGO_DIMENSIONAL_v0_2.json'
DEFAULT_SCHEMA=A2_BASE/'schemas/A2_GOLDEN_CONTRATO_SALIDA_PROPUESTA_v0_3.schema.json'
SCHEMA_SHA256='3cfff9ba5d9df8d3ab88283ff99c04d70af46ec20d971b3bca45baa8afea79e4'
A2_POLICY_REF='sandbox/lf_contract_gate_test/programming_agent_four_stage/wave1_boundary_contracts/analysis_change_classification_contract_v1.json'
A3_CONTRACT_REF='sandbox/lf_contract_gate_test/programming_agent_four_stage/wave1_boundary_contracts/analysis_targeted_evidence_contract_v1.json'
A3_CONTRACT_BLOB='97d06e88b963690202424a2936ae2b7bf597cea7'


def _load_projection():
    path=A2_BASE/'adapters/golden_dimensions_v1.py'
    spec=importlib.util.spec_from_file_location('golden_dimensional_projection',path)
    if spec is None or spec.loader is None:
        raise ValueError('GOLDEN_PROJECTION_SOURCE_MISSING')
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _digest(x):
    return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,
        separators=(',',':')).encode('utf8')).hexdigest()


def _load_schema(path):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SCHEMA_SHA256:
        raise ValueError('GOLDEN_V03_SCHEMA_DIGEST_DRIFT')
    return json.loads(raw)


def _source_request(item,reqid):
    return {
        'need_id':reqid,
        'material_question':item['a3_handoff'],
        'source_refs':deepcopy(item['evidence_refs']),
        'expected_evidence':'CURRENT_ATTESTED_SOURCE_OR_TYPED_BLOCKER',
        'decision_effect':'RESOLVE_DIMENSION_'+item['element_id'],
        'stop_condition':'EXACT_CURRENT_READBACK_OR_MATERIAL_CONTRADICTION',
        'dimension_refs':[item['dimension_id']],
    }


def prepare_golden_v03(a1_result:Any, a2_result:Any, signal_bundle:Any, *,
                        catalog_path:Path=DEFAULT_CATALOG,
                        schema_path:Path=DEFAULT_SCHEMA)->dict:
    """Verify the exact source/schema before producing the design-only handoff."""
    projection=_load_projection()
    draft=projection.build_golden(a1_result,a2_result,signal_bundle,catalog_path=catalog_path)
    if draft['status']=='BLOCKED':
        return draft  # This is a typed fail-closed diagnostic, NOT a valid v0.3 handoff.
    try:
        schema=_load_schema(schema_path)
    except (OSError,ValueError):
        return projection._blocked('GOLDEN_V03_SCHEMA_SOURCE_UNAVAILABLE_OR_DRIFTED')
    c=draft['classification']
    output=[]; byid={x['element_id']:x for x in draft['elements']}
    for dim in draft['dimensions']:
        els=[]
        for x in dim['elements']:
            eid=x['element_id']
            reqid='GOLDEN-'+eid
            always=x['applicability']=='REQUIRED'
            active=x['applicability']=='CONDITIONAL_REQUIRED'
            tri='TRUE' if always or active else 'UNKNOWN'
            basis=('CATALOG_ALWAYS' if always else
                   'SEMANTIC_TRIGGER_UNRESOLVED' if not active else
                   ('A1_CONTEXT' if any(t.startswith(('a1.','A1:')) for t in x['trigger_inputs']) else
                    'CANONICAL_TYPED_SIGNALS'))
            finding=None
            if x['value'] is not None and eid!='D12-E05':
                finding={
                    'claim':json.dumps(x['value'],ensure_ascii=False,sort_keys=True),
                    'rationale':'Valor declarado o derivado de A1/A2; no acredita currentness',
                    'source_refs':deepcopy(x['evidence_refs']),
                    'provisional':True,
                    'uncertainty':'CURRENT_SERVER_READBACK_AND_JUDGE_PENDING',
                }
            els.append({
                'element_id':eid,'applicability':x['applicability'],
                'fulfilment':'PENDING_EVIDENCE',
                'trigger':{'rule_ref':eid,'result':tri,
                           'source_refs':deepcopy(x['evidence_refs']), 'basis':basis},
                'finding':finding,'not_applicable_reason':None,
                'gap_codes':[] if eid=='D12-E05' else ['SOURCE_ATTESTATION_PENDING'],
                'a3_need_refs':[reqid] if x['applicability']!='REQUIRED' else [],
            })
        output.append({'dimension_id':dim['dimension_id'],'elements':els})
    requests=[_source_request(x,'GOLDEN-'+x['element_id'])
              for x in draft['elements'] if x['applicability']!='REQUIRED']
    source_refs=signal_bundle['evidence_refs']
    # Neither the declaration nor this manifest can authenticate the nine signals.
    signal_map=[{'signal_name':x['signal_key'],
                 'declared_value':deepcopy(x['declared_value']),
                 'source_refs':deepcopy(x['source_refs']),
                 'attestation_state':'DECLARED_UNATTESTED'} for x in draft['signal_lineage']]
    target_request={
        'need_id':'GOLDEN-TARGET-CURRENT',
        'material_question':'Resolver identidad, autoridad y estado CURRENT del target declarado',
        'source_refs':deepcopy(source_refs),
        'expected_evidence':'CANONICAL_TARGET_AUTHORITY_AND_IMPLEMENTATION_STATE',
        'decision_effect':'BLOCK_FALSE_TARGET_IDENTITY',
        'stop_condition':'EXACT_SOURCE_READBACK_OR_TYPED_BLOCKER',
        'dimension_refs':['D01','D02'],
    }
    a3={
      'target_ref':c['target_ref'],'target_granularity':c['target_granularity'],
      'depth_level':c['depth_level'],'source_refs':deepcopy(source_refs),
      'source_resolution_requests':requests,
      'target_resolution_requests':[target_request],
      'material_gap_codes':['SOURCE_ATTESTATION_PENDING'],
      'specialist_requirements':[
         {'requirement_ref':'A2_REQUIRED_SPECIALIST_COUNT',
          'scope_ref':c['target_ref'],'selection_mode':'UNDETERMINED',
          'status':'PENDING_SELECTOR'}
      ] if signal_bundle['depth_signals']['required_specialist_count']>0 else [],
      'blocking_codes':list(a2_result.get('blocking_codes',[])),
      'consumer_state':'PENDING_NATIVE_REVIEW',
      'expected_a3_output_contract':'TARGETED_EVIDENCE_SET_V1',
      'reclassification_policy':'NEW_VERSION_IF_A3_RETURNS_MATERIAL_NEW_EVIDENCE_OR_SOURCE_DRIFT',
    }
    out={
      'schema_version':'A2_GOLDEN_HANDOFF_PROPOSAL_V0_3',
      'contract_status':'DESIGN_CANDIDATE_NOT_ADMITTED',
      'source_binding':{
        'a1_output_sha256':_digest(a1_result),
        'signal_bundle_sha256':_digest(signal_bundle),
        'a2_policy_ref':A2_POLICY_REF,
        'a2_policy_blob_sha1':projection.CANONICAL_A2_BLOB,
        'a3_contract_ref':A3_CONTRACT_REF,
        'a3_contract_blob_sha1':A3_CONTRACT_BLOB,
        'catalog_version':'A2_GOLDEN_DYNAMIC_DIMENSION_CATALOG_PROPOSAL_V0_2',
        'catalog_sha256':projection.CATALOG_SHA256,
      },
      'processing_state':a2_result['status'],
      'canonical_classification':deepcopy(c),
      'dimension_results':output,
      'signal_evidence_map':signal_map,
      'a3_resolution_plan':a3,
      'producer_assertions':{
        'source_attested':False,'independent_judge_verified':False,
        'effects_executed':False,'operationally_integrated':False,
        'next_step':None,
      },
    }
    errors=list(Draft202012Validator(schema).iter_errors(out))
    if errors:
        block=projection._blocked('GOLDEN_V03_OUTPUT_SCHEMA_NOT_MET')
        # Do not report a malformed v0.3 output as a valid candidate.
        block['validation_failures']=[str(x.message)[:160] for x in errors[:6]]
        return block
    return out
