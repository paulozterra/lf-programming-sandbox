#!/usr/bin/env python3
"""F4 A1→A9 offline pipeline; writes only simulated CP3.2 intake files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from analysis.host.run_a1_a8_fixture import run_f3
from analysis.host.fixture_readback_host import FixtureHost
from analysis.host.run_a1_a5_fixture import REQUEST, encoded
from analysis.a9.package import build, validate
from pilot.orchestrator import intake

SLUG = "f4-login"


def make_rule_sources(fixtures=None):
    """Reuse F1 host SHA verification, never infer category/config from prose."""
    host = FixtureHost(fixtures) if fixtures is not None else FixtureHost()
    rows = host.read_all()
    direct = rows["direct_rules.json"]
    config = {x["code"]: x["valor_config"] for x in direct["valor_config"]}
    return {
        "direct": {x["code"]: {**x, "valor_config": config[x["code"]]}
                   for x in direct["linked_rules"]},
        "effective": {x["code"]: x for x in rows["effective_rules.json"]["rules"]},
        "provenance": {name: host.provenance[name]
                       for name in ("direct_rules.json", "effective_rules.json")},
    }


def run_f4(root, slug=SLUG, fixtures=None):
    source = run_f3(fixtures=fixtures)
    source["rule_sources"] = make_rule_sources(fixtures)
    raw = (REQUEST + "\n").encode("utf-8")
    package = build(source, raw)
    validate(package, raw, result=source)
    dest = Path(root) / "pilot" / "runs" / slug
    dest.mkdir(parents=True, exist_ok=True)
    request = dest / "request.md"
    output = dest / "analysis.json"
    request_bytes = intake.normalized_request_bytes(raw)
    expected_json = intake.canonical(package)
    for path, content in ((request, request_bytes), (output, expected_json)):
        if path.exists() and path.read_bytes() != content:
            raise ValueError("F4_A9_OUTPUT_DRIFT:" + path.name)
        if not path.exists():
            path.write_bytes(content)
    status = intake.accept(Path(root), slug)
    return {"package": package, "state": status, "root": str(root), "slug": slug,
            "source": source}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--slug", default=SLUG)
    args = p.parse_args()
    result = run_f4(args.root, slug=args.slug)
    print(json.dumps({
        "a9_intake": result["state"]["stage"],
        "pg01": result["state"]["pg01"],
        "analysis_sha256": result["state"]["analysis_sha256"],
        "request_sha256": result["state"]["request_sha256"],
        "applicable_rules": result["package"]["applicable_rules"],
        "requirements": [{"id": x["requirement_id"], "source": x["source_requirement_id"],
                          "acceptance_checks": x["acceptance_checks"],
                          "evidence_refs": x["evidence_refs"]}
                         for x in result["package"]["requirements"]],
        "scopes": result["package"]["scope_proposals"],
        "readiness": result["package"]["package_readiness_candidate"],
        "research_stop": {"decision": result["package"]["research_stop"]["decision"],
                          "decision_stable_basis":
                          result["package"]["research_stop"]["decision_stable_basis"],
                          "reason": result["package"]["research_stop"]["reason"]},
        "simulation_mode": result["package"]["simulation_mode"],
    }, sort_keys=True, ensure_ascii=False))
