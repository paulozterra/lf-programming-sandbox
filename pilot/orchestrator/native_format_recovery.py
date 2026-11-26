"""CP3.6 format-only recovery. No examiner/registration writes or proof forgiveness."""
from __future__ import annotations
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker_v08"))
import native_format_history as history
import native_format_activation as activation
from native_format_admission import identity
from native_run_history import _recognized_run

TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")


class Recovery:
    """One sweep-local cache. Shared across R1, T21, T23 and feedback recovery."""
    def __init__(self, run, api, repo, root):
        self.run, self.api, self.repo, self.root = run, api, repo, root
        self._rows = None
        self._boundaries = {}
        self.policy = activation.policy_at_root()
        self._data = {}
        self.exhausted_tasks = set()

    def rows(self):
        if self._rows is None:
            self._rows = history.listed(self.api)
        return self._rows

    def enabled(self, task):
        return activation.eligible(self.root, task, self.policy)

    def boundary(self, task):
        if task not in self._boundaries:
            self._boundaries[task] = activation.boundary(self.api, task, self.policy)
        return self._boundaries[task]

    def task_rows(self, task):
        if not self.enabled(task):
            return []
        boundary = self.boundary(task)
        return [row for row in self.rows()
                if _recognized_run({**row, "run_attempt":1},task)
                and history.stamp(row.get("created_at")) >= boundary]

    def result(self, row, task):
        rid = row["id"]
        if rid not in self._data:
            self._data[rid] = history.result_for_run(self.api,self.run,self.repo,row,task)
        return self._data[rid]

    def decision(self, task, sha):
        """No dispatch on terminal evidence; only a verified infra failure can retry."""
        rows = self.task_rows(task)
        if any(r.get("status") != "completed" for r in rows):
            return "WAITING"
        rejected = {}
        same = []
        for row in rows:
            result = self.result(row,task)
            if result is not None:
                if result["status"] == "FORMAT_FAIL":
                    rejected.setdefault(result["patch_sha256"],result)
                if result["proposal_commit_sha"] == sha:
                    same.append(result)
        if len(rejected) >= history.LIMIT:
            return "FORMAT_REJECTION_LIMIT_EXCEEDED"
        if rejected:
            hashes = identity(history.envelope_at(self.api,task,sha))
            if hashes["patch_sha256"] in rejected:
                return "FORMAT_DUPLICATE_REJECTED_PATCH"
        if same:
            latest = max(same,key=lambda r:r["run_id"])
            if latest["status"] == "INFRA_ERROR":
                # Existing T21 retries only functional attempt 1, never guess
                # a later attempt or authorize a retry of an invalid envelope.
                return ("FORMAT_INFRA_RETRY" if latest["next_functional_attempt"] == 1
                        and latest["patch_sha256"] is not None else "FORMAT_INFRA_REVIEW")
            if latest["status"] in history.BLOCK:
                return latest["status"]
        return "CONTINUE"

    def pending_decision(self, task, sha):
        # R1's historical policy remains untouched outside enrolled tasks.
        state = self.decision(task, sha)
        if state != 'CONTINUE' or not self.enabled(task):
            return state
        for row in self.task_rows(task):
            if (row.get('display_title') == f'lf-native-pending-retry-{task}-{sha}'
                    and row.get('event') == 'workflow_dispatch'):
                history.trusted_run(row, self.repo)
                return 'FORMAT_PENDING_RETRY_EXHAUSTED'
        return state

    def recover_feedback(self, allowed_task):
        outcomes=[]
        if not self.policy:
            return outcomes
        rejected, unresolved, active = {}, set(), set()
        for row in self.rows():
            # Exact title identity, including pending retry; no task guessing.
            title=row.get("display_title") or ""
            match=re.fullmatch(r"lf-native-(?:auto-lf/native-proposal/|(?:infra|route|pending)-retry-)([a-z][a-z0-9_-]{0,31})-[0-9a-f]{40}",title)
            if match is None:
                match=re.fullmatch(r"lf-native-([a-z][a-z0-9_-]{0,31})-a[123]-[0-9a-f]{40}",title)
            if match is None:
                continue
            task=match.group(1)
            try:
                if not self.enabled(task) or not allowed_task(task):
                    continue
                if history.stamp(row.get('created_at')) < self.boundary(task):
                    continue
                if row.get("status") != "completed":
                    active.add(task)
                    continue
                result=self.result(row,task)
                if result is None or result["status"] in history.CONTINUE:
                    continue
                status=result["status"]
                if status == "FORMAT_FAIL":
                    rejected.setdefault(task,set()).add(result["patch_sha256"])
                if status in ("FORMAT_FAIL","INVALID_PROPOSAL","BASELINE_FAIL"):
                    try:
                        status=history.publish(self.run,self.api,self.repo,self.root,task,result)
                    except (ValueError,OSError,KeyError,TypeError):
                        status="FORMAT_FEEDBACK_PENDING"
                outcomes.append({"task":task,"run_id":row["id"],"status":status})
            except (ValueError,OSError,KeyError,TypeError) as exc:
                unresolved.add(task)
                code=str(exc)
                outcomes.append({"task":task,"run_id":row["id"],"status":"BLOCKED",
                                 "reason":code if re.fullmatch(r"FORMAT_[A-Z0-9_]+",code) else "FORMAT_RECOVERY_UNRESOLVED"})
        self.exhausted_tasks = {task for task, patches in rejected.items()
                                if len(patches) >= history.LIMIT and task not in unresolved | active}
        outcomes.extend({"task":task,"status":"BLOCKED","reason":"FORMAT_REJECTION_LIMIT_EXCEEDED"}
                        for task in sorted(self.exhausted_tasks))
        return outcomes
