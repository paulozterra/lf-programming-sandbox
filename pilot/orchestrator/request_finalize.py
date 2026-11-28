#!/usr/bin/env python3
"""T9 final notification. Never close an issue on a candidate-only H_REPORT."""
from __future__ import annotations

# Resolve the trusted repository package for direct script execution.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))

import argparse
import base64
import hashlib
import json
import os
import subprocess
from urllib.error import HTTPError
from pathlib import Path
import re

from pilot.orchestrator.issue_intake import API, Blocked
from pilot.orchestrator.intervention_report import markdown, report
from pilot.config.project_config import storage_path, storage

ROOT = Path(__file__).resolve().parents[2]
SUCCESS_STAGES = {"COMPLETED", "COMPLETE", "FINISHED"}
TERMINAL = SUCCESS_STAGES | {"FAILED_FINAL", "BLOCKED_FINAL", "CANCELLED_FINAL"}
DECIDED = {"FAILED_FINAL", "CANCELLED_FINAL"}
SHA = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
TERMINAL_SCHEMA = "LF_REQUEST_TERMINAL_V1"
BOT = "github-actions[bot]"


class FinalizationError(ValueError):
    pass


def deny():
    raise FinalizationError("REQUEST_TERMINAL_EVIDENCE_INVALID")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            deny()
        result[key] = value
    return result


def decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique)
    except (TypeError, ValueError, UnicodeError):
        deny()


def request_path(slug):
    if not re.fullmatch(r"req-[1-9][0-9]*", slug):
        deny()
    return storage()["requests_root"] + "/" + slug


def _missing(exc):
    # A missing content path is not a transport failure. The ref itself has
    # already been authenticated. Never infer absence from a generic error.
    while exc is not None:
        if isinstance(exc, HTTPError) and exc.code == 404:
            return True
        if (str(exc) == "GITHUB_HTTP_404:API"
                or re.search(r"^CP35_COMMAND_FAILED:gh:stderr=.*\bHTTP 404\b", str(exc))):
            return True
        if isinstance(exc, subprocess.CalledProcessError):
            err = exc.stderr or ""
            if isinstance(err, bytes):
                err = err.decode("utf-8", "replace")
            if re.search(r"\bHTTP 404\b", err):
                return True
        exc = exc.__cause__
    return False


class MainView:
    """Immutable data snapshot pinned to a live trusted main ref.

    A stale runner may read the exact Git object if available; otherwise fetch
    the same immutable revision via GitHub. Never read mutable worktree bytes.
    """
    def __init__(self, root, api, revision):
        if not isinstance(revision, str) or not SHA.fullmatch(revision):
            deny()
        self.root, self.api, self.revision = root, api, revision
        self.local = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", revision + "^{commit}"],
            capture_output=True, timeout=15).returncode == 0

    def at(self, revision):
        return MainView(self.root, self.api, revision)

    def read(self, path):
        if self.local:
            row = subprocess.check_output(
                ["git", "-C", str(self.root), "ls-tree", "-z", self.revision, "--", path],
                timeout=15)
            if not row:
                return None
            match = re.fullmatch(rb"100(?:644|755) blob ([0-9a-f]{40})\t([^\0]+)\0", row)
            if not match or match.group(2).decode() != path:
                deny()
            return subprocess.check_output(
                ["git", "-C", str(self.root), "cat-file", "blob", match.group(1).decode()],
                timeout=15)
        try:
            item = self.api(f"contents/{path}?ref={self.revision}")
        except Exception as exc:
            if _missing(exc):
                return None
            raise FinalizationError("REQUEST_TERMINAL_EVIDENCE_INVALID") from exc
        if (not isinstance(item, dict) or item.get("type") != "file"
                or item.get("encoding") != "base64" or type(item.get("size")) is not int
                or not isinstance(item.get("content"), str)):
            deny()
        raw = base64.b64decode("".join(item["content"].splitlines()), validate=True)
        if len(raw) != item["size"]:
            deny()
        return raw


class LocalView:
    """Read-only preparation from a trusted main checkout; never authorizes close."""
    def __init__(self, root):
        self.root = root

    def read(self, path):
        target = self.root / path
        if any(parent.is_symlink() for parent in (target, *target.parents)
               if parent != self.root.parent):
            deny()
        if not target.exists():
            return None
        if not target.is_file():
            deny()
        return target.read_bytes()


def current_view(api, root=ROOT):
    try:
        ref = api("git/ref/heads/main")
        if (not isinstance(ref, dict) or ref.get("ref") != "refs/heads/main"
                or ref.get("object", {}).get("type") != "commit"):
            deny()
        return MainView(root, api, ref["object"]["sha"])
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        raise FinalizationError("REQUEST_TERMINAL_EVIDENCE_INVALID") from exc


def read_state(view, slug):
    raw = view.read(request_path(slug) + "/state.json")
    if raw is None:
        return {}
    value = decode(raw)
    if not isinstance(value, dict) or not isinstance(value.get("stage"), str):
        deny()
    return value


def terminal_intent(state):
    return state.get("stage") in TERMINAL or "terminal" in state


def validate_shared_registry(view):
    """A corrupt or unavailable shared ledger is not a local request error."""
    try:
        raw = view.read("pilot/registry/implemented.json")
        ledger = decode(raw)
        if (not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list)
                or any(not isinstance(row, dict) for row in ledger["entries"])):
            deny()
    except (ValueError, OSError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        raise GlobalCloseError("T9_GLOBAL_REGISTRY_INVALID") from exc


def lot_registry(view, slug):
    """Historical registry remains the authority, not the report text."""
    folder = request_path(slug)
    lots_raw = view.read(folder + "/lots.json")
    if lots_raw is None:
        return None, {}
    lots = decode(lots_raw)
    rows = lots.get("lots") if isinstance(lots, dict) else None
    if not isinstance(rows, list) or not rows:
        deny()
    ids = [row.get("id", row.get("lot_id")) if isinstance(row, dict) else None for row in rows]
    if (not all(isinstance(lot, str) and re.fullmatch(r"[A-Za-z0-9_-]+", lot) for lot in ids)
            or len(set(ids)) != len(ids)):
        deny()
    ledger_raw = view.read("pilot/registry/implemented.json")
    ledger = decode(ledger_raw) if ledger_raw is not None else {"entries": []}
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        deny()
    merged = {}
    for entry in ledger["entries"]:
        if not isinstance(entry, dict):
            deny()
        if entry.get("request") != slug:
            continue
        lot, sha = entry.get("lot"), entry.get("merge_sha")
        if (lot not in ids or lot in merged or not isinstance(sha, str)
                or not SHA.fullmatch(sha) or entry.get("status") not in ("ATTESTED", "NO_DERIVABLE")):
            deny()
        merged[lot] = sha
    return ids, merged


def legacy_complete(view, slug):
    """Existing D22 historical success proof; do not retroactively strengthen it."""
    try:
        if view.read(request_path(slug) + "/H_REPORT.md") is None:
            return False
        lots = decode(view.read(request_path(slug) + "/lots.json"))["lots"]
        ledger = decode(view.read("pilot/registry/implemented.json"))["entries"]
        if not isinstance(lots, list) or not lots:
            return False
        planned = {x.get("id", x.get("lot_id")) for x in lots if isinstance(x, dict)}
        if len(planned) != len(lots) or not all(isinstance(x, str) and x for x in planned):
            return False
        merged = {x.get("lot") for x in ledger if isinstance(x, dict)
                  and x.get("request") == slug and x.get("merge_sha")
                  and x.get("status") in ("ATTESTED", "NO_DERIVABLE")}
        return planned.issubset(merged)
    except (OSError, ValueError, TypeError, KeyError):
        return False


def verified_chain_complete(folder: Path, *, root: Path = ROOT) -> bool:
    # Compatibility entrypoint used by D22 and existing offline fixtures.
    return legacy_complete(LocalView(root), folder.name)


def evidence_records(view, slug, ids, merged):
    from pilot.orchestrator.pg37_evidence import validate_record
    folder = request_path(slug)
    rows = []
    for lot in ids:
        if lot not in merged:
            continue
        sha = merged[lot]
        raw = view.read(f"{folder}/evidence/{lot}-{sha[:12]}.json")
        if raw is None:
            deny()
        rows.append(validate_record(decode(raw), slug, lot, sha))
    return rows


def verified_report(view, slug, ids, merged):
    from pilot.orchestrator.pg37_evidence import render
    expected = render(slug, evidence_records(view, slug, ids, merged)).encode("utf-8")
    if view.read(request_path(slug) + "/H_REPORT.md") != expected:
        deny()
    return hashlib.sha256(expected).hexdigest()


def validate_exhaustion(rows, remaining):
    """Persist only a verified, effective native budget projection.

    CP3.6 rederives this projection before preparing and admitting a terminal
    PR. This structural check deliberately never reopens an exhausted request
    when old Actions artifacts have expired.
    """
    if not isinstance(rows, dict) or not rows or not set(rows).issubset(remaining):
        deny()
    for lot, row in rows.items():
        if (not isinstance(row, dict)
                or set(row) != {"task", "max_attempts", "run_ids", "original_run_ids"}
                or not isinstance(row["task"], str)
                or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", row["task"])
                or type(row["max_attempts"]) is not int
                or row["max_attempts"] not in (1, 3)):
            deny()
        for key in ("run_ids", "original_run_ids"):
            ids = row[key]
            if (not isinstance(ids, list) or not all(type(n) is int and n > 0 for n in ids)
                    or ids != sorted(set(ids))):
                deny()
        if (len(row["run_ids"]) != row["max_attempts"]
                or len(row["original_run_ids"]) != (3 if row["max_attempts"] == 1 else 0)
                or set(row["run_ids"]) & set(row["original_run_ids"])):
            deny()


def terminal_outcome(view, slug, state=None):
    """Canonical new terminal proof. No issue state is an implementation receipt."""
    state = read_state(view, slug) if state is None else state
    stage = state.get("stage")
    if not state:
        return None
    # Ordinary requests without a report cannot already be successful.
    explicit = stage in DECIDED or "terminal" in state or stage == "BLOCKED_FINAL"
    if not explicit and view.read(request_path(slug) + "/H_REPORT.md") is None:
        if stage in SUCCESS_STAGES:
            deny()
        return None
    ids, merged = lot_registry(view, slug)
    if ids is None:
        if explicit or stage in SUCCESS_STAGES:
            deny()
        return None
    if explicit:
        proof = state.get("terminal")
        if (stage not in DECIDED or not isinstance(proof, dict)
                or set(proof) != {"schema_version", "base_sha", "authorization_pr",
                                   "completed_merge_shas", "report_sha256", "exhaustion"}
                or proof["schema_version"] != TERMINAL_SCHEMA
                or not isinstance(proof["base_sha"], str) or not SHA.fullmatch(proof["base_sha"])
                or type(proof["authorization_pr"]) is not int or proof["authorization_pr"] <= 0
                or state.get("request_id") != slug
                or state.get("production_authority") is not False
                or state.get("handoff_allowed") is not False
                or state.get("downstream_authorized") is not False
                or proof["completed_merge_shas"] != merged
                or set(merged) == set(ids)
                or proof["report_sha256"] != verified_report(view, slug, ids, merged)):
            deny()
        if stage == "FAILED_FINAL":
            validate_exhaustion(proof["exhaustion"], set(ids) - set(merged))
        elif proof["exhaustion"] != {}:
            deny()
    else:
        if set(ids) != set(merged):
            if stage in SUCCESS_STAGES:
                deny()
            return None
        try:
            verified_report(view, slug, ids, merged)
        except (ValueError, KeyError, TypeError, OSError):
            if stage in SUCCESS_STAGES:
                deny()
            return None
        stage = "CHAIN_COMPLETE_VERIFIED"
    # Bind manifest to exact source bytes and per-request receipts. A stale
    # artifact cannot authorize closure against a later or changed snapshot.
    fingerprint = hashlib.sha256(json.dumps(
        {"slug": slug, "stage": stage, "state": state, "merged": merged,
         "report_sha256": verified_report(view, slug, ids, merged)},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    return {"stage": stage, "fingerprint": fingerprint,
            "planned": ids, "merged": merged}


def terminal_requests():
    view = LocalView(ROOT)
    for folder in sorted(storage_path("requests_root", root=ROOT).glob("req-*")):
        if not re.fullmatch(r"req-[1-9][0-9]*", folder.name):
            continue
        try:
            raw = view.read(request_path(folder.name) + "/request_meta.json")
            if raw is None:
                continue
            meta = decode(raw)
            if not isinstance(meta, dict) or meta.get("issue") != int(folder.name[4:]):
                continue
            outcome = terminal_outcome(view, folder.name)
            if outcome is not None:
                yield folder.name, meta, outcome["stage"]
        except (ValueError, OSError, TypeError, KeyError):
            # One malformed request cannot close or block other requests.
            continue


def prepare(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    revision = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                       text=True, timeout=15).strip()
    validate_shared_registry(LocalView(ROOT))
    rows = []
    for slug, meta, stage in terminal_requests():
        try:
            outcome = terminal_outcome(LocalView(ROOT), slug)
            try:
                r = report(slug, rev=revision, with_labels=False)
            except SystemExit as exc:
                # The producer reports absent intake history with this exact code.
                # Other exits (including successful exit codes) are not local errors.
                if exc.code != "REQUEST_NOT_FOUND":
                    raise
                print(f"T9_LOCAL_REPORT_FAILURE:{slug}:REQUEST_NOT_FOUND")
                continue
            rendered = markdown(r)
        except (ValueError, KeyError, TypeError) as exc:
            print(f"T9_LOCAL_REPORT_FAILURE:{slug}:{type(exc).__name__}")
            continue
        # Git subprocess failure or output filesystem failure is global.
        path = out / f"{slug}-INTERVENTION_REPORT.md"
        path.write_text(rendered, encoding="utf-8")
        rows.append({"slug": slug, "issue": meta["issue"], "stage": stage,
                     "fingerprint": outcome["fingerprint"], "revision": revision,
                     "intervencion_manual": r["intervencion_manual"]})
    (out / "manifest.json").write_text(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    return rows


class LocalCloseError(ValueError):
    pass


class GlobalCloseError(RuntimeError):
    pass


def _causes(exc):
    while exc is not None:
        yield exc
        exc = exc.__cause__


def _close_call(api, method, path, payload=None):
    try:
        result = api.call(method, path, payload)
        if method == "GET" and path == "/git/ref/heads/main":
            if (not isinstance(result, dict) or result.get("ref") != "refs/heads/main"
                    or not isinstance(result.get("object"), dict)
                    or result["object"].get("type") != "commit"
                    or not isinstance(result["object"].get("sha"), str)
                    or not SHA.fullmatch(result["object"]["sha"])):
                raise GlobalCloseError("T9_GLOBAL_MAIN_INVALID")
        if method == "GET" and path == "/contents/pilot/orchestrator/request_lifecycle_control.json?ref=main":
            from pilot.orchestrator.request_lifecycle import read_control, RequestStateError
            try:
                read_control(lambda _: result)
            except RequestStateError as exc:
                raise GlobalCloseError("T9_GLOBAL_CONTROL_INVALID") from exc
        return result
    except (Blocked, HTTPError, json.JSONDecodeError) as exc:
        status = next((x.code for x in _causes(exc) if isinstance(x, HTTPError)), None)
        # Only request-specific 404/410/422 is local. Auth, throttling,
        # transport, malformed global responses and server errors must surface.
        if method == "GET" and status == 404 and path.startswith("/contents/") and "/req-" in path:
            raise
        if re.fullmatch(r"/issues/[1-9][0-9]*(?:/comments(?:[?].*)?|/labels/lf-request-blocked)?", path) and status in (404, 410, 422):
            raise LocalCloseError("T9_LOCAL_ISSUE_FAILURE") from exc
        raise GlobalCloseError("T9_GLOBAL_API_FAILURE") from exc


def _close_one(api, row, url):
    from pilot.orchestrator.request_lifecycle import (
        require_administrative_close, RequestStateError, _paged)
    reader = lambda route: _close_call(api, "GET", "/" + route)

    def enabled(*, closed=False):
        try:
            return require_administrative_close(row, reader, root=ROOT, closed=closed)
        except (RequestStateError, FinalizationError) as exc:
            for cause in _causes(exc):
                if isinstance(cause, GlobalCloseError):
                    raise cause
            return False

    path = f"/issues/{row['issue']}"
    issue = reader(path[1:])
    if not isinstance(issue, dict) or issue.get("state") not in ("open", "closed"):
        raise LocalCloseError("T9_LOCAL_ISSUE_INVALID")
    if issue["state"] == "closed":
        if row["stage"] == "CHAIN_COMPLETE_VERIFIED" and "lf-request-blocked" in {x.get("name") for x in issue.get("labels", [])} and enabled(closed=True):
            _close_call(api, "DELETE", path + "/labels/lf-request-blocked")
        return
    if not enabled():
        return
    marker = f"<!-- LF_TERMINAL_CLOSE:{row['slug']}:{row['fingerprint']} -->"
    comments = _paged(reader, path[1:] + "/comments")
    if not any((c.get("user") or {}).get("login") == BOT
               and c.get("body", "").startswith(marker) for c in comments):
        if not enabled():
            return
        _close_call(api, "POST", path + "/comments", {"body": f"{marker}\nRuta finalizada: {row['stage']}.\n"
                    f"Intervención manual: {row['intervencion_manual']}.\n"
                    f"Informe de intervención: {url} (artefacto t9-intervention-reports, "
                    f"archivo {row['slug']}-INTERVENTION_REPORT.md)."})
    if not enabled():
        return
    reason = "completed" if row["stage"] == "CHAIN_COMPLETE_VERIFIED" else "not_planned"
    _close_call(api, "PATCH", path, {"state": "closed", "state_reason": reason})
    if row["stage"] == "CHAIN_COMPLETE_VERIFIED":
        issue = reader(path[1:])
        if "lf-request-blocked" in {x.get("name") for x in issue.get("labels", [])} and enabled(closed=True):
            _close_call(api, "DELETE", path + "/labels/lf-request-blocked")


def close(out: Path):
    from pilot.orchestrator.request_lifecycle import RequestStateError
    api = API(os.environ["GH_TOKEN"])
    run_id = os.environ["GITHUB_RUN_ID"]
    manifest = decode((out / "manifest.json").read_bytes())
    if not isinstance(manifest, list):
        deny()
    url = (f"https://github.com/{os.environ['GITHUB_REPOSITORY']}"
           f"/actions/runs/{run_id}")
    for row in manifest:
        try:
            if (not isinstance(row, dict) or not isinstance(row.get("slug"), str)
                    or not re.fullmatch(r"req-[1-9][0-9]*", row["slug"])
                    or type(row.get("issue")) is not int or row["issue"] != int(row["slug"][4:])):
                raise LocalCloseError("T9_LOCAL_MANIFEST_ROW_INVALID")
            _close_one(api, row, url)
        except (LocalCloseError, RequestStateError, FinalizationError, KeyError, TypeError) as exc:
            print(f"T9_LOCAL_CLOSE_FAILURE:{row.get('slug', 'unknown') if isinstance(row, dict) else 'unknown'}:{type(exc).__name__}")


if __name__ == "__main__":
    # The workflow wrapper uses runpy with run_name="__main__".
    # Execute the canonical package functions so lifecycle and T9 share
    # the same exception classes, including GlobalCloseError.
    from pilot.orchestrator.request_finalize import close as canonical_close, prepare as canonical_prepare

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--close", action="store_true")
    args = parser.parse_args()
    if args.close:
        canonical_close(Path(args.out))
    else:
        canonical_prepare(Path(args.out))
