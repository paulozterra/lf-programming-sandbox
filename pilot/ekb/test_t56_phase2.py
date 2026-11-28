"""T56 phase 2: ekb.md in the lot context and route failures recorded in the EKB.

Offline: fake psql, no network, no real database.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "pilot/worker_v08"))
import route_ekb as r  # noqa: E402
import test_register_task_context as base  # noqa: E402
from test_t56_route_ekb import URL, ROWS, doc, fake_psql, calls  # noqa: E402

spec = importlib.util.spec_from_file_location("rfn", ROOT / "pilot/request_failure_notify.py")
notify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify)

EKB = b"# Errores conocidos (EKB) para este lote\n\n## LF-ROUTE-X-001 \xe2\x80\x94 ejemplo\n"


class LotContext(unittest.TestCase):
    def test_without_ekb_registration_is_unchanged(self):
        a, fa = base.run(base.task_spec())
        b, fb = base.run(base.task_spec(), ekb_markdown=None)
        self.assertEqual(a, b)
        self.assertEqual(fa, fb)
        self.assertFalse(any(p.endswith("/ekb.md") for p in fa))

    def test_ekb_md_is_added_protected_and_attested(self):
        out, files = base.run(base.task_spec(), ekb_markdown=EKB)
        path = ".lf/worker-context/ex8/ekb.md"
        self.assertEqual(files[path], EKB)
        spec_ = out["task_spec"] if "task_spec" in out else out
        self.assertIn(path, spec_["context_path_patterns"])
        self.assertIn(path, spec_["protected_path_patterns"])
        receipt = json.loads(files[".lf/worker-context/ex8/receipt.json"])
        self.assertIn(path, receipt["context_paths"])
        self.assertEqual(receipt["context_sha256"]["ekb.md"], base.mod.digest(EKB))

    def test_invalid_ekb_is_blocked(self):
        for bad in (b"", b"x" * 64_001):
            with self.assertRaises(base.mod.ContextBlocked):
                base.run(base.task_spec(), ekb_markdown=bad)

    def test_lot_terms_use_area_skills_and_path_stems(self):
        terms = r.lot_terms("BACKEND", ["SPRINGBOOT_EXP", "bad term;"], [
            "backend/src/main/java/sbx/auth/LoginController.java", "backend/src/test/java/sbx/auth/X.java"])
        self.assertIn("SPRINGBOOT_EXP", terms)
        self.assertIn("auth", terms)
        self.assertIn("logincontroller", terms)
        self.assertNotIn("bad term;", terms)
        self.assertNotIn("java", terms)

    def test_context_for_lot_never_blocks(self):
        self.assertEqual(r.context_for_lot("BACKEND", [], ["a/auth.java"], env={}),
                         (None, "EKB_CONTEXT_SKIPPED:SECRET_MISSING"))
        tmp = Path(tempfile.mkdtemp())
        down = fake_psql(tmp, "", 2, "psql: error: could not connect")
        raw, status = r.context_for_lot("BACKEND", [], ["a/auth.java"],
                                        env={"LF_EKB_READONLY_URL": URL}, psql=down)
        self.assertIsNone(raw)
        self.assertEqual(status, "EKB_CONTEXT_SKIPPED:ROUTE_EKB_UNAVAILABLE:NETWORK")
        empty = fake_psql(Path(tempfile.mkdtemp()), doc([]) + "\n")
        self.assertEqual(r.context_for_lot("BACKEND", [], ["a/auth.java"],
                                           env={"LF_EKB_READONLY_URL": URL}, psql=empty)[1],
                         "EKB_CONTEXT_EMPTY")

    def test_context_for_lot_returns_sanitised_markdown(self):
        tmp = Path(tempfile.mkdtemp())
        raw, status = r.context_for_lot("BACKEND", [], ["a/maven.java"], env={"LF_EKB_READONLY_URL": URL},
                                        psql=fake_psql(tmp, doc(ROWS) + "\n"))
        self.assertEqual(status, "EKB_CONTEXT_ADDED:2")
        text = raw.decode()
        self.assertIn("use the mirror profile", text)
        for leak in ("https://", "ops@lf.example", "hunter2", "secret-ish"):
            self.assertNotIn(leak, text)

    def test_registration_and_replay_pass_ekb_through(self):
        reg = (ROOT / "pilot/orchestrator/native_lot_registration.py").read_text()
        self.assertIn("ekb_markdown=ekb", reg)
        self.assertIn("_lot_ekb_context(", reg)
        replay = (ROOT / "pilot/orchestrator/t4_admission.py").read_text()
        self.assertIn('prefix + "ekb.md" in context_paths', replay)
        chain = (ROOT / ".github/workflows/chain-lots.yml").read_text()
        self.assertIn("LF_EKB_READONLY_URL: ${{ secrets.LF_EKB_READONLY_URL }}", chain)
        self.assertNotIn("LF_EKB_ROUTE_WRITE_URL", chain)


class Catalogue(unittest.TestCase):
    def test_every_catalogue_entry_is_valid_and_clean(self):
        cfg = r.load_config()
        catalog = r.load_catalog()
        self.assertGreaterEqual(len(catalog), 8)
        for code in catalog:
            entry = r.catalog_entry(code, run_id=123456789, request="req-286", cfg=cfg, catalog=catalog)
            self.assertEqual(entry["codigo"], "LF-ROUTE-" + code.replace("_", "-"))
            self.assertEqual(entry["evidencia"], "run 123456789; lote req-286")

    def test_catalogue_covers_notifier_codes(self):
        codes = set(notify.ROUTES.values()) - {"PEDIDO_T7_FALLIDO", "PEDIDO_INTAKE_FALLIDO",
                                                  "PEDIDO_FINALIZE_FALLIDO", "PEDIDO_EVIDENCIA_FALLIDA"}
        self.assertLessEqual(codes, set(r.load_catalog()))


class Record(unittest.TestCase):
    RECEIPT = json.dumps({"classification": "RECURRENCE", "error_code": "LF-ROUTE-BASE-NO-VERDE",
                          "frequency_after": 4, "event_id": 9})

    def test_records_catalogued_and_reports_uncatalogued(self):
        tmp = Path(tempfile.mkdtemp())
        res = r.record([{"code": "BASE_NO_VERDE", "run_id": 44776069010, "request": "req-286"},
                        {"code": "ALGO_NUEVO", "run_id": 1234567},
                        {"code": "x; drop", "run_id": 1}],
                       execution_id="gha-123456789-1", env={"LF_EKB_ROUTE_WRITE_URL": URL},
                       psql=fake_psql(tmp, self.RECEIPT + "\n"))
        self.assertEqual(res[0]["status"], "RECURRENCE")
        self.assertEqual(res[1], {"status": "UNCATALOGUED", "code": "ALGO_NUEVO"})
        self.assertEqual(res[2]["reason"], "ROUTE_EKB_CANDIDATE_INVALID")
        payload = json.loads(next(a for a in calls(tmp)[0]["argv"] if a.startswith("payload="))[8:])
        self.assertEqual(payload["evidencia"], "run 44776069010; lote req-286")
        self.assertEqual(payload["source_context"], "LF_ROUTE_SANDBOX")

    def test_record_never_raises_when_ekb_is_down(self):
        tmp = Path(tempfile.mkdtemp())
        res = r.record([{"code": "BASE_NO_VERDE", "run_id": 4477606901}], execution_id="gha-123456789-1",
                       env={}, psql=fake_psql(tmp, ""))
        self.assertEqual(res[0]["status"], "SKIPPED")
        self.assertEqual(res[0]["reason"], "ROUTE_EKB_UNAVAILABLE:SECRET_MISSING")

    def test_notifier_writes_candidate_only_when_configured(self):
        tmp = Path(tempfile.mkdtemp()) / "c.jsonl"
        old = os.environ.pop("LF_ROUTE_EKB_CANDIDATES", None)
        try:
            notify.ekb_candidate("BASE_NO_VERDE", {"id": 77}, 286)
            self.assertFalse(tmp.exists())
            os.environ["LF_ROUTE_EKB_CANDIDATES"] = str(tmp)
            notify.ekb_candidate("BASE_NO_VERDE", {"id": 77}, 286)
            notify.ekb_candidate("BASE_NO_VERDE", {"id": "x"}, 286)
        finally:
            os.environ.pop("LF_ROUTE_EKB_CANDIDATES", None)
            if old is not None:
                os.environ["LF_ROUTE_EKB_CANDIDATES"] = old
        self.assertEqual([json.loads(x) for x in tmp.read_text().splitlines()],
                         [{"code": "BASE_NO_VERDE", "run_id": 77, "request": "req-286"}])

    def test_watchdog_records_with_write_secret_in_separate_non_blocking_step(self):
        wf = (ROOT / ".github/workflows/request-failure-watchdog.yml").read_text()
        notify_step, record_step = wf.split("Record notified route failures in the EKB")
        self.assertNotIn("LF_EKB_ROUTE_WRITE_URL", notify_step)
        self.assertIn("LF_EKB_ROUTE_WRITE_URL: ${{ secrets.LF_EKB_ROUTE_WRITE_URL }}", record_step)
        self.assertIn("continue-on-error: true", record_step)


class ManualRegistration(unittest.TestCase):
    def test_catalogue_manual_write_and_exact_readback(self):
        from unittest.mock import patch
        receipt = {"status": "NEW_ERROR", "codigo": "LF-ROUTE-BRANCH-CONFLICT",
                   "frequency_after": 1, "event_id": 7}
        row = {"codigo": receipt["codigo"], "source_context": "LF_ROUTE_SANDBOX",
               "frecuencia": 1}
        with patch.object(r, "register", return_value=receipt) as write, \
                patch.object(r, "lookup", return_value={"entries": [row]}):
            result = r.register_catalogued("BRANCH_CONFLICT", "PR #459; CHG-0310",
                                          execution_id="gha-123456789-1")
            self.assertTrue(result["readback"])
            self.assertEqual(write.call_args.args[0]["evidencia"], "PR #459; CHG-0310")

    def test_manual_invalid_reference_and_unknown_code_never_write(self):
        from unittest.mock import patch
        with patch.object(r, "register") as write:
            for code, ref in (("BRANCH_CONFLICT", "raw log"), ("UNKNOWN_CODE", "PR #459")):
                with self.assertRaises(r.EkbError):
                    r.register_catalogued(code, ref, execution_id="gha-123456789-1")
            write.assert_not_called()

    def test_manual_readback_must_match_source_and_frequency(self):
        from unittest.mock import patch
        receipt = {"status": "NEW_ERROR", "codigo": "LF-ROUTE-BRANCH-CONFLICT",
                   "frequency_after": 2, "event_id": 7}
        with patch.object(r, "register", return_value=receipt), \
                patch.object(r, "lookup", return_value={"entries": []}):
            with self.assertRaisesRegex(r.EkbError, "ROUTE_EKB_READBACK_NOT_VERIFIED"):
                r.register_catalogued("BRANCH_CONFLICT", "PR #459",
                                      execution_id="gha-123456789-1")

    def test_verified_origin_not_discarded_when_label_removed(self):
        from unittest.mock import patch
        class Api:
            def api(self, method, path, body=None):
                from pilot.orchestrator.lifecycle_test_support import content, CONTROL, main_response
                if method == "GET" and path == f"/contents/{CONTROL}?ref=main":
                    return content({})
                if path.startswith("/pulls?"):
                    return [{"user": {"login": "github-actions[bot]"},
                             "head": {"ref": "lf/request/req-123"}}]
                if method == "GET" and path == "/issues/123":
                    return {"number": 123, "state": "open", "labels": []}
                if method == "POST":
                    return {}
                if method == "GET":
                    return main_response(path.lstrip("/"))
                raise AssertionError(path)
            def pages(self, path):
                return []
        run = {"id": 123456789, "name": "T7 main request auto-admission (trusted, no model)",
               "path": ".github/workflows/t7-request.yml", "event": "workflow_dispatch",
               "display_title": "T7 req-123", "conclusion": "failure",
               "repository": {"full_name": notify.REPO},
               "html_url": f"https://github.com/{notify.REPO}/actions/runs/123456789"}
        with patch.object(notify, "ekb_candidate") as candidate:
            self.assertEqual(notify.emit(Api(), run, []), "RUTA_NOTIFIED")
            candidate.assert_called_once_with("PEDIDO_T7_FALLIDO", run, 123)


if __name__ == "__main__":
    unittest.main()
