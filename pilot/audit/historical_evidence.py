"""Read-only T46 evidence view: exact closing-commit blobs + scoped audit captures.

No checkout, archive extraction, hash rewrite, fallback to current source, or
execution of historical code. The pinned skill validates the unmodified report.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

SHA = re.compile(r"[0-9a-f]{40}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
AUDIT_DIR = re.compile(r"pilot/runs/(req-[1-9][0-9]*)/audit\Z")


class EvidenceError(ValueError):
    pass


def fail(code):
    raise EvidenceError("AUDIT_PROVENANCE:" + code)


def git(root, *args):
    try:
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              capture_output=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        fail("GIT_UNRESOLVED")


def ref_path(ref):
    if not isinstance(ref, str):
        fail("PATH_INVALID")
    name = ref.partition("#")[0]
    p = PurePosixPath(name)
    if (not name or p.is_absolute() or p.as_posix() != name
            or any(part in (".", "..", ".git") for part in p.parts)
            or "\\" in name or ":" in name or any(ord(c) < 32 for c in name)):
        fail("PATH_INVALID")
    return name


def tree_blob(root, rev, name, *, optional=False):
    name = ref_path(name)
    if not SHA.fullmatch(rev):
        fail("REVISION_INVALID")
    raw = git(root, "ls-tree", "-z", rev, "--", ":(literal)" + name)
    if not raw and optional:
        return None
    entries = raw.rstrip(b"\0").split(b"\0")
    if len(entries) != 1:
        fail("BLOB_UNRESOLVED:" + name)
    meta, sep, actual = entries[0].partition(b"\t")
    parts = meta.split()
    if (not sep or actual != name.encode("utf-8") or len(parts) != 3
            or parts[0] not in (b"100644", b"100755") or parts[1] != b"blob"):
        fail("BLOB_UNRESOLVED:" + name)
    return git(root, "cat-file", "blob", parts[2].decode("ascii"))


def regular_bytes(root, name):
    name = ref_path(name)
    p = root
    for part in PurePosixPath(name).parts:
        p = p / part
        if p.is_symlink():
            fail("SYMLINK:" + name)
    if not p.is_file():
        fail("CAPTURE_MISSING:" + name)
    return p.read_bytes()


def committed_base(root, report, audit_input, audit_dir):
    base = audit_input.get("base_commit")
    ctx = report.get("audit_context") or {}
    if (not isinstance(base, str) or not SHA.fullmatch(base)
            or ctx.get("source_revision") != base):
        fail("REVISION_INVALID")
    # CI and the auditor use a full checkout of this repository. The PR's
    # synthetic merge or branch tip is not the authority for closing receipts.
    main = git(root, "rev-parse", "--verify", "refs/remotes/origin/main^{commit}").decode().strip()
    history = git(root, "rev-list", "--first-parent", main).decode().splitlines()
    if base not in history:
        fail("REVISION_NOT_MAIN_HISTORY")
    match = AUDIT_DIR.fullmatch(audit_dir)
    if not match or audit_input.get("evidence_destination") != audit_dir:
        fail("REQUEST_SCOPE_INVALID")
    request = match.group(1)
    lots_path = f"pilot/runs/{request}/lots.json"
    lots = json.loads(tree_blob(root, base, lots_path))["lots"]
    wanted = {lot["id"] for lot in lots}
    registry = json.loads(tree_blob(root, main, "pilot/registry/implemented.json"))
    receipts = [e for e in registry["entries"] if e.get("request") == request]
    if (not wanted or len(wanted) != len(lots) or len(receipts) != len(wanted)
            or {e.get("lot") for e in receipts} != wanted
            or any(e.get("status") not in ("ATTESTED", "NO_DERIVABLE")
                   or e.get("merge_sha") not in history for e in receipts)):
        fail("CLOSING_RECEIPTS_UNRESOLVED")
    if min((e["merge_sha"] for e in receipts), key=history.index) != base:
        fail("REVISION_NOT_REQUEST_CLOSE")
    # Bind input authorities to the same historical bytes, not working tree.
    repository = audit_input.get("repository")
    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        fail("REPOSITORY_INVALID")
    prefix = f"github://{repository}@{base}/"
    expected = {lots_path, f"pilot/runs/{request}/analysis.json"}
    seen = set()
    for row in audit_input.get("authority_refs", []):
        uri = row.get("uri", "")
        if not isinstance(uri, str) or not uri.startswith(prefix):
            fail("AUTHORITY_UNRESOLVED")
        name = uri[len(prefix):]
        if (name not in expected or name in seen or row.get("resolved_revision") != base
                or hashlib.sha256(tree_blob(root, base, name)).hexdigest() != row.get("expected_sha256")):
            fail("AUTHORITY_UNRESOLVED")
        seen.add(name)
    if seen != expected:
        fail("AUTHORITY_UNRESOLVED")
    return base, main


def referenced_paths(report, base):
    refs = [e["capture_ref"] for e in report.get("evidence_catalog", [])]
    for contract in report.get("contracts", []):
        for cell in contract["fields"].values():
            refs.extend(cell["source_refs"])
    refs.extend(e["file"] for e in report.get("pass_emitters", []))
    for finding in report.get("findings", []):
        loc = finding["location"]
        if loc.get("commit") != base:
            fail("FINDING_REVISION_INVALID")
        refs.append(loc["file"])
        refs.extend(finding["expected"]["contract_refs"])
        refs.extend(finding["observed_result"]["evidence_refs"])
        refs.extend(finding["readback"]["evidence_refs"])
        refs.extend(t["evidence_ref"] for t in (finding["positive_test"], finding["negative_test"])
                    if t["evidence_ref"])
        refs.extend(finding[k] for k in ("before_ref", "after_ref") if finding.get(k))
    return {ref_path(ref) for ref in refs}


@contextmanager
def evidence_view(root, report_file, report, audit_input):
    root = root.resolve()
    report_file = report_file.absolute()
    rel = report_file.relative_to(root).as_posix()
    audit_dir = str(PurePosixPath(rel).parent)
    if PurePosixPath(rel).name != "report.json":
        fail("REPORT_PATH_INVALID")
    base, main = committed_base(root, report, audit_input, audit_dir)
    # Previously published report/input and captures cannot be silently
    # rewritten by a later PR (including changing both capture and its hash).
    published = tree_blob(root, main, rel, optional=True) is not None
    captures = {}
    for e in report.get("evidence_catalog", []):
        name = ref_path(e["capture_ref"])
        digest = e.get("capture_sha256")
        if not isinstance(digest, str) or not HASH.fullmatch(digest):
            fail("HASH_INVALID:" + str(e.get("id")))
        if name in captures and captures[name] != digest:
            fail("CAPTURE_HASH_CONFLICT:" + name)
        captures[name] = digest
    with tempfile.TemporaryDirectory(prefix="lf-audit-history-") as tmp:
        view = Path(tmp)
        # The skill's location check also runs git show. Give it access to
        # the existing object store; nothing in this view is executed.
        git_dir = git(root, "rev-parse", "--absolute-git-dir").decode().strip()
        (view / ".git").write_text("gitdir: " + git_dir + "\n", encoding="utf-8")
        for name in sorted(referenced_paths(report, base) | {rel, audit_dir + "/audit_input_v2.json"}):
            if name.startswith(audit_dir + "/"):
                data = regular_bytes(root, name)
                if published and tree_blob(root, main, name, optional=True) != data:
                    fail("PUBLISHED_CAPTURE_CHANGED:" + name)
            else:
                # External sources never fall back to a later working tree.
                data = tree_blob(root, base, name)
            if name in captures and hashlib.sha256(data).hexdigest() != captures[name]:
                fail("CAPTURE_HASH_DRIFT:" + name)
            target = view / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        yield view
