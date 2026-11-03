"""Explicit cross-repository PG03 C1/C2/C3 technical experiment.

Invoke manually with LF_PG03_UPSTREAM_REPO=/path/to/claude-persona-lf-patch
at the pinned #3498 commit (which includes C1). Does not copy engines,
modify external sources, write Supabase, or grant production authority.

This is a synthetic boundary test, not governed runtime proof.
"""
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]
UPSTREAM_SHA = "1a3dfe22a8ceaed4306a719e9391694d122342a2"
SOURCE_ROOT = Path("sandbox/lf_contract_gate_test/programming_agent_four_stage")
UPSTREAM = os.environ.get("LF_PG03_UPSTREAM_REPO", "")
if not UPSTREAM:
    raise SystemExit("BLOCKED_UPSTREAM_CHECKOUT_REQUIRED: set LF_PG03_UPSTREAM_REPO")
UPSTREAM = Path(UPSTREAM).resolve()
def git(*args, cwd):
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()

if git("rev-parse", "HEAD", cwd=UPSTREAM) != UPSTREAM_SHA:
    raise SystemExit("BLOCKED_UPSTREAM_SHA_DRIFT")
def module_from_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("BLOCKED_UPSTREAM_MODULE_MISSING:" + str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

c1 = module_from_path("original_pg03_c1",
    UPSTREAM / SOURCE_ROOT / "pg03_stack_source_candidate/pg03_stack_source_v1.py")
c3 = module_from_path("original_pg03_c3",
    UPSTREAM / SOURCE_ROOT / "pg03_strategy_candidate/pg03_strategy_v1.py")
sys.path.insert(0, str(SANDBOX / "standards/tools"))
import skills

catalog = (SANDBOX / "standards/catalog.json").read_bytes()
pin = {"catalog_sha256": hashlib.sha256(catalog).hexdigest(),
       "catalog_version": json.loads(catalog)["catalog_version"]}

with tempfile.TemporaryDirectory(prefix="pg03_chain_") as temp:
    root = Path(temp)
    subprocess.check_call(["git", "init", "-q", str(root)])
    subprocess.check_call(["git", "-C", str(root), "config", "user.email", "test@invalid.local"])
    subprocess.check_call(["git", "-C", str(root), "config", "user.name", "PG03 Fixture"])
    (root / "pom.xml").write_text(
        "<project><modelVersion>4.0.0</modelVersion>"
        "<groupId>synthetic</groupId><artifactId>pg03</artifactId>"
        "<version>1</version></project>", encoding="utf-8")
    subprocess.check_call(["git", "-C", str(root), "add", "pom.xml"])
    subprocess.check_call(["git", "-C", str(root), "commit", "-qm", "Synthetic stack snapshot"])
    fixture_sha = git("rev-parse", "HEAD", cwd=root)

    stack = c1.resolve_stack(root, "synthetic/pg03-fixture", fixture_sha, ["pom.xml"])
    assert stack["status"] == "CANDIDATE_NOT_ADMITTED" and stack["authority"] is False
    content, selection = skills.select_and_assemble(
        evidence={"spring_boot": True}, active=["STD-BE", "STD-API"], pin=pin)
    assert content and selection["production_authority"] is False
    assert selection["selection_status"] == "CANDIDATE_NOT_ADMITTED"
    assert [x["skill"] for x in selection["skills"]] == ["spring-boot"]
    classification = {"status": "CANDIDATE_NOT_ADMITTED", "dispatch_allowed": False,
        "candidate": {"status": "CANDIDATE_NOT_ADMITTED",
            "scopes": [{"scope_id": "S1", "state": "READY_FOR_CLASSIFICATION",
                        "candidate_domains": ["STD-BE", "STD-API"]}]}}
    partition = {"schema_version": "PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1",
        "partition_policy": {"canonical_spec_count": 1, "partition_unit": "SOLUTION",
                             "minimum_rule": "SMALLEST_COHERENT_VALID_CHANGE"},
        "coverage": {"material_requirement_coverage_required_percent": 100,
                     "acceptance_obligation_coverage_required_percent": 100}}
    def test_only_preconditions(c, s, selected, expected_sha):
        # Assertions here belong to the TEST, not any runtime guard/authority.
        domains = sorted({d for row in c["candidate"]["scopes"]
                          for d in row["candidate_domains"]})
        assert domains == sorted(["STD-BE", "STD-API"]), "TEST_DOMAIN_DRIFT"
        assert s["commit_sha"] == expected_sha, "TEST_COMMIT_DRIFT"
        assert selected["production_authority"] is False
        assert selected["selection_status"] == "CANDIDATE_NOT_ADMITTED"
        assert selected["catalog_sha256"] == pin["catalog_sha256"]
    test_only_preconditions(classification, stack, selection, fixture_sha)
    kw = dict(classification=classification, stack_evidence=stack,
              partition_contract=partition, requirement_ids=["R1"],
              acceptance_ids=["A1"], reuse_refs=["existing-module"],
              capability_selector="REUSE_COMPONENT",
              alternatives=["NEW_COMPONENT"], fallback="REQUIRES_DECISION")
    strategy = c3.prepare_strategy(**kw)
    assert strategy["scope_ids"] == ["S1"]
    assert strategy["active_domains"] == ["STD-API", "STD-BE"]
    assert strategy["stack_commit_sha"] == fixture_sha
    assert strategy["production_authority"] is False
    assert strategy["handoff_allowed"] is False
    assert strategy == c3.prepare_strategy(**copy.deepcopy(kw))
    print("PASS_PG03_C1_C2_C3_SYNTHETIC_FUNCTION_CHAIN exact_upstream_sha=true "
          "c1_git_source=true c2_original_select_and_assemble=true "
          "c3_original_strategy=true authority=false")

    for label, altered in (
        ("commit_drift", dict(stack, commit_sha="0"*40)),
        ("domain_drift", dict(classification,
             candidate={"status": "CANDIDATE_NOT_ADMITTED",
                        "scopes": [{"scope_id": "S1", "state": "READY_FOR_CLASSIFICATION",
                                    "candidate_domains": ["STD-FE"]}]})),
    ):
        try:
            test_only_preconditions(
                altered if label == "domain_drift" else classification,
                altered if label == "commit_drift" else stack,
                selection, fixture_sha)
        except AssertionError:
            print("PASS_PG03_C1_C2_C3_TEST_ONLY_NEGATIVE=" + label)
        else:
            raise AssertionError("EXPECTED_TEST_BOUNDARY_BLOCK:" + label)

    # The original C3 function does not accept C2 selection as an argument,
    # so this experiment CANNOT prove C2 context was enforced in strategy.
    assert "selection" not in c3.prepare_strategy.__code__.co_varnames
    print("PG03_C2_TO_C3_ENFORCEMENT_UNVERIFIED "
          "test_only_preconditions=true strategy_binds_c2_receipt=false "
          "selector_execution_attested=false authority=false")
