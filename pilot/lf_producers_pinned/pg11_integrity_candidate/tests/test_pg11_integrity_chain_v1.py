"""PG11: C1-C5 real producers; hunk/waiver/canonical alias negative tests.

Fixtures are declarations only, NOT proof of Git readback or approvals.
"""
import copy,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"pg11_integrity_candidate"/"tools"))
from pg11_c1_diff_hygiene_candidate_v1 import prepare_pg11_c1,PG11C1Blocked
from pg11_c2_terminology_catalog_candidate_v1 import prepare_pg11_c2,PG11C2Blocked
from pg11_c3_suppression_waiver_candidate_v1 import prepare_pg11_c3,PG11C3Blocked
from pg11_c4_diff_requirement_batch_trace_candidate_v1 import prepare_pg11_c4,PG11C4Blocked
from pg11_c5_independent_reviewer_candidate_v1 import prepare_pg11_c5,PG11C5Blocked
from pg11_integrity_extension_candidate_v1 import (
    prepare_pg11_hunk_trace,reject_invalid_waiver,guard_pg11_reviewer_aliases,
    PG11IntegrityBlocked)
SHA="a"*64
FILE="src/contracts/feature.py"

def diff_scope():
    diff=[{"path":FILE,"change_type":"MODIFIED","old_path":None}]
    scope=[{**diff[0],"scope_ref":"fixture://scope/S1",
        "requirement_ref":"fixture://requirements/R1","batch_ref":"fixture://batches/B1"}]
    return diff,scope

def terminology():
    return [{"path":FILE,"symbol_ref":"fixture://symbol/Feature",
        "kind":"DOMAIN_IDENTIFIER","literal_value":"Feature",
        "source_ref":"fixture://source/feature.py","term_ids":["TERM-001"],
        "term_exists_reported":True,"term_matches_reported":True,
        "literal_match_reported":True,"neighbor_match_reported":True}]

def waiver(suppression_id="SUP-001",status="APPROVED",standard="STD-GEN-05"):
    return {"waiver_ref":"fixture://waiver/1","standard_ref":standard,
        "scope_path":FILE,"suppression_id":suppression_id,
        "approving_authority_ref":"fixture://owner",
        "approval_record_ref":"fixture://approval/1",
        "approval_status_reported":status,
        "effective_version_ref":"fixture://std/version","rationale_ref":"fixture://reason"}

def suppression():
    return {"suppression_id":"SUP-001","path":FILE,"kind":"CODE_REMOVAL",
        "removed_element_ref":"fixture://old/helper",
        "requirement_ref":"fixture://requirements/R1",
        "waiver_ref":"fixture://waiver/1"}

def hunks():
    return [
        {"hunk_id":"HUNK-1","path":FILE,
         "old_start":8,"old_count":3,"new_start":8,"new_count":5,
         "content_sha256":"b"*64,"header_ref":"fixture://git/hunk-1"},
        {"hunk_id":"HUNK-2","path":FILE,
         "old_start":40,"old_count":4,"new_start":44,"new_count":7,
         "content_sha256":"c"*64,"header_ref":"fixture://git/hunk-2"}]

def links():
    return [{"hunk_id":hid,"requirement_ref":"fixture://requirements/R1",
        "batch_ref":"fixture://batches/B1","scope_ref":"fixture://scope/S1",
        "evidence_ref":"fixture://source/"+hid} for hid in ("HUNK-1","HUNK-2")]

def people(same=False):
    return [
        {"principal_ref":"github:builder-x",
         "canonical_person_ref":"identity:person-001",
         "identity_provider_ref":"fixture://identity/provider"},
        {"principal_ref":"email:reviewer-alt",
         "canonical_person_ref":"identity:person-001" if same else "identity:person-002",
         "identity_provider_ref":"fixture://identity/provider"}]

def fixture():
    diff,scope=diff_scope()
    c1=prepare_pg11_c1(expected_base_sha="a"*40,expected_head_sha="b"*40,
         declared_diff=diff,authorized_scope=scope,residue_observations=[],
         dependency_observations=[],
         compatibility_observations=[{"surface":"MODULE_CONTRACT",
             "contract_ref":"fixture://module","baseline_ref":"fixture://base",
             "evidence_ref":"fixture://evidence/compat","compatible_reported":True}])
    term=terminology()
    c2=prepare_pg11_c2(pg11_c1=c1,declared_changed_paths=[FILE],
         terminology_observations=term,
         glossary_snapshot_ref="fixture://glossary",
         catalog_snapshot_ref="fixture://catalog",messages_snapshot_ref="fixture://messages",
         neighbor_baseline_ref="fixture://neighbors")
    sup=[suppression()];waivers=[waiver()]
    c3=prepare_pg11_c3(pg11_c2=c2,suppression_observations=sup,
        waiver_observations=waivers,std_gen_05_source_ref="fixture://std/STD-GEN-05")
    traces=[{"path":FILE,"status_reported":"LINKED",
             "links":[{"requirement_ref":"fixture://requirements/R1",
                 "batch_ref":"fixture://batches/B1","scope_ref":"fixture://scope/S1",
                 "evidence_ref":"fixture://change/1",
                 "change_reason_ref":"fixture://reason/1"}]}]
    c4=prepare_pg11_c4(pg11_c1=c1,pg11_c2=c2,pg11_c3=c3,
        declared_diff=diff,authorized_scope=scope,trace_observations=traces)
    reviews=[{"path":FILE,"builder_principal_ref":"github:builder-x",
        "reviewer_principal_ref":"email:reviewer-alt",
        "reviewer_role_ref":"fixture://role/reviewer",
        "builder_provenance_ref":"fixture://builder/provenance",
        "reviewer_provenance_ref":"fixture://reviewer/provenance",
        "review_scope_ref":"fixture://review/paths",
        "reviewer_is_builder_reported":False,"reviewer_independence_reported":True}]
    c5=prepare_pg11_c5(pg11_c4=c4,review_observations=reviews,
        review_policy_ref="fixture://policy/independence")
    return locals()

class PG11Tests(unittest.TestCase):
    def test_positive_real_c1_c5_and_hunks(self):
        x=fixture()
        self.assertEqual(x["c2"]["source_pg11_c1_sha256"],x["c1"]["candidate_sha256"])
        self.assertEqual(x["c3"]["source_pg11_c2_sha256"],x["c2"]["candidate_sha256"])
        self.assertEqual(x["c4"]["source_pg11_c3_sha256"],x["c3"]["candidate_sha256"])
        self.assertEqual(x["c5"]["source_pg11_c4_sha256"],x["c4"]["candidate_sha256"])
        h=prepare_pg11_hunk_trace(pg11_c4=x["c4"],hunk_manifest=hunks(),hunk_links=links())
        self.assertEqual(h["hunk_count_reported"],2)
        self.assertFalse(h["hunk_coverage_verified"])
        self.assertEqual(len(h["hunks"]),2)
        assert all(not hunk["real_diff_hunk_verified"] for hunk in h["hunks"])
        w=reject_invalid_waiver(pg11_c3=x["c3"],waiver_observations=x["waivers"])
        self.assertFalse(w["suppression_allowed"])
        p=guard_pg11_reviewer_aliases(pg11_c5=x["c5"],principal_alias_records=people())
        self.assertFalse(p["independence_verified"])
        for key in ("c1","c2","c3","c4","c5"):
            self.assertFalse(x[key]["production_authority"])
            self.assertFalse(x[key]["handoff_allowed"])
    def test_c1_out_of_scope_reported_blocker(self):
        x=fixture()
        diff=copy.deepcopy(x["diff"]);diff.append({"path":"private.txt","change_type":"ADDED","old_path":None})
        c=prepare_pg11_c1(expected_base_sha="a"*40,expected_head_sha="b"*40,
             declared_diff=diff,authorized_scope=x["scope"],residue_observations=[],
             dependency_observations=[],
             compatibility_observations=[{"surface":"API","contract_ref":"fixture://api",
              "baseline_ref":"fixture://base","evidence_ref":"fixture://evidence",
              "compatible_reported":True}])
        self.assertIn("private.txt",c["findings"]["out_of_scope_paths_reported"])
        self.assertIn("SCOPE_INVENTORY_MISMATCH",c["blocker_hints"])
    def test_c2_domain_identifier_without_glossary_term_rejected(self):
        x=fixture();term=terminology();term[0]["term_ids"]=[]
        with self.assertRaises(PG11C2Blocked):
            prepare_pg11_c2(pg11_c1=x["c1"],declared_changed_paths=[FILE],
                terminology_observations=term,glossary_snapshot_ref="fixture://glossary",
                catalog_snapshot_ref="fixture://catalog",messages_snapshot_ref="fixture://messages",
                neighbor_baseline_ref="fixture://neighbors")
    def test_c3_expired_waiver_blocked_even_if_original_declaration_was_approved(self):
        x=fixture()
        expired=[waiver(status="EXPIRED")]
        with self.assertRaisesRegex(PG11IntegrityBlocked,"WAIVER_EXPIRED"):
            reject_invalid_waiver(pg11_c3=x["c3"],waiver_observations=expired)
    def test_c3_waiver_unrelated_to_std_gen_05_blocked(self):
        x=fixture();wrong=[waiver(standard="STD-GEN-07")]
        with self.assertRaisesRegex(PG11IntegrityBlocked,"WRONG_STD_GEN_05"):
            reject_invalid_waiver(pg11_c3=x["c3"],waiver_observations=wrong)
    def test_c3_expired_original_source_is_not_authority(self):
        x=fixture()
        result=prepare_pg11_c3(pg11_c2=x["c2"],suppression_observations=x["sup"],
            waiver_observations=[waiver(status="EXPIRED")],
            std_gen_05_source_ref="fixture://std/STD-GEN-05")
        self.assertEqual(result["suppressions"][0]["diagnostic"],"WAIVER_NOT_APPROVED_REPORTED")
        self.assertFalse(result["all_suppressions_authorized"])
    def test_c4_hunk_without_requirement_blocked(self):
        x=fixture();partial=links()[:-1]
        with self.assertRaisesRegex(PG11IntegrityBlocked,"PG11_HUNK_ORPHAN"):
            prepare_pg11_hunk_trace(pg11_c4=x["c4"],hunk_manifest=hunks(),hunk_links=partial)
    def test_c4_wrong_requirement_ref_blocked(self):
        x=fixture();bad=links();bad[1]["requirement_ref"]="fixture://requirements/FOREIGN"
        with self.assertRaisesRegex(PG11IntegrityBlocked,"LINK_NOT_AUTHORIZED"):
            prepare_pg11_hunk_trace(pg11_c4=x["c4"],hunk_manifest=hunks(),hunk_links=bad)
    def test_c4_missing_hunk_in_changed_path_blocked(self):
        x=fixture();missing=[{**hunks()[0],"path":"some/other.py"}]
        with self.assertRaises(PG11IntegrityBlocked):
            prepare_pg11_hunk_trace(pg11_c4=x["c4"],hunk_manifest=missing,hunk_links=links())
    def test_c4_hunk_content_digest_invalid_rejected(self):
        x=fixture();bad=hunks();bad[0]["content_sha256"]="bad"
        with self.assertRaisesRegex(PG11IntegrityBlocked,"CONTENT_DIGEST_INVALID"):
            prepare_pg11_hunk_trace(pg11_c4=x["c4"],hunk_manifest=bad,hunk_links=links())
    def test_c5_builder_and_reviewer_same_person_under_different_aliases(self):
        x=fixture()
        self.assertNotEqual(x["reviews"][0]["builder_principal_ref"],x["reviews"][0]["reviewer_principal_ref"])
        with self.assertRaisesRegex(PG11IntegrityBlocked,"SELF_REVIEW_CANONICAL_ALIAS"):
            guard_pg11_reviewer_aliases(pg11_c5=x["c5"],principal_alias_records=people(same=True))
    def test_c5_missing_canonical_identity_fails_closed(self):
        x=fixture()
        with self.assertRaisesRegex(PG11IntegrityBlocked,"CANONICAL_IDENTITY_MISSING"):
            guard_pg11_reviewer_aliases(pg11_c5=x["c5"],principal_alias_records=people()[:1])
    def test_c5_forged_same_principal_exact_ref_rejected_by_original(self):
        x=fixture();bad=copy.deepcopy(x["reviews"])
        bad[0]["reviewer_principal_ref"]=bad[0]["builder_principal_ref"]
        with self.assertRaises(PG11C5Blocked):
            prepare_pg11_c5(pg11_c4=x["c4"],review_observations=bad,
                review_policy_ref="fixture://policy/independence")
    def test_hunk_source_authority_forgery_blocked(self):
        x=fixture();bad=copy.deepcopy(x["c4"]);bad["production_authority"]=True
        from pg11_integrity_extension_candidate_v1 import digest
        bad["candidate_sha256"]=digest({k:v for k,v in bad.items() if k!="candidate_sha256"})
        with self.assertRaisesRegex(PG11IntegrityBlocked,"UNAUTHORIZED_SOURCE"):
            prepare_pg11_hunk_trace(pg11_c4=bad,hunk_manifest=hunks(),hunk_links=links())
if __name__=="__main__": unittest.main()
