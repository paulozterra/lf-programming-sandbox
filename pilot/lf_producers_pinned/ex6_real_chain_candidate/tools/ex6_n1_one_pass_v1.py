"""Run PG04-PG14 once, with independently checked N+1 build/format evidence.
The original EX6 patch and Git identity are N; PG12/13 local freeze remains
identified as N, never misrepresented as a freeze of reformatted N+1 blobs.
"""
from __future__ import annotations
import json
from ex6_n1_receipts_v1 import verify_both, EXPECTED
from ex6_build_lint_inputs_v1 import using_receipt
from ex6_one_pass_v1 import run_all

def run_n1():
    verify_both()
    with using_receipt("N1"):
        result=run_all()  # one invocation of PG04..PG14, including original v2 producers
    if [x["stage"] for x in result["stages"]] != ["PG-%02d"%i for i in range(4,15)]:
        raise AssertionError("EX6_N1_STAGE_COVERAGE")
    ev=result["evidence"]
    if ev["pg08_c2_format_aosp_exit_code"]!=0:
        raise AssertionError("EX6_N1_AOSP_NOT_PASS")
    if (ev["rem_d4_process"]["aosp_exit_code"]!=0 or
        ev["rem_d4_process"]["visible_test_exit_code"]!=0 or
        ev["rem_d4_process"]["process_requirement_satisfied"] is not True):
        raise AssertionError("EX6_N1_REM_D4_NOT_PASS")
    local=ev["local_v2"]
    if (local["pg11_actual_link_count"]!=4 or
        local["pg13_local_mutations_blocked"]!=5 or
        local["pg14_tampered_verdict"]!="BLOCK" or
        local["real_analysis_ready"] is not False or
        local["real_testing_invoked"] is not False or
        local["production_authority"] is not False):
        raise AssertionError("EX6_N1_V2_LOCAL_GUARD_FAILED")
    result["evidence_lineage"]={
        "formatting_snapshots":{"N":EXPECTED["N"]["candidate"],"N1":EXPECTED["N1"]["candidate"]},
        "active_build_and_lint_receipt":"N1",
        "original_patch_blobs_source":"N",
        "pg12_c1_git_identity":"N_ORIGINAL_PATCH_NOT_REBASED_TO_N1",
        "pg13_local_git_freeze_identity":"N_ORIGINAL_PATCH_NOT_N1",
        "PG12_13_14_N1_production_admission":False,
        "holdout_accessed":False,
        "super_admin_signed":False,
        "production_authority":False,
    }
    return result

if __name__=="__main__":
    data=run_n1()
    print(json.dumps(data,sort_keys=True,indent=2))
    print("EX6_N1_PG04_PG14_ONE_PASS_SOURCE_ONLY_PASS")
