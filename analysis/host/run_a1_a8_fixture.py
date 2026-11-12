#!/usr/bin/env python3
"""F3: extend the actual F2 runner with A7 front coverage and A8 stop rule."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis.host.run_a1_a5_fixture import encoded
from analysis.host.run_a1_a6_fixture import run_f2
from analysis.host.fixture_readback_host import FixtureHost
from analysis.a7.front_coverage import run as run_a7
from analysis.a8.stop_rule import run as run_a8


def run_f3(fixtures=None, output_dir=None):
    result = run_f2(fixtures=fixtures, output_dir=output_dir)
    # Verified by F1 host SOURCE_PIN.json before this metadata is read.
    checked_host = FixtureHost(fixtures) if fixtures is not None else FixtureHost()
    pinned = checked_host.read_all()
    def binding(rows):
        return {row["code"]: {"source_ref": row["source_ref"],
                              "categoria": row["categoria"]} for row in rows}
    category_sources = {
        "direct": binding(pinned["direct_rules.json"]["linked_rules"]),
        "effective": binding(pinned["effective_rules.json"]["rules"]),
        "fixture_provenance": {
            name: checked_host.provenance[name] for name in
            ("direct_rules.json", "effective_rules.json")
        },
    }
    result["category_sources"] = category_sources
    a7 = run_a7(
        result["stages"], result["a2_signals"], result["admission_envelope"],
        result["admission"], result["a6"], category_sources)
    a8 = run_a8(result["stages"]["A3"], result["stages"]["A5"], a7, result["admission"])
    result["a7"] = a7
    result["a8"] = a8
    if output_dir is not None:
        dest = Path(output_dir)
        (dest / "a7.json").write_bytes(encoded(a7))
        (dest / "a8.json").write_bytes(encoded(a8))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = run_f3(output_dir=args.output_dir)
    print(json.dumps({
        "simulation_mode": "SIMULATED_SANDBOX_ONLY",
        "materiality_level": output["a7"]["materiality_level"],
        "fronts": [{
            "front_id": row["front_id"],
            "kind": row["front_kind"],
            "status": row["status"],
            "closure": row["closure"],
            "area": row["execution_area_hint"],
            "area_candidates": row["execution_area_candidates"],
            "obligations": row["obligation_refs"],
            "blockers": row["blockers"],
            "closure_basis": row["closure_basis"],
            "lifted_code": row["lifted_code"],
        } for row in output["a7"]["material_fronts"]],
        "all_material_fronts_accounted": output["a7"]["all_material_fronts_accounted"],
        "a8_decision": output["a8"]["decision"],
        "a8_reason": output["a8"]["reason"],
        "a8_decision_stable": output["a8"]["decision_stable"],
        "a8_decision_stable_basis": output["a8"]["decision_stable_basis"],
        "a8_decision_stable_lifted_codes": output["a8"]["decision_stable_lifted_codes"],
        "a8_requested_material_evidence": output["a8"]["requested_material_evidence_refs"],
        "a7_fingerprint": output["a7"]["coverage_fingerprint_sha256"],
        "a8_fingerprint": output["a8"]["stop_rule_fingerprint_sha256"],
    }, sort_keys=True, ensure_ascii=False))
