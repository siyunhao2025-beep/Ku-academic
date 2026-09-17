"""Tests for the simulated reviewer panel.

The tests that matter most here are the ones pinning what the panel must NOT do:
average reviewers together, pass a panel that found no scientific problems, or
emit an acceptance probability.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import review


def scores(value):
    return {d: value for d, _ in review.DIMENSIONS}


def full_panel(manuscript="manuscript/draft.md", ids=None):
    return review.build_panel(manuscript, ids)


class PanelTests(unittest.TestCase):
    def test_default_panel_is_four_distinct_reviewers(self):
        panel = full_panel()
        self.assertEqual(len(panel["reviewers"]), 4)
        self.assertEqual(len({r["id"] for r in panel["reviewers"]}), 4)

    def test_accepts_three_and_five(self):
        for n in (3, 5):
            ids = list(review.PERSONAS)[:n]
            self.assertEqual(len(full_panel(ids=ids)["reviewers"]), n)

    def test_rejects_two_and_six(self):
        for n in (2, 6):
            ids = list(review.PERSONAS)[:n] if n <= len(review.PERSONAS) else \
                list(review.PERSONAS) + ["dupe"]
            with self.assertRaises(ValueError):
                full_panel(ids=ids)

    def test_rejects_unknown_and_duplicate_reviewers(self):
        with self.assertRaises(ValueError):
            full_panel(ids=["handling-editor", "domain-expert", "nobody"])
        with self.assertRaises(ValueError):
            full_panel(ids=["handling-editor", "handling-editor", "domain-expert"])

    def test_rubric_matches_phase_gates(self):
        panel = full_panel()
        self.assertEqual(panel["rubric"]["panel_total"], 35)
        self.assertEqual(panel["rubric"]["pass_threshold"], 28)
        self.assertEqual(len(panel["rubric"]["dimensions"]), 7)

    def test_rules_forbid_averaging_and_probabilities(self):
        text = " ".join(full_panel()["rules"])
        self.assertIn("never averaged", text)
        self.assertIn("acceptance probability", text)


class ScoringTests(unittest.TestCase):
    def test_all_seven_dimensions_required_before_a_total_exists(self):
        panel = full_panel()
        review.score_reviewer(panel, "handling-editor", {"argument_clarity": 5})
        self.assertIsNone(panel["reviewers"][0]["total"])
        self.assertEqual(panel["reviewers"][0]["verdict"], "not_scored")

    def test_total_and_verdict_after_full_scoring(self):
        panel = full_panel()
        r = review.score_reviewer(panel, "handling-editor", scores(5))
        self.assertEqual(r["total"], 35)
        self.assertEqual(r["verdict"], "meets_bar")
        r2 = review.score_reviewer(panel, "domain-expert", scores(3))
        self.assertEqual(r2["total"], 21)
        self.assertEqual(r2["verdict"], "below_bar")

    def test_out_of_range_and_unknown_dimension_rejected(self):
        panel = full_panel()
        with self.assertRaises(ValueError):
            review.score_reviewer(panel, "handling-editor", {"argument_clarity": 6})
        with self.assertRaises(ValueError):
            review.score_reviewer(panel, "handling-editor", {"vibes": 5})

    def test_unknown_reviewer_rejected(self):
        with self.assertRaises(ValueError):
            review.score_reviewer(full_panel(), "nobody", scores(4))


class FindingTests(unittest.TestCase):
    def test_finding_needs_location_and_comment(self):
        panel = full_panel()
        with self.assertRaises(ValueError):
            review.add_finding(panel, "handling-editor", "major", "", "text")
        with self.assertRaises(ValueError):
            review.add_finding(panel, "handling-editor", "major", "Discussion p2", "")

    def test_invalid_severity_and_kind_rejected(self):
        panel = full_panel()
        with self.assertRaises(ValueError):
            review.add_finding(panel, "handling-editor", "fatal", "p1", "x")
        with self.assertRaises(ValueError):
            review.add_finding(panel, "handling-editor", "major", "p1", "x", kind="style")

    def test_ids_are_stable_and_unique(self):
        panel = full_panel()
        a = review.add_finding(panel, "handling-editor", "major", "p1", "one")
        b = review.add_finding(panel, "handling-editor", "minor", "p2", "two")
        self.assertEqual(a["id"], "handling-editor.1")
        self.assertEqual(b["id"], "handling-editor.2")

    def test_resolve_finding(self):
        panel = full_panel()
        f = review.add_finding(panel, "handling-editor", "major", "p1", "one")
        review.resolve_finding(panel, "handling-editor", f["id"], "resolved")
        self.assertEqual(panel["reviewers"][0]["findings"][0]["status"], "resolved")
        with self.assertRaises(ValueError):
            review.resolve_finding(panel, "handling-editor", "nope.9", "resolved")


class VerdictTests(unittest.TestCase):
    def _scored(self, values, findings=3):
        panel = full_panel()
        for rid, value in zip([r["id"] for r in panel["reviewers"]], values):
            review.score_reviewer(panel, rid, scores(value))
        for i in range(findings):
            review.add_finding(panel, "handling-editor", "minor", "p%d" % i, "sci %d" % i,
                               kind="science")
        return review.compute_verdict(panel)

    def test_incomplete_until_every_reviewer_is_scored(self):
        panel = full_panel()
        review.score_reviewer(panel, "handling-editor", scores(5))
        self.assertEqual(review.compute_verdict(panel)["panel_verdict"], "INCOMPLETE")

    def test_all_high_is_ready_for_human_check(self):
        panel = self._scored([5, 5, 5, 5])
        self.assertEqual(panel["panel_verdict"], "READY_FOR_HUMAN_SUBMISSION_CHECK")

    def test_exactly_at_threshold_passes_and_below_requires_revision(self):
        # 4 x 7 = 28 == PASS_THRESHOLD, so a uniform 4 passes; a uniform 3 does not.
        self.assertEqual(self._scored([4, 4, 4, 4])["panel_verdict"],
                         "READY_FOR_HUMAN_SUBMISSION_CHECK")
        self.assertEqual(self._scored([3, 3, 3, 3])["panel_verdict"],
                         "REVISION_REQUIRED")

    def test_open_blocker_blocks_the_panel(self):
        panel = full_panel()
        for rid in [r["id"] for r in panel["reviewers"]]:
            review.score_reviewer(panel, rid, scores(5))
        for i in range(3):
            review.add_finding(panel, "handling-editor", "minor", "p%d" % i, "sci")
        review.add_finding(panel, "methods-reviewer", "blocker", "Methods p3", "design flaw")
        self.assertEqual(review.compute_verdict(panel)["panel_verdict"], "BLOCKED")

    def test_no_scientific_findings_fails_the_panel(self):
        panel = full_panel()
        for rid in [r["id"] for r in panel["reviewers"]]:
            review.score_reviewer(panel, rid, scores(5))
        for i in range(4):
            review.add_finding(panel, "handling-editor", "minor", "p%d" % i, "fmt",
                               kind="format")
        verdict = review.compute_verdict(panel)
        self.assertEqual(verdict["panel_verdict"], "INSUFFICIENT_SCIENTIFIC_COVERAGE")

    def test_disagreement_is_reported_not_averaged(self):
        panel = self._scored([5, 5, 5, 3])
        self.assertEqual(panel["panel_verdict"], "PANEL_DISAGREEMENT")
        self.assertGreater(panel["summary"]["spread"], review.DISAGREEMENT_SPREAD)

    def test_never_emits_an_acceptance_probability(self):
        panel = self._scored([5, 5, 5, 5])
        self.assertEqual(panel["summary"]["acceptance_probability"], "not_estimated")
        report = review.render_report(panel)
        self.assertNotIn("%", report.split("## 不允许做的事")[0].replace("100%", ""))

    def test_summary_counts_science_vs_format(self):
        panel = self._scored([4, 4, 4, 4], findings=2)
        review.add_finding(panel, "domain-expert", "minor", "p9", "fmt", kind="format")
        review.compute_verdict(panel)
        self.assertEqual(panel["summary"]["science_findings"], 2)
        self.assertEqual(panel["summary"]["format_findings"], 1)


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.panel = self.dir / "panel.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_panel_command_writes_worksheet_and_report(self):
        report = self.dir / "review.md"
        code = review.main(["panel", "manuscript/draft.md", "--out", str(self.panel),
                            "--report", str(report)])
        self.assertEqual(code, 0)
        data = json.loads(self.panel.read_text(encoding='utf-8'))
        self.assertEqual(len(data["reviewers"]), 4)
        self.assertIn("审稿人评审意见", report.read_text(encoding='utf-8'))

    def test_panel_command_respects_reviewer_list(self):
        review.main(["panel", "m.md", "--out", str(self.panel),
                     "--reviewers", "handling-editor,domain-expert,methods-reviewer"])
        data = json.loads(self.panel.read_text(encoding='utf-8'))
        self.assertEqual(len(data["reviewers"]), 3)

    def test_score_finding_and_verdict_round_trip(self):
        review.main(["panel", "m.md", "--out", str(self.panel)])
        self.assertEqual(review.main(["score", str(self.panel), "handling-editor",
                                      "--scores", "5,5,5,5,5,5,5"]), 0)
        self.assertEqual(review.main(["finding", str(self.panel), "handling-editor",
                                      "--severity", "minor", "--location", "p1",
                                      "--comment", "science point"]), 0)
        data = json.loads(self.panel.read_text(encoding='utf-8'))
        self.assertEqual(data["reviewers"][0]["total"], 35)
        self.assertEqual(data["reviewers"][0]["findings"][0]["kind"], "science")
        self.assertEqual(review.main(["verdict", str(self.panel)]), 0)

    def test_bad_scores_argument_returns_2(self):
        review.main(["panel", "m.md", "--out", str(self.panel)])
        self.assertEqual(review.main(["score", str(self.panel), "handling-editor",
                                      "--scores", "5,5"]), 2)

    def test_missing_panel_file_returns_2(self):
        self.assertEqual(review.main(["verdict", "no/such/panel.json"]), 2)


if __name__ == '__main__':
    unittest.main()
