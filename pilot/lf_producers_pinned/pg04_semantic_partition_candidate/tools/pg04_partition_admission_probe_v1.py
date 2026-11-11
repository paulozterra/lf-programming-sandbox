"""Offline PG-04 C1/C2 candidate inspection. No partition generation or authority."""
import hashlib
import json

class PartitionProbeBlocked(ValueError):
    pass

def _deny(code):
    raise PartitionProbeBlocked(code)

def _ids(rows, label, allow_empty=False):
    if not isinstance(rows, list) or (not rows and not allow_empty) or any(not isinstance(x, str) or not x.strip() for x in rows) or len(rows) != len(set(rows)):
        _deny(label + "_INVALID")
    return set(rows)

def inspect_candidate(*, partition_policy, strategy, source_refs, solutions):
    """Inspect externally proposed semantic solutions; never produce partitions."""
    if not isinstance(partition_policy, dict) or partition_policy.get("schema_version") != "PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1" or partition_policy.get("unit") != "PG-04" or partition_policy.get("runtime_activation") is not False or partition_policy.get("production_activation") is not False:
        _deny("PG04_SOURCE_CONTRACT_INVALID")
    policy = partition_policy.get("partition_policy")
    coverage = partition_policy.get("coverage")
    if not isinstance(policy, dict) or not isinstance(coverage, dict):
        _deny("PG04_POLICY_INVALID")
    if any(policy.get(k) is not True for k in (
            "semantic_boundary_first", "dependency_closure_required",
            "risk_boundary_considered", "write_scope_boundary_considered",
            "shared_contracts_referenced_not_copied",
            "token_count_alone_must_not_define_partition",
            "file_count_alone_must_not_define_partition")) or (
            policy.get("partition_unit") != "SOLUTION" or
            policy.get("minimum_rule") != "SMALLEST_COHERENT_VALID_CHANGE" or
            policy.get("canonical_spec_count") != 1 or
            coverage.get("material_requirement_coverage_required_percent") != 100 or
            coverage.get("acceptance_obligation_coverage_required_percent") != 100):
        _deny("PG04_POLICY_DRIFT")
    if not isinstance(strategy, dict) or strategy.get("status") != "CANDIDATE_NOT_ADMITTED" or strategy.get("handoff_allowed") is not False or strategy.get("production_authority") is not False:
        _deny("PG03_STRATEGY_NOT_CANDIDATE")
    digest = strategy.get("candidate_sha256")
    raw = json.dumps({k: v for k, v in strategy.items() if k != "candidate_sha256"}, sort_keys=True, separators=(",", ":")).encode()
    if not isinstance(digest, str) or len(digest) != 64 or hashlib.sha256(raw).hexdigest() != digest:
        _deny("PG03_STRATEGY_DIGEST_DRIFT")
    if not isinstance(source_refs, dict) or any(
            not isinstance(source_refs.get(k), str) or not source_refs[k].strip()
            for k in ("contract_path", "contract_commit", "j02_source_path", "j02_source_commit")):
        _deny("SOURCE_TRACE_MISSING")
    if not isinstance(solutions, list) or not solutions:
        _deny("NO_SOLUTION_CANDIDATES")
    seen = set()
    dependency_graph = {}
    req_owners = {}
    acc_owners = {}
    for sol in solutions:
        if not isinstance(sol, dict) or not isinstance(sol.get("id"), str) or not sol["id"].strip() or sol["id"] in seen:
            _deny("SOLUTION_ID_INVALID")
        sid = sol["id"]
        seen.add(sid)
        if sol.get("strategy_ref") != digest:
            _deny("STRATEGY_REF_DRIFT")
        if sol.get("partition_basis") != "SEMANTIC_SOLUTION":
            _deny("FILE_OR_TOKEN_BASED_PARTITION_FORBIDDEN")
        for key in ("business_outcome", "semantic_boundary_reason", "risk_boundary_reason", "write_scope_reason"):
            if not isinstance(sol.get(key), str) or not sol[key].strip():
                _deny("SEMANTIC_RATIONALE_MISSING")
        if not isinstance(sol.get("write_scope"), list):
            _deny("WRITE_SCOPE_MISSING")
        if "shared_contracts" in sol:
            _deny("INLINE_SHARED_CONTRACT_FORBIDDEN")
        refs = sol.get("shared_contract_refs")
        if not isinstance(refs, list) or any(not isinstance(x, str) or not x.strip() for x in refs) or len(set(refs)) != len(refs):
            _deny("SHARED_CONTRACT_REFS_INVALID")
        state = sol.get("implementation_state")
        if state not in ("EXISTING", "NEW"):
            _deny("IMPLEMENTATION_STATE_MISSING")
        if state == "EXISTING" and (
                not isinstance(sol.get("as_is_ref"), str) or not sol["as_is_ref"].strip() or
                not isinstance(sol.get("delta_ref"), str) or not sol["delta_ref"].strip()):
            _deny("EXISTING_DELTA_MISSING")
        if state == "NEW" and (
                not isinstance(sol.get("bounded_reuse_assessment_ref"), str) or
                not sol["bounded_reuse_assessment_ref"].strip()):
            _deny("NEW_REUSE_ASSESSMENT_MISSING")
        if state == "EXISTING" and "bounded_reuse_assessment_ref" in sol:
            _deny("EXISTING_CONTAINS_NEW_EVIDENCE")
        if state == "NEW" and ("as_is_ref" in sol or "delta_ref" in sol):
            _deny("NEW_CONTAINS_EXISTING_EVIDENCE")
        # Detailed source bindings are optional for older caller-supplied shapes;
        # when present, each atom must preserve the exact solution state/evidence.
        if "source_bindings" in sol:
            bindings = sol["source_bindings"]
            if not isinstance(bindings, list) or not bindings:
                _deny("ATOM_IMPLEMENTATION_BINDINGS_INVALID")
            bound_ids = set()
            for atom in bindings:
                if not isinstance(atom, dict) or not isinstance(atom.get("atom_id"), str) or not atom["atom_id"].strip() or atom["atom_id"] in bound_ids:
                    _deny("ATOM_IMPLEMENTATION_BINDINGS_INVALID")
                bound_ids.add(atom["atom_id"])
                if atom.get("implementation_state") != state:
                    _deny("ATOM_IMPLEMENTATION_STATE_DRIFT")
                if state == "EXISTING":
                    if atom.get("as_is_ref") != sol["as_is_ref"] or atom.get("delta_ref") != sol["delta_ref"] or "bounded_reuse_assessment_ref" in atom:
                        _deny("ATOM_IMPLEMENTATION_EVIDENCE_DRIFT")
                elif atom.get("bounded_reuse_assessment_ref") != sol["bounded_reuse_assessment_ref"] or "as_is_ref" in atom or "delta_ref" in atom:
                    _deny("ATOM_IMPLEMENTATION_EVIDENCE_DRIFT")
            if "atom_ids" in sol:
                ids = sol["atom_ids"]
                if (not isinstance(ids, list) or
                    any(not isinstance(aid, str) or not aid.strip() for aid in ids) or
                    len(ids) != len(set(ids)) or set(ids) != bound_ids):
                    _deny("ATOM_IMPLEMENTATION_BINDINGS_INVALID")
        for key, owners in (("requirement_ids", req_owners), ("acceptance_ids", acc_owners)):
            for identifier in _ids(sol.get(key), key.upper(), allow_empty=True):
                if identifier in owners:
                    _deny("DUPLICATE_MATERIAL_OWNERSHIP")
                owners[identifier] = sid
        if not sol["requirement_ids"] and not sol["acceptance_ids"]:
            _deny("SOLUTION_WITHOUT_MATERIAL_OBLIGATION")
        dependencies = sol.get("depends_on")
        if not isinstance(dependencies, list) or any(not isinstance(x, str) or not x.strip() for x in dependencies) or len(set(dependencies)) != len(dependencies) or sid in dependencies:
            _deny("DEPENDENCIES_INVALID")
        dependency_graph[sid] = dependencies
    if set(req_owners) != _ids(strategy.get("requirement_ids"), "STRATEGY_REQUIREMENTS") or set(acc_owners) != _ids(strategy.get("acceptance_ids"), "STRATEGY_ACCEPTANCE"):
        _deny("MATERIAL_COVERAGE_MISMATCH")
    visited = set()
    active = set()
    def visit(n):
        if n in active:
            _deny("DEPENDENCY_CYCLE")
        if n in visited:
            return
        active.add(n)
        for dep in dependency_graph[n]:
            if dep not in dependency_graph:
                _deny("DEPENDENCY_UNKNOWN")
            visit(dep)
        active.remove(n)
        visited.add(n)
    for n in sorted(dependency_graph):
        visit(n)
    return {
        "status": "CANDIDATE_NOT_ADMITTED",
        "production_authority": False,
        "dispatch_allowed": False,
        "handoff_allowed": False,
        "source_trace": "CALLER_SUPPLIED_NOT_ATTESTED",
        "semantic_partition": "DECLARED_NOT_INDEPENDENTLY_JUDGED",
        "solution_count": len(solutions),
        "requirement_coverage_count": len(req_owners),
        "acceptance_coverage_count": len(acc_owners),
    }
