"""T26.1: an integrated contract lot may carry exactly the trusted T25 generator outputs."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from chain_contract import ChainBlocked, attest_merge  # noqa: E402

SHA = "a" * 40
REPO = {"full_name": "paulozterra/lf-programming-sandbox"}


def pr(branch: str) -> dict:
    return {"merged": True, "merge_commit_sha": SHA, "number": 9,
            "base": {"ref": "main", "repo": REPO},
            "head": {"ref": branch, "repo": REPO}}


LOTS = {"lots": [
    {"id": "SOL-001", "area": "CONTRATO", "write_paths": ["contracts/demo-gadgets.openapi.yaml"]},
    {"id": "SOL-002", "area": "BACKEND",
     "write_paths": ["apps/time-service/src/main/java/demo/GadgetController.java"]},
]}
BINDINGS = {"SOL-001": {"task_name": "demotask1"}, "SOL-002": {"task_name": "demotask2"}}
STD = {"standards/CAMBIOS.md", "standards/changes/CHG-0999.json"}
GEN = {"frontend/src/lib/api/generated/index.ts",
       "frontend/src/lib/api/generated/demo-gadgets.ts"}


def test_contract_lot_with_generator_outputs_is_attested():
    lot_id, receipt = attest_merge(SHA, pr("lf/native-integration/demotask1-run-123"), LOTS,
                                   BINDINGS, {"contracts/demo-gadgets.openapi.yaml"} | GEN | STD)
    assert lot_id == "SOL-001"
    # The Worker scope stays the planned lot scope; generator outputs are not attributed to it.
    assert receipt["expected_files"] == ["contracts/demo-gadgets.openapi.yaml"]


@pytest.mark.parametrize("extra", [
    "frontend/src/lib/api/client.ts",               # outside the generator output
    "frontend/src/lib/api/generated/nested/x.ts",   # not a generator file name
    "frontend/src/app/demo/page.tsx",
])
def test_contract_lot_with_other_frontend_paths_is_rejected(extra):
    with pytest.raises(ChainBlocked, match="INTEGRATION_SCOPE_MISMATCH"):
        attest_merge(SHA, pr("lf/native-integration/demotask1-run-123"), LOTS, BINDINGS,
                     {"contracts/demo-gadgets.openapi.yaml", extra} | STD)


def test_non_contract_lot_cannot_carry_generator_outputs():
    with pytest.raises(ChainBlocked, match="INTEGRATION_SCOPE_MISMATCH"):
        attest_merge(SHA, pr("lf/native-integration/demotask2-run-124"), LOTS, BINDINGS,
                     {"apps/time-service/src/main/java/demo/GadgetController.java"} | GEN | STD)
