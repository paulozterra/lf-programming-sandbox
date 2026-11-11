"""Offline-only PG01/PG03/PG04 diagnostic chain; never performs real admission.

A switch skips only a lab authority gate and reports SKIPPED_FOR_DIAGNOSTICS.
It NEVER changes a canonical validator or grants PASS to a governed checkpoint.
"""
import argparse
import hashlib
import json
from pathlib import Path

from pg04_semantic_partition_candidate_v1 import partition_by_semantic_outcome
from pg04_partition_admission_probe_v1 import inspect_candidate
from pg04_definition_of_done_candidate_v1 import prepare_dod
from pg04_independent_review_request_v1 import prepare_partition_review_request

HERE=Path(__file__).resolve().parents[1]
PACKET=HERE/"fixtures/programming_synthetic_lab_packet_v1.json"
GATES=("A9_CURRENTNESS","PG03_GOVERNED_RECEIPT","PG04_SOURCE_AUTHENTICITY",
       "PG04_INDEPENDENT_REVIEW")

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                                     ensure_ascii=True).encode()).hexdigest()

def _note(rows,step,status,detail):
    rows.append({"step":step,"status":status,"detail":detail})

def _result(rows,packet):
    return {
        "schema_version":"LF_PROGRAMMING_OFFLINE_CHAIN_REPORT_V1",
        "case_id":packet["case_id"],
        "simulation_only":True,"source_authenticity":"SYNTHETIC_NOT_ATTESTED",
        "governed_execution":False,"production_authority":False,
        "pg01_admitted":False,"pg03_admitted":False,"pg04_admitted":False,
        "checkpoint_closure_allowed":False,"receipts_verified":False,
        "stages":rows,
        "first_authority_blocker":next((r["step"] for r in rows
             if r["status"] in ("BLOCKED","SKIPPED_FOR_DIAGNOSTICS")),None),
    }

def _gate(rows,name,skips):
    if name in skips:
        _note(rows,name,"SKIPPED_FOR_DIAGNOSTICS",
              "Synthetic-only continuation. Gate NOT PASSED; production still blocked.")
        return True
    _note(rows,name,"BLOCKED",
          "Requires current governed source and authenticated receipt; synthetic inputs never qualify.")
    return False

def _strategy(packet):
    base=dict(packet["strategy_fixture"],
              status="CANDIDATE_NOT_ADMITTED",
              production_authority=False,handoff_allowed=False,
              simulation_only=True)
    base["candidate_sha256"]=digest(base)
    return base

def _plans(partition,standards):
    plans=[]
    for sol in partition["solutions"]:
        scopes=set(sol["write_scope"])
        codes=sorted(x["standard_code"] for x in standards
                     if scopes.intersection(x["applies_to_write_scopes"]))
        checks=[]
        def append(kind,ident,bound=None):
            ch={"check_id":kind+"-"+ident,"kind":kind,
                "validation_code":"PROGRAMMING_GITHUB_FILE_TEXT_ASSERT_V1",
                "input_ref":"synthetic://planned-check/"+sol["id"]+"/"+ident,
                "requirement_ids":[],"acceptance_ids":[]}
            if kind=="STANDARD":ch["standard_code"]=ident
            if kind=="REQUIREMENT":ch["requirement_ids"]=[ident]
            if kind=="ACCEPTANCE":ch["acceptance_ids"]=[ident]
            if kind=="DEPENDENCY":ch["dependency_ids"]=[ident]
            checks.append(ch)
        for code in codes:append("STANDARD",code)
        for req in sol["requirement_ids"]:append("REQUIREMENT",req)
        for acc in sol["acceptance_ids"]:append("ACCEPTANCE",acc)
        for dep in sol["depends_on"]:append("DEPENDENCY",dep)
        plans.append({"solution_id":sol["id"],"standard_codes":codes,"checks":checks})
    return plans

def run(packet,*,mode="strict",skip_gates=()):
    if mode not in ("strict","diagnostic"):
        raise ValueError("LAB_MODE_INVALID")
    skipped=set(skip_gates)
    if not skipped.issubset(GATES):
        raise ValueError("LAB_UNKNOWN_GATE")
    if skipped and mode!="diagnostic":
        raise ValueError("STRICT_MODE_CANNOT_SKIP_GATES")
    if packet.get("schema_version")!="LF_PROGRAMMING_SYNTHETIC_LAB_PACKET_V1" or packet.get("simulation_only") is not True or packet.get("source_authenticity")!="SYNTHETIC_NOT_ATTESTED" or packet.get("fake_a9",{}).get("receipt_id") is not None:
        raise ValueError("LAB_REQUIRES_UNTRUSTED_SYNTHETIC_PACKET")
    rows=[]
    _note(rows,"PACKET","SYNTHETIC_INPUT_ACCEPTED","Fixture only, not A9 admitted")
    if not _gate(rows,"A9_CURRENTNESS",skipped):return _result(rows,packet)
    _note(rows,"PG01","SIMULATED_NOT_ADMITTED","No official PG01 writer, receipt or verdict")
    if not _gate(rows,"PG03_GOVERNED_RECEIPT",skipped):return _result(rows,packet)
    strategy=_strategy(packet)
    _note(rows,"PG03","FIXTURE_NOT_EXECUTED",
          "PG03 strategy candidate created from supplied typed fields, not PG03 engine")
    partition=partition_by_semantic_outcome(
        strategy=strategy,partition_contract=packet["partition_contract"],
        obligations=packet["obligations"],outcome_registry=packet["outcome_registry"])
    _note(rows,"PG04_C2","VALIDATED_SYNTHETIC",
          "Real candidate partitioner generated "+str(len(partition["solutions"]))+" SOLUTIONs")
    probe=inspect_candidate(partition_policy=packet["partition_contract"],
        strategy=strategy,
        source_refs={"contract_path":"synthetic://partition-policy",
                     "contract_commit":"0"*40,
                     "j02_source_path":"synthetic://j02",
                     "j02_source_commit":"0"*40},
        solutions=partition["solutions"])
    _note(rows,"PG04_C3_C4","VALIDATED_SYNTHETIC",
          "Real inspector: "+str(probe["requirement_coverage_count"])+
          " requirements, "+str(probe["acceptance_coverage_count"])+" acceptances")
    dod=prepare_dod(partition=partition,
        standards_catalog_version=packet["standard_catalog_version"],
        standards=packet["standards"],
        validation_registry=packet["validator_registry"],
        solution_plans=_plans(partition,packet["standards"]))
    _note(rows,"PG04_C5","PLANNED_NOT_EXECUTED",
          str(sum(x["check_count"] for x in dod["solutions"]))+
          " planned checks, zero test receipts")
    if not _gate(rows,"PG04_SOURCE_AUTHENTICITY",skipped):return _result(rows,packet)
    sources={key:{"ref":"synthetic://"+key,"sha256":digest(packet.get(key,{}))}
             for key in ("a9_package","pg03_strategy","pg04_partition_contract",
                         "outcome_registry","typed_obligations")}
    sources["pg03_strategy"]["sha256"]=strategy["candidate_sha256"]
    sources["source_head_sha"]="0"*40
    request=prepare_partition_review_request(partition=partition,
        sources=sources,producer_execution_id="synthetic://producer/001")
    _note(rows,"PG04_C7","REQUEST_PREPARED_NOT_EXECUTED",
          request["first_runtime_blocker"]+"; subject_receipt_id=null")
    if not _gate(rows,"PG04_INDEPENDENT_REVIEW",skipped):return _result(rows,packet)
    _note(rows,"END","LAB_REACHED_END_NO_AUTHORITY",
          "All structural steps inspected. No judge run, no PG07 readiness, no production admission.")
    return _result(rows,packet)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--mode",choices=("strict","diagnostic"),default="strict")
    ap.add_argument("--skip-gates",default="",
                    help="comma-separated lab gates; diagnostic mode only")
    ap.add_argument("--fixture",type=Path,default=PACKET)
    opts=ap.parse_args()
    packet=json.loads(opts.fixture.read_text(encoding="utf-8"))
    skipped=tuple(x for x in opts.skip_gates.split(",") if x)
    report=run(packet,mode=opts.mode,skip_gates=skipped)
    print(json.dumps(report,indent=2,ensure_ascii=False))
if __name__=="__main__":main()
