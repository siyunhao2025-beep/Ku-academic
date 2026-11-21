import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import journal_match  # noqa: E402


def source(status):
    return {
        "status": status,
        "source_url": "https://journal.example.invalid/authors/scope",
        "checked_at": "2026-11-16T10:30:00+08:00",
    }


def evidence(channel, suffix):
    return {
        "channel": channel,
        "title": f"Located paper {suffix}",
        "venue": "Journal of Synthetic Examples",
        "year": 2025,
        "locator": f"doi:10.0000/example.{suffix}",
    }


def valid_ledger():
    return {
        "schema_version": "1.0",
        "captured_at": "2026-11-16T10:31:00+08:00",
        "manuscript": {
            "title": "A manuscript-specific working title",
            "article_type": "Research Article",
            "scope_terms": ["inverse modelling", "uncertainty quantification"],
            "constraints": ["open_access"],
        },
        "searches": [
            {
                "query": '"inverse modelling" uncertainty',
                "source": "Crossref",
                "status": "completed",
                "searched_at": "2026-11-16T10:20:00+08:00",
                "limit": 100,
                "hits": 18,
            }
        ],
        "venues": [
            {
                "name": "Journal of Synthetic Examples",
                "band": "strong_fit",
                "reason": "The manuscript topic and article type match located recent papers and the official scope.",
                "topic_evidence": [
                    evidence("bibliography", "one"),
                    evidence("recent_similarity_search", "two"),
                ],
                "official_checks": {
                    "scope": source("fit"),
                    "article_type": source("accepted"),
                },
                "constraint_checks": [
                    {
                        "name": "open_access",
                        "status": "met",
                        "source_url": "https://journal.example.invalid/authors/open-access",
                        "checked_at": "2026-11-16T10:30:00+08:00",
                    }
                ],
            }
        ],
    }


class JournalMatchContractTests(unittest.TestCase):
    def test_complete_evidence_ledger_passes_without_predicting_acceptance(self):
        result = journal_match.audit_ledger(valid_ledger())

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["blockers"], [])
        self.assertIn("does not", result["important_limit"])

    def test_strong_fit_requires_two_independent_discovery_channels(self):
        payload = valid_ledger()
        payload["venues"][0]["topic_evidence"][1]["channel"] = "bibliography"

        result = journal_match.audit_ledger(payload)

        self.assertIn("VENUE_1_STRONG_EVIDENCE", result["blockers"])

    def test_same_paper_cannot_count_twice_under_two_channels(self):
        payload = valid_ledger()
        payload["venues"][0]["topic_evidence"][1]["locator"] = payload["venues"][0]["topic_evidence"][0]["locator"]

        result = journal_match.audit_ledger(payload)

        self.assertIn("VENUE_1_EVIDENCE_2_UNIQUE", result["blockers"])

    def test_paper_evidence_must_be_published_in_the_candidate_venue(self):
        payload = valid_ledger()
        payload["venues"][0]["topic_evidence"][0]["venue"] = "A Different Journal"

        result = journal_match.audit_ledger(payload)

        self.assertIn("VENUE_1_EVIDENCE_1_VENUE", result["blockers"])

    def test_official_mismatch_or_constraint_conflict_must_be_blocked(self):
        payload = valid_ledger()
        venue = payload["venues"][0]
        venue["band"] = "plausible"
        venue["official_checks"]["scope"] = source("mismatch")

        result = journal_match.audit_ledger(payload)

        self.assertIn("VENUE_1_PLAUSIBLE_NO_BLOCK", result["blockers"])

    def test_blocked_band_needs_a_recorded_hard_reason(self):
        payload = valid_ledger()
        payload["venues"][0]["band"] = "blocked"

        result = journal_match.audit_ledger(payload)

        self.assertIn("VENUE_1_BLOCK_REASON", result["blockers"])

    def test_verified_official_fact_needs_url_and_timezone_aware_time(self):
        payload = valid_ledger()
        payload["venues"][0]["official_checks"]["scope"].pop("source_url")

        result = journal_match.audit_ledger(payload)

        self.assertIn("VENUE_1_SCOPE_SOURCE", result["blockers"])

    def test_acceptance_probability_and_automatic_ranking_fields_are_rejected(self):
        payload = valid_ledger()
        payload["venues"][0]["acceptance_probability"] = 0.72

        result = journal_match.audit_ledger(payload)

        self.assertIn("NO_ACCEPTANCE_OR_RANKING_SCORE", result["blockers"])

    def test_duplicate_journal_names_are_rejected_case_insensitively(self):
        payload = valid_ledger()
        duplicate = json.loads(json.dumps(payload["venues"][0]))
        duplicate["name"] = payload["venues"][0]["name"].upper()
        payload["venues"].append(duplicate)

        result = journal_match.audit_ledger(payload)

        self.assertIn("VENUE_2_UNIQUE", result["blockers"])

    def test_every_declared_author_constraint_must_be_checked_per_venue(self):
        payload = valid_ledger()
        payload["manuscript"]["constraints"].append("publication_fee")

        result = journal_match.audit_ledger(payload)

        self.assertIn("VENUE_1_CONSTRAINT_COVERAGE", result["blockers"])

    def test_failed_search_is_not_recorded_as_zero_hits(self):
        payload = valid_ledger()
        payload["searches"][0].update({"status": "failed", "hits": 0, "failure_reason": "Database timeout"})

        result = journal_match.audit_ledger(payload)

        self.assertIn("SEARCH_1_FAILED_HITS", result["blockers"])

    def test_check_command_writes_a_machine_readable_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger = root / "journal-match.json"
            report = root / "audit" / "journal-match.json"
            ledger.write_text(json.dumps(valid_ledger()), encoding="utf-8")

            exit_code = journal_match.main(["check", str(ledger), "--out", str(report)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["status"], "PASS")

    def test_init_refuses_to_overwrite_an_existing_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "journal-match.json"
            target.write_text("{}", encoding="utf-8")

            exit_code = journal_match.main(["init", str(target)])

            self.assertEqual(exit_code, 2)
            self.assertEqual(target.read_text(encoding="utf-8"), "{}")


if __name__ == "__main__":
    unittest.main()
