#!/usr/bin/env python3
"""T9 final notification. Never close an issue on a candidate-only H_REPORT."""
from __future__ import annotations

# Resolve the trusted repository package for direct script execution.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))

import argparse
import json
import os
from pathlib import Path
import re

from pilot.orchestrator.issue_intake import API
from pilot.orchestrator.intervention_report import markdown, report
from pilot.config.project_config import storage_path

ROOT = Path(__file__).resolve().parents[2]
TERMINAL = {"COMPLETED", "COMPLETE", "FINISHED", "FAILED_FINAL", "BLOCKED_FINAL"}
BOT = "github-actions[bot]"


def verified_chain_complete(folder: Path, *, root: Path = ROOT) -> bool:
    """Every planned lot must be in the merged historical registry and H_REPORT on main."""
    if not (folder / "H_REPORT.md").is_file():
        return False
    try:
        lots = json.loads((folder / "lots.json").read_text(encoding="utf-8"))["lots"]
        ledger = json.loads((root / "pilot/registry/implemented.json").read_text(
            encoding="utf-8"))["entries"]
    except (OSError, ValueError, TypeError, KeyError):
        return False
    if not isinstance(lots, list) or not lots:
        return False
    planned = {x.get("id", x.get("lot_id")) for x in lots if isinstance(x, dict)}
    if len(planned) != len(lots) or not all(isinstance(x, str) and x for x in planned):
        return False
    merged = {x.get("lot") for x in ledger if isinstance(x, dict) and
              x.get("request") == folder.name and x.get("merge_sha") and
              x.get("status") in ("ATTESTED", "NO_DERIVABLE")}
    return planned.issubset(merged)


def terminal_requests():
    for folder in sorted((storage_path("requests_root", root=ROOT)).glob("req-*")):
        if not re.fullmatch(r"req-[1-9][0-9]*", folder.name):
            continue
        meta_path, state_path = folder / "request_meta.json", folder / "state.json"
        if not meta_path.is_file() or not state_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if meta.get("issue") != int(folder.name[4:]):
            continue
        stage = state.get("stage")
        if stage in TERMINAL:
            yield folder.name, meta, stage
        elif stage in ("LOTS_PLANNED", "CHAIN_COMPLETE_CANDIDATE") and verified_chain_complete(folder, root=ROOT):
            yield folder.name, meta, "CHAIN_COMPLETE_VERIFIED"


def prepare(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for slug, meta, stage in terminal_requests():
        r = report(slug, with_labels=False)
        path = out / f"{slug}-INTERVENTION_REPORT.md"
        path.write_text(markdown(r), encoding="utf-8")
        rows.append({"slug": slug, "issue": meta["issue"], "stage": stage,
                     "intervencion_manual": r["intervencion_manual"]})
    (out / "manifest.json").write_text(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    return rows


def close(out: Path):
    api = API(os.environ["GH_TOKEN"])
    from pilot.orchestrator.request_lifecycle import require_open, RequestStateError
    def enabled(slug):
        try:
            require_open(slug, lambda route: api.call("GET", "/" + route))
            return True
        except RequestStateError as exc:
            if str(exc) in ("REQUEST_CLOSED", "REQUEST_SUSPENDED"):
                return False
            raise
    run_id = os.environ["GITHUB_RUN_ID"]
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    url = (f"https://github.com/{os.environ['GITHUB_REPOSITORY']}"
           f"/actions/runs/{run_id}")
    for row in manifest:
        if not enabled(row["slug"]):
            continue
        issue = api.issue(row["issue"])
        if issue.get("state") == "closed":
            continue
        # The artifact is uploaded before any closure, so the report is available.
        if not enabled(row["slug"]):
            continue
        api.comment(row["issue"], f"Ruta finalizada: {row['stage']}.\n"
                    f"Intervención manual: {row['intervencion_manual']}.\n"
                    f"Informe de intervención: {url} (artefacto t9-intervention-reports, "
                    f"archivo {row['slug']}-INTERVENTION_REPORT.md).")
        if not enabled(row["slug"]):
            continue
        api.call("PATCH", f"/issues/{row['issue']}", {"state": "closed"})
        # A historically blocked request may later complete via a verified
        # Train integration. Only a successful completion clears that label.
        if row["stage"] in ("CHAIN_COMPLETE_VERIFIED", "COMPLETED", "COMPLETE", "FINISHED"):
            if "lf-request-blocked" in {
                    item.get("name") for item in issue.get("labels", [])
                    if isinstance(item, dict)}:
                api.call("DELETE", f"/issues/{row['issue']}/labels/lf-request-blocked")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--close", action="store_true")
    args = parser.parse_args()
    if args.close:
        close(Path(args.out))
    else:
        prepare(Path(args.out))
