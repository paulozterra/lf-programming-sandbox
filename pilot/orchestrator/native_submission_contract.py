"""T19 public, deterministic native proposal handoff contract.

Derived solely from the frozen Worker envelope and patch proposal schema.
Never writes or reads a private exam or invokes a model.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

CONTRACT_VERSION = "LF_NATIVE_PROPOSAL_SUBMISSION_V1"
FORMAT = "canonical_json_bytes(proposal): UTF-8 JSON; sort_keys=True, separators=(',', ':'), ensure_ascii=False"
FIELDS = ["task_pack_sha256", "proposal_sha256", "proposal", "author"]


def canonical(data: object) -> bytes:
    # Match programming_agent_runner.hashutil.canonical_json_bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def proposal_submission_contract(task: str, spec: dict) -> dict:
    paths = spec.get("write_path_patterns", [])
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
        raise ValueError("NATIVE_SUBMISSION_WRITE_SCOPE_INVALID")
    sample_path = paths[0]
    diff = ("diff --git a/" + sample_path + " b/" + sample_path +
            "\n--- a/" + sample_path + "\n+++ b/" + sample_path +
            "\n@@ -1 +1 @@\n-old line\n+new line\n")
    proposal = {
        "schema_version": 1,
        "summary": "Ejemplo de reemplazo: usar un diff real de la tarea",
        "patch": diff,
        "changed_paths": [sample_path],
    }
    return {
        "schema_version": CONTRACT_VERSION,
        "envelope_path": f"pilot/native_proposals/{task}.json",
        "branch": f"lf/native-proposal/{task}",
        "envelope_fields_exact": FIELDS,
        "author_literal": "GPT_NATIVE",
        "proposal_sha256": {
            "algorithm": "SHA-256",
            "input": FORMAT,
            "python": "hashlib.sha256(json.dumps(proposal, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()",
        },
        "proposal_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version", "summary", "patch", "changed_paths"],
            "properties": {
                "schema_version": {"const": 1},
                "summary": {"type": "string", "minLength": 1, "maxUtf8Bytes": 4000},
                "patch": {"type": "string", "format": "git-unified-diff-utf8"},
                "changed_paths": {"type": "array", "minItems": 1, "items": {"type": "string"},
                                  "sortedUnique": True},
            },
            "max_changed_files": spec.get("max_changed_files"),
            "max_patch_bytes": spec.get("max_patch_bytes"),
            "write_path_patterns": paths,
            "protected_path_patterns": spec.get("protected_path_patterns", []),
        },
        "proposal_example": proposal,
        "base_commit_rule": {
            "required": "El commit del sobre debe ser descendiente del main confiable verificado por el guard en el momento de recibir el push; NO basta descender de task_spec.base_head_sha.",
            "scope": "Desde ese main hasta el HEAD, cada commit cambia solo el mismo archivo envelope_path; sin merges, renames ni otros archivos.",
            "only_one_file": True,
            "no_direct_source_push": True,
        },
        "steps": [
            "Construir un git unified diff UTF-8 solo de los archivos write_path_patterns autorizados; no comitear los archivos fuente en la rama de propuesta.",
            "Crear proposal con exactamente schema_version, summary, patch y changed_paths; changed_paths ordenados, únicos y coincidentes con el diff.",
            "Calcular proposal_sha256 sobre los bytes JSON canónicos de proposal (no del sobre ni del patch por separado).",
            "Crear en envelope_path un objeto JSON con exactamente task_pack_sha256 (tomado de proposal-request.json), proposal_sha256, proposal y author='GPT_NATIVE'.",
            "Crear la rama indicada desde main confiable actualizado, comitear UNICAMENTE envelope_path y hacer push de esa rama.",
            "Un push inválido falla guard y se notifica con código exacto; nunca se ejecuta código de la rama.",
        ],
    }


def enrich_request(request: dict, spec: dict) -> dict:
    task = request.get("task_name")
    if not isinstance(task, str) or not task:
        raise ValueError("NATIVE_SUBMISSION_TASK_INVALID")
    result = dict(request)
    result["submission"] = proposal_submission_contract(task, spec)
    return result


def is_current(request: dict, spec: dict) -> bool:
    return request.get("submission") == proposal_submission_contract(request["task_name"], spec)
