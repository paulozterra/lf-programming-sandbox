from __future__ import annotations

from pathlib import Path
from typing import Any

from . import programming_quality_hardening_v6 as v6
from .programming_quality import QualityPlan
from .programming_quality_hardening_v15 import validate_test007_command_semantics
from .worker_oracle import HiddenOracle
from .worker_spec import WorkerTaskSpec

load_quality_plan = v6.load_quality_plan
load_readback_manifest = v6.load_readback_manifest
readback_source_paths = v6.readback_source_paths


def run_programming_quality_worker_hardened(
    repo_path: Path,
    spec: WorkerTaskSpec,
    client: Any,
    oracle: HiddenOracle,
    plan: QualityPlan,
    readback_manifest: Any,
    *,
    work_parent: Path | None = None,
):
    """Run v6 pipeline with the AUD24 V15 closed TEST-007 contract.

    V8 proves exact source causality. V9 constrains hidden TEST-007 code to a
    closed target/observer/concurrency proof surface. V10 preserves semantic
    return provenance through local container construction/extraction. V11
    extends that provenance across destructuring and multi-target assignments.
    V12 extends it across For/AsyncFor and comprehension bindings. V13 preserves
    provenance through BoolOp value selection. V14 preserves provenance through
    context-manager ``with ... as`` bindings. V15 preserves provenance through
    ``submit`` transport and ``Future.result`` without treating all Futures as
    semantic results. The temporary v6 binding is restored in ``finally``.
    """
    original = v6.validate_test007_command_semantics

    def source_bound_validator(plan: QualityPlan, oracle: HiddenOracle) -> list[str]:
        return validate_test007_command_semantics(
            plan,
            oracle,
            repo_path=repo_path,
        )

    v6.validate_test007_command_semantics = source_bound_validator
    try:
        return v6.run_programming_quality_worker_hardened(
            repo_path,
            spec,
            client,
            oracle,
            plan,
            readback_manifest,
            work_parent=work_parent,
        )
    finally:
        v6.validate_test007_command_semantics = original
