"""T8: deterministic LF standard checks on ADDED patch lines only.

Does not change repository-wide shadow policy, hidden exams or vendor code.
Each reported code is an actual ID from standards/catalog.json. Unsupported
rules are explicitly unverified; regex is not presented as semantic proof.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
MACHINE = {
    "STD-FE-04": re.compile(r"(?<![\w.])(?:fetch\s*\(|window[.]fetch\s*\(|axios\s*[.](?:get|post|put|delete|patch)\s*\()"),
    "STD-GEN-03": re.compile(r"""(?i)(?:(?:password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key)\s*[:=]\s*['"][^'"]{3,}['"]|(?:AKIA|ASIA)[A-Z0-9]{16})"""),
    "STD-GEN-04": re.compile(r"(?i)(?:log(?:ger)?[.](?:info|debug|warn|error|trace)|console[.]log)\s*\([^)]*(?:password|passwd|secret|token|ssn|dni|email)"),
    "STD-BE-04": re.compile(r"(?i)(?:log(?:ger)?[.](?:info|debug|warn|error|trace))\s*\([^)]*(?:password|passwd|secret|token|dni|email)"),
    "STD-GEN-05": re.compile(r"(?i)(?:noinspection|eslint-disable|@ts-ignore|@SuppressWarnings)[^\n]*(?!WAIVER-[A-Z0-9-]+)$"),
    "STD-DB-09": None,
}
MIGRATION=re.compile(r"V[1-9][0-9]*__[a-z][a-z0-9_]*[.]sql\Z")

class RuleGateBlocked(ValueError):
    pass

def catalog(root=ROOT):
    source=json.loads((root/"standards/catalog.json").read_text("utf-8"))
    return {r["id"]:r for r in source["rules"]}

def _waiver_allowed(root: Path, path: str, line: str) -> bool:
    """Delegate scope, expiry, target and ID matching to the official C8 tool."""
    source = root / "standards/tools/waivers.py"
    spec = importlib.util.spec_from_file_location("lf_official_waiver_checks", source)
    if spec is None or spec.loader is None:
        raise RuleGateBlocked("LF_WAIVER_CHECK_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    targets = module.parse_suppression(line)
    ids = set(re.findall(r"WAIVER-[0-9]{4,}", line))
    if not targets or not ids or any(not isinstance(x, dict) for x in targets):
        return False
    official = json.loads((root / "standards/catalog.json").read_text("utf-8"))
    registry = json.loads((root / "standards/waivers/waivers.json").read_text("utf-8"))
    now = dt.datetime.now(dt.timezone.utc)
    for target in targets:
        result, _, authorized = module.evaluate(official, registry, path, target, now)
        if result != "AUTHORIZED" or not ids.intersection(authorized):
            return False
    return True


def _added(patch):
    path=None
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            match=re.fullmatch(r"diff --git a/([^\s]+) b/\1",line)
            if not match:
                raise RuleGateBlocked("LF_PATCH_PATH_INVALID")
            path=match.group(1)
        elif line.startswith("+") and not line.startswith("+++"):
            if path is None:
                raise RuleGateBlocked("LF_PATCH_PATH_INVALID")
            yield path,line[1:]

def evaluate(patch: str, rule_ids: list[str], *, root=ROOT):
    known=catalog(root)
    if not isinstance(patch,str) or not isinstance(rule_ids,list) or not rule_ids or any(
        not isinstance(x,str) or x not in known for x in rule_ids):
        raise RuleGateBlocked("LF_RULES_UNRESOLVED")
    selected=set(rule_ids)
    violations=[]
    checked=set()
    partial=set()
    rows=list(_added(patch))
    for rule,pattern in MACHINE.items():
        if rule not in selected:
            continue
        # A regex can reject a known-bad patch but cannot prove absence of
        # all equivalent violations (aliases, literals, multi-line, etc.).
        partial.add(rule)
        for path,line in rows:
            relevant = (rule=="STD-FE-04" and path.endswith((".ts",".tsx",".js",".jsx")) or
                        rule=="STD-BE-04" and path.endswith(".java") or
                        rule=="STD-GEN-04" and path.endswith((".java",".ts",".tsx",".py")) or
                        rule=="STD-GEN-05" and path.endswith((".java",".ts",".tsx",".js",".py")) or
                        rule=="STD-GEN-03" and path.endswith((".java",".ts",".tsx",".js",".py",".properties",".yaml",".yml")) or
                        rule=="STD-DB-09" and path.endswith(".sql"))
            if not relevant:
                continue
            if rule=="STD-DB-09":
                if "/db/migration/" in path and not MIGRATION.fullmatch(path.rsplit("/",1)[-1]):
                    violations.append({"rule_id":rule,"code":rule.replace("-","_"),"path":path})
            elif pattern and pattern.search(line):
                if rule=="STD-GEN-05" and _waiver_allowed(root,path,line):
                    continue
                violations.append({"rule_id":rule,"code":rule.replace("-","_"),"path":path})
    result={"schema_version":"T8_RULE_CHECK_V1",
            "machine_checked":sorted(checked),
            "partial_checks":sorted(partial),
            "violations":violations,
            "not_machine_verified":sorted(selected-checked),
            "status":"FAIL" if violations else "PASS"}
    return result

def coverage(report, *, hidden_coverage=None):
    """Honest coverage: a partial negative-pattern scan never attests a rule.

    Hidden exams can only be credited when a separately authenticated
    examination receipt is supplied; this local projection never has one.
    """
    if hidden_coverage:
        raise RuleGateBlocked("LF_HIDDEN_COVERAGE_NOT_ATTESTED")
    ids=set(report["machine_checked"])|set(report["not_machine_verified"])
    partial=set(report.get("partial_checks", []))
    return [{"rule_id":key,
             "coverage":("MACHINE" if key in report["machine_checked"]
                         else "NO_VERIFICADO"),
             **({"reason":("DETECCION_PARCIAL_NO_PRUEBA_CUMPLIMIENTO" if key in partial
                           else "SIN_VERIFICADOR_COMPLETO")}
                if key not in report["machine_checked"] else {})}
            for key in sorted(ids)]


def verified_visible_commands(rows: list[dict], visible: dict | None,
                              declared: list[dict]) -> list[dict]:
    """Attribute only an exact, successful owner-declared visible command.

    Never infer what an encrypted hidden oracle covers.
    """
    table = [dict(row) for row in rows]
    registered = {(c.get("name"),tuple(c.get("argv",[]))) for c in declared
                  if isinstance(c,dict) and isinstance(c.get("argv"),list)}
    if not isinstance(visible,dict):
        return table
    # Only the pinned full formatter can attest complete formatting.
    # A command merely named std-XX-YY is not proof (it might run "true").
    from register_task_context import FORMAT_COMMAND
    successful = set()
    for attempt in visible.get("attempts",[]):
        if not isinstance(attempt,dict):
            continue
        for command in attempt.get("acceptance",[]):
            if not isinstance(command,dict) or command.get("status") != "PASS":
                continue
            name,argv=command.get("name"),command.get("argv")
            if not isinstance(name,str) or not isinstance(argv,list):
                continue
            marker=re.match(r"(std-[a-z]+-[0-9]+)(?:-|$)",name)
            if (marker and marker.group(1).upper() == "STD-BE-05"
                    and name == FORMAT_COMMAND["name"]
                    and argv == FORMAT_COMMAND["argv"]
                    and (name, tuple(argv)) in registered):
                successful.add("STD-BE-05")
    for row in table:
        if row["coverage"]=="NO_VERIFICADO" and row["rule_id"] in successful:
            row["coverage"]="MACHINE"
            row.pop("reason", None)
            row["evidence"]="PINNED_VISIBLE_ACCEPTANCE_COMMAND"
    return table


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--patch",type=Path,required=True)
    parser.add_argument("--rule-receipt",type=Path,required=True)
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    report=json.loads(args.rule_receipt.read_text("utf-8"))
    result=evaluate(args.patch.read_text("utf-8"),report["rule_ids"])
    if args.out:
        args.out.write_text(json.dumps({"evaluation":result,"coverage":coverage(result)},indent=2)+"\n")
    print(json.dumps(result,sort_keys=True))
    return int(result["status"]!="PASS")

if __name__=="__main__":
    sys.exit(main())
