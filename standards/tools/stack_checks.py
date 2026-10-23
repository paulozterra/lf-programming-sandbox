"""Deterministic V1 stack check runner. Shared source of CI and skills."""
import argparse,json,subprocess,sys,re,shlex
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
CHECKS=ROOT/"standards/skills/checks/stack-checks.json"

def load():return json.loads(CHECKS.read_text(encoding="utf-8"))
def validate_ci(cfg,ci_text):
    errors=[]
    commands=[]
    for raw in ci_text.splitlines():
        match=re.search(r"\brun:\s*(.+)$",raw)
        if match and match.group(1).strip() not in ("|",">"):
            commands.append(match.group(1).strip())
        elif raw.lstrip().startswith(("python3 ","mvn ","npm ","docker ","npx ")):
            commands.append(raw.strip())
    used=set()
    for line in commands:
        match=re.search(r"stack_checks\.py\s+run\b(.*)",line)
        if match:
            args=shlex.split(match.group(1))
            def get(flag):
                return args[args.index(flag)+1] if flag in args and args.index(flag)+1<len(args) else None
            check=get("--check-id");set_name=get("--set")
            if check:used.add(check)
            elif set_name in cfg["sets"]:used.update(cfg["sets"][set_name])
    for set_name,checks in cfg["sets"].items():
        for check in checks:
            if check not in used:errors.append("COMMAND_DRIFT")
    for line in commands:
        if "stack_checks.py" in line:continue
        try:tokens=shlex.split(line)
        except ValueError:continue
        for item in cfg["checks"].values():
            argv=item["argv"]
            if len(tokens)>=len(argv) and any(tokens[i:i+len(argv)]==argv for i in range(len(tokens)-len(argv)+1)):
                errors.append("COMMAND_DRIFT")
    return sorted(set(errors))

def run(name,dry_run=False,check_id=None):
    cfg=load();results=[]
    for ident in ([check_id] if check_id else cfg["sets"][name]):
        c=cfg["checks"][ident]
        if dry_run: results.append({"check_id":ident,"argv":c["argv"],"cwd":c["cwd"],"status":c["status"]});continue
        try:rc=subprocess.run(c["argv"],cwd=ROOT/c["cwd"],check=False).returncode
        except OSError:rc=127
        results.append({"check_id":ident,"exit_code":rc,"status":c["status"]})
        if rc and c["status"]=="shadow":print(f"::warning title={ident} (sombra)::Check falló con {rc}; sigue en sombra",flush=True)
    print(json.dumps({"results":results},ensure_ascii=False))
    return int(any(x.get("exit_code",0)!=0 and x["status"]=="blocking" for x in results))
def main():
    p=argparse.ArgumentParser();p.add_argument("command",choices=["run","validate"])
    p.add_argument("--set",choices=["spring-boot","nextjs","postgres-flyway"])
    p.add_argument("--dry-run",action="store_true");p.add_argument("--check-id");p.add_argument("--ci");a=p.parse_args()
    if a.command=="validate":
        d=load();errs=[x for k,v in d["sets"].items() for x in v if x not in d["checks"]]
        if a.ci:errs+=validate_ci(d,Path(a.ci).read_text(encoding="utf-8"))
        print(json.dumps({"findings":errs}));return int(bool(errs))
    if not a.set and not a.check_id:p.error("--set or --check-id required")
    return run(a.set,a.dry_run,a.check_id)
if __name__=="__main__":sys.exit(main())
