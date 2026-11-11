"""CP3.7 offline candidate evidence and two-lot end-to-end report tests."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from pg37_evidence import generate,render,trace_requirements,STAGES

SHA="a"*40
def analysis():
 return {"production_authority":False,"requirements":[{"requirement_id":"REQ-A-001"},{"requirement_id":"REQ-B-002"}]}
def packet(lot,path,req):
 return {"schema_version":"CP37_EVIDENCE_INPUTS_V1","lot_id":lot,"requirement_links":[{"path":path,"requirement_ids":[req],"evidence_ref":"fixture://visible"}],"producer_inputs":{}}
def stage(name,p):
 if name=="PG-13":return {"local_git_attacks":5,"production_freeze_verified":False}
 raise ValueError("PINNED_INPUT_MISSING:"+name)
def build(root,area):return [{"result":"PASS","check":area,"exit_code":0}]
def test_two_lots_full_report_no_fake_authority(tmp_path):
 records=[]
 for i,area,path,req in [(1,"DATA","db/migration/V001__test.sql","REQ-A-001"),
                         (2,"BACKEND","apps/time-service/src/main/java/x/X.java","REQ-B-002")]:
  lot={"id":f"L{i}","area":area,"write_paths":[path]}
  r=generate(tmp_path,"req",lot,SHA,{path},packet(lot["id"],path,req),
             analysis(),build_runner=build,stage_runner=stage)
  assert r["stages"]["PG-08"]["status"]=="LOCAL_CHECKS_PASS_PINNED_INPUT_BLOCKED"
  assert r["stages"]["PG-09"]["status"]=="BLOCKED"
  assert r["stages"]["PG-13"]["status"]=="LOCAL_TEST_PASS_ONLY"
  assert r["requirements"]["trace_candidate_only"]
  assert not r["complete"] and not r["production_authority"]
  records.append(r)
 report=render("req",records)
 assert "# H_REPORT — req" in report and "L1" in report and "L2" in report
 assert "REQ-A-001" in report and "REQ-B-002" in report
 assert "BLOCKED_EVIDENCE_INCOMPLETE" in report and "PG-14" in report
def test_requirements_unknown_or_orphan_block():
 p=packet("L1","db/X.sql","REQ-UNKNOWN")
 with pytest.raises(ValueError,match="UNKNOWN"):
  trace_requirements(analysis(),p,{"db/X.sql"})
 p=packet("L1","db/X.sql","REQ-A-001")
 with pytest.raises(ValueError,match="ORPHAN"):
  trace_requirements(analysis(),p,{"db/X.sql","db/Y.sql"})
def test_no_scope_or_authority_escapes(tmp_path):
 lot={"id":"L1","area":"DATA","write_paths":["db/X.sql"]}
 with pytest.raises(ValueError,match="DIFF_OUT_OF_SCOPE"):
  generate(tmp_path,"req",lot,SHA,{"vendor/X.java"},packet("L1","db/X.sql","REQ-A-001"),
           analysis(),build_runner=build,stage_runner=stage)
 with pytest.raises(ValueError,match="ANALYSIS_AUTHORITY"):
  generate(tmp_path,"req",lot,SHA,{"db/X.sql"},packet("L1","db/X.sql","REQ-A-001"),
           {"production_authority":True},build_runner=build,stage_runner=stage)
def test_original_producer_registry_versions():
 assert set(STAGES)=={"PG-06","PG-08","PG-09","PG-10","PG-11","PG-12","PG-13","PG-14"}
 assert STAGES["PG-09"][1].endswith("_v2")
 assert STAGES["PG-12"][1].endswith("_v2")
 assert STAGES["PG-14"][1].endswith("_v2")
