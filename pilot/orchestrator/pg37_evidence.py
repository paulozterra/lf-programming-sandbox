#!/usr/bin/env python3
"""CP3.7: original pinned candidates + local tests; never grant production authority."""
from __future__ import annotations
import contextlib,hashlib,importlib,io,json,re,subprocess,sys
from pathlib import Path

PIN=Path(__file__).resolve().parents[1]/"lf_producers_pinned"
STAGES={
 "PG-06":("pg06_preflight_candidate","pg06_c1_currentness_reuse_candidate_v1","prepare_pg06_c1",("pg05_exit","pg01_currentness_binding")),
 "PG-08":("pg08_build_candidate","pg08_c1_build_compilation_candidate_v1","prepare_pg08_c1",("pg07_c6","build_observations")),
 "PG-09":("pg09_iteration_candidate","pg09_c1_iteration_cost_governor_candidate_v2","prepare_pg09_c1",("pg07_c1","pg07_c5","budget_policy","usage_observations","native_execution_evidence")),
 "PG-10":("pg10_conflict_candidate","pg10_c1_conflict_inventory_candidate_v1","prepare_pg10_c1",("pg07_c5","pg09_c4","conflict_observations")),
 "PG-11":("pg11_integrity_candidate","pg11_c4_diff_requirement_batch_trace_candidate_v2","prepare_pg11_c4",("pg11_c1","pg11_c2","pg11_c3","declared_diff","authorized_scope","trace_observations")),
 "PG-12":("pg12_identity_candidate","pg12_disposable_postgres_readback_v2","persist_readback",("pg12_c4",)),
 "PG-13":("pg13_freeze_candidate","pg13_disposable_git_mutation_test_v1","main",()),
 "PG-14":("pg14_testing_handoff_candidate","pg14_local_testing_receiver_v2","simulate_testing_receiver",("pg14_bridge","pg14_c1","pg14_c2","pg14_c3","request_payload"))
}
REQ=re.compile(r"REQ-[A-Z0-9-]+\Z")
SHA=re.compile(r"[a-f0-9]{40}\Z")
def canonical(v):
 return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
def digest(v): return hashlib.sha256(canonical(v)).hexdigest()
def pinned(stage):
 directory,module,_,_=STAGES[stage]
 path=(PIN/directory/"tools").resolve()
 if not path.is_dir():raise ValueError("CP37_PINNED_PRODUCER_MISSING")
 if str(path) not in sys.path:sys.path.insert(0,str(path))
 loaded=importlib.import_module(module)
 if Path(loaded.__file__).resolve()!=path/(module+".py"):raise ValueError("CP37_PINNED_MODULE_REDIRECT")
 return loaded
def run_stage(stage,packet):
 """Invokes original pinned producer with its exact named parameters."""
 module=pinned(stage)
 method=getattr(module,STAGES[stage][2])
 if stage=="PG-13":
  stream=io.StringIO()
  with contextlib.redirect_stdout(stream):method()
  raw=stream.getvalue()
  if raw.count("_BLOCK=PASS")!=5 or "PG13_C3_PRODUCTION_FREEZE_VERIFIED=FALSE" not in raw:
   raise ValueError("CP37_LOCAL_FREEZE_ATTACK_INCOMPLETE")
  return {"local_git_attacks":5,"stdout_sha256":hashlib.sha256(raw.encode()).hexdigest(),"production_freeze_verified":False}
 names=STAGES[stage][3]
 data=packet.get("producer_inputs",{}).get(stage)
 if not isinstance(data,dict) or any(key not in data for key in names):
  raise ValueError("CP37_PINNED_INPUTS_MISSING")
 if set(data)!=set(names):raise ValueError("CP37_PINNED_INPUTS_SHAPE_DRIFT")
 if stage=="PG-12":
  with contextlib.redirect_stdout(io.StringIO()) as stream:
   sha=method(data["pg12_c4"])
  return {"local_postgres_sha256":sha,"stdout_sha256":hashlib.sha256(stream.getvalue().encode()).hexdigest(),"production_persisted":False}
 result=method(**data)
 if not isinstance(result,dict) or result.get("production_authority") is not False:
  raise ValueError("CP37_PINNED_OUTPUT_AUTHORITY_INVALID")
 if stage=="PG-14":
  if result.get("testing_real_invoked") is not False or result.get("local_fixture_only") is not True:
   raise ValueError("CP37_TESTING_RECEIVER_NOT_LOCAL")
 else:
  if result.get("handoff_allowed") is not False:
   raise ValueError("CP37_PINNED_OUTPUT_HANDOFF_UNSAFE")
 return result
def trace_requirements(analysis,packet,paths):
 rows=analysis.get("requirements")
 if not isinstance(rows,list) or not rows:raise ValueError("CP37_REQUIREMENTS_MISSING")
 ids=[x.get("requirement_id") for x in rows if isinstance(x,dict)]
 if len(ids)!=len(rows) or len(ids)!=len(set(ids)) or not all(isinstance(x,str) and REQ.fullmatch(x) for x in ids):
  raise ValueError("CP37_REQUIREMENTS_INVALID")
 links=packet.get("requirement_links")
 if not isinstance(links,list) or not links:raise ValueError("CP37_REQUIREMENT_LINKS_MISSING")
 matched=set()
 result=[]
 for item in links:
  if not isinstance(item,dict) or set(item)!={"path","requirement_ids","evidence_ref"}:
   raise ValueError("CP37_LINK_INVALID")
  p,refs,e=item["path"],item["requirement_ids"],item["evidence_ref"]
  if p not in paths or not isinstance(refs,list) or not refs or len(refs)!=len(set(refs)):
   raise ValueError("CP37_REQUIREMENT_SCOPE_INVALID")
  if not set(refs).issubset(ids) or not isinstance(e,str) or not e.strip():
   raise ValueError("CP37_UNKNOWN_REQUIREMENT_OR_EVIDENCE")
  matched.add(p)
  result.append({"path":p,"requirement_ids":sorted(refs),"evidence_ref":e,"source_verified":False})
 if matched!=set(paths):raise ValueError("CP37_ORPHAN_DIFF_PATH")
 return {"requirements_from_analysis":ids,"links":sorted(result,key=lambda x:x["path"]),"trace_candidate_only":True,"requirements_approved":False}
def build_lint(root,area):
 commands={
 "BACKEND":[(["mvn","-B","-q","-f","apps/time-service/pom.xml","spotless:check"],"palantir"),(["mvn","-B","-q","-f","apps/time-service/pom.xml","test"],"maven-test")],
 "FRONTEND":[(["python3","standards/tools/stack_checks.py","run","--set","nextjs","--check-id","next-lint"],"next-lint"),(["python3","standards/tools/stack_checks.py","run","--set","nextjs","--check-id","next-build"],"next-build")],
 "DATA":[(["python3","standards/tools/stack_checks.py","run","--set","postgres-flyway","--check-id","db-catalog-files"],"db-catalog")]}
 if area not in commands:raise ValueError("CP37_AREA_UNKNOWN")
 out=[]
 for argv,label in commands[area]:
  try:
   p=subprocess.run(argv,cwd=root,capture_output=True,timeout=180)
   out.append({"check":label,"command":argv,"result":"PASS" if p.returncode==0 else "FAIL","exit_code":p.returncode,"stdout_sha256":hashlib.sha256(p.stdout).hexdigest(),"stderr_sha256":hashlib.sha256(p.stderr).hexdigest()})
  except (OSError,subprocess.TimeoutExpired):
   out.append({"check":label,"command":argv,"result":"BLOCKED","reason_code":"CP37_TOOLCHAIN_UNAVAILABLE"})
 return out
def generate(root,request,lot,merge_sha,changed,packet,analysis,*,build_runner=build_lint,stage_runner=run_stage):
 if not SHA.fullmatch(merge_sha) or not isinstance(packet,dict):
  raise ValueError("CP37_BAD_MERGE_OR_PACKET")
 if packet.get("schema_version")!="CP37_EVIDENCE_INPUTS_V1" or packet.get("lot_id")!=lot["id"]:
  raise ValueError("CP37_INPUT_LOT_MISMATCH")
 if not changed or not set(changed).issubset(lot["write_paths"]):
  raise ValueError("CP37_DIFF_OUT_OF_SCOPE")
 if analysis.get("production_authority") is not False:
  raise ValueError("CP37_ANALYSIS_AUTHORITY_INVALID")
 report={"schema_version":"CP37_LOT_EVIDENCE_V1","request_id":request,"lot_id":lot["id"],"merge_sha":merge_sha,"changed_paths":sorted(changed),"analysis_sha256":digest(analysis),"packet_sha256":digest(packet),"production_authority":False,"handoff_allowed":False,"requirements":None,"stages":{}}
 try:report["requirements"]=trace_requirements(analysis,packet,changed)
 except ValueError as e:report["requirements"]={"status":"BLOCKED","reason_code":str(e)}
 for stage in ["PG-06","PG-07","PG-08","PG-09","PG-10","PG-11","PG-12","PG-13","PG-14"]:
  try:
   if stage=="PG-07":
    value={"native_worker_reinvoked":False,"integration_merge_sha":merge_sha,"source":"CP35_VERIFIED_MERGE"}
    status="OBSERVED_MERGE_ONLY"
   elif stage=="PG-08":
    checks=build_runner(root,lot["area"])
    if not checks or any(row["result"]!="PASS" for row in checks):raise ValueError("CP37_BUILD_LINT_NOT_PASS")
    value={"observed_build_lint":checks}
    try:
     value["pinned_candidate"]=stage_runner(stage,packet)
     status="LOCAL_CHECKS_PASS_SOURCE_CANDIDATE"
    except ValueError as e:
     value["pinned_input_blocker"]=str(e);status="LOCAL_CHECKS_PASS_PINNED_INPUT_BLOCKED"
   else:
    if stage=="PG-11" and report["requirements"].get("status")=="BLOCKED":
     raise ValueError("CP37_REQUIREMENT_TRACE_BLOCKED")
    value=stage_runner(stage,packet)
    status="LOCAL_TEST_PASS_ONLY" if stage in ("PG-12","PG-13","PG-14") else "PINNED_SOURCE_CANDIDATE_ONLY"
    if stage=="PG-14" and value.get("verdict")!="ACCEPT":
     raise ValueError("CP37_LOCAL_RECEIVER_BLOCKED")
   report["stages"][stage]={"status":status,"evidence_sha256":digest(value),"evidence":value,"production_authority":False}
  except (ValueError,AssertionError,OSError,KeyError,subprocess.TimeoutExpired) as e:
   report["stages"][stage]={"status":"BLOCKED","reason_code":str(e).splitlines()[0][:160],"production_authority":False}
 report["complete"]=all(x["status"] not in ("BLOCKED","LOCAL_CHECKS_PASS_PINNED_INPUT_BLOCKED") for x in report["stages"].values()) and report["requirements"].get("status")!="BLOCKED"
 report["evidence_sha256"]=digest(report)
 return report
def render(request,rows):
 lines=[f"# H_REPORT — {request}","","Evidencia candidata sin autoridad productiva ni admisión real de Testing.","","| Lote | Merge | Etapas | Estado |","|---|---|---|---|"]
 for r in rows:
  blocked=sum(x["status"]=="BLOCKED" for x in r["stages"].values())
  lines.append(f"| {r['lot_id']} | `{r['merge_sha']}` | {len(r['stages'])} ({blocked} bloqueadas) | {'CANDIDATE_ONLY' if r['complete'] else 'BLOCKED_EVIDENCE_INCOMPLETE'} |")
 lines+=["","## Evidencia por lote",""]
 for r in rows:
  lines += [f"### {r['lot_id']}",f"Huella: `{r['evidence_sha256']}`","Requisitos A9: "+(", ".join("`"+x+"`" for x in r["requirements"].get("requirements_from_analysis",[])) or "SIN_TRAZA_VERIFICABLE"),"","| Etapa | Estado | Código |","|---|---|---|"]
  for stage,e in r["stages"].items():
   lines.append(f"| {stage} | {e['status']} | {e.get('reason_code','sin autoridad')} |")
  lines.append("")
 lines+=["## Límites","", "No se ejecutan oráculos ocultos, Supabase productivo ni Testing real. La ausencia de entradas originales permanece BLOCKED.", ""]
 return "\n".join(lines)
