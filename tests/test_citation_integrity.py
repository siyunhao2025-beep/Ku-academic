"""Synthetic publication-integrity fixtures; no record is a real paper."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import research as r


def record(**overrides):
    row = {
        "id": "synthetic-1",
        "citation_verdict": "VERIFIED",
        "integrity_status": "NO_SIGNAL_FOUND",
        "integrity_checked_at": "2026-10-06T01:00:00+00:00",
        "integrity_source_url": "https://example.org/synthetic-notice-check",
        "correction_effect": "NOT_APPLICABLE",
    }
    row.update(overrides)
    return row


class CitationIntegrityTests(unittest.TestCase):
    def test_documented_as_an_independent_axis_with_provenance(self):
        root = Path(__file__).resolve().parents[1]
        module = (root / "modules/evidence-integrity.md").read_text(encoding="utf-8")
        provenance = (root / "docs/PEER_COMPARISON.md").read_text(encoding="utf-8")
        for token in ("NO_SIGNAL_FOUND", "CORRECTED", "correction_effect", "citation-integrity"):
            self.assertIn(token, module)
        for token in (
            "jostelzer/grounded",
            "4b909ab102e5552126c4189381599ae9834e35e2",
            "maximalfocus/peerreview-skills",
            "611f378607b66850723fb2b15d18a4c948b562ba",
            "rokokol/papers-skill",
            "c0960762390bcf5309a8de797133bf6258d1d384",
        ):
            self.assertIn(token, provenance)

    def test_identity_and_publication_integrity_are_separate(self):
        report = r.assess_citation_integrity([record()])
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["counts"]["identity_review"], 0)
        self.assertTrue(report["absence_of_signal_is_not_proof_of_clean_record"])

    def test_correction_without_known_effect_needs_author_action(self):
        report = r.assess_citation_integrity([
            record(integrity_status="CORRECTED", correction_effect="UNKNOWN")
        ])
        self.assertEqual(report["status"], "AUTHOR_ACTION_REQUIRED")
        self.assertEqual(report["records"][0]["decision"], "REVIEW_CORRECTION")

    def test_correction_affecting_cited_content_is_blocked(self):
        report = r.assess_citation_integrity([
            record(integrity_status="CORRECTED", correction_effect="AFFECTS_CITED_CONTENT")
        ])
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["records"][0]["decision"], "DO_NOT_USE_AS_SUPPORT")

    def test_unaffected_correction_is_not_retraction(self):
        report = r.assess_citation_integrity([
            record(integrity_status="CORRECTED", correction_effect="UNAFFECTED")
        ])
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["records"][0]["decision"], "USABLE_WITH_CORRECTION_DISCLOSED")

    def test_retraction_and_expression_of_concern_are_blocked(self):
        for status in ("RETRACTED", "WITHDRAWN", "REMOVED", "EXPRESSION_OF_CONCERN"):
            with self.subTest(status=status):
                report = r.assess_citation_integrity([record(integrity_status=status)])
                self.assertEqual(report["status"], "BLOCKED")

        legacy = r.assess_citation_integrity([record(citation_verdict="RETRACTED")])
        self.assertEqual(legacy["status"], "BLOCKED")

    def test_not_checked_and_identity_mismatch_cannot_pass(self):
        unchecked = r.assess_citation_integrity([
            record(integrity_status="NOT_CHECKED", integrity_source_url="", integrity_checked_at="")
        ])
        mismatch = r.assess_citation_integrity([record(citation_verdict="MISMATCH")])
        self.assertEqual(unchecked["status"], "AUTHOR_ACTION_REQUIRED")
        self.assertEqual(mismatch["status"], "IDENTITY_REVIEW_REQUIRED")

    def test_rejects_naive_timestamp_and_invalid_source(self):
        with self.assertRaises(ValueError):
            r.assess_citation_integrity([record(integrity_checked_at="2026-10-06T01:00:00")])
        with self.assertRaises(ValueError):
            r.assess_citation_integrity([record(integrity_source_url="http://example.org/check")])

    def test_optional_freshness_policy_is_explicit(self):
        report = r.assess_citation_integrity(
            [record(integrity_checked_at="2026-09-01T00:00:00+00:00")],
            now="2026-10-06T02:00:00+00:00",
            max_age_days=30,
        )
        self.assertEqual(report["status"], "AUTHOR_ACTION_REQUIRED")
        self.assertEqual(report["records"][0]["decision"], "REFRESH_INTEGRITY_CHECK")
        self.assertEqual(report["freshness_policy_days"], 30)

    def test_cli_writes_report_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "ledger.json"
            output = root / "audit.json"
            ledger.write_text(json.dumps([record()]), encoding="utf-8")
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                code = r.main(["citation-integrity", str(ledger), "--out", str(output)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "PASS")
            with patch("sys.stderr", io.StringIO()):
                self.assertEqual(r.main(["citation-integrity", str(ledger), "--out", str(output)]), 2)


if __name__ == "__main__":
    unittest.main()
