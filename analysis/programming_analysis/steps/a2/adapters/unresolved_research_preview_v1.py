"""Design-only A2 research preview for an A1 material ambiguity.

No A2 depth classification, no A3 dispatch, model judge, authority or I/O.
Canonical A1/A2/A3 schemas and the A3 two-input interface remain unchanged.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

SCHEMA = "A2_UNRESOLVED_RESEARCH_PREVIEW_CANDIDATE_V1"
RESOLUTION_ORDER = (
    "EXACT_TARGET_IDENTITY", "CURRENT_CANONICAL_AUTHORITY",
    "CURRENT_IMPLEMENTATION", "RELATED_AUTHORITIES",
    "CONSUMERS_AND_DEPENDENCIES",
)


def _hash(data: Any) -> str:
    return hashlib.sha256(json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _blocked(code: str) -> dict:
    return {
        "schema_version": SCHEMA, "status": "BLOCKED",
        "blocking_codes": [code], "research_plan": None,
        "a2_classification": None, "a3_canonical_inputs": None,
        "a3_dispatch_allowed": False, "a2_depth_classified": False,
        "source_authenticated": False, "independent_judge_attested": False,
        "runtime_integrated": False, "next_step": None,
    }


def _actionable_research_order(raw: str, outcome: str, operation: str,
                               artifact: str, capability: str, hints: list,
                               constraints: list, pending: list, dimensions: list) -> dict:
    """Generate source-bound A3 work instructions; never infer actual system state."""
    exact = hints[0]
    common = [
        "Referencia exacta de fuente y objeto consultado",
        "Versión/hash y evidencia de vigencia (CURRENTNESS)",
        "Fragmento o resultado verificable, sin suponer que existe",
        "Contradicciones, ausencias y ámbito de búsqueda utilizado",
    ]
    tasks = [
        {
            "id": "A3-01-IDENTITY",
            "question": f"¿Cuál es la identidad canónica vigente de «{exact}» y existe ya su implementación?",
            "verify": [
                "Distinguir autoridad EXISTING/NEW/UNKNOWN de implementación EXISTING/NEW/UNKNOWN",
                "Localizar identificador y referencia exactos, no inferirlos de la frase del usuario",
                "Anotar candidatos de reutilización antes de proponer un artefacto nuevo",
            ],
            "evidence_required": common + [
                "exact_target_ref, authority_state, implementation_state",
                "authority_refs[] e implementation_refs[] o evidencia negativa de búsqueda",
            ],
            "if_unresolved": "TARGET_UNKNOWN: conservar candidatos y búsqueda pendiente; no declarar inexistencia",
        },
        {
            "id": "A3-02-BASELINE",
            "question": f"¿Qué reglas, definiciones, comportamiento y cambios previamente aprobados rigen «{exact}»?",
            "verify": [
                "Recuperar especificaciones, políticas, diseño y comportamiento implementado si existen",
                "Identificar qué está decidido, qué funciona y qué está pendiente",
                "Separar documentación vigente, histórica, contradictoria y no encontrada",
            ],
            "evidence_required": common + [
                "Definiciones y reglas con authority_refs[], currentness_refs[]",
                "as_is_baseline, as_is_consumers[], as_is_dependencies[]",
            ],
            "if_unresolved": "BASELINE_UNVERIFIED: no convertir la hipótesis del usuario en estado actual",
        },
        {
            "id": "A3-03-DELTA",
            "question": f"¿Qué diferencia verificable existe entre «{outcome}» y la definición/implementación actual de «{exact}»?",
            "verify": [
                f"Comparar la operación solicitada {operation!r} con el estado real del artefacto {artifact!r}",
                f"Comprobar si la capacidad declarada {capability!r} ya está cubierta o es desconocida",
                "Separar AS-IS, TO-BE declarado, modificaciones necesarias y decisiones pendientes",
                "Si no hay delta documentado, informar NO_CHANGE_CANDIDATE; no generar modificación",
            ],
            "evidence_required": common + [
                "explicit_delta o NO_CHANGE_CANDIDATE respaldado por comparación de fuentes",
                "restrictions_impact[] y unresolved_material_gaps[]",
            ],
            "if_unresolved": "DELTA_UNVERIFIED: no construir requisitos ni solución nuevos",
        },
        {
            "id": "A3-04-IMPACT",
            "question": f"¿Qué consumidores, dependencias, reglas y riesgos serían afectados al actuar sobre «{exact}»?",
            "verify": [
                "Inspeccionar consumidores y dependencias materiales con referencias comprobables",
                "Identificar contradicciones entre autoridades, efectos colaterales y controles afectados",
                "Conservar toda prohibición explícita como criterio bloqueante del delta",
            ],
            "evidence_required": common + [
                "dependency_refs[], consumer_refs[], material_risk_refs[] o brechas tipadas",
            ],
            "if_unresolved": "IMPACT_UNKNOWN: no afirmar bajo riesgo ni autorizar implementación",
        },
    ]
    for i, phrase in enumerate(constraints, 1):
        tasks.append({
            "id": f"A3-CONSTRAINT-{i:02d}",
            "literal_constraint": phrase,
            "question": f"¿La alternativa que respeta «{phrase}» puede satisfacer «{outcome}» con el artefacto existente?",
            "verify": [
                "Comparar cada alternativa propuesta contra la prohibición literal, sin reinterpretarla",
                "Rechazar cualquier alternativa que infrinja la restricción, aunque otro control parezca PASS",
            ],
            "evidence_required": common + ["constraint_compliance=PASS|FAIL|UNVERIFIED con motivo y referencia"],
            "if_unresolved": "CONSTRAINT_UNVERIFIED: no levantar prohibición ni proponer bypass",
        })
    for i, ambiguity in enumerate(pending, 1):
        tasks.append({
            "id": f"A3-AMBIGUITY-{i:02d}",
            "ambiguity_code": ambiguity["code"],
            "question": ambiguity["statement"],
            "verify": [
                "Buscar definición y comportamiento ya existentes que determinen la interpretación correcta",
                "Comparar alternativas compatibles con las restricciones declaradas",
                "No elegir por intuición una capacidad que la solicitud no especifica",
            ],
            "evidence_required": common + ["ambiguity_resolution=RESOLVED_FROM_SOURCE|STILL_OPEN con referencias"],
            "if_unresolved": "Pedir decisión al propietario solo cuando la investigación no pueda resolver una ambigüedad material",
        })
    for i, dimension in enumerate(dimensions, 1):
        tasks.append({
            "id": f"A3-DIMENSION-{i:02d}",
            "dimension": dimension,
            "question": f"¿Qué documentación o implementación vigente resuelve la dimensión «{dimension}» para «{exact}»?",
            "verify": [
                "Consultar exclusivamente las autoridades y el inventario pertinentes al target",
                "Conservar UNKNOWN si la dimensión no tiene sustento documental",
            ],
            "evidence_required": common + ["dimension_resolution=RESOLVED|UNKNOWN y fuente o gap"],
            "if_unresolved": "DIMENSION_UNKNOWN: no inferir un requisito ni una nueva capacidad",
        })
    return {
        "status": "SOURCE_RESEARCH_INSTRUCTIONS_ONLY",
        "request_literal": raw,
        "target_hint_unverified": exact,
        "requested_operation": operation,
        "artifact_hint": artifact,
        "functional_capability_hint": capability,
        "source_resolution_order": list(RESOLUTION_ORDER),
        "source_search_limit": "Buscar target exacto, luego autoridades y consumidores relacionados; ampliar solo ante brecha material",
        "source_refs_are_current_verified": False,
        "tasks": tasks,
        "acceptance_after_research": [
            "Cada hallazgo presenta fuente, versión/hash, vigencia y resultado verificable",
            "Todas las restricciones literales están preservadas y contrastadas",
            "Cada ambigüedad queda RESOLVED_FROM_SOURCE o STILL_OPEN con motivo",
            "El delta AS-IS versus objetivo es explícito o NO_CHANGE_CANDIDATE comprobado",
            "Ningún UNKNOWN se convierte en CURRENT, READY o evidencia de ausencia",
        ],
        "decision_if_no_delta": "NO_CHANGE_CANDIDATE: no modificar; verificar por evidencia antes de cerrar",
        "decision_if_evidence_missing": "NEED_MORE_EVIDENCE; no clasificar como READY",
        "decision_if_owner_only": "REQUIRES_DECISION únicamente tras agotar fuentes pertinentes",
        "a3_dispatch_allowed": False,
        "implementation_allowed": False,
    }


def prepare(a1_result: Any) -> dict:
    """Conserve reviewed-candidate content only; never promote an open A1.

    A1's reviewer reference is untrusted until verified by the governed host.
    Output is a plan for subsequent source investigation, NOT its execution.
    """
    if not isinstance(a1_result, dict) or any(
        a1_result.get(k) != v for k, v in (
            ("schema_version", "A1_INTERNAL_STEP_CANDIDATE_RESULT_V1"),
            ("skill_code", "PROGRAMMING_ANALYSIS_LF"),
            ("step_code", "A1"),
            ("status", "REQUIRES_DECISION"),
        )
    ):
        return _blocked("A2_RESEARCH_A1_DECISION_REQUIRED")
    if (a1_result.get("next_capability") is not None
            or a1_result.get("external_authority_verified") is not False
            or a1_result.get("operationally_integrated") is not False
            or a1_result.get("effects_executed") is not False
            or a1_result.get("semantic_review_identity_verified") is not False
            or a1_result.get("interpretation_state") not in (
                "SEMANTIC_CANDIDATE_UNATTESTED", "SEMANTIC_REVIEWED_CANDIDATE"
            )):
        return _blocked("A2_RESEARCH_A1_FALSE_AUTHORITY")
    business = a1_result.get("business")
    context, intent = a1_result.get("payload"), a1_result.get("intent_analysis")
    if (business != "LF"
            or not isinstance(context, dict) or not isinstance(intent, dict)
            or not isinstance(a1_result.get("semantic_reviewer_ref"), str)
            or not a1_result["semantic_reviewer_ref"].strip()):
        return _blocked("A2_RESEARCH_A1_CONTEXT_INVALID")
    raw = context.get("objective", {}).get("problem_statement") if isinstance(
        context.get("objective"), dict
    ) else None
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest() if isinstance(raw, str) else None
    if (not isinstance(raw, str) or not raw.strip()
            or a1_result.get("original_request_sha256") != digest
            or a1_result.get("semantic_candidate_sha256") != _hash(intent)):
        return _blocked("A2_RESEARCH_A1_DIGEST_MISMATCH")
    # The canonical A1 payload derives this outcome from its reviewed intent.
    # A digest over intent alone does not protect against payload tampering.
    outcome = context["objective"].get("desired_outcome")
    if (not isinstance(outcome, str) or not outcome.strip()
            or outcome != intent.get("desired_outcome")):
        return _blocked("A2_RESEARCH_DESIRED_OUTCOME_DRIFT")
    target, operation = intent.get("target"), intent.get("operation")
    if not isinstance(target, dict) or not isinstance(operation, dict):
        return _blocked("A2_RESEARCH_INTENT_UNTYPED")
    refs, hints, constraints = (
        context.get("source_refs"), context.get("target_hints"),
        context.get("constraints"),
    )
    mentions = target.get("raw_mentions")
    if (not isinstance(refs, list) or not refs
            or not all(isinstance(r, str) and r.strip() for r in refs)
            or not isinstance(hints, list) or not hints
            or not all(isinstance(h, str) and h.strip() for h in hints)
            or not isinstance(mentions, list) or not mentions
            or not all(isinstance(m, str) and m.strip() for m in mentions)
            or mentions[:1] != hints
            or not isinstance(constraints, list)
            or not all(isinstance(c, str) and c.strip() and c in raw for c in constraints)):
        return _blocked("A2_RESEARCH_SOURCE_OR_CONSTRAINT_DRIFT")
    # Prevent a consumer from deleting a negation while keeping intent hash
    # and the original text unchanged. All A1 constraints must travel intact.
    declared_constraints = intent.get("explicit_constraints")
    if (not isinstance(declared_constraints, list)
            or any(not isinstance(c, dict)
                   or not isinstance(c.get("text"), str)
                   or not c["text"].strip() for c in declared_constraints)
            or constraints != [c["text"] for c in declared_constraints]):
        return _blocked("A2_RESEARCH_EXPLICIT_CONSTRAINT_DRIFT")
    spans = intent.get("evidence_spans")
    if (not isinstance(spans, list) or not spans or any(
        not isinstance(s, dict) or type(s.get("start")) is not int
        or type(s.get("end")) is not int
        or not isinstance(s.get("quote"), str) or not s["quote"]
        or not (0 <= s["start"] < s["end"] <= len(raw))
        or raw[s["start"]:s["end"]] != s["quote"]
        for s in spans
    )):
        return _blocked("A2_RESEARCH_SEMANTIC_EVIDENCE_DRIFT")
    if any(not any(
        s.get("dimension") in ("NEGATION", "CONSTRAINT")
        and c in s["quote"] for s in spans
    ) for c in constraints):
        return _blocked("A2_RESEARCH_CONSTRAINT_SPAN_MISSING")
    ambiguities = context.get("ambiguities")
    declared = intent.get("material_ambiguities")
    if not isinstance(ambiguities, list) or not isinstance(declared, list):
        return _blocked("A2_RESEARCH_AMBIGUITY_INVALID")
    if any(not isinstance(a, dict)
           or not isinstance(a.get("code"), str) or not a["code"].strip()
           or not isinstance(a.get("statement"), str) or not a["statement"].strip()
           or a.get("materiality") not in ("MATERIAL", "UNKNOWN")
           for a in declared):
        return _blocked("A2_RESEARCH_AMBIGUITY_INVALID")
    if any(not isinstance(a, dict)
           or not isinstance(a.get("code"), str) or not a["code"].strip()
           or not isinstance(a.get("statement"), str) or not a["statement"].strip()
           for a in ambiguities):
        return _blocked("A2_RESEARCH_AMBIGUITY_INVALID")
    pending = [a for a in ambiguities if a.get("resolution_state") == "OPEN"
               and a.get("materiality") in ("MATERIAL", "UNKNOWN")]
    declared_map = {(a["code"], a["statement"], a["materiality"])
                    for a in declared}
    if (not pending or len(pending) != len(declared)
            or len({a.get("code") for a in pending}) != len(pending)
            or any((a.get("code"), a.get("statement"), a.get("materiality"))
                   not in declared_map for a in pending)):
        return _blocked("A2_RESEARCH_MATERIAL_AMBIGUITY_DRIFT")
    dims = intent.get("dimensions_to_investigate")
    if not isinstance(dims, list) or not dims or not all(isinstance(d, str) and d.strip() for d in dims):
        return _blocked("A2_RESEARCH_DIMENSIONS_INVALID")
    tasks = [
        {"ambiguity_code": a["code"], "materiality": a["materiality"],
         "question": a["statement"], "state": "OPEN",
         "priority_order": list(RESOLUTION_ORDER),
         "owner_decision": "ONLY_IF_MATERIAL_UNRESOLVED_AFTER_SOURCE_REVIEW"}
        for a in pending
    ]
    return {
        "schema_version": SCHEMA, "status": "RESEARCH_PLAN_ONLY",
        "blocking_codes": ["A1_MATERIAL_INTENT_AMBIGUITY_UNRESOLVED"],
        "business": business, "request_sha256": digest,
        "a1_semantic_candidate_sha256": _hash(intent),
        "research_plan": {
            "objective_literal": raw,
            "desired_outcome_declared": context["objective"].get("desired_outcome"),
            "operation_hint": operation.get("kind"),
            "artifact_hint": target.get("artifact_kind"),
            "functional_capability_hint": target.get("canonical_capability"),
            "target_hints": deepcopy(hints), "declared_source_refs": deepcopy(refs),
            "source_refs_are_current_verified": False,
            "constraints": deepcopy(constraints),
            "unresolved_ambiguities": deepcopy(pending),
            "dimensions_to_investigate": deepcopy(dims),
            "source_research_tasks": tasks,
            "actionable_research_order": _actionable_research_order(
                raw, context["objective"].get("desired_outcome"),
                operation.get("kind"), target.get("artifact_kind"),
                target.get("canonical_capability"), hints,
                constraints, pending, dims,
            ),
            "classification_state": "DEFERRED_UNTIL_MATERIAL_AMBIGUITIES_RESOLVED",
        },
        "a2_classification": None, "a3_canonical_inputs": None,
        "a3_dispatch_allowed": False, "a2_depth_classified": False,
        "source_authenticated": False, "independent_judge_attested": False,
        "runtime_integrated": False, "next_step": None,
    }
