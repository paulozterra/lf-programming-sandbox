"""A2 Golden review-cycle candidate. Offline pure decision function; NO native judge call or ticket writes.
The original A2 v0.3 producer schema is validated separately from this external review envelope.
"""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
from typing import Any
from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).with_name('A2_GOLDEN_CICLO_REVISION_v0_7.schema.json')
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
VALIDATOR = Draft202012Validator(SCHEMA)


def _out(status: str, reason: str, n: int, issues: list[dict] | None = None,
         next_action: str = 'NONE', ticket_closure: str = 'CLOSURE_NOT_VERIFIED') -> dict:
    return {
        'status': status, 'terminal_reason': reason,
        'attempts_used': n, 'max_submissions': 3,
        'a3_invocation_allowed': next_action == 'INVOKE_A3_ONCE',
        'a3_invoked': False,
        'next_action': next_action,
        'open_findings': issues or [],
        'ticket_closure': ticket_closure,
        'operational_readback_completed': False,
        'profile_report_required': status in ('A2_EXHAUSTED', 'A2_BLOCKED'),
        'execution_status_claim': 'UNVERIFIED_DESIGN_ONLY',
    }


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def _issues_of(attempt: dict) -> list[dict]:
    return attempt['deterministic']['feedback'] + attempt['native_review']['feedback']


def evaluate_cycle(packet: dict, verified_native_receipts: dict[int, dict] | None = None,
                   verified_ticket_closure: dict | None = None,
                   verified_deterministic_receipts: dict[int, dict] | None = None,
                   verified_handoff_gate: dict | None = None) -> dict:
    """Return purely logical controller decision; NEVER attest producer or native judge itself.

    NOT A RUNTIME ENTRYPOINT. The native semantic judge is an EXTERNAL host action.
    A result is never permission to call A3 absent readback by the authorized native host.

    verified_native_receipts MUST be supplied by an external trusted readback caller;
    self-asserted review content in packet is not evidence.
    """
    errors = sorted(VALIDATOR.iter_errors(packet), key=lambda e: (list(map(str, e.absolute_path)), e.message))
    if errors:
        return _out('A2_BLOCKED', 'REVIEW_CYCLE_SCHEMA_INVALID', 0)
    attempts = packet['submissions']
    seen_pairs = set()
    for i, current in enumerate(attempts):
        n = i + 1
        if current['attempt_number'] != n:
            return _out('A2_BLOCKED', 'ATTEMPT_NUMBER_SEQUENCE_INVALID', n)
        if current['candidate_sha256'] in seen_pairs:
            return _out('A2_BLOCKED', 'REPEATED_UNCHANGED_CANDIDATE', n)
        seen_pairs.add(current['candidate_sha256'])
        det, judge = current['deterministic'], current['native_review']
        if i:
            prior = attempts[i-1]
            if prior['deterministic']['result'] == 'PASS' and prior['native_review']['result'] == 'PASS':
                return _out('A2_BLOCKED','SUBMISSION_AFTER_APPROVAL', n)
            if prior['native_review']['result'] == 'TECHNICAL_BLOCK':
                return _out('A2_BLOCKED','SUBMISSION_AFTER_TECHNICAL_BLOCK', n)
            p_issues = _issues_of(prior)
            if not p_issues:
                return _out('A2_BLOCKED','PRIOR_REPAIR_INSTRUCTION_MISSING', n)
            original_ids = {d['finding_id'] for d in p_issues}
            resolutions = current['previous_defect_resolution']
            if {r['finding_id'] for r in resolutions} != original_ids or len(resolutions)!=len(original_ids):
                return _out('A2_BLOCKED','PREVIOUS_FINDING_COVERAGE_INCOMPLETE', n)
            current_ids = {d['finding_id'] for d in _issues_of(current)}
            for r in resolutions:
                if r['status'] == 'RESOLVED' and (r['finding_id'] in current_ids or not r['evidence_refs']):
                    return _out('A2_BLOCKED','FALSE_RESOLUTION_OR_MISSING_EVIDENCE', n)
        elif current['previous_defect_resolution']:
            return _out('A2_BLOCKED','FIRST_ATTEMPT_CANNOT_RESOLVE_PRIOR_FINDINGS',n)

        det_receipt=(verified_deterministic_receipts or {}).get(n)
        if not det_receipt or (
             det_receipt.get('execution_id') != packet['execution_id'] or
             det_receipt.get('candidate_sha256') != current['candidate_sha256'] or
             det_receipt.get('validator_ref') != det['validator_ref'] or
             det_receipt.get('result') != det['result'] or
             det_receipt.get('feedback_sha256') != _sha(det['feedback']) or
             det_receipt.get('source_verified') is not True):
            return _out('A2_BLOCKED','DETERMINISTIC_RECEIPT_UNVERIFIED',n)
        if any(issue['retryable'] is False for issue in _issues_of(current)):
            return _out('A2_BLOCKED','NON_RETRYABLE_FINDING',n,_issues_of(current),next_action='RETURN_TERMINAL_REPORT_TO_PROFILE')
        if det['result']=='PASS' and det['feedback']:
            return _out('A2_BLOCKED','DETERMINISTIC_PASS_WITH_FINDINGS',n)
        if det['result']=='FAIL' and not det['feedback']:
            return _out('A2_BLOCKED','DETERMINISTIC_FAIL_WITHOUT_ACTIONABLE_FEEDBACK',n)
        if det['result']=='FAIL' and judge['result']!='NOT_INVOKED':
            return _out('A2_BLOCKED','JUDGE_INVOKED_AFTER_DETERMINISTIC_FAIL',n)
        if det['result']=='PASS' and judge['result']=='NOT_INVOKED':
            return _out('A2_BLOCKED','NATIVE_JUDGE_NOT_INVOKED',n)
        if judge['result']=='TECHNICAL_BLOCK':
            return _out('A2_BLOCKED','NATIVE_JUDGE_TECHNICAL_BLOCK',n)
        if judge['result']=='FAIL' and not judge['feedback']:
            return _out('A2_BLOCKED','JUDGE_FAIL_WITHOUT_ACTIONABLE_FEEDBACK',n)
        if judge['result']=='PASS' and judge['feedback']:
            return _out('A2_BLOCKED','JUDGE_PASS_WITH_FINDINGS',n)
        if judge['result'] in ('PASS','FAIL'):
            receipt=(verified_native_receipts or {}).get(n)
            if not receipt or (
                receipt.get('execution_id') != packet['execution_id'] or
                receipt.get('candidate_sha256') != current['candidate_sha256'] or
                receipt.get('review_sha256') != judge['review_sha256'] or
                receipt.get('receipt_ref') != judge['receipt_ref'] or
                receipt.get('verdict') != judge['result'] or
                receipt.get('feedback_sha256') != _sha(judge['feedback']) or
                receipt.get('source_verified') is not True
            ):
                return _out('A2_BLOCKED','NATIVE_JUDGE_READBACK_UNVERIFIED',n)
        # Reject all earlier submissions if intermediate decisions were not actionable.
        if i < len(attempts)-1 and not _issues_of(current):
            return _out('A2_BLOCKED','RETRY_WITHOUT_PREVIOUS_FEEDBACK',n)
        if i == len(attempts)-1:
            if det['result'] == 'PASS' and judge['result'] == 'PASS':
                gate=verified_handoff_gate or {}
                if not (gate.get('execution_id') == packet['execution_id'] and
                        gate.get('a1_input_sha256') == packet['a1_input_sha256'] and
                        gate.get('candidate_sha256') == current['candidate_sha256'] and
                        gate.get('judge_review_sha256') == judge['review_sha256'] and
                        gate.get('validator_ref') == det['validator_ref'] and
                        gate.get('a2_stage_source_attested') is True and
                        gate.get('readback_verified') is True and
                        gate.get('source_verified') is True):
                    return _out('A2_GATE_PENDING','GOVERNED_A2_TO_A3_GATE_NOT_ATTESTED',n)
                return _out('A2_APPROVED','GATED_PASS_RECEIPT_VERIFIED',n, next_action='INVOKE_A3_ONCE')
            if n == 3:
                res=_out('A2_EXHAUSTED','A2_MAX_ATTEMPTS_EXCEEDED',n,_issues_of(current),next_action='RETURN_TERMINAL_REPORT_TO_PROFILE')
                if (packet['ticket_ref'] and verified_ticket_closure and
                    verified_ticket_closure.get('ticket_ref') == packet['ticket_ref'] and
                    verified_ticket_closure.get('execution_id') == packet['execution_id'] and
                    verified_ticket_closure.get('receipt_ref') and
                    verified_ticket_closure.get('closed') is True and
                    verified_ticket_closure.get('source_verified') is True):
                    res['ticket_closure']='TICKET_CLOSED_VERIFIED'
                return res
            return _out('A2_REPAIR_REQUIRED','RETURN_TO_A2_WITH_FEEDBACK',n,_issues_of(current),next_action='REGENERATE_A2_WITH_HISTORY')
    return _out('A2_BLOCKED','UNREACHABLE_STATE',len(attempts))


def make_profile_terminal_report(packet: dict, decision: dict) -> dict:
    if decision['status'] not in ('A2_EXHAUSTED', 'A2_BLOCKED'):
        raise ValueError('Terminal report requires terminal negative decision')
    last=packet['submissions'][-1]
    return {
      'schema_version':'A2_PROFILE_TERMINAL_REPORT_PROPOSAL_V0_7',
      'execution_id':packet['execution_id'],
      'ticket_ref':packet['ticket_ref'],
      'last_a2_output_ref':last['candidate_ref'],
      'last_a2_output_sha256':last['candidate_sha256'],
      'last_judge_receipt_ref':last['native_review']['receipt_ref'],
      'attempts_used':decision['attempts_used'],
      'max_submissions':3,
      'terminal_status':decision['status'],
      'terminal_reason':decision['terminal_reason'],
      'attempt_history':[
          {'attempt_number':x['attempt_number'], 'candidate_sha256':x['candidate_sha256'],
           'deterministic_result':x['deterministic']['result'],
           'native_result':x['native_review']['result'],
           'findings': _issues_of(x)} for x in packet['submissions']],
      'open_findings':decision['open_findings'],
      'a3_invoked':False,
      'ticket_closure':decision['ticket_closure'],
      'operationally_verified':False,
      'user_message':'Análisis A2 no aprobado; consulte el historial de hallazgos y las acciones pendientes.'
    }