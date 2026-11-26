"""CP3.6 format-only recovery. No examiner/registration writes or proof forgiveness."""
from __future__ import annotations
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker_v08"))
import native_format_history as history
from native_format_admission import identity
from native_run_history import _recognized_run

TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")


class Recovery:
    """One sweep-local cache. Shared across R1, T21, T23 and feedback recovery."""
    def __init__(self, run, api, repo, root):
        self.run, self.api, self.repo, self.root = run, api, repo, root
        self._rows = None
        self._boundary = None
        self._data = {}

    def rows(self):
        if self._rows is None:
            self._boundary = history.cutover(self.api)
            self._rows = history.listed(self.api)
        return self._rows

    def task_rows(self, task):
        return [row for row in self.rows()
                if _recognized_run({**row, "run_attempt":1},task)
                and history.stamp(row.get("created_at")) >= self._boundary]

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

    def recover_feedback(self, allowed_task):
        outcomes=[]
        for row in self.rows():
            if row.get("status") != "completed" or history.stamp(row.get("created_at")) < self._boundary:
                continue
            # Exact title identity, including pending retry; no task guessing.
            title=row.get("display_title") or ""
            match=re.fullmatch(r"lf-native-(?:auto-lf/native-proposal/|(?:infra|route|pending)-retry-)([a-z][a-z0-9_-]{0,31})-[0-9a-f]{40}",title)
            if match is None:
                match=re.fullmatch(r"lf-native-([a-z][a-z0-9_-]{0,31})-a[123]-[0-9a-f]{40}",title)
            if match is None:
                continue
            task=match.group(1)
            try:
                if not allowed_task(task):
                    continue
                result=self.result(row,task)
                if result is None or result["status"] in history.CONTINUE:
                    continue
                status=result["status"]
                if status in ("FORMAT_FAIL","INVALID_PROPOSAL","BASELINE_FAIL"):
                    status=history.publish(self.run,self.api,self.repo,self.root,task,result)
                outcomes.append({"task":task,"run_id":row["id"],"status":status})
            except (ValueError,OSError,KeyError,TypeError) as exc:
                code=str(exc)
                outcomes.append({"task":task,"run_id":row["id"],"status":"BLOCKED",
                                 "reason":code if re.fullmatch(r"FORMAT_[A-Z0-9_]+",code) else "FORMAT_RECOVERY_UNRESOLVED"})
        return outcomes
