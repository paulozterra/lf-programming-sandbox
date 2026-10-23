"""Deterministic V1 stack check runner. Shared source of CI and skills."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
CHECKS=ROOT/"standards/skills/checks/stack-checks.json"

def load():return json.loads(CHECKS.read_text(encoding="utf-8"))
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
    p.add_argument("--dry-run",action="store_true");p.add_argument("--check-id");a=p.parse_args()
    if a.command=="validate":
        d=load();errs=[x for k,v in d["sets"].items() for x in v if x not in d["checks"]]
        print(json.dumps({"findings":errs}));return int(bool(errs))
    if not a.set and not a.check_id:p.error("--set or --check-id required")
    return run(a.set,a.dry_run,a.check_id)
if __name__=="__main__":sys.exit(main())
