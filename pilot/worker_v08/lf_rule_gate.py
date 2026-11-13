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
    rows=list(_added(patch))
    for rule,pattern in MACHINE.items():
        if rule not in selected:
            continue
        checked.add(rule)
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
            "machine_checked":sorted(checked),"violations":violations,
            "not_machine_verified":sorted(selected-checked),
            "status":"FAIL" if violations else "PASS"}
    return result

def coverage(report, *, hidden_coverage=None):
    hidden=set(hidden_coverage or [])
    if not isinstance(hidden_coverage,(list,type(None))):
        raise RuleGateBlocked("LF_HIDDEN_COVERAGE_INVALID")
    if hidden.intersection(report["machine_checked"]):
        hidden-=set(report["machine_checked"])
    ids=set(report["machine_checked"])|set(report["not_machine_verified"])
    if not hidden.issubset(ids):
        raise RuleGateBlocked("LF_HIDDEN_COVERAGE_INVALID")
    return [{"rule_id":key,
             "coverage":("MACHINE" if key in report["machine_checked"] else
                         "HIDDEN_ORACLE" if key in hidden else "NOT_VERIFIED")}
            for key in sorted(ids)]

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
