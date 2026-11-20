"""T56: route EKB lookup/register with a fake psql (no network, no real DB)."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import route_ekb as r  # noqa: E402

URL = "postgresql://reader:pw@db.example.invalid:5432/postgres"
ROWS = [
    {"codigo": "LF-ROUTE-MAVEN-429-001", "categoria": "CI_GOVERNANCE", "titulo": "Maven Central 429",
     "patron": "dependency resolution fails with 429", "causa_raiz": "rate limit",
     "prevencion": "use the mirror profile", "validacion": "test_t57_maven_mirror",
     "severidad": "ALTA", "frecuencia": 3, "source_context": "LF_ROUTE_SANDBOX",
     "evidencia": "run log with secret-ish stuff"},
    {"codigo": "GOV-024", "categoria": "GOVERNANCE", "titulo": "token leak",
     "patron": "see https://internal.example/x and mail ops@lf.example",
     "causa_raiz": "password=hunter2", "prevencion": "rotate", "validacion": "scan",
     "severidad": "ALTA", "frecuencia": 1, "source_context": None},
]


def doc(rows: list[dict]) -> str:
    return json.dumps({"schema_version": "ENGINEERING_EKB_LOOKUP_V1", "row_count": len(rows), "rows": rows})


def fake_psql(tmp: Path, stdout: str, rc: int = 0, stderr: str = "") -> str:
    log = tmp / "calls.jsonl"
    script = tmp / "psql"
    script.write_text(
        "#!/usr/bin/env python3\nimport json,sys\n"
        f"open({str(log)!r},'a').write(json.dumps({{'argv':sys.argv[1:],'stdin':sys.stdin.read()}})+'\\n')\n"
        f"sys.stdout.write({stdout!r}); sys.stderr.write({stderr!r}); sys.exit({rc})\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def calls(tmp: Path) -> list[dict]:
    return [json.loads(x) for x in (tmp / "calls.jsonl").read_text().splitlines()]


class Config(unittest.TestCase):
    def test_repo_config_is_valid_and_never_stores_evidence(self):
        cfg = r.load_config()
        self.assertFalse(cfg["store_evidence"])
        self.assertNotEqual(cfg["read_secret"], cfg["write_secret"])
        self.assertTrue(cfg["source_context"].startswith("LF_ROUTE"))

    def test_bad_config_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            cfg = r.load_config()
            for bad in ({**cfg, "store_evidence": True}, {**cfg, "lookup_function": "x; drop table"}, {**cfg, "operation_code": "x y"},
                        {**cfg, "write_secret": cfg["read_secret"]}, {**cfg, "source_context": "LF_OPS"}):
                p.write_text(json.dumps(bad))
                with self.assertRaises(r.EkbError):
                    r.load_config(p)


class Lookup(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.out = doc(ROWS) + "\n"

    def test_returns_only_content_columns_sanitised(self):
        res = r.lookup(["maven", "429"], area="BACKEND", env={"LF_EKB_READONLY_URL": URL},
                       psql=fake_psql(self.tmp, self.out))
        self.assertEqual([e["codigo"] for e in res["entries"]], ["LF-ROUTE-MAVEN-429-001", "GOV-024"])
        for e in res["entries"]:
            self.assertNotIn("evidencia", e)
        leak = res["entries"][1]
        blob = json.dumps(leak)
        for s in ("https://", "ops@lf.example", "hunter2"):
            self.assertNotIn(s, blob)
        self.assertEqual(res["redactions"], 3)
        call = calls(self.tmp)[0]
        self.assertIn("transaction read only", call["stdin"])
        self.assertIn("programacion.fn_engineering_ekb_lookup_v1(t, null, :lim)", call["stdin"])
        self.assertIn("terms=" + json.dumps(["429", "BACKEND", "maven"]), call["argv"])

    def test_mostly_sensitive_rows_are_dropped(self):
        row = {**ROWS[0], "codigo": "X-1", "patron": "a@b.co c@d.co", "causa_raiz": "https://a.b https://c.d"}
        res = r.lookup(["xx"], env={"LF_EKB_READONLY_URL": URL},
                       psql=fake_psql(self.tmp, doc([row]) + "\n"))
        self.assertEqual(res["entries"], [])
        self.assertEqual(res["dropped"], 1)

    def test_rows_from_several_terms_are_merged_ranked_and_superseded_skipped(self):
        a = {**ROWS[0], "codigo": "A-1", "severidad": "Low", "frecuencia": 9}
        b = {**ROWS[0], "codigo": "B-1", "severidad": "High", "frecuencia": 1}
        old = {**ROWS[0], "codigo": "C-1", "estado": "SUPERSEDED"}
        out = doc([a, b, old]) + "\n" + doc([b]) + "\n"
        res = r.lookup(["one", "two"], env={"LF_EKB_READONLY_URL": URL}, psql=fake_psql(self.tmp, out))
        self.assertEqual([e["codigo"] for e in res["entries"]], ["B-1", "A-1"])

    def test_bad_function_shape_is_refused(self):
        with self.assertRaises(r.EkbError):
            r.lookup(["xx"], env={"LF_EKB_READONLY_URL": URL}, psql=fake_psql(self.tmp, '{"rows": "x"}\n'))

    def test_terms_are_whitelisted(self):
        with self.assertRaises(r.EkbError) as c:
            r.lookup(["'; drop table x; --", "\n"], env={"LF_EKB_READONLY_URL": URL},
                     psql=fake_psql(self.tmp, ""))
        self.assertEqual(str(c.exception), "ROUTE_EKB_TERMS_EMPTY")

    def test_errors_are_code_classes_never_server_text(self):
        psql = fake_psql(self.tmp, "", 2, f"psql: error: connection to server failed {URL}")
        with self.assertRaises(r.EkbError) as c:
            r.lookup(["maven"], env={"LF_EKB_READONLY_URL": URL}, psql=psql)
        self.assertEqual(str(c.exception), "ROUTE_EKB_UNAVAILABLE:NETWORK")
        with self.assertRaises(r.EkbError) as c:
            r.lookup(["maven"], env={}, psql=psql)
        self.assertEqual(str(c.exception), "ROUTE_EKB_UNAVAILABLE:SECRET_MISSING")
        with self.assertRaises(r.EkbError) as c:
            r.lookup(["maven"], env={"LF_EKB_READONLY_URL": "https://x"}, psql=psql)
        self.assertEqual(str(c.exception), "ROUTE_EKB_UNAVAILABLE:SECRET_MALFORMED")

    def test_cli_writes_content_only_to_out_and_stdout_has_codes(self):
        out = self.tmp / "ekb.md"
        psql = fake_psql(self.tmp, self.out)
        real = r._psql
        r._psql = lambda url, script, v, _p, env: real(url, script, v, psql, env)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), unittest.mock.patch.dict(os.environ, {"LF_EKB_READONLY_URL": URL}):
                self.assertEqual(r.main(["lookup", "--term", "maven", "--out", str(out)]), 0)
        finally:
            r._psql = real
        printed = buf.getvalue()
        self.assertIn("LF-ROUTE-MAVEN-429-001", printed)
        for s in ("use the mirror profile", URL, "rate limit"):
            self.assertNotIn(s, printed)
        self.assertIn("use the mirror profile", out.read_text())

    def test_cli_refuses_out_inside_repo_and_allows_missing_secret(self):
        repo_out = Path(r.__file__).resolve().parent / "leak.md"
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(r.main(["lookup", "--term", "maven", "--out", str(repo_out)]), 1)
        self.assertIn("ROUTE_EKB_OUT_INSIDE_REPO", buf.getvalue())
        self.assertFalse(repo_out.exists())
        out = self.tmp / "ekb.md"
        env = {k: v for k, v in os.environ.items() if k != "LF_EKB_READONLY_URL"}
        with unittest.mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(r.main(["lookup", "--term", "maven", "--out", str(out), "--allow-missing"]), 0)
        self.assertIn("SECRET_MISSING", buf.getvalue())
        self.assertIn("Sin coincidencias", out.read_text())


class Register(unittest.TestCase):
    ENTRY = {"codigo": "LF-ROUTE-CRLF-WINDOWS-001", "categoria": "CI_GOVERNANCE", "severidad": "Medium",
             "titulo": "CRLF rompe el validador", "descripcion": "el validador falla en Windows",
             "patron": "checkout en Windows convierte LF a CRLF", "causa_raiz": "core.autocrlf",
             "prevencion": "gitattributes eol=lf", "validacion": "test de finales de linea",
             "lifecycle_phase": "CI_VALIDATION", "consumer_role": ["Builder", "Auditor"],
             "root_cause_family": "R2_NO_VE", "detectability": "LOUD_EARLY",
             "evidencia": "PR #355; CHG-0234", "pr": "#355"}
    RECEIPT = json.dumps({"classification": "NEW_ERROR", "error_code": "LF-ROUTE-CRLF-WINDOWS-001",
                          "frequency_after": 1, "event_id": 7})

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = r.load_config()

    def test_uses_governed_writer_with_route_operation_and_forced_context(self):
        psql = fake_psql(self.tmp, self.RECEIPT + "\n")
        res = r.register({**self.ENTRY}, execution_id="gha-123456789-1",
                         env={"LF_EKB_ROUTE_WRITE_URL": URL, "LF_EKB_READONLY_URL": "postgresql://no"}, psql=psql)
        self.assertEqual(res, {"status": "NEW_ERROR", "codigo": self.ENTRY["codigo"],
                               "frequency_after": 1, "event_id": 7})
        call = calls(self.tmp)[0]
        self.assertIn(URL, call["argv"])
        self.assertIn("op=LF_ROUTE_SANDBOX_EKB", call["argv"])
        self.assertIn("exec=gha-123456789-1", call["argv"])
        payload = json.loads(next(a for a in call["argv"] if a.startswith("payload="))[len("payload="):])
        self.assertEqual(payload["source_context"], "LF_ROUTE_SANDBOX")
        self.assertEqual(payload["source_ref"], "lf-programming-sandbox")
        self.assertIn("public.lf_write_pipeline_ekb_v1(:'op', :'payload'::jsonb, :'exec')", call["stdin"])

    def test_refuses_foreign_codes_catalogue_and_sensitive_text(self):
        bad = [({**self.ENTRY, "codigo": "GOV-024"}, "ROUTE_EKB_ENTRY_CODE"),
               ({**self.ENTRY, "source_context": "LF_OPS"}, "ROUTE_EKB_ENTRY_FIELD:source_context"),
               ({**self.ENTRY, "severidad": "ALTA"}, "ROUTE_EKB_ENTRY_SEVERITY"),
               ({**self.ENTRY, "root_cause_family": "R9"}, "ROUTE_EKB_ENTRY_CATALOGUE:root_cause_family"),
               ({**self.ENTRY, "detectability": "LOUD"}, "ROUTE_EKB_ENTRY_CATALOGUE:detectability"),
               ({**self.ENTRY, "consumer_role": []}, "ROUTE_EKB_ENTRY_CATALOGUE:consumer_role"),
               ({**self.ENTRY, "evidencia": "log completo: error at line 3"}, "ROUTE_EKB_ENTRY_EVIDENCE"),
               ({**self.ENTRY, "causa_raiz": "ver https://lf.internal/x"}, "ROUTE_EKB_ENTRY_SENSITIVE:causa_raiz"),
               ({**self.ENTRY, "patron": "falla para juan@cliente.pe"}, "ROUTE_EKB_ENTRY_SENSITIVE:patron"),
               ({**self.ENTRY, "pr": "1; drop"}, "ROUTE_EKB_ENTRY_FIELD:pr")]
        for entry, code in bad:
            with self.assertRaises(r.EkbError) as c:
                r.validate_entry(entry, self.cfg)
            self.assertEqual(str(c.exception), code)

    def test_execution_id_and_receipt_are_checked(self):
        env = {"LF_EKB_ROUTE_WRITE_URL": URL}
        with self.assertRaises(r.EkbError) as c:
            r.register({**self.ENTRY}, execution_id="x'; drop", env=env, psql=fake_psql(self.tmp, self.RECEIPT))
        self.assertEqual(str(c.exception), "ROUTE_EKB_EXECUTION_ID")
        other = json.dumps({"classification": "NEW_ERROR", "error_code": "OTHER-1"})
        for out in ("ok\n", other + "\n"):
            with self.assertRaises(r.EkbError):
                r.register({**self.ENTRY}, execution_id="gha-123456789-1", env=env,
                           psql=fake_psql(Path(tempfile.mkdtemp()), out))


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()
