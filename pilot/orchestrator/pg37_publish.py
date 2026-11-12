#!/usr/bin/env python3
"""Publish CP3.7 per-request H_REPORT draft after a verified Train merge."""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
import chain_lots
from pg37_evidence import generate,render,canonical,digest

ROOT=Path(__file__).resolve().parents[2]
def reconcile(source_run_id,*,root=ROOT,evidence_generator=generate,publisher=None):
 head=chain_lots.check_main()
 if chain_lots.event_kind(source_run_id,head)!="TRAIN":
  return [{"status":"NOT_SUCCESSFUL_TRAIN"}]
 history=chain_lots.first_parent_merges()
 results=[]
 for request,lots,state,bindings in chain_lots.plans():
  completed=chain_lots.completed_lots(lots,bindings,history)
  if not completed:continue
  records=[]
  for lot in lots["lots"]:
   receipt=completed.get(lot["id"])
   if receipt is None:continue
   history_item=next((h for h in history if h[0]==receipt["merge_sha"]),None)
   if history_item is None:raise ValueError("CP37_MERGE_NOT_IN_HISTORY")
   changed=set(history_item[2])&set(lot["write_paths"])
   folder=root/"pilot"/"runs"/request
   afile=folder/"analysis.json"
   pfile=root/"pilot"/"orchestrator"/"evidence_inputs"/request/(lot["id"]+".json")
   if not afile.is_file() or afile.is_symlink() or pfile.is_symlink():
    raise ValueError("CP37_ANALYSIS_MISSING_OR_SYMLINK")
   analysis=json.loads(afile.read_text("utf-8"))
   exists=pfile.is_file()
   packet=json.loads(pfile.read_text("utf-8")) if exists else {
    "schema_version":"CP37_EVIDENCE_INPUTS_V1","lot_id":lot["id"],"producer_inputs":{},"requirement_links":[]}
   evidence=evidence_generator(root,request,lot,receipt["merge_sha"],changed,packet,analysis)
   if not exists:
    evidence["input_status"]="BLOCKED_CP37_EVIDENCE_INPUTS_MISSING"
    evidence["complete"]=False
    evidence["evidence_sha256"]=digest({k:v for k,v in evidence.items() if k!="evidence_sha256"})
   records.append(evidence)
  if not records:continue
  branch=f"lf/evidence/{request}-{head[:12]}"
  if chain_lots.pending_draft(f"lf/evidence/{request}-") or chain_lots.run("git","ls-remote","--heads","origin",branch):
   results.append({"request":request,"status":"REPORT_DRAFT_ALREADY_PRESENT"});continue
  report=render(request,records)
  def prepare(work):
   paths=[]
   for row in records:
    target=work/"pilot"/"runs"/request/"evidence"/(row["lot_id"]+"-"+row["merge_sha"][:12]+".json")
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(canonical(row)+b"\n")
    paths.append(target.relative_to(work).as_posix())
   target=work/"pilot"/"runs"/request/"H_REPORT.md"
   target.parent.mkdir(parents=True,exist_ok=True)
   target.write_text(report,encoding="utf-8")
   paths.append(target.relative_to(work).as_posix())
   create=publisher or chain_lots.draft
   info=create(work,branch,request,paths,
     f"CP3.7 pinned source-only evidence for verified integration merges at {head}; no production authority",
     f"H_REPORT {request} PG06-PG14")
   return {"request":request,"status":"EVIDENCE_DRAFT_CREATED","lot_count":len(records),
           "all_candidates_complete":all(row["complete"] for row in records),**info}
  results.append(chain_lots.worktree(head,branch,prepare))
 return results or [{"status":"NO_MERGED_LOTS_FOR_REPORT"}]

def main():
 p=argparse.ArgumentParser();p.add_argument("--source-run-id",type=int,required=True)
 args=p.parse_args()
 if args.source_run_id<=0 or os.environ.get("GITHUB_REPOSITORY")!=chain_lots.REPO or not os.environ.get("GH_TOKEN"):
  raise SystemExit("CP37_TRUSTED_CONTEXT_REQUIRED")
 print(json.dumps(reconcile(args.source_run_id),sort_keys=True))
if __name__=="__main__":main()
