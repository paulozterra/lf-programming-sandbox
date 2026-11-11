"""A3 policy projection: existing effective-rule inventory + LF screen contract.

The host acquires lf_ops.reglas.valor_config and the existing
lf_ops.fn_screen_contract_v1 contract.policies (no extra resolver or SQL here).
A source readback is not a currentness attestation or runtime permission.
"""
from __future__ import annotations
from copy import deepcopy
import re
from typing import Any

POLICY_TABLE = re.compile(r"^lf_ops\.politicas_[a-z][a-z0-9_]*$")
POLICY_PK = re.compile(r"^[a-z][a-z0-9_]*_policy_id$")


def blocked(code: str) -> dict:
    return {"status": "BLOCKED", "blocking_code": code}


def _references(config: Any, prefix: str = "$") -> list[dict]:
    result = []
    if isinstance(config, dict):
        for key, val in config.items():
            pointer = prefix + "/" + str(key).replace("~", "~0").replace("/", "~1")
            if key.endswith("_policy_id"):
                if type(val) is int and val > 0:
                    result.append({"role": key, "id": val, "path": pointer})
                elif val is not None:
                    result.append({"role": key, "id": None, "path": pointer,
                                   "unresolved_reason": "POLICY_ID_NOT_POSITIVE_INTEGER"})
            elif key in ("relation_key", "relation_keys"):
                # Generic declared linkage can reference a central policy
                # without duplicating its numeric ID inside the rule.
                roles = [val] if isinstance(val, str) else val if isinstance(val, list) else []
                for role in roles:
                    if isinstance(role, str) and role.endswith("_policy_id"):
                        result.append({"role": role, "id": None, "path": pointer,
                                       "reference_kind": "DECLARED_POLICY_ROLE"})
            elif isinstance(val, (dict, list)):
                result.extend(_references(val, pointer))
    elif isinstance(config, list):
        for i, val in enumerate(config):
            if isinstance(val, (dict, list)):
                result.extend(_references(val, prefix + "/" + str(i)))
    return result


def project(effective: Any, policy_links: Any, readback: Any,
            *, target_ref: str, screen_ref: str) -> dict:
    if not isinstance(readback, dict):
        return blocked("A3_POLICY_DEFINITIONS_READ_REQUIRED")
    if (readback.get("schema_version") != "LF_SCREEN_POLICIES_READBACK_V1"
            or readback.get("source_function") != "lf_ops.fn_screen_contract_v1"
            or readback.get("business") != "LF"
            or readback.get("target_ref") != target_ref
            or readback.get("source_ref") != screen_ref
            or readback.get("source_attested") is not False):
        return blocked("A3_POLICY_DEFINITIONS_SOURCE_IDENTITY_INVALID")
    if (not isinstance(effective, dict)
            or not isinstance(effective.get("rules"), list)
            or not isinstance(policy_links, list)):
        return blocked("A3_POLICY_INVENTORY_INPUT_INVALID")
    records = readback.get("policy_objects")
    if not isinstance(records, list):
        return blocked("A3_POLICY_DEFINITIONS_ITEMS_MISSING")
    supplemental = readback.get("supplemental_policy_source_refs")
    if not isinstance(supplemental, list) or any(
        not isinstance(x, str) or not x.startswith("supabase://lf_ops.politicas_")
        for x in supplemental
    ) or len(supplemental) != len(set(supplemental)):
        return blocked("A3_SUPPLEMENTAL_POLICY_SOURCE_INVENTORY_REQUIRED")
    by_ref, by_key, approved_objects, excluded_objects = {}, {}, [], []
    for obj in records:
        if not isinstance(obj, dict):
            return blocked("A3_POLICY_OBJECT_INVALID")
        table, pk, pid = obj.get("table"), obj.get("primary_key"), obj.get("policy_id")
        status, policy_code = obj.get("status"), obj.get("policy_code")
        values = obj.get("parameters")
        if (not isinstance(table, str) or not POLICY_TABLE.fullmatch(table)
                or not isinstance(pk, str) or not POLICY_PK.fullmatch(pk)
                or type(pid) is not int or pid < 1
                or not isinstance(policy_code, str) or not policy_code
                or not isinstance(status, str) or not status
                or not isinstance(values, dict) or not values):
            return blocked("A3_POLICY_OBJECT_SOURCE_FIELDS_INVALID")
        ref = "supabase://" + table + "/" + str(pid)
        if obj.get("source_ref") != ref or ref in by_ref:
            return blocked("A3_POLICY_OBJECT_DUPLICATE_OR_REF_DRIFT")
        origin = obj.get("read_origin")
        if origin == "DIRECT_CANONICAL_POLICY_LOOKUP":
            if ref not in supplemental or obj.get("read_source_ref") != ref:
                return blocked("A3_SUPPLEMENTAL_POLICY_PROVENANCE_MISSING")
        elif origin == "LF_SCREEN_CONTRACT":
            if ref in supplemental or obj.get("read_source_ref") != screen_ref:
                return blocked("A3_SCREEN_CONTRACT_POLICY_PROVENANCE_MISMATCH")
        else:
            return blocked("A3_POLICY_OBJECT_ORIGIN_NOT_DECLARED")
        entry = {"source_ref": ref, "policy_code": policy_code,
                 "read_origin": origin, "read_source_ref": obj["read_source_ref"],
                 "status": status, "parameter_values": deepcopy(values),
                 "source_attested": False}
        by_ref[ref] = entry
        by_key[ref] = (table, pk, pid)
        (approved_objects if status == "VIGENTE" else excluded_objects).append(entry)
    if set(supplemental) != {
        obj["source_ref"] for obj in records
        if obj["read_origin"] == "DIRECT_CANONICAL_POLICY_LOOKUP"
    }:
        return blocked("A3_SUPPLEMENTAL_POLICY_SOURCES_UNRECONCILED")
    bindings = {}
    link_items = []
    for link in policy_links:
        if not isinstance(link, dict):
            return blocked("A3_POLICY_LINK_INVALID")
        target = link.get("policy_target_ref")
        role = link.get("reference_role")
        status = link.get("status")
        if (not isinstance(target, str) or not target.startswith("supabase://lf_ops.")
                or not isinstance(role, str) or not role.endswith("_policy_id")
                or not isinstance(status, str) or not status):
            return blocked("A3_POLICY_LINK_TARGET_UNRESOLVED")
        if target not in by_ref:
            return blocked("A3_POLICY_LINK_TARGET_NOT_READ")
        if not role.endswith(by_key[target][1]):
            return blocked("A3_POLICY_LINK_ROLE_TARGET_MISMATCH")
        key = (role, target)
        if key in bindings:
            return blocked("A3_POLICY_LINK_DUPLICATE")
        bindings[key] = status
        link_items.append({
            "source_ref": link["source_ref"], "reference_role": role,
            "policy_target_ref": target, "link_status": status,
            "policy_status": by_ref[target]["status"],
            "approved_for_binding": status == "VIGENTE" and by_ref[target]["status"] == "VIGENTE",
        })
    dependencies, impacted, eligible = [], set(), set()
    total_refs = 0
    for row in effective["rules"]:
        if not isinstance(row, dict) or "config" not in row:
            return blocked("A3_POLICY_RULE_CONFIG_READ_REQUIRED")
        code, status, pending = row.get("code"), row.get("status"), row.get("pending_decision")
        if not isinstance(code, str) or status is None or type(pending) is not bool:
            return blocked("A3_POLICY_RULE_STATUS_INVALID")
        if status != "VIGENTE" or pending:
            continue
        config = row["config"]
        if config is not None and not isinstance(config, (dict, list)):
            return blocked("A3_POLICY_RULE_CONFIG_INVALID")
        refs = _references(config)
        numeric_roles = {p["role"] for p in refs if p["id"] is not None}
        # A declared relation is satisfied by a more specific numeric role,
        # e.g. security_policy_id by mfa_security_policy_id.
        refs = [
            p for p in refs
            if p["id"] is not None or not any(
                r == p["role"] or r.endswith(p["role"]) for r in numeric_roles
            )
        ]
        if not refs:
            eligible.add(code)
            continue
        applicable = True
        for p in refs:
            total_refs += 1
            if p["id"] is None and p.get("reference_kind") == "DECLARED_POLICY_ROLE":
                options = [target for (role, target) in bindings if role == p["role"]]
            else:
                options = [ref for ref, (_table, pk, pid) in by_key.items()
                           if p["role"].endswith(pk) and p["id"] == pid]
            if (p["id"] is None and p.get("reference_kind") != "DECLARED_POLICY_ROLE") or len(options) > 1:
                dependencies.append({
                    "rule_code": code, "reference_role": p["role"], "path": p["path"],
                    "status": "UNRESOLVED_POLICY_REFERENCE", "eligible_for_implementation": False,
                })
                applicable = False
                continue
            target = options[0] if options else None
            obj = by_ref.get(target) if target else None
            bind_status = bindings.get((p["role"], target))
            binding_role = p["role"] if bind_status is not None else None
            # A generic policy PK may be bound by ONE exact-target specialised
            # role on this screen. Resolve by target, never numeric ID alone.
            alias_links = []
            if obj is not None and bind_status is None and p["role"] == by_key[target][1]:
                alias_links = [(role, state) for (role, ref), state in bindings.items()
                               if ref == target and role.endswith(p["role"])]
                if len(alias_links) == 1:
                    binding_role, bind_status = alias_links[0]
            # E.g. trusted_device_policy_id does not mean security_policy_id.
            # An equal numeric ID can only be an untyped observation.
            untyped_id_observation = None
            if obj is None and p["id"] is not None and not any(
                p["role"].endswith(pk) for _table, pk, _pid in by_key.values()
            ):
                id_matches = [ref for ref, (_table, _pk, pid) in by_key.items()
                              if pid == p["id"]]
                if len(id_matches) == 1:
                    observed = by_ref[id_matches[0]]
                    untyped_id_observation = {
                        "source_ref": id_matches[0],
                        "policy_code": observed["policy_code"],
                        "status": observed["status"],
                        "relation_attested": False,
                        "observation_basis": "NUMERIC_ID_ONLY_NOT_TYPED_BINDING",
                    }
                    disposition = "POLICY_REFERENCE_TYPE_UNBOUND_OBJECT_OBSERVED"
                elif len(id_matches) > 1:
                    disposition = "POLICY_REFERENCE_TYPE_UNBOUND_AMBIGUOUS_ID"
                else:
                    disposition = "POLICY_REFERENCE_TYPE_UNBOUND_NO_OBJECT"
            elif obj is None:
                disposition = "POLICY_TARGET_MISSING"
            elif obj["status"] != "VIGENTE":
                disposition = "POLICY_NOT_VIGENTE"
            elif len(alias_links) > 1:
                disposition = "POLICY_BINDING_ROLE_AMBIGUOUS"
            elif bind_status == "VIGENTE":
                disposition = "APPROVED_POLICY_AND_BINDING"
            else:
                # Approved central object cannot turn a candidate or unknown
                # screen-level association into a granted implementation.
                disposition = "POLICY_BINDING_NOT_APPROVED_OR_UNRESOLVED"
            ok = disposition == "APPROVED_POLICY_AND_BINDING"
            applicable = applicable and ok
            dependencies.append({
                "rule_code": code, "reference_role": p["role"], "path": p["path"],
                "reference_kind": p.get("reference_kind", "NUMERIC_POLICY_ID"),
                "policy_target_ref": target,
                "policy_status": obj["status"] if obj else (
                    "UNBOUND_TYPE" if untyped_id_observation else "NOT_FOUND"),
                "policy_code": obj["policy_code"] if obj else None,
                "binding_status": bind_status or "NOT_FOUND",
                "binding_role": binding_role,
                "status": disposition,
                "untyped_id_observation": untyped_id_observation,
                "eligible_for_implementation": ok,
            })
        if applicable:
            eligible.add(code)
        else:
            impacted.add(code)
    return {
        "status": "POLICIES_PROJECTED_UNATTESTED",
        "policy_source_ref": screen_ref, "policy_source_function": readback["source_function"],
        "supplemental_policy_source_refs": supplemental[:],
        "approved_policy_objects": approved_objects,
        "excluded_policy_objects": excluded_objects,
        "policy_link_resolution": link_items,
        "rule_policy_dependencies": dependencies,
        "rule_codes_policy_dependency_pending": sorted(impacted),
        "rule_codes_without_unapproved_policy_dependency": sorted(eligible),
        "counts": {
            "policy_objects": len(records),
            "policy_objects_vigente": len(approved_objects),
            "policy_objects_excluded": len(excluded_objects),
            "screen_policy_links": len(policy_links),
            "rules_with_unapproved_or_unresolved_policy": len(impacted),
            "referenced_policy_occurrences": total_refs,
        },
        "source_attested": False, "currentness_attested": False,
        "no_write_performed": True, "a4_allowed": False,
    }
