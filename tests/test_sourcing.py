"""Tests for target-journal sourcing. No network: plan and record are offline.

The point of most of these tests is that the module must never imply access it
does not have. Paywall bypass is out of scope by construction, the plan may not
claim to know access status before it is checked, and an item that was not
obtained must never look obtained.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sourcing


def record(idx, title, journal, year, doi="", rtype="journal-article"):
    return {
        "id": doi or "metadata:%d" % idx,
        "doi": doi,
        "title": title,
        "journal": journal,
        "type": rtype,
        "authors": [{"family": "Author%d" % idx}],
        "first_available_date": "%d-01-01" % year,
        "url": "https://example.invalid/%d" % idx,
        "abstract_available": True,
    }


FIXTURES = [
    record(1, "Newest paper in target", "Target Journal", 2026, "10.1/a"),
    record(2, "Older paper in target", "Target Journal", 2019, "10.1/b"),
    record(3, "Paper elsewhere", "Other Journal", 2026, "10.1/c"),
    record(4, "Review in target", "Target Journal", 2025, "10.1/d", rtype="review-article"),
    record(5, "Subjournal paper", "Target Journal: Subsection", 2024, "10.1/e"),
]


class SelectionTests(unittest.TestCase):
    def test_journal_filter_matches_exact_and_subjournal(self):
        rows = sourcing.select(FIXTURES, "Target Journal")
        self.assertEqual(len(rows), 4)
        self.assertNotIn("Paper elsewhere", [r["title"] for r in rows])

    def test_newest_first(self):
        rows = sourcing.select(FIXTURES, "Target Journal")
        years = [sourcing._year(r) for r in rows]
        self.assertEqual(years, sorted(years, reverse=True))

    def test_since_year_and_top(self):
        rows = sourcing.select(FIXTURES, "Target Journal", since_year=2025, top=2)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(sourcing._year(r) >= 2025 for r in rows))

    def test_type_filter(self):
        rows = sourcing.select(FIXTURES, "Target Journal", types=["review-article"])
        self.assertEqual([r["title"] for r in rows], ["Review in target"])

    def test_no_journal_matches_returns_empty_not_everything(self):
        self.assertEqual(sourcing.select(FIXTURES, "Nonexistent Journal"), [])


class PlanTests(unittest.TestCase):
    def test_stable_ids_and_order(self):
        plan = sourcing.build_plan(FIXTURES, "Target Journal", "direction")
        self.assertEqual([i["id"] for i in plan["items"]], ["P001", "P002", "P003", "P004"])
        self.assertEqual(plan["items"][0]["title"], "Newest paper in target")

    def test_access_is_not_claimed_before_checking(self):
        plan = sourcing.build_plan(FIXTURES, "Target Journal", "direction")
        for item in plan["items"]:
            self.assertEqual(item["expected_access"], "unverified_pending_check")
            self.assertEqual(item["status"], "pending")

    def test_plan_carries_the_access_rule(self):
        plan = sourcing.build_plan(FIXTURES, "Target Journal", "direction")
        self.assertIn("Never bypass", plan["access_rule"])

    def test_suggested_filename_is_pdf_and_carries_year(self):
        plan = sourcing.build_plan(FIXTURES, "Target Journal", "direction")
        name = plan["items"][0]["manual"]["suggested_filename"]
        self.assertTrue(name.endswith(".pdf"))
        self.assertIn("2026", name)

    def test_selection_counters(self):
        plan = sourcing.build_plan(FIXTURES, "Target Journal", "direction", since_year=2025)
        self.assertEqual(plan["selection"]["candidates_considered"], len(FIXTURES))
        self.assertEqual(plan["selection"]["selected"], 2)

    def test_missing_year_does_not_crash(self):
        rows = [{"title": "No date", "journal": "Target Journal", "type": "journal-article"}]
        plan = sourcing.build_plan(rows, "Target Journal", "d")
        self.assertEqual(plan["items"][0]["year"], 0)


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.plan = sourcing.build_plan(FIXTURES, "Target Journal", "direction")
        sourcing.recount(self.plan)

    def test_record_updates_status_and_counts(self):
        sourcing.record_status(self.plan, "P001", "fetched")
        sourcing.record_status(self.plan, "P002", "manual_download_required")
        self.assertEqual(self.plan["counts"]["fetched"], 1)
        self.assertEqual(self.plan["counts"]["manual_download_required"], 1)
        self.assertEqual(self.plan["counts"]["pending"], 2)

    def test_invalid_status_rejected(self):
        with self.assertRaises(ValueError):
            sourcing.record_status(self.plan, "P001", "probably_fine")

    def test_unknown_id_rejected(self):
        with self.assertRaises(ValueError):
            sourcing.record_status(self.plan, "P999", "fetched")

    def test_note_is_stored(self):
        sourcing.record_status(self.plan, "P001", "not_accessible", "paywalled")
        self.assertEqual(self.plan["items"][0]["note"], "paywalled")


class ChecklistTests(unittest.TestCase):
    def test_checklist_lists_pending_items_with_fallback_instructions(self):
        text = sourcing.render_checklist(sourcing.recount(self.plan_for()))
        self.assertIn("人工下载兜底", text)
        self.assertIn("private-corpus/inbox", text)
        self.assertIn("P001", text)
        self.assertIn("corpus.py ingest", text)

    def test_fetched_items_drop_off_the_fallback_table(self):
        plan = sourcing.recount(self.plan_for())
        sourcing.record_status(plan, "P001", "fetched")
        text = sourcing.render_checklist(plan)
        rows = [ln for ln in text.splitlines() if ln.startswith("| P")]
        self.assertNotIn("| P001 |", " ".join(rows))

    def test_checklist_keeps_not_accessible_visible(self):
        plan = sourcing.recount(self.plan_for())
        sourcing.record_status(plan, "P002", "not_accessible", "paywalled")
        text = sourcing.render_checklist(plan)
        self.assertIn("not_accessible", text)

    def test_checklist_forbids_paywall_bypass(self):
        text = sourcing.render_checklist(sourcing.recount(self.plan_for()))
        self.assertIn("不要绕过付费墙", text)

    def test_checklist_warns_extraction_is_not_reading(self):
        text = sourcing.render_checklist(sourcing.recount(self.plan_for()))
        self.assertIn("提取成功不等于读过", text)

    def plan_for(self):
        return sourcing.build_plan(FIXTURES, "Target Journal", "direction")


class CliTests(unittest.TestCase):
    def test_plan_command_writes_both_files(self):
        with tempfile.TemporaryDirectory() as t:
            search = Path(t) / "search.json"
            search.write_text(json.dumps({"records": FIXTURES}), encoding="utf-8")
            out = Path(t) / "sourcing-plan.json"
            code = sourcing.main([
                "plan", str(search), "--journal", "Target Journal",
                "--direction", "d", "--out", str(out),
            ])
            self.assertEqual(code, 0)
            self.assertTrue(out.is_file())
            checklist = out.with_name("sourcing-checklist.md")
            self.assertTrue(checklist.is_file())
            written = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(len(written["items"]), 4)

    def test_plan_command_rejects_empty_records(self):
        with tempfile.TemporaryDirectory() as t:
            search = Path(t) / "search.json"
            search.write_text(json.dumps({"records": []}), encoding="utf-8")
            out = Path(t) / "plan.json"
            self.assertEqual(sourcing.main(["plan", str(search), "--out", str(out)]), 2)

    def test_record_command_persists(self):
        with tempfile.TemporaryDirectory() as t:
            search = Path(t) / "search.json"
            search.write_text(json.dumps({"records": FIXTURES}), encoding="utf-8")
            out = Path(t) / "sourcing-plan.json"
            sourcing.main(["plan", str(search), "--journal", "Target Journal", "--out", str(out)])
            self.assertEqual(sourcing.main(["record", str(out), "P001", "--status", "fetched"]), 0)
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(saved["items"][0]["status"], "fetched")

    def test_list_command_missing_file_returns_2(self):
        self.assertEqual(sourcing.main(["list", "no/such/plan.json"]), 2)


if __name__ == '__main__':
    unittest.main()
