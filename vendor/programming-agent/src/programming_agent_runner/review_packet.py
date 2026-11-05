from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .hashutil import sha256_json
from .structured_test_receipt import successful_test_ids, validate_structured_test_receipt

RISK_CATEGORIES = (
    "security",
    "data_integrity",
    "financial_logic",
    "permissions",
    "state_transitions",
    "external_integration",
    "maintainability",
)
CI_VERIFICATION_EVIDENCE_SCHEMA_VERSION = 1
CI_CHECKS = (
    "build",
    "lint",
    "typecheck",
    "structured_tests",
    "negative_tests",
    "mutation_property",
)
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_P1A_TEST_SUFFIXES = (
    "HiddenOracleTests.test_visible_and_hidden_pass_delivers_patch_without_oracle_leakage",
    "HiddenOracleTests.test_oracle_change_during_builder_execution_fails_closed",
    "OracleCoreBoundaryTests.test_regular_oracle_inside_repo_is_blocked_before_model",
    "OracleCoreBoundaryTests.test_repo_local_symlink_to_external_oracle_is_blocked",
)
_REQUIRED_P1B_TEST_SUFFIXES = (
    "HiddenOracleTests.test_hardcoded_visible_pass_fails_hidden_holdout_and_suppresses_patch",
    "HiddenOracleTests.test_hidden_failure_is_not_returned_to_builder_for_repair",
)
_REQUIRED_P1D_TEST_SUFFIXES = (
    "ReviewPacketTests.test_packet_maps_real_diff_symbols_dependencies_risk_and_evidence",
    "ReviewEvidenceTests.test_relative_imports_and_markdown_show_full_impact",
    "ReviewEvidenceTests.test_missing_or_unbound_evidence_is_unverified",
)


def _git(root: Path, args: list[str]) -> str:
    completed = subprocess.run(["git", *args], cwd=root, capture_output=True, check=True, text=True)
    return completed.stdout


def _changed_files(root: Path, base_ref: str, head_ref: str) -> list[str]:
    value = _git(root, ["diff", "--name-only", "--no-renames", f"{base_ref}..{head_ref}"])
    return sorted(line for line in value.splitlines() if line)


def _symbols(path: Path) -> list[str]:
    if path.suffix != ".py" or not path.is_file():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sorted(
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )


def _module_name(path: str) -> str | None:
    prefix = "src/"
    if not path.startswith(prefix) or not path.endswith(".py"):
        return None
    relative = path[len(prefix) : -3]
    if relative.endswith("/__init__"):
        relative = relative[: -len("/__init__")]
    return relative.replace("/", ".")


def _package_for_file(root: Path, path: Path) -> str | None:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return None
    module = _module_name(relative)
    if module is None:
        return None
    if path.name == "__init__.py":
        return module
    package, _, _ = module.rpartition(".")
    return package or None


def _relative_import_base(package: str | None, level: int, module: str | None) -> str | None:
    if package is None or level <= 0:
        return module
    target = "." * level + (module or "")
    try:
        return importlib.util.resolve_name(target, package)
    except (ImportError, ValueError):
        return None


def _imports(root: Path, path: Path) -> list[str]:
    if path.suffix != ".py" or not path.is_file():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _package_for_file(root, path)
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _relative_import_base(package, node.level, node.module)
            if base:
                values.add(base)
                for alias in node.names:
                    if alias.name != "*":
                        values.add(f"{base}.{alias.name}")
            elif node.level and package:
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    resolved = _relative_import_base(package, node.level, alias.name)
                    if resolved:
                        values.add(resolved)
    return sorted(values)


def _symbol_calls(path: Path) -> dict[str, list[str]]:
    if path.suffix != ".py" or not path.is_file():
        return {}
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls: set[str] = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        calls.add(child.func.id)
                    elif isinstance(child.func, ast.Attribute):
                        calls.add(child.func.attr)
            result[node.name] = sorted(calls)
    return result


def _python_files(root: Path) -> list[Path]:
    values: list[Path] = []
    for base in (root / "src", root / "tests", root / "tools"):
        if base.exists():
            values.extend(sorted(base.rglob("*.py")))
    return values


def _incoming_dependencies(root: Path, changed: list[str]) -> dict[str, list[str]]:
    modules = {module: path for path in changed if (module := _module_name(path))}
    result: dict[str, list[str]] = {path: [] for path in modules.values()}
    for candidate in _python_files(root):
        imports = set(_imports(root, candidate))
        relative = candidate.relative_to(root).as_posix()
        for module, path in modules.items():
            if module in imports or any(item.startswith(f"{module}.") for item in imports):
                result[path].append(relative)
    return {key: sorted(set(value)) for key, value in result.items()}


def _risk_heatmap(changed: list[str]) -> dict[str, dict[str, Any]]:
    joined = "\n".join(changed).lower()
    token_map = {
        "security": ("secret", "auth", "oracle", "permission", "security"),
        "data_integrity": ("receipt", "hash", "snapshot", "evidence", "oracle"),
        "financial_logic": ("financial", "money", "amount", "interest", "fee"),
        "permissions": ("permission", "scope", "protected", "auth"),
        "state_transitions": ("state", "status", "transition", "worker"),
        "external_integration": ("openai", "anthropic", "github", "supabase", "http"),
        "maintainability": ("src/", "tests/", "tools/", "docs/"),
    }
    result: dict[str, dict[str, Any]] = {}
    for category in RISK_CATEGORIES:
        hits = sorted(token for token in token_map[category] if token in joined)
        score = min(3, len(hits))
        result[category] = {
            "level": ("LOW", "MEDIUM", "HIGH", "HIGH")[score],
            "basis": "deterministic filename/path heuristic",
            "signals": hits,
        }
    return result


def ci_verification_evidence_sha256(evidence: dict[str, Any]) -> str:
    return sha256_json({key: value for key, value in evidence.items() if key != "evidence_sha256"})


def _test_suffixes_pass(test_receipt: dict[str, Any], suffixes: tuple[str, ...]) -> bool:
    successful = successful_test_ids(test_receipt)
    return all(any(test_id.endswith(suffix) for test_id in successful) for suffix in suffixes)


def verification_evidence_problems(
    *,
    head_ref: str,
    mutation: Any,
    test_receipt: Any,
    ci_evidence: Any,
) -> list[str]:
    problems: list[str] = []
    if not isinstance(ci_evidence, dict):
        return ["CI_EVIDENCE_MISSING"]
    expected_fields = {
        "schema_version",
        "source",
        "repository",
        "head_sha",
        "source_snapshot_sha256",
        "run_id",
        "run_attempt",
        "job_name",
        "test_receipt_sha256",
        "mutation_evidence_sha256",
        "checks",
        "evidence_sha256",
    }
    if set(ci_evidence) != expected_fields:
        problems.append("CI_EVIDENCE_FIELDS_MISMATCH")
    if ci_evidence.get("schema_version") != CI_VERIFICATION_EVIDENCE_SCHEMA_VERSION:
        problems.append("CI_EVIDENCE_SCHEMA_INVALID")
    if ci_evidence.get("source") != "github-actions-control-flow":
        problems.append("CI_EVIDENCE_SOURCE_INVALID")
    head = ci_evidence.get("head_sha")
    if not isinstance(head, str) or _SHA40.fullmatch(head) is None or head != head_ref:
        problems.append("CI_EVIDENCE_HEAD_MISMATCH")
    snapshot = ci_evidence.get("source_snapshot_sha256")
    if not isinstance(snapshot, str) or _SHA256.fullmatch(snapshot) is None:
        problems.append("CI_EVIDENCE_SNAPSHOT_INVALID")
    digest = ci_evidence.get("evidence_sha256")
    if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        problems.append("CI_EVIDENCE_DIGEST_INVALID")
    elif digest != ci_verification_evidence_sha256(ci_evidence):
        problems.append("CI_EVIDENCE_DIGEST_MISMATCH")
    checks = ci_evidence.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(CI_CHECKS):
        problems.append("CI_EVIDENCE_CHECKS_INVALID")
    elif any(status not in {"PASS", "FAIL", "BLOCKED"} for status in checks.values()):
        problems.append("CI_EVIDENCE_CHECK_STATUS_INVALID")
    if not isinstance(test_receipt, dict):
        problems.append("TEST_RECEIPT_MISSING")
    else:
        receipt_errors = validate_structured_test_receipt(
            test_receipt,
            expected_repository=ci_evidence.get("repository") if isinstance(ci_evidence.get("repository"), str) else None,
            expected_head_sha=head if isinstance(head, str) else None,
            expected_run_id=ci_evidence.get("run_id") if type(ci_evidence.get("run_id")) is int else None,
            expected_run_attempt=ci_evidence.get("run_attempt") if type(ci_evidence.get("run_attempt")) is int else None,
            expected_job_name=ci_evidence.get("job_name") if isinstance(ci_evidence.get("job_name"), str) else None,
        )
        problems.extend(f"TEST_RECEIPT_{item.upper()}" for item in receipt_errors)
        if test_receipt.get("source_snapshot_sha256") != snapshot:
            problems.append("TEST_RECEIPT_SNAPSHOT_MISMATCH")
        if test_receipt.get("receipt_sha256") != ci_evidence.get("test_receipt_sha256"):
            problems.append("TEST_RECEIPT_DIGEST_BINDING_MISMATCH")
    if not isinstance(mutation, dict):
        problems.append("MUTATION_EVIDENCE_MISSING")
    elif sha256_json(mutation) != ci_evidence.get("mutation_evidence_sha256"):
        problems.append("MUTATION_EVIDENCE_DIGEST_BINDING_MISMATCH")
    return sorted(set(problems))


def _rollup(checks: dict[str, str], names: tuple[str, ...]) -> str:
    statuses = [checks.get(name) for name in names]
    if any(status == "FAIL" for status in statuses):
        return "FAIL"
    if any(status == "BLOCKED" for status in statuses):
        return "BLOCKED"
    return "PASS" if all(status == "PASS" for status in statuses) else "UNVERIFIED"


def derive_verification_matrix(
    *,
    head_ref: str,
    mutation: Any,
    test_receipt: Any,
    ci_evidence: Any,
) -> dict[str, Any]:
    problems = verification_evidence_problems(
        head_ref=head_ref,
        mutation=mutation,
        test_receipt=test_receipt,
        ci_evidence=ci_evidence,
    )
    base_evidence = {
        "head_sha": head_ref,
        "ci_evidence_sha256": ci_evidence.get("evidence_sha256") if isinstance(ci_evidence, dict) else None,
        "test_receipt_sha256": test_receipt.get("receipt_sha256") if isinstance(test_receipt, dict) else None,
        "problems": problems,
    }
    unverified = "UNVERIFIED" if problems else None
    checks = ci_evidence.get("checks", {}) if isinstance(ci_evidence, dict) else {}
    p1a = unverified or _rollup(checks, ("structured_tests", "negative_tests"))
    p1b = unverified or _rollup(checks, ("structured_tests", "negative_tests"))
    p1d = unverified or _rollup(checks, ("structured_tests",))
    baseline = unverified or _rollup(checks, ("build", "lint", "typecheck", "structured_tests", "negative_tests"))
    if not problems and isinstance(test_receipt, dict):
        if p1a == "PASS" and not _test_suffixes_pass(test_receipt, _REQUIRED_P1A_TEST_SUFFIXES):
            p1a = "UNVERIFIED"
        if p1b == "PASS" and not _test_suffixes_pass(test_receipt, _REQUIRED_P1B_TEST_SUFFIXES):
            p1b = "UNVERIFIED"
        if p1d == "PASS" and not _test_suffixes_pass(test_receipt, _REQUIRED_P1D_TEST_SUFFIXES):
            p1d = "UNVERIFIED"
    p1c = unverified or _rollup(checks, ("mutation_property",))
    if not problems and p1c == "PASS":
        if not isinstance(mutation, dict) or not (
            mutation.get("baseline_properties_pass") is True
            and mutation.get("property_cases") == 8
            and mutation.get("mutants_generated") == 5
            and mutation.get("survived") == []
            and mutation.get("global_threshold_declared") is False
        ):
            p1c = "UNVERIFIED"
    return {
        "P1-A_ORACLE_ISOLATION": {
            "requirement": "hidden oracle content/path/commands excluded from Builder context and core rejects repo-local oracle locations",
            "code": [
                "src/programming_agent_runner/worker_oracle.py",
                "src/programming_agent_runner/verified_worker.py",
                "src/programming_agent_runner/worker_cli.py",
            ],
            "test_or_oracle": ["tests/test_worker_oracle.py", "tests/test_oracle_core_boundary.py"],
            "result": p1a,
            "evidence": base_evidence,
        },
        "P1-B_HIDDEN_HOLDOUT": {
            "requirement": "final PASS requires visible + hidden holdout; hidden failure never repairs through Builder",
            "code": ["src/programming_agent_runner/verified_worker.py"],
            "test_or_oracle": ["tests/test_worker_oracle.py"],
            "result": p1b,
            "evidence": base_evidence,
        },
        "P1-C_MUTATION_PROPERTY": {
            "requirement": "pilot challenges the conjunctive oracle gate without global threshold",
            "code": ["src/programming_agent_runner/mutation_pilot.py"],
            "test_or_oracle": ["tests/test_mutation_pilot.py"],
            "result": p1c,
            "evidence": {**base_evidence, "mutation": mutation if isinstance(mutation, dict) else None},
        },
        "P1-D_HUMAN_REVIEW_PACKET": {
            "requirement": "review begins with change/risk/evidence, then complete static impact views, then diff/code",
            "code": ["src/programming_agent_runner/review_packet.py", "tools/human_review_packet.py"],
            "test_or_oracle": ["tests/test_review_packet.py", "tests/test_review_evidence.py"],
            "result": p1d,
            "evidence": base_evidence,
        },
        "BASELINE_QUALITY": {
            "requirement": "build + lint + typecheck + structured tests + negative controls",
            "code": [".github/workflows/ci.yml"],
            "test_or_oracle": ["canonical-ci structured evidence"],
            "result": baseline,
            "evidence": base_evidence,
        },
    }


def build_review_packet(root: Path, base_ref: str, head_ref: str, verification: dict[str, Any]) -> dict[str, Any]:
    root = root.resolve()
    changed = _changed_files(root, base_ref, head_ref)
    change_map = []
    for path in changed:
        absolute = root / path
        change_map.append(
            {
                "file": path,
                "module": _module_name(path),
                "symbols": _symbols(absolute),
                "outgoing_imports": _imports(root, absolute),
                "callees_by_symbol": _symbol_calls(absolute),
            }
        )
    heuristic_note = (
        "Static AST approximation: relative/absolute imports and direct calls are normalized; "
        "dynamic imports, decorators, monkey-patching, reflection and runtime dispatch may be incomplete."
    )
    packet: dict[str, Any] = {
        "schema_version": 1,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "change_summary": {
            "changed_file_count": len(changed),
            "files": changed,
            "why": "P1 Oracle Isolation, hidden holdout acceptance, mutation/property pilot, and Human Review Packet",
        },
        "change_map": change_map,
        "impact_graph": {
            "incoming_dependencies": _incoming_dependencies(root, changed),
            "outgoing_dependencies": {item["file"]: item["outgoing_imports"] for item in change_map},
            "callees_by_changed_symbol": {item["file"]: item["callees_by_symbol"] for item in change_map},
            "callers_note": heuristic_note,
        },
        "risk_heatmap": _risk_heatmap(changed),
        "verification_matrix": verification,
        "auditor_views": ["1_summary_risk_evidence", "2_impact_graph", "3_diff_and_code"],
        "diff_command": f"git diff --no-renames {base_ref}..{head_ref}",
    }
    packet["packet_sha256"] = sha256_json(packet)
    return packet


def packet_markdown(packet: dict[str, Any]) -> str:
    summary = packet["change_summary"]
    lines = [
        "# Human Review Packet v0",
        "",
        f"Base: `{packet['base_ref']}`",
        f"Head: `{packet['head_ref']}`",
        f"Packet SHA256: `{packet['packet_sha256']}`",
        "",
        "## 1. Resumen, riesgo y evidencia",
        "",
        f"Archivos cambiados: {summary['changed_file_count']}",
        f"Motivo: {summary['why']}",
        "",
        "### Risk heatmap",
    ]
    for category, value in packet["risk_heatmap"].items():
        lines.append(f"- {category}: **{value['level']}** — {', '.join(value['signals']) or 'sin señal por path'}")
    lines.extend(["", "### Verification matrix", ""])
    for key, value in packet["verification_matrix"].items():
        lines.append(f"- {key}: `{json.dumps(value, sort_keys=True)}`")
    graph = packet["impact_graph"]
    lines.extend(["", "## 2. Impact graph", "", "### Incoming importers", ""])
    for path, incoming in graph["incoming_dependencies"].items():
        lines.append(f"- `{path}` ← {', '.join(incoming) or 'sin importadores detectados'}")
    lines.extend(["", "### Outgoing dependencies", ""])
    for path, outgoing in graph["outgoing_dependencies"].items():
        lines.append(f"- `{path}` → {', '.join(outgoing) or 'sin imports detectados'}")
    lines.extend(["", "### Callees by changed symbol", ""])
    for path, symbols in graph["callees_by_changed_symbol"].items():
        if not symbols:
            lines.append(f"- `{path}` → sin funciones top-level con llamadas detectadas")
            continue
        lines.append(f"- `{path}`")
        for symbol, callees in symbols.items():
            lines.append(f"  - `{symbol}` → {', '.join(callees) or 'sin callees directos detectados'}")
    lines.extend(["", "### Límites heurísticos", "", graph["callers_note"], ""])
    lines.extend(["## 3. Diff/código", "", f"`{packet['diff_command']}`", ""])
    for item in packet["change_map"]:
        symbols = ", ".join(item["symbols"]) or "sin símbolos top-level"
        lines.append(f"- `{item['file']}` → {symbols}")
    return "\n".join(lines) + "\n"
