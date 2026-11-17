"""T43: a lot is complete with the files it actually integrated inside its
allowed scope; an EXTEND lot need not create every planned path."""
import pytest

from chain_contract import attest_merge, ChainBlocked

SHA = "a" * 40
REPO = "paulozterra/lf-programming-sandbox"
SCOPE = ["svc/auth/AuthController.java", "svc/b2b/NewController.java", "svc/b2b/NewService.java"]
LOTS = {"lots": [{"id": "SOL-002", "write_paths": SCOPE, "depends_on": []}]}
BINDINGS = {"SOL-002": {"task_name": "req9backend2"}}


def pr():
    return {"merged": True, "merge_commit_sha": SHA, "number": 5,
            "base": {"ref": "main", "repo": {"full_name": REPO}},
            "head": {"ref": "lf/native-integration/req9backend2-run-77", "repo": {"full_name": REPO}}}


def test_extend_lot_expects_only_integrated_files():
    changes = {"svc/auth/AuthController.java", "standards/CAMBIOS.md", "standards/changes/CHG-0001.json"}
    lot, receipt = attest_merge(SHA, pr(), LOTS, BINDINGS, changes)
    assert lot == "SOL-002" and receipt["expected_files"] == ["svc/auth/AuthController.java"]


def test_out_of_scope_change_still_blocks():
    with pytest.raises(ChainBlocked):
        attest_merge(SHA, pr(), LOTS, BINDINGS, {"svc/other/Hack.java"})


def test_empty_integration_still_blocks():
    with pytest.raises(ChainBlocked):
        attest_merge(SHA, pr(), LOTS, BINDINGS, {"standards/CAMBIOS.md"})
