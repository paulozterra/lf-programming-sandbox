#!/usr/bin/env python3
"""F2: run actual pinned A1–A5, bounded simulated admission, then A6."""
from __future__ import annotations

from copy import deepcopy
import argparse
import json
from pathlib import Path

from analysis.host.fixture_readback_host import FixtureHost
from analysis.host.run_a1_a5_fixture import REQUEST, execute, encoded, LEGACY_FIXTURES
from analysis.host.simulated_admission_gate import seal_envelope, admit
from analysis.a6.implementability import run as run_a6


def run_f2(fixtures=None, output_dir=None, request=None):
    host = FixtureHost(fixtures if fixtures is not None else LEGACY_FIXTURES)
    data = host.read_all(request)
    signal = deepcopy(data["semantic_signals.json"]["a2_signals"])
    signal["evidence_refs"] = [host.provenance["semantic_signals.json"]]
    actual_request = data["semantic_signals.json"]["request_text"] if request is None else request
    real = execute(actual_request, fixtures=fixtures if fixtures is not None else LEGACY_FIXTURES)
    stages = real["stages"]
    envelope = seal_envelope(stages, signal)
    admission = admit(stages, signal, envelope)
    a6 = run_a6(stages, signal, envelope, admission,
                source_obligations=data["semantic_signals.json"].get("source_obligations"))
    result = {
        "simulation_mode": "SIMULATED_SANDBOX_ONLY",
        "authority_flags": admission["authority_flags"],
        "stages": stages,
        "a2_signals": signal,
        "admission_envelope": envelope,
        "admission": admission,
        "a6": a6,
    }
    if output_dir is not None:
        dest = Path(output_dir)
        dest.mkdir(parents=True, exist_ok=True)
        for stage, item in stages.items():
            (dest / (stage.lower() + ".json")).write_bytes(encoded(item))
        for name in ("a2_signals", "admission_envelope", "admission", "a6"):
            (dest / (name + ".json")).write_bytes(encoded(result[name]))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, required=True)
    a = p.parse_args()
    out = run_f2(output_dir=a.output_dir)
    print(json.dumps({
        "simulation_mode": out["simulation_mode"],
        "a6_admitted": out["admission"]["a6_admitted"],
        "materiality_level": out["admission"]["materiality_level"],
        "reversibility_state": out["a2_signals"]["depth_signals"]["reversibility_state"],
        "lifted_codes": out["admission"]["lifted_codes"],
        "obligations": [{
            "code": x["requirement_id"], "area": x["area"],
            "materiality_level": x["materiality_level"],
            "requires_independent_exam": x["requires_independent_exam"],
            "acceptance_checks": x["acceptance_signals"],
            "criterion": x["acceptance_signals"][0],
            "source_ref": x["evidence_refs"][0],
        } for x in out["a6"]["requirements"]],
        "a6_fingerprint": out["a6"]["implementability_fingerprint_sha256"],
        "a6_authority": out["a6"]["authority_flags"],
    }, sort_keys=True, ensure_ascii=False))
