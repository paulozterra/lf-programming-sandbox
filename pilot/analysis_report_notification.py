"""Post-Train issue report notification; split from verify-t7's read-only entrypoint."""
from __future__ import annotations
import json
import re
from .train_handoff import REPO, SHA, HandoffBlocked

def comment(api, sha: str, slug: str, git) -> str:
    """Comment once after a verified Train merge of the analysis PR.

    Report and request metadata are read from the *merged git tree*. Never
    trust a PR body or read an unmerged candidate for issue attribution.
    """
    if not re.fullmatch(r"req-[1-9][0-9]*", slug) or not SHA.fullmatch(sha):
        raise HandoffBlocked("ANALYSIS_REPORT_PROVENANCE_INVALID")
    report_path = f"pilot/runs/{slug}/ANALYSIS_REPORT.md"
    changed = set(git("diff", "--name-only", sha + "^1", sha).splitlines())
    if report_path not in changed:
        raise HandoffBlocked("ANALYSIS_REPORT_NOT_MERGED")
    metadata = json.loads(git("show", f"{sha}:pilot/runs/{slug}/request_meta.json"))
    number = int(slug[4:])
    if metadata.get("issue") != number:
        raise HandoffBlocked("ANALYSIS_REPORT_ISSUE_INVALID")
    report = git("show", f"{sha}:{report_path}")
    if not report.startswith("# Informe del análisis"):
        raise HandoffBlocked("ANALYSIS_REPORT_FORMAT_INVALID")
    issue = api.call("GET", f"/issues/{number}")
    if issue.get("state") != "open" or "lf-request" not in {
            label.get("name") for label in issue.get("labels", [])}:
        return "REPORT_ISSUE_NOT_OPEN"
    marker = f"<!-- LF_ANALYSIS_REPORT_MERGE:{sha}:{slug} -->"
    for page in range(1, 11):
        entries = api.call("GET", f"/issues/{number}/comments?per_page=100&page={page}")
        if not isinstance(entries, list):
            raise HandoffBlocked("ANALYSIS_REPORT_COMMENTS_INVALID")
        if any(marker in str(row.get("body", ""))
               and row.get("user", {}).get("login") == "github-actions[bot]"
               for row in entries):
            return "REPORT_ALREADY_COMMENTED"
        if len(entries) < 100:
            break
    else:
        raise HandoffBlocked("ANALYSIS_REPORT_COMMENTS_UNBOUNDED")
    link = f"https://github.com/{REPO}/blob/{sha}/{report_path}"
    preface = marker + "\nInforme de Análisis fusionado (candidato simulado).\n"
    body = preface + "\n" + report
    if len(body.encode("utf-8")) > 60_000:
        body = preface + "Informe completo: " + link + "\n"
    api.call("POST", f"/issues/{number}/comments", {"body": body})
    return "REPORT_COMMENTED"


