"""T46: route audit stage — config, pinned skill, input, EKB reader, report checks."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import audit_config as cfg  # noqa: E402
import build_input as bi  # noqa: E402
import ekb_reader as ekb  # noqa: E402
import skill_pin as pin  # noqa: E402
import validate_report as vr  # noqa: E402

ROOT = HERE.parents[1]


# ---- configuration -------------------------------------------------------
def test_lf_config_and_manifest_are_valid():
    config = cfg.load("lf")
    files = cfg.manifest(config)
    assert config["audit"]["mode"] == "SHADOW" and config["audit"]["ekb"]["store_content"] is False
    assert "SKILL.md" in files and len(files) > 50


def _project(tmp_path, **audit_over):
    base = json.loads((ROOT / "pilot/audit/projects/lf.json").read_text())
    base["project"] = "demo"
    base["audit"].update(audit_over)
    (tmp_path / "pilot/audit/projects").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pilot/audit/projects/demo.json").write_text(json.dumps(base))
    return base


@pytest.mark.parametrize("over", [
    {"mode": "AUTO"},
    {"ekb": {"source": "POSTGRES_READONLY", "secret": "X", "table": "t; drop", "code_column": "c",
             "store_content": False}},
    {"ekb": {"source": "NONE", "store_content": True}},
    {"skill": {"repository": "a/b", "commit": "short", "path": "p", "manifest": "m"}},
    {"skill": {"repository": "a/b", "commit": "a" * 40, "path": "../x", "manifest": "m"}},
])
def test_invalid_configs_are_rejected(tmp_path, over):
    _project(tmp_path, **over)
    with pytest.raises(cfg.AuditConfigError):
        cfg.load("demo", tmp_path)


def test_project_without_ekb_is_allowed(tmp_path):
    _project(tmp_path, ekb={"source": "NONE", "store_content": False})
    assert ekb.read_codes(cfg.load("demo", tmp_path), env={}) == []


# ---- pinned skill --------------------------------------------------------
def _tree(tmp_path):
    d = tmp_path / "skill"
    (d / "a").mkdir(parents=True)
    (d / "SKILL.md").write_text("x")
    (d / "a/b.py").write_text("y")
    import hashlib
    return d, {"SKILL.md": hashlib.sha256(b"x").hexdigest(), "a/b.py": hashlib.sha256(b"y").hexdigest()}


def test_skill_tree_matches_manifest(tmp_path):
    d, files = _tree(tmp_path)
    pin.verify_tree(d, files)


@pytest.mark.parametrize("mutate,code", [
    (lambda d: (d / "SKILL.md").write_text("changed"), "changed=SKILL.md"),
    (lambda d: (d / "extra.py").write_text("z"), "extra=extra.py"),
    (lambda d: (d / "a/b.py").unlink(), "missing=a/b.py"),
])
def test_skill_tree_drift_blocks(tmp_path, mutate, code):
    d, files = _tree(tmp_path)
    mutate(d)
    with pytest.raises(pin.SkillPinError, match="AUDIT_SKILL_PIN_MISMATCH:.*" + code):
        pin.verify_tree(d, files)


def test_fetch_verifies_against_local_source(tmp_path):
    src = tmp_path / "src"
    (src / "skills/s").mkdir(parents=True)
    (src / "skills/s/SKILL.md").write_text("x")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "s"]):
        subprocess.run(["git", "-C", str(src), *c], check=True, capture_output=True)
    sha = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(src), "config", "uploadpack.allowReachableSHA1InWant", "true"], check=True)
    import hashlib
    man = tmp_path / "pilot/audit/projects/demo.audit-skill.manifest.json"
    man.parent.mkdir(parents=True)
    man.write_text(json.dumps({"schema_version": "LF_AUDIT_SKILL_MANIFEST_V1", "repository": "o/r", "commit": sha,
                               "path": "skills/s", "files": {"SKILL.md": hashlib.sha256(b"x").hexdigest()}}))
    config = {"audit": {"skill": {"repository": "o/r", "commit": sha, "path": "skills/s",
                                  "manifest": "pilot/audit/projects/demo.audit-skill.manifest.json"}}}
    out = pin.fetch(config, tmp_path / "dest", root=tmp_path, source_url=str(src))
    assert (out / "SKILL.md").read_text() == "x"
    other = {"audit": {"skill": dict(config["audit"]["skill"], commit="b" * 40)}}
    with pytest.raises(cfg.AuditConfigError, match="AUDIT_SKILL_MANIFEST_INVALID"):
        pin.fetch(other, tmp_path / "dest2", root=tmp_path, source_url=str(src))  # config != manifest
    data = json.loads(man.read_text())
    man.write_text(json.dumps(dict(data, commit="b" * 40)))
    with pytest.raises(pin.SkillPinError, match="AUDIT_SKILL_UNREACHABLE"):
        pin.fetch(other, tmp_path / "dest3", root=tmp_path, source_url=str(src))  # commit not in source


# ---- input ---------------------------------------------------------------
def _repo_with_merges(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    g = lambda *a: subprocess.run(["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                  check=True, capture_output=True, text=True).stdout.strip()
    g("init", "-q")
    shas = []
    for i in range(3):
        (r / f"f{i}").write_text(str(i))
        g("add", ".")
        g("commit", "-qm", str(i))
        shas.append(g("rev-parse", "HEAD"))
    import shutil
    config_source = ROOT / "pilot/config"
    config_target = r / "pilot/config"
    (config_target / "projects").mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_source / "active_project.json", config_target / "active_project.json")
    shutil.copy2(config_source / "projects/sandbox.json", config_target / "projects/sandbox.json")
    (r / "pilot/runs/req-9").mkdir(parents=True)
    (r / "pilot/runs/req-9/analysis.json").write_text("{}")
    (r / "pilot/runs/req-9/lots.json").write_text("{}")
    (r / "pilot/audit/projects").mkdir(parents=True)
    for f in ("lf.json", "lf.audit-skill.manifest.json"):
        (r / "pilot/audit/projects" / f).write_text((ROOT / "pilot/audit/projects" / f).read_text())
    return r, shas


LOTS = {"lots": [{"id": "C", "depends_on": []}, {"id": "B", "depends_on": ["C"]}, {"id": "F", "depends_on": ["B", "C"]}]}
ANALYSIS = {"requirements": [{"source_requirement_id": "R-1", "outcome": "uno"},
                             {"source_requirement_id": "R-2", "outcome": "dos"}]}


def test_input_from_closed_request(tmp_path):
    r, shas = _repo_with_merges(tmp_path)
    done = {"C": {"merge_sha": shas[0], "expected_files": ["contracts/x.yaml"]},
            "F": {"merge_sha": shas[2], "expected_files": ["frontend/p.tsx", "standards/CAMBIOS.md"]},
            "B": {"merge_sha": shas[1], "expected_files": ["apps/A.java"]}}
    data = bi.build("req-9", "lf", "o/r", done, LOTS, ANALYSIS, root=r)
    assert data["base_commit"] == shas[2]
    assert data["entrypoints"] == ["apps/A.java", "contracts/x.yaml", "frontend/p.tsx"]
    assert data["consumer_targets"] == ["apps/A.java", "frontend/p.tsx"]
    assert data["acceptance_criteria"] == ["RULE:R-1 :: uno", "RULE:R-2 :: dos"]
    assert data["evidence_destination"] == "pilot/runs/req-9/audit"
    assert data["schema_version"] == "LF_DEEP_AUDIT_INPUT_V2" and not data["new_e2e_requested"]


def test_input_requires_every_lot_integrated(tmp_path):
    r, shas = _repo_with_merges(tmp_path)
    with pytest.raises(bi.AuditInputError, match="AUDIT_REQUEST_NOT_CLOSED"):
        bi.build("req-9", "lf", "o/r", {"C": {"merge_sha": shas[0], "expected_files": ["a"]}}, LOTS, ANALYSIS, root=r)


def test_input_matches_skill_schema_when_available(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    skill = os.environ.get("LF_AUDIT_SKILL_DIR")
    if not skill:
        pytest.skip("skill not fetched")
    r, shas = _repo_with_merges(tmp_path)
    done = {k: {"merge_sha": s, "expected_files": [f"src/{k}"]} for k, s in zip("CBF", shas)}
    data = bi.build("req-9", "lf", "o/r", done, LOTS, ANALYSIS, root=r)
    schema = json.loads((Path(skill) / "schemas/audit_input_v2.schema.json").read_text())
    assert not list(jsonschema.Draft202012Validator(schema).iter_errors(data))


# ---- EKB reader ----------------------------------------------------------
def _fake_psql(tmp_path, stdout="", stderr="", rc=0):
    f = tmp_path / "psql"
    f.write_text(f"#!/bin/sh\nprintf '%s' '{stdout}'\nprintf '%s' '{stderr}' >&2\nexit {rc}\n")
    f.chmod(0o755)
    return str(f)


def test_ekb_returns_codes_only(tmp_path):
    config = cfg.load("lf")
    psql = _fake_psql(tmp_path, stdout="BEGIN\nE-2\nE-1\nE-1\nROLLBACK\n")
    codes = ekb.read_codes(config, env={"LF_EKB_READONLY_URL": ' "postgresql://u:p@h/db"\n', "PATH": "/bin"}, psql=psql)
    assert codes == ["E-1", "E-2"] and ekb.summary(codes)["rows"] == 2


@pytest.mark.parametrize("env,stderr,code", [
    ({}, "", "SECRET_MISSING"),
    ({"LF_EKB_READONLY_URL": "host=h user=u password=PASSWD123"}, "", "SECRET_MALFORMED"),
    ({"LF_EKB_READONLY_URL": "postgresql://x"}, "password authentication failed for postgresql://u:PASSWD123@h", "AUTH"),
    ({"LF_EKB_READONLY_URL": "postgresql://x"}, "relation does not exist", "SCHEMA"),
    ({"LF_EKB_READONLY_URL": "postgresql://x"}, "ERROR:  42501: permission denied for schema PASSWD123", "PERMISSION:42501:SCHEMA"),
    ({"LF_EKB_READONLY_URL": "postgresql://x"}, 'connection to server at "db.x" (2600::1), port 5432 failed: Network is unreachable', "NETWORK_IPV6_UNREACHABLE"),
    ({"LF_EKB_READONLY_URL": "postgresql://x"}, 'psql: error: invalid URI query parameter: "foo"', "SECRET_MALFORMED"),
    ({"LF_EKB_READONLY_URL": "postgresql://x"}, "FATAL:  Tenant or user not found", "AUTH"),
    ({"LF_EKB_READONLY_URL": "postgresql://x"}, "ERROR:  25006: PASSWD123 weird", "QUERY:25006"),
])
def test_ekb_failures_never_echo_the_server_message(tmp_path, env, stderr, code):
    psql = _fake_psql(tmp_path, stderr=stderr, rc=2)
    with pytest.raises(ekb.EkbError) as info:
        ekb.read_codes(cfg.load("lf"), env=dict(env, PATH="/bin"), psql=psql)
    assert str(info.value) == "AUDIT_EKB_UNAVAILABLE:" + code and "PASSWD123" not in str(info.value)


# ---- report route checks -------------------------------------------------
INPUT = {"base_commit": "c" * 40, "acceptance_criteria": ["RULE:R-1 :: uno", "RULE:R-2 :: dos"]}


def _report(**over):
    rep = {"audit_context": {"source_revision": "c" * 40, "promotion_authorized": False},
           "audit_tasks": [{"id": "RULE:R-1", "status": "VERIFIED", "reason": ""},
                           {"id": "RULE:R-2", "status": "NOT_EXECUTED", "reason": "sin backend levantado"}],
           "checklist": [{"ekb_code": "E-1"}]}
    rep.update(over)
    return rep


def test_route_checks_pass():
    assert vr.route_checks(_report(), INPUT, ["E-1"]) == []


def test_route_checks_catch_every_breach():
    bad = _report(audit_context={"source_revision": "d" * 40, "promotion_authorized": True},
                  audit_tasks=[{"id": "RULE:R-2", "status": "BLOCKED", "reason": " "}],
                  checklist=[{"ekb_code": "E-404"}])
    errors = vr.route_checks(bad, INPUT, ["E-1"])
    assert set(errors) == {"AUDIT_REPORT_INVALID:SOURCE_REVISION_NOT_REQUEST_CLOSE",
                           "AUDIT_REPORT_INVALID:PROMOTION_NOT_ALLOWED",
                           "AUDIT_CRITERIA_UNCOVERED:RULE:R-1",
                           "AUDIT_CRITERIA_UNJUSTIFIED:RULE:R-2",
                           "AUDIT_EKB_CODE_UNKNOWN:E-404"}


def _historical_case(tmp_path):
    import hashlib
    r = tmp_path / "repo"
    r.mkdir()
    def g(*args):
        return subprocess.check_output(["git", "-C", str(r), "-c", "user.name=t",
                                        "-c", "user.email=t@t", *args]).decode().strip()
    g("init", "-q")
    run = r / "pilot/runs/req-9"
    run.mkdir(parents=True)
    (run / "lots.json").write_text('{"lots":[{"id":"L1"}]}')
    (run / "analysis.json").write_text("{}")
    (r / "contract.yaml").write_bytes(b"historical\n")
    g("add", ".")
    g("commit", "-qm", "request closing")
    base = g("rev-parse", "HEAD")
    ledger = r / "pilot/registry/implemented.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps({"entries": [{"request":"req-9", "lot":"L1",
                        "status":"ATTESTED", "merge_sha":base}]}))
    g("add", ".")
    g("commit", "-qm", "registry")
    g("update-ref", "refs/remotes/origin/main", g("rev-parse", "HEAD"))
    d = run / "audit"
    d.mkdir()
    capture = d / "capture.json"
    capture.write_text('{"ok":true}')
    audit_dir = "pilot/runs/req-9/audit"
    inp = dict(INPUT, base_commit=base, repository="o/r", evidence_destination=audit_dir,
               authority_refs=[{"uri": f"github://o/r@{base}/pilot/runs/req-9/{name}",
                                "resolved_revision": base,
                                "expected_sha256": hashlib.sha256((run / name).read_bytes()).hexdigest()}
                               for name in ("analysis.json", "lots.json")])
    rep = _report(ok=True, audit_context={"source_revision":base, "promotion_authorized":False},
                  evidence_catalog=[{"id":"source", "capture_ref":"contract.yaml",
                                     "capture_sha256":hashlib.sha256(b"historical\n").hexdigest()},
                                    {"id":"capture", "capture_ref":audit_dir+"/capture.json#/ok",
                                     "capture_sha256":hashlib.sha256(capture.read_bytes()).hexdigest()}])
    (d / "audit_input_v2.json").write_text(json.dumps(inp))
    file = d / "report.json"
    file.write_text(json.dumps(rep))
    skill = tmp_path / "skill"
    (skill / "validators").mkdir(parents=True)
    (skill / "scripts").mkdir()
    (skill / "validators/validate_audit_v2.py").write_text(
        "def validate(report, root):\n"
        "    assert (root / 'contract.yaml').read_bytes() == b'historical\\n'\n"
        "    assert (root / 'pilot/runs/req-9/audit/capture.json').read_text() == '{\\\"ok\\\":true}'\n"
        "    return [] if report.get('ok') else ['SCHEMA:x']\n")
    return r, file, rep, inp, skill, g


def test_validate_runs_skill_validator(tmp_path):
    r, file, rep, inp, skill, _ = _historical_case(tmp_path)
    sys.modules.pop("validate_audit_v2", None)
    assert vr.validate(file, skill, r, ["E-1"]) == []
    rep.pop("ok")
    file.write_text(json.dumps(rep))
    assert vr.validate(file, skill, r, ["E-1"]) == ["SKILL:SCHEMA:x"]
    sys.modules.pop("validate_audit_v2", None)


def test_evolved_source_is_valid_without_rehashing(tmp_path):
    r, file, rep, inp, skill, g = _historical_case(tmp_path)
    original = file.read_bytes()
    (r / "contract.yaml").write_bytes(b"legitimate evolution\n")
    g("add", "contract.yaml")
    g("commit", "-qm", "MODIFY contract")
    g("update-ref", "refs/remotes/origin/main", g("rev-parse", "HEAD"))
    sys.modules.pop("validate_audit_v2", None)
    assert vr.validate(file, skill, r, ["E-1"]) == []
    assert file.read_bytes() == original
    sys.modules.pop("validate_audit_v2", None)


@pytest.mark.parametrize("case,code", [
    ("wrong_hash", "CAPTURE_HASH_DRIFT"), ("invalid_hash", "HASH_INVALID"),
    ("altered_capture", "CAPTURE_HASH_DRIFT"), ("unknown_commit", "REVISION_NOT_MAIN_HISTORY"),
    ("wrong_close", "REVISION_NOT_REQUEST_CLOSE"), ("missing_source", "BLOB_UNRESOLVED"),
    ("path_traversal", "PATH_INVALID"), ("missing_authority", "AUTHORITY_UNRESOLVED"),
    ("paired_rewrite", "PUBLISHED_CAPTURE_CHANGED"),
])
def test_historical_evidence_fails_closed(tmp_path, case, code):
    import hashlib
    r, file, rep, inp, skill, g = _historical_case(tmp_path)
    capture = file.parent / "capture.json"
    if case == "wrong_hash":
        rep["evidence_catalog"][0]["capture_sha256"] = "f"*64
    elif case == "invalid_hash":
        rep["evidence_catalog"][0]["capture_sha256"] = "x"
    elif case == "altered_capture":
        capture.write_text("changed")
    elif case in ("unknown_commit", "wrong_close"):
        sha = "f"*40 if case == "unknown_commit" else g("rev-parse", "HEAD")
        rep["audit_context"]["source_revision"] = inp["base_commit"] = sha
    elif case == "missing_source":
        rep["evidence_catalog"][0]["capture_ref"] = "later-only.yaml"
        (r / "later-only.yaml").write_bytes(b"historical\n")
    elif case == "path_traversal":
        rep["evidence_catalog"][0]["capture_ref"] = "../contract.yaml"
    elif case == "missing_authority":
        inp["authority_refs"] = []
    elif case == "paired_rewrite":
        g("add", ".")
        g("commit", "-qm", "published audit")
        g("update-ref", "refs/remotes/origin/main", g("rev-parse", "HEAD"))
        capture.write_text("altered")
        rep["evidence_catalog"][1]["capture_sha256"] = hashlib.sha256(capture.read_bytes()).hexdigest()
    file.write_text(json.dumps(rep))
    (file.parent / "audit_input_v2.json").write_text(json.dumps(inp))
    assert any(code in e for e in vr.validate(file, skill, r, ["E-1"]))



def test_ekb_strips_orm_only_parameters(tmp_path):
    f = tmp_path / "psql"
    f.write_text('#!/bin/sh\ncase "$1" in *pgbouncer*|*connection_limit*) exit 3;; esac\necho E-1\n')
    f.chmod(0o755)
    url = "postgresql://u:p@h:6543/postgres?pgbouncer=true&connection_limit=1&sslmode=require"
    assert ekb.read_codes(cfg.load("lf"), env={"LF_EKB_READONLY_URL": url, "PATH": "/bin"}, psql=str(f)) == ["E-1"]


def test_ekb_with_no_rows_is_a_failure(tmp_path):
    psql = _fake_psql(tmp_path, stdout="BEGIN\nROLLBACK\n")
    with pytest.raises(ekb.EkbError, match="AUDIT_EKB_UNAVAILABLE:EMPTY"):
        ekb.read_codes(cfg.load("lf"), env={"LF_EKB_READONLY_URL": "postgresql://x", "PATH": "/bin"}, psql=psql)


# ---- T48 trigger ---------------------------------------------------------
def test_trigger_selects_closed_requests_after_cutoff(tmp_path, monkeypatch):
    import types
    import request_trigger as rt
    r, shas = _repo_with_merges(tmp_path)
    fake = types.SimpleNamespace(
        first_parent_merges=lambda *_a, **_kw: [],
        completed_lots=lambda lots, b, h: b)
    monkeypatch.setitem(sys.modules, "chain_lots", fake)
    lots = {"lots": [{"id": "A"}, {"id": "B"}]}
    plans = [("req-old", lots, {}, {"A": {"merge_sha": shas[0]}, "B": {"merge_sha": shas[0]}}),
             ("req-new", lots, {}, {"A": {"merge_sha": shas[1]}, "B": {"merge_sha": shas[2]}}),
             ("req-open", lots, {}, {"A": {"merge_sha": shas[2]}})]
    config = {"audit": {"since_commit": shas[1]}}
    # The legacy fixture models verified, already-closed requests explicitly.
    monkeypatch.setattr(rt, "_finalized_request", lambda request, *a, **k: request != "req-open")
    assert rt.candidates(config, plans, root=r, repository="o/r") == ["req-new"]
    (r / "pilot/runs/req-new/audit").mkdir(parents=True)
    assert rt.candidates(config, plans, root=r, repository="o/r") == []


def test_trigger_issue_carries_marker_and_input():
    import request_trigger as rt
    config = cfg.load("lf")
    body = rt.issue_body("req-9", {"base_commit": "c" * 40, "evidence_destination": "pilot/runs/req-9/audit"}, config)
    assert body.startswith("<!-- audit-request:req-9 -->") and config["audit"]["auditor"] in body and "```json" in body


# ---- A4 issue lifecycle --------------------------------------------------
def test_close_done_closes_only_requests_with_merged_report(tmp_path, monkeypatch):
    import request_trigger as rt
    (tmp_path / "pilot/runs/req-a/audit").mkdir(parents=True)
    (tmp_path / "pilot/runs/req-a/audit/report.json").write_text("{}")
    calls = []
    issues = [{"number": 1, "body": "<!-- audit-request:req-a -->"},
              {"number": 2, "body": "<!-- audit-request:req-b -->"},
              {"number": 3, "body": "sin marca"}]

    def fake_gh(*args, data=None):
        calls.append((args, data))
        return json.dumps(issues) if args[0].endswith("state=open&per_page=100") else "{}"
    monkeypatch.setattr(rt, "gh", fake_gh)
    closed = rt.close_done("o/r", root=tmp_path)
    assert [c["issue"] for c in closed] == [1]
    patches = [c for c in calls if c[0][0] == "-X"]
    assert len(patches) == 1 and patches[0][0][2].endswith("/issues/1") and patches[0][1]["state"] == "closed"


# ---- A7 skill bytes independent of the environment's git settings -------
def test_fetch_ignores_autocrlf_and_attributes(tmp_path, monkeypatch):
    import hashlib
    src = tmp_path / "src"
    (src / "skills/s").mkdir(parents=True)
    (src / "skills/s/SKILL.md").write_bytes(b"linea uno\nlinea dos\n")
    (src / "skills/s/.gitattributes").write_bytes(b"* text eol=crlf\n")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "s"]):
        subprocess.run(["git", "-C", str(src), *c], check=True, capture_output=True)
    sha = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(src), "config", "uploadpack.allowReachableSHA1InWant", "true"], check=True)
    hostile = tmp_path / "gitconfig"
    hostile.write_text("[core]\n\tautocrlf = true\n\teol = crlf\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(hostile))
    files = {n: hashlib.sha256((src / "skills/s" / n).read_bytes()).hexdigest() for n in ("SKILL.md", ".gitattributes")}
    man = tmp_path / "m.json"
    man.write_text(json.dumps({"schema_version": "LF_AUDIT_SKILL_MANIFEST_V1", "repository": "o/r", "commit": sha,
                               "path": "skills/s", "files": files}))
    config = {"audit": {"skill": {"repository": "o/r", "commit": sha, "path": "skills/s", "manifest": "m.json"}}}
    out = pin.fetch(config, tmp_path / "dest", root=tmp_path, source_url=str(src))
    assert (out / "SKILL.md").read_bytes() == b"linea uno\nlinea dos\n"


def test_mismatch_reports_counts(tmp_path):
    d, files = _tree(tmp_path)
    (d / "SKILL.md").write_text("otro")
    with pytest.raises(pin.SkillPinError, match="counts=missing:0/extra:0/changed:1"):
        pin.verify_tree(d, files)


def test_remove_tree_handles_readonly_files(tmp_path):
    import stat
    d = tmp_path / "skill/.git/objects/pack"
    d.mkdir(parents=True)
    f = d / "pack-x.idx"
    f.write_text("x")
    os.chmod(f, stat.S_IREAD)
    os.chmod(d, stat.S_IREAD | stat.S_IEXEC | stat.S_IWRITE)
    pin._remove_tree(tmp_path / "skill")
    assert not (tmp_path / "skill").exists()
