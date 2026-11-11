"""Human-readable A2 intent brief (candidate, NOT an LLM/judge or A3 dispatch).

The producer transcribes *declared* A1 fields and creates explicitly tentative
questions. Semantic sufficiency must later be reviewed by an independent judge.
Nothing here authenticates provenance, currentness, or grants execution.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from typing import Any

SCHEMA = 'A2_HUMAN_INTENT_BRIEF_CANDIDATE_V1'


def digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def invalid(code: str) -> dict:
    return {'schema_version': SCHEMA, 'status': 'BLOCKED', 'blocking_codes': [code],
        'intent_review_required': True, 'source_attested': False,
        'independent_judge_verified': False, 'a3_allowed': False,
        'owner_questions_sent': False, 'next_step': None}


def _text(x: Any, limit: int=4000) -> bool:
    return isinstance(x, str) and 0 < len(x.strip()) <= limit and x == x.strip()


def build_brief(a1: dict, a2: dict, signals: dict, golden: dict) -> dict:
    """Only to be called after the existing A2→A3 preview's structural gates."""
    if not all(isinstance(x,dict) for x in (a1,a2,signals,golden)):
        return invalid('INTENT_INPUT_INVALID')
    context=a1.get('payload')
    obj=context.get('objective') if isinstance(context,dict) else None
    if not isinstance(obj,dict) or not all(_text(obj.get(k)) for k in ('problem_statement','desired_outcome')):
        return invalid('INTENT_OBJECTIVE_INCOMPLETE')
    if a1.get('business')!=a2.get('business') or a1.get('business')!=signals.get('business'):
        return invalid('INTENT_BUSINESS_MISMATCH')
    # A human preview must never read as a SALY-qualified LF skill output.
    if a1.get('business') != 'LF':
        return invalid('INTENT_BUSINESS_NOT_ENABLED_FOR_SKILL')
    classification=a2.get('classification')
    if not isinstance(classification,dict) or not _text(classification.get('target_ref')):
        return invalid('INTENT_CLASSIFICATION_MISSING')
    if not isinstance(golden.get('dimension_results'),list) or len(golden['dimension_results'])!=12:
        return invalid('INTENT_COVERAGE_NOT_PRESENT')
    target=classification['target_ref']
    if target not in context.get('target_hints',[]):
        return invalid('INTENT_TARGET_UNDECLARED')
    refs=context.get('source_refs')
    if not isinstance(refs,list) or not refs or not all(_text(x,512) for x in refs):
        return invalid('INTENT_SOURCE_REFS_REQUIRED')
    ambiguities=context.get('ambiguities')
    if not isinstance(ambiguities,list):
        return invalid('INTENT_AMBIGUITY_INPUT_INVALID')
    open_ambiguities=[]
    for x in ambiguities:
        if not isinstance(x,dict) or not all(_text(x.get(k),1200) for k in ('code','statement')) or x.get('resolution_state') not in ('OPEN','RESOLVED_FROM_SOURCE'):
            return invalid('INTENT_AMBIGUITY_INPUT_INVALID')
        if x['resolution_state']=='OPEN':
            open_ambiguities.append({'code':x['code'],'issue':x['statement'],
                'materiality':x.get('materiality','UNKNOWN'),'status':'DECLARED_OPEN_NOT_VERIFIED'})
    constraints_supplied='constraints' in context
    constraints=context.get('constraints',[])
    if not isinstance(constraints,list) or any(not _text(c) for c in constraints):
        return invalid('INTENT_CONSTRAINTS_INVALID')
    items=[e for d in golden['dimension_results'] for e in d.get('elements',[]) if isinstance(e,dict)]
    if len(items)!=59 or any(e.get('fulfilment')!='PENDING_EVIDENCE' for e in items):
        return invalid('INTENT_ELEMENT_STATUS_DRIFT')
    # A declaration that ambiguities=[] means only *no ambiguities recorded*.
    # It can never be converted into an independent semantic approval.
    required_ids=[e['element_id'] for e in items if e.get('applicability')=='REQUIRED']
    if len(required_ids)!=33 or len(set(required_ids))!=33:
        return invalid('INTENT_REQUIRED_ELEMENT_COVERAGE_MISMATCH')
    # A1 already provides a literal problem and desired outcome. Do not make
    # asking the owner a universal prerequisite; assess semantic sufficiency
    # and compare existing definitions before escalating an open ambiguity.
    owner=[]
    intent_quality_checks=[{
        'id':'CHECK_OBSERVABLE_OUTCOME',
        'question':'¿La intención y el resultado declarados permiten definir un criterio observable de éxito?',
        'routing':'SEMANTIC_REVIEW_THEN_EXISTING_DEFINITIONS',
        'status':'PENDING_SEMANTIC_REVIEW_NOT_OWNER_QUESTION'
    }]
    for x in open_ambiguities:
        if x['materiality'] in ('MATERIAL','UNKNOWN'):
            owner.append({'id':'OWNER-'+x['code'],
                'question':'¿Cómo debe resolverse esta interpretación pendiente: '+x['issue']+'?',
                'reason':'Ambigüedad declarada en A1: verificar definiciones y fuentes antes de pedir decisión al propietario.',
                'routing':'A3_RESEARCH_FIRST_THEN_OWNER_IF_MATERIAL_UNRESOLVED',
                'status':'SUGGESTED_NOT_SENT_NEEDS_SEMANTIC_REVIEW'})
    research=[
      {'id':'A3-TARGET','request':f'Verificar identidad exacta, autoridad y estado actual del objetivo {target}.',
       'source':'CANONICAL_TARGET_AND_IMPLEMENTATION_CURRENTNESS'},
      {'id':'A3-ASIS','request':'Describir las definiciones y el funcionamiento actuales, cambios previos y delta real frente al objetivo, sin inferir una solución nueva.',
       'source':'CURRENT_IMPLEMENTATION_AND_DELTA'},
      {'id':'A3-POLICY','request':'Localizar políticas, reglas, límites y controles pertinentes; registrar fuente, versión y vigencia.',
       'source':'CURRENT_CANONICAL_AUTHORITY'},
      {'id':'A3-IMPACT','request':'Identificar consumidores, dependencias y riesgos de cambio comprobados, diferenciándolos de hipótesis.',
       'source':'CURRENT_CONSUMER_AND_DEPENDENCY_READBACK'}]
    assumptions=[
      'El negocio, objetivo y target provienen de A1 y aún no están atestados.',
      'Las nueve señales de profundidad son declaradas, no equivalen a políticas vigentes verificadas.',
      'A1 sin ambigüedades registradas no equivale a intención inequívoca.',
      'La clasificación de profundidad no autoriza ejecutar ni implementar.']
    constraint_text=('; '.join(constraints) if constraints else
       'No se proporcionaron restricciones comprobables en esta entrada.')
    ambiguity_text=('; '.join(x['issue'] for x in open_ambiguities) if open_ambiguities else
       'A1 no registró ambigüedades; esto no prueba que no existan.')
    plain=(
      f'El solicitante pidió: «{obj["problem_statement"]}». El resultado que expresó fue: '
      f'«{obj["desired_outcome"]}». Se trata del negocio declarado {a1["business"]} '
      f'y del objetivo señalado {target}, cuya identidad y vigencia aún deben comprobarse.\n\n'
      f'Restricciones recibidas: {constraint_text} Ambigüedades: {ambiguity_text} '
      f'La profundidad {classification.get("depth_level","sin clasificar")} fue calculada con señales declaradas, no verificadas.\n\n'
      f'A2 conserva esa intención sin suponer qué solución construir. Debe comprobarse primero '
      f'la suficiencia semántica del problema y del criterio observable de éxito ya declarados, '
      f'comparándolos con definiciones y fuentes existentes. Preguntar al solicitante solo si '
      f'persiste una decisión material no resoluble por esas fuentes. '
      f'No se han enviado preguntas.\n\n'
      f'A3 deberá comprobar la situación actual, las autoridades, las reglas y los consumidores del objetivo. '
      f'No debe decidir por el usuario el propósito del cambio ni interpretar las señales declaradas '
      f'como evidencia de vigencia. El inventario Golden de 59 elementos es soporte de calidad, '
      f'no el texto principal del encargo. Los 33 elementos obligatorios también requieren '
      f'evidencia; no basta con preguntar por los 26 condicionales.\n\n'
      f'Estado: propuesta no atestada; juez de A2 y RUN gobernado pendientes; A3 no autorizado.'
    )
    return {'schema_version':SCHEMA, 'status':'HUMAN_BRIEF_CANDIDATE_UNATTESTED',
      'source_ref':deepcopy(refs), 'source_binding':{
          'a1_result_sha256':digest(a1),'a2_classification_sha256':digest(classification),
          'golden_handoff_sha256':digest(golden)},
      'business':a1['business'], 'target_ref':target,
      'request_literal':obj['problem_statement'], 'desired_outcome_literal':obj['desired_outcome'],
      'scope_constraints_declared':deepcopy(constraints),
      'constraints_status':'DECLARED_UNVERIFIED' if constraints_supplied else 'NOT_PROVIDED_UNVERIFIED',
      'recorded_open_ambiguities':open_ambiguities,
      'ambiguities_absent_not_proven':not bool(ambiguities),
      'user_questions_candidates':owner, 'intent_quality_checks':intent_quality_checks,
      'a3_investigation_tasks':research,
      'assumptions_to_verify':assumptions,
      'required_evidence_gaps':required_ids,
      'required_evidence_gaps_status':'33_MANDATORY_ITEMS_NEED_A3_EVIDENCE',
      'human_readable_document':plain,
      'golden_controls':{'dimensions':12,'elements':59,'required':33,'conditional':26,
                         'coverage_state':'INTERNAL_CHECKLIST_NOT_DOCUMENT_MAIN'},
      'intent_review_required':True,'source_attested':False,
      'independent_judge_verified':False,'owner_questions_sent':False,
      'run_verified':False,'a3_allowed':False,'next_step':None,'no_write_performed':True}
