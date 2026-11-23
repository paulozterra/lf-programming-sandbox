"""Run-local, read-only GitHub query reuse and phase counters for CP3.6 sweeps.

Only actions workflow-run inventories and per-run artifact inventories are
memoized. No admission writes, concurrency controls, or failure responses are
cached. GitHub CLI PR listings are shared in one fully typed 100-row snapshot;
writes invalidate it before a subsequent read.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import json
import re

_ACTIVE = ContextVar("cp36_api_budget", default=None)
_PHASE = ContextVar("cp36_api_phase", default="PREFLIGHT")
_RUNS = re.compile(r"actions/workflows/[a-z0-9_-]+[.]yml/runs[?]")
_ARTIFACTS = re.compile(r"actions/runs/[1-9][0-9]*/artifacts[?]")
_FIELDS = "number,headRefName,headRefOid,author,isDraft,title"


class Session:
    def __init__(self):
        self.calls = Counter()
        self.hits = Counter()
        self.cache = {}
        self.open_prs = None

    def record(self):
        self.calls[_PHASE.get()] += 1

    def report(self):
        for phase, n in sorted(self.calls.items()):
            print(f"API_CALLS:{phase}:{n}", flush=True)
        print(f"API_CALLS:TOTAL:{sum(self.calls.values())}", flush=True)
        for phase, n in sorted(self.hits.items()):
            print(f"API_CACHE_HITS:{phase}:{n}", flush=True)


@contextmanager
def session():
    active = Session()
    token = _ACTIVE.set(active)
    try:
        yield active
    finally:
        active.report()
        _ACTIVE.reset(token)


@contextmanager
def phase(name):
    token = _PHASE.set(name)
    try:
        yield
    finally:
        _PHASE.reset(token)


def current():
    return _ACTIVE.get()


def read(path, fetch):
    active = current()
    if active is None or not (_RUNS.match(path) or _ARTIFACTS.match(path)):
        return fetch()
    if path in active.cache:
        active.hits[_PHASE.get()] += 1
        return deepcopy(active.cache[path])
    result = fetch()
    # Do not cache unsuccessful or malformed API responses.
    active.cache[path] = deepcopy(result)
    return result


def is_open_pr_list(args):
    return (len(args) >= 10 and args[:3] == ("gh", "pr", "list")
            and "--state" in args and args[args.index("--state") + 1] == "open"
            and "--limit" in args and args[args.index("--limit") + 1] == "100"
            and "--json" in args)


def pr_list(args, fetch):
    active = current()
    if active is None or not is_open_pr_list(args):
        return None
    wanted = args[args.index("--json") + 1].split(",")
    if not set(wanted).issubset(_FIELDS.split(",")):
        return None
    if active.open_prs is None:
        query = list(args)
        query[query.index("--json") + 1] = _FIELDS
        raw = fetch(tuple(query))
        rows = json.loads(raw)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("PENDING_DRAFT_LIST_INVALID")
        active.open_prs = rows
    else:
        active.hits[_PHASE.get()] += 1
    return json.dumps([{k: row.get(k) for k in wanted} for row in active.open_prs])


def invalidate_prs(args):
    active = current()
    if (active is not None and len(args) >= 3 and
            args[:2] == ("gh", "pr") and args[2] in ("close", "create", "edit")):
        active.open_prs = None
