"""T12 offline: stale T7 regeneration, de-duped issue intake and examiner races."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent / "orchestrator"))
from pilot import request_duplicate as dup, auto_integrate as policy
from pilot.orchestrator import issue_intake, chain_lots
from pilot.orchestrator.lifecycle_test_support import fake_api


def configured_root(root: Path) -> Path:
    """Explicit project fixture for synthetic checkout roots."""
    import shutil
    source = Path(__file__).resolve().parents[1] / "pilot/config"
    target = root / "pilot/config"
    (target / "projects").mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "active_project.json", target / "active_project.json")
    shutil.copy2(source / "projects/sandbox.json", target / "projects/sandbox.json")
    return root


class IssueAPI:
    def __init__(self, recent):
        self.recent = recent
        self.writes = []
    def call(self, method, path, payload=None):
        from pilot.orchestrator.lifecycle_test_support import content, CONTROL
        if method == "GET" and path == f"/contents/{CONTROL}?ref=main":
            return content({})
        if method == "GET" and path.startswith("/issues?state=open&labels=lf-request&"):
            return self.recent
        if method == "GET" and path == "/labels?per_page=100":
            return [{"name": "lf-request-duplicate"}]
        if method == "GET" and path.startswith("/pulls?"):
            return []
        if method in ("POST", "PATCH"):
            self.writes.append((method, path, payload))
            return {"html_url":"https://github.com/org/repo/pull/222"}
        if method == "GET":
            return fake_api({})(path[1:])
        raise AssertionError((method,path))
    def issue(self, number):
        return next(x for x in self.recent if x["number"]==number)
    def permission(self, author):
        return "write"
    def comment(self, number, body):
        self.writes.append(("POST", f"/issues/{number}/comments", {"body":body}))


def request(n, when, text="Implementa SBX-REM-LIST", *, labels=None):
    return {"number": n, "created_at": when, "state":"open",
            "body":"### Pedido\n\n"+text+"\n",
            "user":{"login":"owner"},
            "labels":labels or [{"name":"lf-request"}]}


class ExamGit:
    def __init__(self):
        self.created = 0
        self.existing = []
        self.calls = []
    def __call__(self, *args, **kw):
        self.calls.append(args)
        if args[:3] == ("gh", "label", "list"):
            return json.dumps([{"name":"exam-request"}])
        if args[:2] == ("gh", "api") and args[2].startswith("repos/"):
            return json.dumps(self.existing)
        if args[:3] == ("gh", "issue", "comment"):
            return ""  # T49 verified-open informational notice
        if args[:3] == ("gh", "issue", "create"):
            self.created += 1
            title = args[args.index("--title")+1]
            body = args[args.index("--body")+1]
            self.existing.append({"number":2000+self.created,"title":title,
                                  "body":body,"state":"OPEN","stateReason":None})
            return "https://github.com/org/repo/issues/"+str(2000+self.created)
        raise AssertionError(args)


class Tests(unittest.TestCase):
    def setUp(self):
        chain_lots._EXAM_RUN_CACHE.clear()

    def test_same_screen_normalized_text_in_24h_is_duplicate(self):
        when = "2026-11-15T02:00:00Z"
        earlier=request(186,when,"Implementa  SBX-REM-LIST")
        current=request(188,"2026-11-15T02:03:00Z",
                        "  implementa SBX-REM-LIST ")
        api=IssueAPI([earlier,current])
        with patch.object(dup,"screen",return_value="SBX-REM-LIST"):
            self.assertEqual(dup.candidate(api,current,issue_intake.request_text(current["body"]),
                                            root=Path(".")),186)
            with patch.object(issue_intake,"git") as git:
                self.assertEqual(issue_intake.intake(api,{"action":"opened","issue":current}),
                                 "PEDIDO_POSIBLE_DUPLICADO")
                git.assert_not_called()
        self.assertEqual([x[1] for x in api.writes],
                         ["/issues/188/labels","/issues/188/comments"])
        self.assertEqual(api.writes[-1][2]["body"],"posible duplicado de #186")

    def test_duplicate_override_requires_exact_unlabeled_event(self):
        older=request(186,"2026-11-15T02:00:00Z")
        current=request(188,"2026-11-15T02:03:00Z")
        api=IssueAPI([older,current])
        with patch.object(dup,"screen",return_value="SBX-REM-LIST"), \
             tempfile.TemporaryDirectory() as temp, \
             patch.object(issue_intake,"git"), \
             patch("pilot.orchestrator.generated_branch_standards.synchronize") as standards:
            from os import getcwd,chdir
            old=getcwd()
            try:
                chdir(temp)
                result=issue_intake.intake(api,{
                    "action":"unlabeled","label":{"name":"lf-request-duplicate"},
                    "issue":current})
            finally:
                chdir(old)
        standards.assert_called_once()
        self.assertEqual(standards.call_args.args[1], "request")
        self.assertIn("/pull/222",result)
        self.assertFalse(api.writes and any(x[1]=="/issues/188/labels" for x in api.writes))

    def test_old_outside_24h_and_different_screen_do_not_match(self):
        old=request(175,"2026-11-13T00:00:00Z")
        now=request(188,"2026-11-15T02:03:00Z")
        with patch.object(dup,"screen",return_value="SBX-REM-LIST"):
            self.assertIsNone(dup.candidate(IssueAPI([old,now]),now,
                              issue_intake.request_text(now["body"]),root=Path(".")))
        near=request(187,"2026-11-15T02:00:00Z","Implementa SBX-AUTH-LOGIN")
        with patch.object(dup,"screen",side_effect=lambda root,value: (
              "SBX-AUTH-LOGIN" if "AUTH" in value else "SBX-REM-LIST")):
            self.assertIsNone(dup.candidate(IssueAPI([near,now]),now,
                               issue_intake.request_text(now["body"]),root=Path(".")))

    def test_stale_generated_pr_closes_and_reruns_from_original_trusted_merge(self):
        origin="a"*12
        current="b"*40
        pr={"number":190,"head":{"sha":"c"*40,
              "ref":"lf/generated-t7/"+origin},
            "state":"open"}
        calls=[]
        class Github:
            def request(self,method,path,payload=None):
                calls.append((method,path,payload))
                if method=="GET":
                    return {"object":{"sha":current}}
                return {}
        completed=Mock(return_value=Mock(returncode=0,stdout=current+"\n"))
        with patch.object(policy.subprocess,"run",completed), \
             patch.object(policy,"original_request_merge",return_value="d"*40):
            self.assertEqual(policy.recover_stale_generated(
                Github(),pr,["pilot/runs/req-188/analysis.json"]),
                "STALE_CLOSED_T7_REDISPATCHED")
        self.assertEqual(calls[1],("PATCH","/pulls/190",{"state":"closed"}))
        self.assertEqual(calls[-1][1],"/actions/workflows/t7-request.yml/dispatches")
        self.assertEqual(calls[-1][2]["inputs"],
                         {"slug":"req-188","merge_sha":"d"*40,"rerun":"true"})
        self.assertEqual(policy.stale_generated_origin("lf/generated-t7/"+current[:12],
                                                      current),False)

    def test_exam_two_serialized_calls_create_only_one_marked_issue(self):
        with tempfile.TemporaryDirectory() as temp:
            root=configured_root(Path(temp))
            template=root/"pilot/runs/req-901/templates/task202.task.json"
            template.parent.mkdir(parents=True, exist_ok=True)
            template.write_text(json.dumps({"task_spec":{
                "write_path_patterns":["contracts/sample.openapi.yaml"],
                "context_path_patterns":[],
                "protected_path_patterns":[]}}))
            bind={"task_name":"task202","template_path":"pilot/runs/req-901/templates/task202.task.json"}
            lot={"id":"SOL-1","area":"CONTRATO","requirement_ids":["REQ-ONE"]}
            state=ExamGit()
            with patch.object(chain_lots,"ROOT",root),patch.object(chain_lots,"api",side_effect=fake_api({})),patch.object(chain_lots,"run",side_effect=state):
                a=chain_lots.request_missing_exam("req-901",bind,lot)
                b=chain_lots.request_missing_exam("req-901",bind,lot)
            self.assertEqual(state.created,1)
            self.assertEqual(a["reason_code"],"EXAMEN_PENDIENTE")
            self.assertEqual(b["exam_issue"],2001)
            self.assertIn("<!-- LF_EXAM_REQUEST_TASK:task202 -->",
                          state.existing[0]["body"])
            self.assertEqual(chain_lots.exam_request_matches(
                state.existing,"task202","req-901")[0]["number"],2001)

    def test_two_concurrent_exam_workers_under_workflow_lock_open_one(self):
        # Reproduce two jobs arriving concurrently. The shared lock models
        # the workflow's repository-global concurrency group.
        from concurrent.futures import ThreadPoolExecutor
        from threading import Lock, Barrier
        with tempfile.TemporaryDirectory() as temp:
            root=configured_root(Path(temp))
            path=root/"pilot/runs/req-901/templates/task202.task.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"task_spec":{
                "write_path_patterns":["contracts/sample.openapi.yaml"],
                "context_path_patterns":[]}}))
            git=ExamGit()
            mutex=Lock()
            barrier=Barrier(2)
            binding={"task_name":"task202","template_path":"pilot/runs/req-901/templates/task202.task.json"}
            lot={"id":"SOL-1","area":"CONTRATO","requirement_ids":["REQ-ONE"]}
            def worker():
                barrier.wait()
                with mutex:
                    return chain_lots.request_missing_exam("req-901",binding,lot)
            with patch.object(chain_lots,"ROOT",root), \
                 patch.object(chain_lots,"api",side_effect=fake_api({})),patch.object(chain_lots,"run",side_effect=git):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results=list(pool.map(lambda _:worker(),range(2)))
            self.assertEqual(git.created,1)
            self.assertEqual(len(results),2)
            self.assertTrue(all(x["reason_code"]=="EXAMEN_PENDIENTE" for x in results))

    def test_duplicate_second_intake_event_is_noop(self):
        first=request(186,"2026-11-15T02:00:00Z")
        again=request(188,"2026-11-15T02:03:00Z",labels=[
            {"name":"lf-request"},{"name":"lf-request-duplicate"}])
        api=IssueAPI([first,again])
        with patch.object(issue_intake,"git") as git:
            self.assertEqual(issue_intake.intake(api,{"action":"labeled",
                 "label":{"name":"lf-request"},"issue":again}),
                 "PEDIDO_POSIBLE_DUPLICADO")
            git.assert_not_called()
        self.assertFalse(api.writes)

    def test_exam_closed_only_if_registration_exists(self):
        row={"number":80,"title":"EXAM_REQUEST: task202",
             "body":"- Pedido: `req-901`\n- Task ID: `task202`\n"
                    "<!-- LF_EXAM_REQUEST_TASK:task202 -->",
             "state":"CLOSED","stateReason":"COMPLETED"}
        with tempfile.TemporaryDirectory() as temp:
            root=configured_root(Path(temp))
            template=root/"pilot/runs/req-901/templates/task202.task.json"
            template.parent.mkdir(parents=True, exist_ok=True)
            template.write_text(json.dumps({"task_spec":{
                "write_path_patterns":["contracts/sample.openapi.yaml"],
                "context_path_patterns":[]}}))
            git=ExamGit();git.existing=[row]
            bind={"task_name":"task202","template_path":"pilot/runs/req-901/templates/task202.task.json"}
            lot={"id":"SOL-1","area":"CONTRATO","requirement_ids":["REQ-ONE"]}
            with patch.object(chain_lots,"ROOT",root),patch.object(chain_lots,"api",side_effect=fake_api({})),patch.object(chain_lots,"run",side_effect=git):
                self.assertEqual(chain_lots.request_missing_exam(
                    "req-901",bind,lot)["reason_code"],"EXAM_REQUEST_CLOSED_UNVERIFIED")
                reg=root/"pilot/worker_v08/native_tasks/task202.json"
                reg.parent.mkdir(parents=True)
                reg.write_text("{}")
                # A later CP3.6 process re-evaluates verified registration state.
                chain_lots._EXAM_RUN_CACHE.clear()
                self.assertEqual(chain_lots.request_missing_exam(
                    "req-901",bind,lot)["status"],"EXAM_ALREADY_REGISTERED")
                self.assertEqual(git.created,0)


if __name__=="__main__":
    unittest.main()
