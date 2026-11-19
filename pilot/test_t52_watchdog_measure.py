"""T52: watchdog arrival record and offline measurement tool."""
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


measure = module(HERE / "tools/measure_watchdog.py", "measure_watchdog_t52")
notify = module(HERE / "request_failure_notify.py", "request_failure_notify_t52")
START, END = "2026-11-19T05:00:00Z", "2026-11-19T05:15:00Z"


def row(run_id, event, source, minute=1, conclusion="success"):
    return {"id": run_id, "event": event, "conclusion": conclusion,
            "status": "completed",
            "created_at": f"2026-11-19T05:{minute:02d}:00Z",
            "display_title": f"T9.1 watchdog {event} source={source}"}


def pages(rows, size=100, total=None):
    chunks = [rows[i:i + size] for i in range(0, len(rows), size)] or [[]]
    calls = []

    def page_fn(endpoint):
        calls.append(endpoint)
        number = int(endpoint.rsplit("page=", 1)[1])
        chunk = chunks[number - 1] if number <= len(chunks) else []
        return {"total_count": len(rows) if total is None else total,
                "workflow_runs": chunk}
    return page_fn, calls


class Measure(unittest.TestCase):
    def test_paginates_and_classifies_arrival_paths(self):
        rows = [row(i, "workflow_run", 9000 + i % 50, minute=i % 15)
                for i in range(1, 151)]
        rows += [row(1000 + i, "workflow_dispatch", 9000 + i, minute=2) for i in range(10)]
        rows += [row(2000, "schedule", "sweep", minute=3)]
        page_fn, calls = pages(rows)
        runs, complete = measure.fetch(START, END, page_fn)
        self.assertTrue(complete)
        self.assertEqual(len(calls), 2)
        self.assertIn(f"created={START}..{END}", calls[0])
        out = measure.summarize(runs, START, END, complete)
        self.assertEqual(out["status"], "COMPLETE")
        self.assertEqual(out["total"], 161)
        self.assertEqual(out["by_event"]["workflow_dispatch"], 10)
        self.assertEqual(out["sources"], 50)
        self.assertEqual(out["sources_both_paths"], 10)
        self.assertEqual(out["sources_only_workflow_run"], 40)
        self.assertEqual(out["both_ratio"], 0.2)

    def test_empty_complete_window_is_zero_not_incomplete(self):
        page_fn, _ = pages([])
        runs, complete = measure.fetch(START, END, page_fn)
        out = measure.summarize(runs, START, END, complete)
        self.assertEqual((out["status"], out["total"], out["both_ratio"]),
                         ("COMPLETE", 0, None))

    def test_short_or_changing_listing_is_incomplete(self):
        page_fn, _ = pages([row(1, "workflow_run", 5)], total=3)
        self.assertFalse(measure.fetch(START, END, page_fn)[1])
        page_fn, _ = pages([row(i, "workflow_run", 5) for i in range(1, 2001)])
        self.assertFalse(measure.fetch(START, END, page_fn, max_pages=2)[1])

    def test_duplicate_or_invalid_rows_are_incomplete(self):
        page_fn, _ = pages([row(1, "workflow_run", 5), row(1, "workflow_run", 5)])
        self.assertFalse(measure.fetch(START, END, page_fn)[1])
        self.assertFalse(measure.fetch(START, END, lambda _: {"total_count": "x"})[1])

    def test_window_is_start_inclusive_end_exclusive(self):
        rows = [dict(row(1, "workflow_run", 5), created_at=START),
                dict(row(2, "workflow_run", 6), created_at=END)]
        out = measure.summarize(rows, START, END, True)
        self.assertEqual(out["total"], 1)

    def test_pre_t52_titles_are_counted_but_not_attributed(self):
        rows = [dict(row(1, "workflow_run", 5), display_title="T9.1 request route")]
        out = measure.summarize(rows, START, END, True)
        self.assertEqual((out["total"], out["sources"],
                          out["runs_without_source_title"]), (1, 0, 1))


class Results(unittest.TestCase):
    def logs(self, texts):
        def page_fn(endpoint):
            run_id = int(endpoint.split("/runs/")[1].split("/")[0])
            return {"jobs": [{"id": run_id * 10}]}

        def text_fn(endpoint):
            job = int(endpoint.split("/jobs/")[1].split("/")[0])
            value = texts[job // 10]
            if isinstance(value, Exception):
                raise value
            return value
        return page_fn, text_fn

    @staticmethod
    def line(source, arrival, klass):
        record = {"schema": "LF_WATCHDOG_ARRIVAL_V1", "source_run_id": source,
                  "arrival": arrival, "result_class": klass}
        return "2026-11-19T05:01:00Z LF_WATCHDOG_ARRIVAL " + json.dumps(record) + "\n"

    def test_counts_result_classes_and_both_paths_from_logs(self):
        texts = {1: self.line(9, "workflow_run", "PROCESSED"),
                 2: self.line(9, "workflow_dispatch", "DEDUPED"),
                 3: self.line(8, "workflow_run", "RUTA_SOURCE_NOT_FAILED"),
                 4: self.line(None, "schedule", "SWEEP")}
        page_fn, text_fn = self.logs(texts)
        runs = [{"id": i} for i in texts]
        records, complete = measure.arrival_records(runs, page_fn, text_fn)
        self.assertTrue(complete)
        out = measure.summarize_results(records)
        self.assertEqual(out["by_result_class"],
                         {"DEDUPED": 1, "PROCESSED": 1,
                          "RUTA_SOURCE_NOT_FAILED": 1, "SWEEP": 1})
        self.assertEqual(out["sources_both_paths_by_record"], 1)

    def test_missing_ambiguous_or_unreadable_log_is_incomplete(self):
        for value in ("no record here", self.line(1, "workflow_run", "PROCESSED") * 2,
                      OSError("log gone")):
            page_fn, text_fn = self.logs({1: value})
            records, complete = measure.arrival_records([{"id": 1}], page_fn, text_fn)
            self.assertFalse(complete)
            self.assertEqual(records, [])


class Arrival(unittest.TestCase):
    def test_record_has_watchdog_and_source_ids_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            env = {"GITHUB_RUN_ID": "777", "GITHUB_EVENT_NAME": "workflow_dispatch",
                   "GITHUB_STEP_SUMMARY": str(summary)}
            with patch.dict(os.environ, env), redirect_stdout(io.StringIO()) as out:
                record = notify.arrival_record(
                    555, {"path": ".github/workflows/ci.yml@refs/heads/main"},
                    "RUTA_SOURCE_NOT_FAILED")
            self.assertEqual(record["watchdog_run_id"], 777)
            self.assertEqual(record["source_run_id"], 555)
            self.assertEqual(record["source_workflow"], ".github/workflows/ci.yml")
            self.assertEqual(record["arrival"], "workflow_dispatch")
            self.assertEqual(record["result_class"], "RUTA_SOURCE_NOT_FAILED")
            line = out.getvalue().strip()
            self.assertTrue(line.startswith("LF_WATCHDOG_ARRIVAL "))
            self.assertEqual(json.loads(line.split(" ", 1)[1])["source_run_id"], 555)
            self.assertIn("| 777 | 555 |", summary.read_text(encoding="utf-8"))

    def test_result_classes(self):
        self.assertEqual(notify.result_class("T20_RETRY_EXHAUSTION_ALREADY_NOTIFIED"),
                         "DEDUPED")
        self.assertEqual(notify.result_class("RUTA_NOTIFICADA"), "PROCESSED")

    def test_unwritable_summary_never_blocks(self):
        env = {"GITHUB_STEP_SUMMARY": "/nonexistent/dir/summary.md"}
        with patch.dict(os.environ, env), redirect_stdout(io.StringIO()):
            self.assertEqual(notify.arrival_record(None, None, "SWEEP")["result_class"],
                             "SWEEP")

    def test_watchdog_title_carries_source_run_id(self):
        text = (ROOT / ".github/workflows/request-failure-watchdog.yml").read_text(
            encoding="utf-8")
        self.assertIn("run-name: \"T9.1 watchdog ${{ github.event_name }} source="
                      "${{ github.event.workflow_run.id || inputs.source_run_id || 'sweep' }}\"",
                      text)


if __name__ == "__main__":
    unittest.main()
