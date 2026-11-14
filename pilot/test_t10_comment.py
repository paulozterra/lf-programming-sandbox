"""T10 report comments use only trusted merged blob and exact issue metadata."""
import unittest

from pilot.analysis_report_notification import comment
from pilot.train_handoff import HandoffBlocked

SHA = "a" * 40


class Fake:
    def __init__(self):
        self.comments = []
        self.writes = []

    def call(self, method, path, body=None):
        if method == "GET" and path == "/issues/987":
            return {"state": "open", "labels": [{"name": "lf-request"}]}
        if method == "GET" and path.startswith("/issues/987/comments?"):
            return self.comments
        if method == "POST" and path == "/issues/987/comments":
            self.writes.append(body["body"])
            self.comments.append({"user": {"login": "github-actions[bot]"},
                                  "body": body["body"]})
            return {}
        raise AssertionError((method, path))


def read(*args, report="# Informe del análisis (candidato simulado)\n\nTexto",
         issue=987, exists=True):
    if args[0] == "diff":
        return "pilot/runs/req-987/ANALYSIS_REPORT.md" if exists else "other.md"
    if args[0] == "show" and args[1].endswith("request_meta.json"):
        return '{"author":"synthetic","issue":%d,"date":"2026-11-14"}' % issue
    if args[0] == "show" and args[1].endswith("ANALYSIS_REPORT.md"):
        return report
    raise AssertionError(args)


class Tests(unittest.TestCase):
    def test_comments_on_merged_report_exactly_once(self):
        api = Fake()
        self.assertEqual(comment(api, SHA, "req-987", read), "REPORT_COMMENTED")
        self.assertIn("Texto", api.writes[0])
        self.assertEqual(comment(api, SHA, "req-987", read), "REPORT_ALREADY_COMMENTED")
        self.assertEqual(len(api.writes), 1)

    def test_long_report_uses_sha_pinned_permalink(self):
        api = Fake()
        body = "# Informe del análisis\n" + "X" * 61_000
        self.assertEqual(comment(api, SHA, "req-987",
                                 lambda *args: read(*args, report=body)),
                         "REPORT_COMMENTED")
        self.assertIn("/blob/" + SHA + "/pilot/runs/req-987/ANALYSIS_REPORT.md",
                      api.writes[0])
        self.assertNotIn("X" * 100, api.writes[0])

    def test_unmerged_report_and_wrong_issue_fail_closed(self):
        for overrides in ({"exists": False}, {"issue": 988}):
            api = Fake()
            with self.assertRaisesRegex(HandoffBlocked, "ANALYSIS_REPORT"):
                comment(api, SHA, "req-987",
                        lambda *args: read(*args, **overrides))
            self.assertFalse(api.writes)

    def test_rejects_invalid_slug(self):
        with self.assertRaisesRegex(HandoffBlocked, "PROVENANCE"):
            comment(Fake(), SHA, "req-987/../req-175", read)


if __name__ == "__main__":
    unittest.main()
