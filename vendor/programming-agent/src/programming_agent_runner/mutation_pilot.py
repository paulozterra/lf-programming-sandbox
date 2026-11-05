from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Callable

from .verified_worker import oracle_gate_passes

Gate = Callable[[bool, bool, bool], bool]


def _cases() -> tuple[tuple[bool, bool, bool], ...]:
    return tuple((visible, hidden, stable) for visible in (False, True) for hidden in (False, True) for stable in (False, True))


def _property_expected(visible: bool, hidden: bool, stable: bool) -> bool:
    return visible and hidden and stable


def _mutants() -> dict[str, Gate]:
    return {
        "ignore_hidden": lambda visible, hidden, stable: visible and stable,
        "ignore_stability": lambda visible, hidden, stable: visible and hidden,
        "visible_or_hidden": lambda visible, hidden, stable: (visible or hidden) and stable,
        "hidden_only": lambda visible, hidden, stable: hidden and stable,
        "invert_hidden": lambda visible, hidden, stable: visible and (not hidden) and stable,
    }


def _passes_properties(gate: Gate) -> bool:
    return all(gate(*case) == _property_expected(*case) for case in _cases())


def run_mutation_property_pilot() -> dict[str, Any]:
    started = time.monotonic()
    baseline_pass = _passes_properties(oracle_gate_passes)
    killed: list[str] = []
    survived: list[str] = []
    for name, mutant in _mutants().items():
        if _passes_properties(mutant):
            survived.append(name)
        else:
            killed.append(name)
    generated = len(killed) + len(survived)
    score = 0.0 if generated == 0 else len(killed) / generated
    return {
        "pilot": "P1-C-oracle-gate",
        "target": "src/programming_agent_runner/verified_worker.py:oracle_gate_passes",
        "baseline_properties_pass": baseline_pass,
        "property_cases": len(_cases()),
        "mutants_generated": generated,
        "killed": killed,
        "survived": survived,
        "invalid": [],
        "timeout": [],
        "mutation_score": score,
        "global_threshold_declared": False,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bounded P1 mutation/property pilot")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_mutation_property_pilot()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["baseline_properties_pass"] and not result["survived"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
