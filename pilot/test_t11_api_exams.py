"""T11 regression: API name, governed encrypted exams, full-DAG requests."""
from __future__ import annotations
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "orchestrator"))
import yaml
from pilot.orchestrator.contract_validate import validate, ContractBlocked
from pilot.orchestrator.contract_generate import generate
from pilot.exam_policy import verify_issue, ExamBlocked
from pilot.exam_issue_lifecycle import close_registered, LifecycleBlocked
from pilot.orchestrator import chain_lots
from pilot import auto_integrate, train_handoff


class API:
    def __init__(self, open_issue=True, author="examiner"):
        self.open_issue = open_issue
        self.author = author
        self.writes = []
    def call(self, method, path, data=None):
        return self.request(method, path, data)
    def pages(self, path, field):
        if path == "/issues?state=open&labels=exam-request":
            return ([{"number": 212, "title": "EXAM_REQUEST: tasktest",
                      "state": "open", "user": {"login": "github-actions[bot]"},
                      "labels": [{"name": "exam-request"}],
                      "body": "- Pedido: `req-901`\n- Task ID: `tasktest`"}]
                    if self.open_issue else [])
        raise AssertionError(path)
    def request(self, method, path, data=None):
        from pilot.orchestrator.lifecycle_test_support import fake_api, CONTROL
        if method == "GET" and (path == f"/contents/{CONTROL}?ref=main" or path == "/issues/901"):
            return fake_api({})(path[1:])
        if method == "GET" and path == "/collaborators/examiner/permission":
            return {"permission": "write"}
        if method == "GET" and path == "/issues?state=open&labels=exam-request&per_page=100":
            return self.pages("/issues?state=open&labels=exam-request", None)
        if method in ("POST", "PATCH"):
            self.writes.append((method, path, data))
            return {}
        if method == "GET":
            from pilot.orchestrator.lifecycle_test_support import fake_api
            return fake_api({})(path[1:])
        raise AssertionError((method, path))


class Tests(TestCase):
    def test_api_name_priority_not_catalog_code(self):
        skeleton = {"schema_version": "T2_CONTRACT_SKELETON_V1",
                    "functional_module": "reminders", "production_authority": False,
                    "fields": [{"field_code": "SBX-F-PRIORITY-FILTER",
                                "api_name": "priority", "tipo_dato": "string",
                                "required": False}],
                    "errors": [{"error_code": "SBX-E-GENERIC"}],
                    "requirement_ids": ["REQ-PRIORITY"],
                    "rules": [{"rule_code": "SBX-R-PRIORITY-FILTER"}],
                    "reused_endpoints": ["GET /api/reminders"],
                    "extended_endpoints": ["GET /api/reminders"]}
        operation = {"operationId": "listReminders",
                     "x-requirement-ids": ["REQ-PRIORITY"],
                     "parameters": [{"in": "query", "name": "priority",
                                    "required": False, "schema": {"type": "string"}}],
                     "responses": {"200": {"description": "OK"},
                                   "400": {"description": "Bad request",
                                           "x-error-codes": ["SBX-E-GENERIC"]}}}
        spec = {"openapi":"3.1.0","info":{"title":"Reminders","version":"1"},
                "paths":{"/api/reminders":{"get":operation}}}
        with TemporaryDirectory() as temp:
            file = Path(temp) / "reminders.openapi.yaml"
            file.write_text(yaml.safe_dump(spec))
            self.assertTrue(validate(file, skeleton, "reminders"))
            spec["paths"]["/api/reminders"]["get"]["parameters"][0]["name"] = "SBX-F-PRIORITY-FILTER"
            file.write_text(yaml.safe_dump(spec))
            with self.assertRaisesRegex(ContractBlocked, "CONTRACT_FIELD_COVERAGE_MISSING:priority"):
                validate(file, skeleton, "reminders")
            broken = dict(skeleton, fields=[{"field_code": "SBX-F-PRIORITY-FILTER",
                                              "required": False}])
            with self.assertRaisesRegex(ContractBlocked, "CAMPO_SIN_NOMBRE_API"):
                validate(file, broken, "reminders")

    def test_normalization_to_api_name_from_source(self):
        package = {"requirements":[{"requirement_id":"REQ-PRIORITY"}],
                   "applicable_rules":[{"requirement_id":"REQ-PRIORITY",
                                        "rule_code":"SBX-R-PRIORITY-FILTER",
                                        "source_ref":"fixture://rule"}],
                   "programming_context_snapshot":{
                       "decision_context":{"material_ledger":{"source_detail":{
                           "a3_material_contract":{"contract_sections":{
                               "fields":[{"field_code":"SBX-F-PRIORITY-FILTER",
                                          "nombre":"priority","tipo_dato":"string",
                                          "status":"VIGENTE","required":False}],
                               "errors":[{"error_code":"SBX-E-GENERIC",
                                          "status":"VIGENTE"}]}}}}}}}
        atoms = [{"functional_module":"reminders","area":area,
                  "requirement_ids":["REQ-PRIORITY"]} for area in ("FRONTEND","BACKEND")]
        result = generate("reminders",package,atoms)
        self.assertEqual(result["fields"][0]["api_name"],"priority")
        self.assertEqual(result["fields"][0]["tipo_dato"],"string")
        del package["programming_context_snapshot"]["decision_context"]["material_ledger"]["source_detail"]["a3_material_contract"]["contract_sections"]["fields"][0]["nombre"]
        with self.assertRaisesRegex(ValueError,"CAMPO_SIN_NOMBRE_API"):
            generate("reminders",package,atoms)

    def test_exam_closed_path_and_open_issue(self):
        paths = ["pilot/holdouts/tasktest.oracle.json.age",
                 "pilot/runs/req-901/claude_meta/tasktest.json"]
        api = API()
        self.assertEqual(verify_issue(api,"lf/exam/tasktest",paths,"examiner"),212)
        obj = {"state":"open", "changed_files":2,
               "base":{"ref":"main","repo":{"full_name":auto_integrate.REPOSITORY}},
               "head":{"ref":"lf/exam/tasktest","sha":"a"*40,
                       "repo":{"full_name":auto_integrate.REPOSITORY}},
               "user":{"login":"examiner"}}
        self.assertEqual(auto_integrate.eligible_pr(obj,paths,api=api),"exam")
        with self.assertRaisesRegex(auto_integrate.PolicyBlocked,"EXAM_REQUEST_UNVERIFIED"):
            auto_integrate.eligible_pr(obj,paths,api=API(open_issue=False))
        with self.assertRaisesRegex(auto_integrate.PolicyBlocked,"EXAM_REQUEST_UNVERIFIED"):
            auto_integrate.eligible_pr(obj,paths+["pilot/holdouts/other.oracle.json.age"],api=api)
        with self.assertRaisesRegex(ExamBlocked,"EXAM_PR_PATH_NOT_ALLOWED"):
            verify_issue(api,"lf/exam/tasktest",paths[:1],"examiner")

    def test_train_handoff_exam_route_and_exact_stage(self):
        mapping = json.loads(train_handoff.MAP.read_text())
        route = train_handoff.route("lf/exam/tasktest",mapping)
        self.assertEqual(route[0]["workflow"],"chain-lots.yml")
        self.assertEqual(route[0]["input_kind"],"train_run_id")
        self.assertTrue(route[0]["requires_green_base"])
        self.assertIsNone(train_handoff.route("lf/exam/../../tasktest",mapping))

    def test_only_lots_without_dependencies_open_at_plan_time(self):
        bindings = {"L1":{"task_name":"root","template_path":"one"},
                    "L2":{"task_name":"dependent","template_path":"two"},
                    "L3":{"task_name":"last","template_path":"three"}}
        lots = {"lots":[{"id":"L1","depends_on":[]},
                        {"id":"L2","depends_on":["L1"]},
                        {"id":"L3","depends_on":["L2"]}]}
        seen = []
        def send(req, binding, lot):
            seen.append((req,lot["id"],binding["task_name"]))
            return {"status":"BLOCKED","reason_code":"EXAMEN_PENDIENTE"}
        with patch.object(chain_lots,"missing_exam",return_value=True), \
             patch.object(chain_lots,"request_missing_exam",side_effect=send):
            outcomes = chain_lots.request_all_lot_exams("req-901",lots,bindings)
        # Dependents are requested at admission, after their predecessors
        # are integrated (CHG: exams against a base their deps still change).
        self.assertEqual([x[1] for x in seen],["L1"])
        self.assertEqual(len(outcomes),1)
        self.assertTrue(all(x["reason_code"]=="EXAMEN_PENDIENTE" for x in outcomes))

    def test_new_plan_requires_exact_generated_t7_merge(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            import shutil
            config_source = Path(__file__).resolve().parents[1] / "pilot/config"
            config_target = root / "pilot/config"
            (config_target / "projects").mkdir(parents=True, exist_ok=True)
            shutil.copy2(config_source / "active_project.json", config_target / "active_project.json")
            shutil.copy2(config_source / "projects/sandbox.json", config_target / "projects/sandbox.json")
            folder = root / "pilot/runs/req-901"
            folder.mkdir(parents=True)
            (folder / "request_meta.json").write_text(json.dumps(
                {"issue": 901, "author": "synthetic", "date": "2026-11-14T00:00:00Z"}))
            source = {
                "merged": True, "merge_commit_sha": "a" * 40,
                "base": {"ref": "main"},
                "head": {"ref": "lf/generated-t7/" + "b" * 12,
                         "repo": {"full_name": chain_lots.REPO}},
            }
            def github(path):
                self.assertEqual(path, "pulls/777")
                return source
            def changed(*args):
                self.assertEqual(args[:3], ("git", "diff", "--name-only"))
                return "pilot/runs/req-901/chain_plan.json"
            with patch.object(chain_lots, "ROOT", root), \
                 patch.object(chain_lots, "api", side_effect=github), \
                 patch.object(chain_lots, "run", side_effect=changed), \
                 patch.object(chain_lots, "require_green_base") as green:
                chain_lots.verify_new_plan("req-901", 777, "a" * 40)
                green.assert_called_once()
                source["head"]["ref"] = "lf/native-integration/other-run-2"
                with self.assertRaisesRegex(Exception, "EXAM_PLAN_PROVENANCE_INVALID"):
                    chain_lots.verify_new_plan("req-901", 777, "a" * 40)

    def test_close_after_verified_registered_main_merge(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            import shutil
            config_source = Path(__file__).resolve().parents[1] / "pilot/config"
            config_target = root / "pilot/config"
            (config_target / "projects").mkdir(parents=True, exist_ok=True)
            shutil.copy2(config_source / "active_project.json", config_target / "active_project.json")
            shutil.copy2(config_source / "projects/sandbox.json", config_target / "projects/sandbox.json")
            folder=root/"pilot/runs/req-901"
            folder.mkdir(parents=True)
            (folder/"chain_plan.json").write_text(json.dumps({
                "bindings":[{"task_name":"tasktest","lot_id":"SOL-002"}]}))
            api=API()
            sha="a"*40
            def git(*args):
                self.assertEqual(args[:2],("diff","--name-only"))
                return "pilot/worker_v08/native_tasks/tasktest.json"
            result=close_registered(api,sha,
                    "lf/native-registration/tasktest-"+("b"*12),git,root)
            self.assertEqual(result,"EXAM_ISSUE_CLOSED")
            self.assertEqual([x[0] for x in api.writes],["POST","PATCH"])
            self.assertIn(sha,api.writes[0][2]["body"])
            with self.assertRaisesRegex(LifecycleBlocked,"NOT_MERGED"):
                close_registered(API(),sha,
                    "lf/native-registration/tasktest-"+("b"*12),
                    lambda *args:"other.file",root)


if __name__ == "__main__":
    main()
