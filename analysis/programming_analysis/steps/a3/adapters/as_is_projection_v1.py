"""Generic A3 projection of existing GitHub AS-IS and canonical authority readbacks.

No new source resolver. Existing governed provider fetches typed references.
The projection NEVER attests source CURRENT, full target implementation or RUN.
"""
from __future__ import annotations
from copy import deepcopy
import re
from typing import Any

SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PATH = re.compile(r"^[A-Za-z0-9_./()@-]+$")


def project(readback: Any, target_ref: str) -> dict:
    def rejected(code: str) -> dict:
        return {"status": "BLOCKED", "blocking_code": code}
    if not isinstance(readback, dict) or readback.get("target_ref") != target_ref:
        return rejected("A3_AS_IS_TARGET_BINDING_MISSING")
    if readback.get("business") != "LF":
        return rejected("A3_AS_IS_BUSINESS_MISMATCH")
    github, authority = readback.get("github"), readback.get("authority")
    if not isinstance(github, dict) or not isinstance(authority, dict):
        return rejected("A3_AS_IS_AND_AUTHORITY_BOTH_REQUIRED")
    repo, commit = github.get("repository"), github.get("commit_sha")
    if (not isinstance(repo, str) or not REPO.fullmatch(repo)
            or not isinstance(commit, str) or not SHA.fullmatch(commit)
            or github.get("source_attested") is not False
            or github.get("currentness_attested") is not False
            or github.get("runtime_authorized") is not False):
        return rejected("A3_GITHUB_AS_IS_SOURCE_UNQUALIFIED")
    ref = authority.get("source_ref")
    if (not isinstance(ref, str)
            or not (ref.startswith("contract://") or ref.startswith("supabase://"))
            or authority.get("status") not in ("defined", "CANDIDATO", "VIGENTE", "deprecated")
            or type(authority.get("version_id")) is not int
            or authority.get("version_id") < 1
            or type(authority.get("logical_only")) is not bool
            or authority.get("runtime_activation") is not False
            or authority.get("currentness_attested") is not False):
        return rejected("A3_AUTHORITY_SOURCE_UNQUALIFIED")
    binding = authority.get("physical_binding")
    if not isinstance(binding, dict):
        return rejected("A3_AUTHORITY_BINDING_MISSING")
    components = github.get("observed_components")
    if not isinstance(components, list) or not components:
        return rejected("A3_AS_IS_COMPONENT_SOURCE_MISSING")
    refs, seen, typed = [], set(), []
    for row in components:
        if not isinstance(row, dict):
            return rejected("A3_AS_IS_COMPONENT_INVALID")
        path, sha, scope = row.get("path"), row.get("blob_sha1"), row.get("scope")
        if (not isinstance(path, str) or not PATH.fullmatch(path)
                or path.startswith("/") or ".." in path.split("/")
                or not isinstance(sha, str) or not SHA.fullmatch(sha)
                or not isinstance(scope, str) or not scope.strip()
                or len(scope) > 100 or path in seen):
            return rejected("A3_AS_IS_COMPONENT_REF_INVALID")
        seen.add(path)
        source_ref = "github://"+repo+"@"+commit+"/"+path+"#blob="+sha
        refs.append(source_ref)
        typed.append({
            "component_scope": scope, "path": path, "source_ref": source_ref,
            "observation": "CODE_EXISTS_IN_REPO",
            "target_implementation_confirmed": False,
            "source_attested": False,
        })
    gaps = [
        "TARGET_IMPLEMENTATION_NOT_CONFIRMED",
        "GITHUB_SOURCE_CURRENTNESS_NOT_ATTESTED",
        "AUTHORITY_CURRENTNESS_NOT_ATTESTED",
    ]
    if authority["status"] != "VIGENTE":
        gaps.append("AUTHORITY_NOT_VIGENTE")
    if authority["logical_only"] and any(v == "UNBOUND" for v in binding.values()):
        gaps.append("LOGICAL_CONTRACT_PHYSICAL_BINDING_UNBOUND")
    return {
        "status": "RELATED_AS_IS_FOUND_TARGET_UNKNOWN",
        "business": "LF", "target_ref": target_ref,
        "related_components": typed,
        "source_refs": refs+[ref],
        "authority_candidate": {
            "source_ref": ref, "status": authority["status"],
            "version_id": authority["version_id"],
            "physical_binding": deepcopy(binding),
            "currentness": "UNKNOWN",
        },
        "authority_state": "UNKNOWN", "implementation_state": "UNKNOWN",
        "material_gaps": gaps, "currentness_refs": [],
        "source_attested": False, "a4_allowed": False,
    }
