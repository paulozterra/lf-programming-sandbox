"""PG-03_C7 exception classification, source-only and fail-closed.

Reuses the existing PG-10 decision-routing contract principles. No waiver is
issued; current authority and authorization must be checked externally.
"""
from collections.abc import Mapping

class ExceptionRoutingBlocked(ValueError):
    pass

_ALLOWED = {"EVIDENCE_GAP", "OWNER_DECISION", "TECHNICAL_STRATEGY", "POLICY_DEVIATION"}

def classify_exceptions(*, strategy, exceptions):
    if not isinstance(strategy, Mapping) or strategy.get("status") != "CANDIDATE_NOT_ADMITTED" or strategy.get("production_authority") is not False or strategy.get("handoff_allowed") is not False:
        raise ExceptionRoutingBlocked("STRATEGY_UNTRUSTED")
    if not isinstance(exceptions, list):
        raise ExceptionRoutingBlocked("EXCEPTIONS_INVALID")
    seen=set()
    routes=[]
    for item in exceptions:
        if not isinstance(item, Mapping):
            raise ExceptionRoutingBlocked("EXCEPTION_INVALID")
        identifier=item.get("id")
        kind=item.get("kind")
        ref=item.get("source_ref")
        if not isinstance(identifier,str) or not identifier.strip() or identifier in seen:
            raise ExceptionRoutingBlocked("EXCEPTION_ID_INVALID")
        seen.add(identifier)
        if kind not in _ALLOWED or not isinstance(ref,str) or not ref.strip():
            raise ExceptionRoutingBlocked("EXCEPTION_TYPE_OR_PROVENANCE_INVALID")
        scope=item.get("scope_id")
        if not isinstance(scope,str) or not scope.strip() or scope not in strategy.get("scope_ids",[]):
            raise ExceptionRoutingBlocked("SCOPE_NOT_CLASSIFIED")
        if item.get("approved") is True or item.get("waiver_granted") is True:
            raise ExceptionRoutingBlocked("UNVERIFIED_APPROVAL_FORBIDDEN")
        if kind=="EVIDENCE_GAP":
            route="TARGETED_ANALYSIS_EVIDENCE"
        elif kind=="OWNER_DECISION":
            # A true owner decision needs currentness/authority lookup before routing.
            route="CHECK_EXISTING_CURRENT_DECISION_FIRST"
        elif kind=="TECHNICAL_STRATEGY":
            route="PG03_TECHNICAL_RESOLUTION"
        else:
            route="EXISTING_POLICY_AUTHORITY_REVIEW"
        routes.append({"id":identifier,"scope_id":scope,"source_ref":ref,"kind":kind,"route":route,"status":"BLOCKED_PENDING_AUTHORITY_OR_EVIDENCE"})
    return {"schema_version":"PG03_C7_EXCEPTION_ROUTING_CANDIDATE_V1",
            "status":"CANDIDATE_NOT_ADMITTED" if not routes else "BLOCKED",
            "production_authority":False,"waiver_authorized":False,"handoff_allowed":False,
            "exceptions":sorted(routes,key=lambda x:x["id"])}
