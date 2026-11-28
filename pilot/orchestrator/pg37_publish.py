#!/usr/bin/env python3
"""Publish CP3.7 per-request H_REPORT draft after a verified Train merge."""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
import chain_lots
from pilot.orchestrator.request_lifecycle import request_state, RequestStateError, OPEN, inactive_reason, require_open
from pg37_evidence import generate,render,canonical,digest,validate_record
from pilot.config.project_config import storage_path

ROOT=Path(__file__).resolve().parents[2]
def report_progress(root,request,lots,completed):
 """Reuse exact existing per-lot evidence. A foreign/malformed report is not
 permission to overwrite historical bytes, even on an open issue.
 """
 folder=storage_path("requests_root",root=root)/request
 target=folder/"H_REPORT.md"
 if target.is_symlink():raise ValueError("CP37_REPORT_SYMLINK")
 known={}
 missing=[]
 for lot in lots["lots"]:
  receipt=completed.get(lot["id"])
  if receipt is None:continue
  sha=receipt["merge_sha"]
  path=folder/"evidence"/(lot["id"]+"-"+sha[:12]+".json")
  if path.is_symlink() or path.parent.is_symlink():
   raise ValueError("CP37_EVIDENCE_SYMLINK")
  if not path.exists():
   missing.append(lot)
   continue
  row=validate_record(json.loads(path.read_text("utf-8")),request,lot["id"],sha)
  known[lot["id"]]=row
 existing=target.read_bytes() if target.exists() else None
 if existing is not None and existing!=render(request,list(known.values())).encode("utf-8"):
  raise ValueError("CP37_EXISTING_REPORT_UNRESOLVED")
 return folder,known,missing,existing is not None and not missing


def reconcile(source_run_id,*,root=ROOT,evidence_generator=generate,publisher=None):
 head=chain_lots.check_main()
 if chain_lots.event_kind(source_run_id,head)!="TRAIN":
  return [{"status":"NOT_SUCCESSFUL_TRAIN"}]
 results=[]
 for request,lots,state,bindings in chain_lots.plans():
  try:
    try:
     current=request_state(request,chain_lots.lifecycle_api,root=root)
     if current!=OPEN:
      results.append({"request":request,"status":inactive_reason(current)});continue
    except RequestStateError:
     results.append({"request":request,"status":"REQUEST_STATE_UNRESOLVED"});continue
    history=chain_lots.first_parent_merges(request,root=root)
    completed=chain_lots.completed_lots(lots,bindings,history)
    if not completed:continue
    folder,known,missing,current=report_progress(root,request,lots,completed)
    if current:
     results.append({"request":request,"status":"REPORT_ALREADY_PRESENT"});continue
    # Keep historical bytes. Check their changed paths against the same
    # verified Train merge before including them in the aggregate.
    records=[]
    new=[]
    for lot in lots["lots"]:
     receipt=completed.get(lot["id"])
     if receipt is None:continue
     history_item=next((h for h in history if h[0]==receipt["merge_sha"]),None)
     if history_item is None:raise ValueError("CP37_MERGE_NOT_IN_HISTORY")
     changed=set(history_item[2])&set(lot["write_paths"])
     if lot["id"] in known:
      row=known[lot["id"]]
      if row.get("changed_paths")!=sorted(changed):
       raise ValueError("CP37_EXISTING_EVIDENCE_SCOPE_DRIFT")
      records.append(row)
      continue
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
     validate_record(evidence,request,lot["id"],receipt["merge_sha"])
     records.append(evidence)
     new.append(evidence)
    if not records:continue
    branch=f"lf/evidence/{request}-{head[:12]}"
    if chain_lots.pending_draft(f"lf/evidence/{request}-") or chain_lots.run("git","ls-remote","--heads","origin",branch):
     results.append({"request":request,"status":"REPORT_DRAFT_ALREADY_PRESENT"});continue
    summary=render(request,records)
    def prepare(work):
     require_open(request,chain_lots.lifecycle_api,root=root)
     paths=[]
     work_folder=storage_path("requests_root",root=work)/request
     for row in new:
      target=work_folder/"evidence"/(row["lot_id"]+"-"+row["merge_sha"][:12]+".json")
      if target.exists() or target.is_symlink():
       raise ValueError("CP37_EVIDENCE_ALREADY_PRESENT")
      target.parent.mkdir(parents=True,exist_ok=True)
      target.write_bytes(canonical(row)+b"\n")
      paths.append(target.relative_to(work).as_posix())
     target=work_folder/"H_REPORT.md"
     target.parent.mkdir(parents=True,exist_ok=True)
     target.write_text(summary,encoding="utf-8")
     paths.append(target.relative_to(work).as_posix())
     create=publisher or chain_lots.draft
     require_open(request,chain_lots.lifecycle_api,root=root)
     info=create(work,branch,request,paths,
       f"CP3.7 pinned source-only evidence for verified integration merges at {head}; no production authority",
       f"H_REPORT {request} PG06-PG14")
     return {"request":request,"status":"EVIDENCE_DRAFT_CREATED","lot_count":len(records),
             "all_candidates_complete":all(row["complete"] for row in records),**info}
    try:
     current=request_state(request,chain_lots.lifecycle_api,root=root)
     if current!=OPEN:
      results.append({"request":request,"status":inactive_reason(current)});continue
    except RequestStateError:
     results.append({"request":request,"status":"REQUEST_STATE_UNRESOLVED"});continue
    results.append(chain_lots.worktree(head,branch,prepare))
  except (chain_lots.ChainBlocked,ValueError,OSError,KeyError,RuntimeError) as exc:
   raw=str(exc)
   code=raw if raw.startswith(("CP36_","CP37_")) and len(raw)<240 else "CP37_LOCAL_FAILURE"
   results.append({"request":request,"status":"BLOCKED","code":code})
 return results or [{"status":"NO_MERGED_LOTS_FOR_REPORT"}]

def sweep(*,root=ROOT):
 """R1: derive missing evidence from persisted plans/main merges, not an event."""
 from pilot.config.project_config import storage_path
 head=chain_lots.check_main()
 ready=[]
 blocked=[]
 for request,lots,state,bindings in chain_lots.plans():
  try:
   if request_state(request,chain_lots.lifecycle_api,root=root)!=OPEN:continue
   prefix=f"lf/evidence/{request}-"
   if chain_lots.pending_draft(prefix):
    # Only supersede bot-authored drafts anchored to an older main; retain
    # same-base or human-authored review branches without modification.
    chain_lots.close_stale_drafts(prefix,head[:12],request)
    if chain_lots.pending_draft(prefix):continue
   history=chain_lots.first_parent_merges(request,root=root)
   completed=chain_lots.completed_lots(lots,bindings,history)
   if not completed:continue
   _,_,_,current=report_progress(root,request,lots,completed)
   if not current:ready.append(request)
  except (RequestStateError,chain_lots.ChainBlocked,OSError,ValueError,KeyError) as exc:
   blocked.append({"request":request,"status":"BLOCKED",
                   "code":"R1_CP37_STATE_UNRESOLVED"})
 if not ready:return blocked or [{"status":"R1_CP37_NO_MISSING_EVIDENCE"}]
 history=chain_lots.api("actions/workflows/sandbox-train.yml/runs?per_page=100")
 count=history.get("total_count")
 if (type(count)is not int or count<0 or count>1000
     or not isinstance(history.get("workflow_runs"),list)
     or len(history["workflow_runs"])!=min(count,100)):
  raise ValueError("R1_CP37_TRAIN_HISTORY_INCOMPLETE")
 rows=list(history["workflow_runs"])
 for page in range(2,(count+99)//100+1):
  chunk=chain_lots.api(f"actions/workflows/sandbox-train.yml/runs?per_page=100&page={page}")
  values=chunk.get("workflow_runs")
  if (chunk.get("total_count")!=count or not isinstance(values,list)
      or len(values)!=min(100,count-len(rows))):
   raise ValueError("R1_CP37_TRAIN_HISTORY_INCOMPLETE")
  rows.extend(values)
 for row in sorted(rows,key=lambda item:item.get("id",0),reverse=True):
  if not isinstance(row,dict) or type(row.get("id")) is not int:continue
  if (row.get("status")!="completed" or row.get("conclusion")!="success"
      or (row.get("path") or "").split("@")[0]!=".github/workflows/sandbox-train.yml"
      or (row.get("repository") or {}).get("full_name")!=chain_lots.REPO):continue
  try:
   if chain_lots.event_kind(row["id"],head)=="TRAIN":
    return blocked+reconcile(row["id"],root=root)
  except (chain_lots.ChainBlocked,ValueError,KeyError):
   continue
 raise ValueError("R1_CP37_SOURCE_UNAVAILABLE")


def main():
 p=argparse.ArgumentParser();p.add_argument("--source-run-id",type=int);p.add_argument("--sweep",action="store_true")
 args=p.parse_args()
 if (args.sweep==(args.source_run_id is not None)
     or (args.source_run_id is not None and args.source_run_id<=0)
     or os.environ.get("GITHUB_REPOSITORY")!=chain_lots.REPO
     or not os.environ.get("GH_TOKEN")):
  raise SystemExit("CP37_TRUSTED_CONTEXT_REQUIRED")
 try:
  if args.sweep:
   from pilot.orchestrator import sweep_api_budget as budget
   with budget.session(), budget.phase("PG37"):
    result=sweep()
  else:
   result=reconcile(args.source_run_id)
 except (chain_lots.ChainBlocked,ValueError,KeyError,OSError) as exc:
  raise SystemExit("R1_CP37_SWEEP_BLOCKED:"+str(exc)) from exc
 print(json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
