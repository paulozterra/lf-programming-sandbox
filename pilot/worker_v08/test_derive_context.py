"""Fully offline: deterministic context routing, no model and no oracle content."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from derive_context import (
    ContextBlocked, EX5C_SPEC, EX5C_WRITES, canonical, derive,
    expected_ex5c,
)

ROOT = Path(__file__).resolve().parents[2]


def file(root: Path, name: str, data: str = "fixture") -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def test_ex5c_real_repo_exact_paths_and_reasons():
    result = derive(ROOT, list(EX5C_WRITES), [EX5C_SPEC])
    expected_ex5c(result, ROOT)
    names = {r["path"]: r["reason"] for r in result["files"]}
    prefix = "apps/time-service/src/main/java/lf/sandbox/time/reminder/"
    desired = {x: "WRITE_TARGET" for x in EX5C_WRITES}
    desired[prefix + "Reminder.java"] = "SAME_PACKAGE_REF"
    desired["apps/time-service/pom.xml"] = "BUILD"
    desired[EX5C_SPEC] = "SPEC"
    desired["apps/time-service/src/test/java/lf/sandbox/time/reminder/ReminderRepositoryVisibleTest.java"] = "VISIBLE_TEST"
    desired["apps/time-service/src/test/java/lf/sandbox/time/reminder/ReminderRepositoryDeleteSearchVisibleTest.java"] = "VISIBLE_TEST"
    desired["apps/time-service/src/test/java/lf/sandbox/time/reminder/ReminderControllerVisibleTest.java"] = "VISIBLE_TEST"
    desired["apps/time-service/src/test/java/lf/sandbox/time/reminder/ReminderControllerDeleteSearchVisibleTest.java"] = "VISIBLE_TEST"
    assert names == desired
    assert not any("TimeController.java" in n or "TimeConfig.java" in n for n in names)
    assert result["bytes"] < 240000
    assert len(result["files"]) <= 12


def test_denied_env_holdout_and_vendor_are_recorded_without_reading(tmp_path):
    src = "apps/x/src/main/java/lf/sandbox/x/Seed.java"
    file(tmp_path, src,
         "package lf.sandbox.x;\nimport lf.sandbox.Foo;\npublic class Seed {}\n")
    file(tmp_path, "apps/x/pom.xml", "<project/>")
    file(tmp_path, "apps/x/SPEC.md", "sample")
    file(tmp_path, "apps/x/.env", "NEVER-READ")
    file(tmp_path, "apps/x/holdout_private.json", "NEVER-READ")
    file(tmp_path, "vendor/Foo.java", "NEVER-READ")
    result = derive(tmp_path, [src], ["apps/x/SPEC.md"])
    selected = result["context_paths"]
    denied = {x["path"]: x["reason"] for x in result["excluded"]}
    for name in ("apps/x/.env", "apps/x/holdout_private.json", "vendor/Foo.java"):
        assert name not in selected
        assert denied[name].startswith("DENIED_")
    assert denied["vendor/Foo.java"] == "DENIED_VENDOR"


def test_determinism_byte_identical_real_repo():
    first = canonical(derive(ROOT, list(EX5C_WRITES), [EX5C_SPEC]))
    second = canonical(derive(ROOT, list(EX5C_WRITES), [EX5C_SPEC]))
    assert first == second


def test_inflated_repo_fails_closed(tmp_path):
    seed = "apps/x/src/main/java/lf/sandbox/x/Seed.java"
    file(tmp_path, seed, "package lf.sandbox.x; class Seed {}")
    file(tmp_path, "apps/x/pom.xml", "<project/>")
    file(tmp_path, "apps/x/SPEC.md", "x" * 240001)
    with pytest.raises(ContextBlocked, match="LOTE_DEMASIADO_GRANDE"):
        derive(tmp_path, [seed], ["apps/x/SPEC.md"])


def test_more_than_six_write_targets_fails_closed(tmp_path):
    with pytest.raises(ContextBlocked, match="LOTE_DEMASIADO_GRANDE"):
        derive(tmp_path, [f"apps/x/Foo{i}.java" for i in range(7)], [])


def test_parent_traversal_never_accepted(tmp_path):
    with pytest.raises(ContextBlocked, match="CONTEXT_PATH_INVALID"):
        derive(tmp_path, ["apps/x/../../.env"], [])

def test_typescript_tsx_relative_imports_and_build_metadata(tmp_path):
    file(tmp_path, "apps/web/package.json", '{"scripts":{}}')
    file(tmp_path, "apps/web/tsconfig.json", '{"compilerOptions":{"strict":true}}')
    file(tmp_path, "apps/web/src/lib/utils.ts", "export const value = 1;")
    file(tmp_path, "apps/web/src/components/sample.tsx",
         'import { value } from "../lib/utils";\\nexport const Sample = () => value;')
    out = derive(tmp_path, ["apps/web/src/components/sample.tsx"], [])
    reasons = {row["path"]: row["reason"] for row in out["files"]}
    assert reasons["apps/web/src/lib/utils.ts"] == "IMPORT"
    assert reasons["apps/web/package.json"] == "BUILD"
    assert reasons["apps/web/tsconfig.json"] == "BUILD"
    assert canonical(out) == canonical(derive(tmp_path, ["apps/web/src/components/sample.tsx"], []))


def test_flyway_only_earlier_migrations_same_directory(tmp_path):
    prefix = "db/migrations/"
    for name in ("V1__initial.sql", "V2__contacts.sql", "V3__future.sql"):
        file(tmp_path, prefix + name, "SELECT 1;")
    file(tmp_path, "db/other/V1__outside.sql", "SELECT 1;")
    out = derive(tmp_path, [prefix + "V2__contacts.sql"], [])
    paths = set(out["context_paths"])
    assert prefix + "V1__initial.sql" in paths
    assert prefix + "V3__future.sql" not in paths
    assert "db/other/V1__outside.sql" not in paths


def test_new_language_denied_sensitive_files(tmp_path):
    file(tmp_path, "apps/web/src/page.tsx", 'import x from "./holdout_secret";')
    file(tmp_path, "apps/web/src/holdout_secret.ts", "DO NOT READ")
    out = derive(tmp_path, ["apps/web/src/page.tsx"], [])
    assert all("holdout" not in p for p in out["context_paths"])
