#!/usr/bin/env python3
"""T26: refresh the plan of a request's PENDING lots with the current planner/generator.

Before CP3.6 registers a lot it calls ``refresh(root, request, completed)``.
Lots already integrated (``completed``) are never touched. For pending lots:

* project tests affected by the lot's own EXTEND obligations are added to the
  lot's planned write scope (lots.json; state.json ``lots_sha256`` follows);
* every pending task template and the chain plan are regenerated with the
  current generator (e.g. ``lf-python`` acceptance), keeping task identity.

The refreshed files are written into the registration worktree, so they enter
main in the same governed registration PR as the task itself.
"""
from __future__ import annotations
# Resolve the trusted repository package when executed as a script.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import ProjectConfigError, storage_path, storage

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from affected_tests import with_affected_tests  # noqa: E402
from intake import canonical  # noqa: E402


class PlanRefreshBlocked(ValueError):
    pass


def _read(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise PlanRefreshBlocked("PLAN_REFRESH_INPUT_MISSING")
    return json.loads(path.read_text("utf-8"))


def refresh(root: Path, request: str, completed: dict) -> list[str]:
    """Return the repository paths rewritten (empty when already current)."""
    root = Path(root)
    folder = storage_path("requests_root", root=root) / request
    lots = _read(folder / "lots.json")
    state = _read(folder / "state.json")
    if state.get("lots_sha256") != hashlib.sha256(canonical(lots)).hexdigest():
        raise PlanRefreshBlocked("PLAN_REFRESH_LOTS_SHA_DRIFT")
    done = set(completed)
    pending = {lot["id"] for lot in lots["lots"]} - done
    refreshed = dict(lots, lots=with_affected_tests(root, request, lots["lots"],
                                                    only_ids=pending))
    for before, after in zip(lots["lots"], refreshed["lots"]):
        if before["id"] in done and before != after:
            raise PlanRefreshBlocked("PLAN_REFRESH_COMPLETED_LOT_CHANGED")
    import generate_chain
    drift = {path for proof in completed.values()
             for path in proof.get("expected_files", []) if isinstance(path, str)}
    try:
        result = generate_chain.generate(str(root), request, refreshed,
                                         persist=False, allow_source_drift=drift,
                                         completed=completed)
    except ProjectConfigError:
        raise
    except ValueError as exc:
        raise PlanRefreshBlocked("PLAN_REFRESH_GENERATION_FAILED:"
                                 + str(exc).split(":", 1)[0]) from exc
    bindings = {b["lot_id"]: b for b in result["plan"]["bindings"]}
    writes: dict[str, bytes] = {}
    for lot in refreshed["lots"]:
        if lot["id"] in done:
            continue
        path = bindings[lot["id"]]["template_path"]
        current = root / path
        old = _read(current) if current.exists() else None
        new = result["templates"][path]
        if old is not None and old["task_spec"].get("task_id") != new["task_spec"].get("task_id"):
            raise PlanRefreshBlocked("PLAN_REFRESH_IDENTITY_CHANGED")
        if old != new:
            writes[path] = generate_chain.canonical(new)
    if refreshed != lots:
        writes[f"pilot/runs/{request}/lots.json"] = canonical(refreshed)
        writes[f"pilot/runs/{request}/state.json"] = canonical(
            dict(state, lots_sha256=hashlib.sha256(canonical(refreshed)).hexdigest()))
        # Every committed copy of the chain plan pins lots_sha256 and must follow.
        for plan_rel in (f"pilot/runs/{request}/chain_plan.json",
                         f"pilot/orchestrator/chain_plans/{request}.json"):
            if (root / plan_rel).exists():
                writes[plan_rel] = generate_chain.canonical(result["plan"])
    for path, content in sorted(writes.items()):
        target = root / path
        if target.is_symlink():
            raise PlanRefreshBlocked("PLAN_REFRESH_OUTPUT_SYMLINK")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return sorted(writes)
