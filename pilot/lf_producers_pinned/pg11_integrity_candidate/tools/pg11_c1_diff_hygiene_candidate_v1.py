"""PG-11_C1: source-only final-diff scope, residue and compatibility inventory.

Caller-supplied manifests are *untrusted*. A matching digest does not prove
that a real Git diff was read. No PR status, merge or release authority.
"""
import hashlib
import json
import posixpath
import re
from copy import deepcopy

HASH = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
RESIDUES = {"DEBUG", "DEAD_CODE", "TODO_WITHOUT_TICKET"}
CHANGES = {"ADDED", "MODIFIED", "DELETED", "RENAMED"}
DEPENDENCY = {"ADDED", "REMOVED", "CHANGED"}
COMPATIBILITY = {"API", "SCHEMA", "DEPENDENCY", "RUNTIME", "MODULE_CONTRACT"}

class PG11C1Blocked(ValueError):
    pass

def fail(code):
    raise PG11C1Blocked(code)

def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()

def string(v):
    return isinstance(v, str) and bool(v.strip()) and v == v.strip()

def path(v):
    return (string(v) and not v.startswith("/") and "\\" not in v and
            not any(c in v for c in ("\x00", "\n", "\r")) and
            posixpath.normpath(v) == v and v not in (".", "..") and
            not v.startswith("../") and "/../" not in v)

def files_index(rows, *, label):
    if not isinstance(rows, list):
        fail("PG11_C1_" + label + "_INVALID")
    out = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "change_type", "old_path"}:
            fail("PG11_C1_" + label + "_SHAPE_INVALID")
        p, change, old = row["path"], row["change_type"], row["old_path"]
        if not path(p) or p in out or change not in CHANGES:
            fail("PG11_C1_" + label + "_ENTRY_INVALID")
        if (change == "RENAMED") != (old is not None) or (old is not None and (not path(old) or old == p)):
            fail("PG11_C1_" + label + "_RENAME_INVALID")
        out[p] = deepcopy(row)
    return out

def prepare_pg11_c1(*, expected_base_sha, expected_head_sha, declared_diff,
                    authorized_scope, residue_observations,
                    dependency_observations, compatibility_observations):
    """Construct an exact-coverage, non-authoritative audit *plan*.

    declared_diff: [{path, change_type, old_path}]
    authorized_scope: [{path, change_type, old_path, scope_ref, requirement_ref, batch_ref}]
    residue_observations: [{path, kind, line_ref, ticket_ref}] where ticket_ref
        is mandatory for TODO_WITHOUT_TICKET if the finding must be cleared.
    dependency_observations: [{path, change_type, dependency_ref, baseline_ref,
                               compatibility_evidence_ref}]
    compatibility_observations: [{surface, contract_ref, baseline_ref,
                                  evidence_ref, compatible_reported}]
    """
    if not all(isinstance(x, str) and HASH.fullmatch(x) for x in
               (expected_base_sha, expected_head_sha)) or expected_base_sha == expected_head_sha:
        fail("PG11_C1_COMMIT_PAIR_INVALID")
    diff = files_index(declared_diff, label="DIFF")
    if not diff:
        fail("PG11_C1_EMPTY_DIFF_UNVERIFIABLE")
    if not isinstance(authorized_scope, list):
        fail("PG11_C1_SCOPE_INVALID")
    scope = {}
    for row in authorized_scope:
        if not isinstance(row, dict) or set(row) != {
            "path", "change_type", "old_path", "scope_ref", "requirement_ref", "batch_ref"
        }:
            fail("PG11_C1_SCOPE_SHAPE_INVALID")
        p = row["path"]
        if not path(p) or p in scope or row["change_type"] not in CHANGES:
            fail("PG11_C1_SCOPE_ENTRY_INVALID")
        old = row["old_path"]
        if (row["change_type"] == "RENAMED") != (old is not None) or (
            old is not None and (not path(old) or old == p)
        ):
            fail("PG11_C1_SCOPE_RENAME_INVALID")
        if not all(string(row[k]) for k in ("scope_ref", "requirement_ref", "batch_ref")):
            fail("PG11_C1_SCOPE_PROVENANCE_MISSING")
        scope[p] = deepcopy(row)
    outside = sorted(set(diff) - set(scope))
    unmatched = sorted(set(scope) - set(diff))
    mismatched = sorted(p for p in set(diff) & set(scope)
                        if any(diff[p][k] != scope[p][k] for k in ("change_type", "old_path")))
    if not isinstance(residue_observations, list):
        fail("PG11_C1_RESIDUES_INVALID")
    residues = []
    seen = set()
    for row in residue_observations:
        if not isinstance(row, dict) or set(row) != {"path", "kind", "line_ref", "ticket_ref"}:
            fail("PG11_C1_RESIDUE_SHAPE_INVALID")
        p, kind = row["path"], row["kind"]
        if p not in diff or kind not in RESIDUES or not string(row["line_ref"]):
            fail("PG11_C1_RESIDUE_ENTRY_INVALID")
        key = (p, kind, row["line_ref"])
        if key in seen:
            fail("PG11_C1_DUPLICATE_RESIDUE")
        seen.add(key)
        ticket = row["ticket_ref"]
        if ticket is not None and not string(ticket):
            fail("PG11_C1_TICKET_REFERENCE_INVALID")
        residues.append({"path": p, "kind_reported": kind,
                         "line_ref_reported": row["line_ref"],
                         "ticket_ref_reported": ticket,
                         "unresolved_reported": kind != "TODO_WITHOUT_TICKET" or ticket is None,
                         "verified_in_real_diff": False})
    if not isinstance(dependency_observations, list):
        fail("PG11_C1_DEPENDENCIES_INVALID")
    dependencies = []
    seen_deps = set()
    for row in dependency_observations:
        fields = {"path", "change_type", "dependency_ref", "baseline_ref",
                  "compatibility_evidence_ref"}
        if not isinstance(row, dict) or set(row) != fields:
            fail("PG11_C1_DEPENDENCY_SHAPE_INVALID")
        if (row["path"] not in diff or row["change_type"] not in DEPENDENCY or
            not all(string(row[k]) for k in ("dependency_ref", "baseline_ref",
                                             "compatibility_evidence_ref"))):
            fail("PG11_C1_DEPENDENCY_ENTRY_INVALID")
        key = (row["path"], row["dependency_ref"])
        if key in seen_deps:
            fail("PG11_C1_DEPENDENCY_DUPLICATE")
        seen_deps.add(key)
        dependencies.append({**deepcopy(row), "verified_from_lockfile": False,
                             "compatibility_verified": False})
    if not isinstance(compatibility_observations, list) or not compatibility_observations:
        fail("PG11_C1_COMPATIBILITY_EVIDENCE_REQUIRED")
    compatibility = []
    surfaces = set()
    for row in compatibility_observations:
        fields = {"surface", "contract_ref", "baseline_ref",
                  "evidence_ref", "compatible_reported"}
        if not isinstance(row, dict) or set(row) != fields:
            fail("PG11_C1_COMPATIBILITY_SHAPE_INVALID")
        surface = row["surface"]
        if (surface not in COMPATIBILITY or surface in surfaces or
            not all(string(row[k]) for k in ("contract_ref", "baseline_ref", "evidence_ref")) or
            type(row["compatible_reported"]) is not bool):
            fail("PG11_C1_COMPATIBILITY_ENTRY_INVALID")
        surfaces.add(surface)
        compatibility.append({**deepcopy(row), "evidence_authenticated": False,
                              "compatibility_verified": False})
    findings = {
        "out_of_scope_paths_reported": outside,
        "authorized_scope_without_diff_reported": unmatched,
        "scope_change_mismatches_reported": mismatched,
        "residue_findings_reported": len(residues),
        "residues_unresolved_reported": sum(x["unresolved_reported"] for x in residues),
        "dependency_changes_reported": len(dependencies),
        "incompatibilities_reported": sorted(x["surface"] for x in compatibility
                                              if x["compatible_reported"] is False),
    }
    blockers = []
    if outside or unmatched or mismatched:
        blockers.append("SCOPE_INVENTORY_MISMATCH")
    if findings["residues_unresolved_reported"]:
        blockers.append("RESIDUES_DECLARED")
    if findings["incompatibilities_reported"]:
        blockers.append("COMPATIBILITY_RISK_DECLARED")
    result = {
        "schema_version": "PG11_C1_DIFF_HYGIENE_CANDIDATE_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "expected_base_sha": expected_base_sha,
        "expected_head_sha": expected_head_sha,
        "declared_diff_sha256": digest(declared_diff),
        "authorized_scope_sha256": digest(authorized_scope),
        "residue_observations_sha256": digest(residue_observations),
        "dependency_observations_sha256": digest(dependency_observations),
        "compatibility_observations_sha256": digest(compatibility_observations),
        "findings": findings,
        "declared_residues": sorted(residues, key=lambda x: (x["path"], x["line_ref"])),
        "declared_dependency_changes": sorted(dependencies, key=lambda x: (x["path"], x["dependency_ref"])),
        "declared_compatibility": sorted(compatibility, key=lambda x: x["surface"]),
        "blocker_hints": sorted(blockers),
        "real_git_diff_readback_verified": False,
        "authorized_scope_provenance_verified": False,
        "static_residue_scan_executed": False,
        "dependency_lockfile_readback_verified": False,
        "compatibility_tests_executed": False,
        "clean_diff_verified": False,
        "pg11_c1_pass": False, "pg11_c1_admitted": False,
        "handoff_allowed": False, "production_authority": False,
        "next_gate": "REAL_GIT_DIFF_SCOPE_RESIDUE_AND_COMPATIBILITY_READBACK"
    }
    result["candidate_sha256"] = digest(result)
    return deepcopy(result)
