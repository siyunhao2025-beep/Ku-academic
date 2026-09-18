"""Tests for citation-tier / access-level gating and legal OA fallback (scripts/access.py).
Network is mocked; no real HTTP calls."""
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import access  # noqa: E402


def cit(citation_id="C1", **kw):
    base = {"citation_id": citation_id, "claim": "x", "reference_key": "10.1/a"}
    base.update(kw)
    return base


class TierGatingTests(unittest.TestCase):
    def test_background_needs_only_metadata(self):
        r = access.evaluate_citation(cit(sentence_tier="background",
                                         access_level="metadata_only"))
        self.assertEqual(r["errors"], [], r["errors"])
        self.assertFalse(r["needs_fulltext"])

    def test_method_needs_abstract(self):
        ok = access.evaluate_citation(cit(sentence_tier="method",
                                          access_level="abstract_only"))
        self.assertEqual(ok["errors"], [])
        bad = access.evaluate_citation(cit(sentence_tier="method",
                                           access_level="metadata_only"))
        self.assertTrue(bad["errors"])

    def test_quantitative_needs_full_text_and_locator(self):
        blocked = access.evaluate_citation(cit(sentence_tier="quantitative",
                                               access_level="abstract_only"))
        self.assertTrue(blocked["needs_fulltext"])
        self.assertTrue(blocked["errors"])
        # full text but no locator still blocked
        no_loc = access.evaluate_citation(cit(sentence_tier="quantitative",
                                              access_level="full_text"))
        self.assertTrue(any("定位" in e for e in no_loc["errors"]))
        # full text + locator passes
        good = access.evaluate_citation(cit(sentence_tier="quantitative",
                                            access_level="full_text",
                                            locator="p.4, Fig.2"))
        self.assertEqual(good["errors"], [], good["errors"])

    def test_causal_needs_full_text(self):
        r = access.evaluate_citation(cit(sentence_tier="causal",
                                         access_level="full_text",
                                         locator="p.7"))
        self.assertEqual(r["errors"], [])

    def test_locator_inferred_from_available_evidence(self):
        r = access.evaluate_citation(cit(
            sentence_tier="quantitative", access_level="full_text",
            available_evidence="full text Fig.3 and Table 2"))
        self.assertEqual(r["errors"], [], r["errors"])

    def test_missing_tier_defaults_to_strictest(self):
        r = access.evaluate_citation(cit(access_level="metadata_only"))
        self.assertEqual(r["tier"], "causal")
        self.assertTrue(any("sentence_tier" in w for w in r["warnings"]))
        self.assertTrue(r["errors"])

    def test_project_result_covers_full_text(self):
        r = access.evaluate_citation(cit(sentence_tier="causal",
                                         access_level="project_result",
                                         locator="p.2"))
        self.assertEqual(r["errors"], [])


class UnpaywallResolveTests(unittest.TestCase):
    EMAIL = "researcher@example.com"

    def test_gold_oa_returns_legal_pdf(self):
        def fake_fetch(url):
            self.assertIn("api.unpaywall.org/v2/", url)
            self.assertIn(self.EMAIL, url)
            return {"is_oa": True, "oa_status": "gold",
                    "best_oa_location": {"host_type": "publisher",
                                         "url_for_pdf": "https://pub/a.pdf",
                                         "url": "https://pub/a", "license": "cc-by"},
                    "oa_locations": []}
        r = access.resolve_oa("10.1/a", self.EMAIL, fetch=fake_fetch)
        self.assertTrue(r["is_oa"])
        self.assertEqual(r["oa_status"], "gold")
        self.assertEqual(r["best_pdf"], "https://pub/a.pdf")

    def test_closed_status(self):
        def fake_fetch(url):
            return {"is_oa": False, "oa_status": "closed",
                    "best_oa_location": None, "oa_locations": []}
        r = access.resolve_oa("10.1/b", self.EMAIL, fetch=fake_fetch)
        self.assertFalse(r["is_oa"])
        self.assertEqual(r["oa_status"], "closed")
        self.assertIsNone(r["best_pdf"])

    def test_missing_email_rejected(self):
        with self.assertRaises(ValueError):
            access.resolve_oa("10.1/a", "not-an-email", fetch=lambda u: {})

    def test_network_failure_is_not_fabricated(self):
        def boom(url):
            raise urllib.error.URLError("connection reset")
        with self.assertRaises(RuntimeError) as ctx:
            access.resolve_oa("10.1/a", self.EMAIL, fetch=boom)
        self.assertIn("待确认", str(ctx.exception))

    def test_only_legal_locations_marked(self):
        def fake_fetch(url):
            return {"is_oa": True, "oa_status": "green",
                    "best_oa_location": {"host_type": "repository",
                                         "url_for_pdf": "https://repo/a.pdf",
                                         "url": "https://repo/a"},
                    "oa_locations": []}
        r = access.resolve_oa("10.1/c", self.EMAIL, fetch=fake_fetch)
        self.assertTrue(all(loc["legal"] for loc in r["locations"]))


class CheckCommandTests(unittest.TestCase):
    def test_end_to_end_blocks_quantitative_without_fulltext(self):
        tmp = tempfile.TemporaryDirectory()
        ws = Path(tmp.name)
        (ws / "audit").mkdir(parents=True)
        prov = {"citations": [
            {"citation_id": "C1", "sentence_tier": "background",
             "access_level": "metadata_only", "reference_key": "10.1/a"},
            {"citation_id": "C2", "sentence_tier": "quantitative",
             "access_level": "abstract_only", "reference_key": "10.2/b"},
        ]}
        (ws / "audit/citation-provenance.json").write_text(
            json.dumps(prov), encoding="utf-8")
        results = [access.evaluate_citation(c) for c in prov["citations"]]
        blockers = [r for r in results if r["errors"]]
        self.assertEqual([b["citation_id"] for b in blockers], ["C2"])
        report = json.loads((ws / "audit/citation-provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(len(report["citations"]), 2)
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
