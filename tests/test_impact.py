"""Tests for change-impact analysis (scripts/impact.py). Pure graph logic, no network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import impact  # noqa: E402


class ClassifyTests(unittest.TestCase):
    def test_design_file(self):
        self.assertEqual(impact.classify("design.json"), "design")

    def test_results_directory(self):
        self.assertEqual(impact.classify("analysis/results/event01.csv"), "results")

    def test_figures_manifest_and_assets(self):
        self.assertEqual(impact.classify("figures/manifest.json"), "figures")
        self.assertEqual(impact.classify("figures/fig1.pdf"), "figures")

    def test_conclusion_more_specific_than_manuscript(self):
        self.assertEqual(impact.classify("manuscript/conclusion.md"), "conclusion")
        self.assertEqual(impact.classify("manuscript/intro.md"), "manuscript")

    def test_evidence_cards(self):
        self.assertEqual(impact.classify("reading-cards/card01.md"), "evidence")

    def test_unknown_path(self):
        self.assertIsNone(impact.classify("random/foo.txt"))


class PropagationTests(unittest.TestCase):
    def test_design_change_invalidates_downstream_pipeline(self):
        affected = impact.propagate(["design"])
        for node in ("results", "figures", "claim_map", "manuscript",
                     "conclusion", "citation_final", "submission"):
            self.assertIn(node, affected, f"{node} should be invalidated")

    def test_design_change_keeps_upstream(self):
        affected = impact.propagate(["design"])
        for node in ("prepped", "scope", "evidence", "gaps", "data_audit"):
            self.assertNotIn(node, affected)

    def test_results_change_does_not_touch_design(self):
        affected = impact.propagate(["results"])
        self.assertIn("figures", affected)
        self.assertIn("manuscript", affected)
        self.assertNotIn("design", affected)
        self.assertNotIn("evidence", affected)

    def test_evidence_change_reaches_conclusion(self):
        affected = impact.propagate(["evidence"])
        self.assertIn("design", affected)
        self.assertIn("conclusion", affected)

    def test_submission_is_leaf(self):
        # nothing downstream of submission
        self.assertEqual(impact.EDGES.get("submission", []), [])


class AnalyzeReportTests(unittest.TestCase):
    def test_rollback_stage_design(self):
        r = impact.analyze(["design.json"])
        self.assertEqual(r["rollback_to_stage"], "P3")

    def test_rollback_stage_results(self):
        r = impact.analyze(["analysis/results/x.csv"])
        self.assertEqual(r["rollback_to_stage"], "P4")

    def test_rollback_stage_evidence(self):
        r = impact.analyze(["evidence.json"])
        self.assertEqual(r["rollback_to_stage"], "P2")

    def test_chain_explains_propagation(self):
        chain = impact.shortest_chain("design", "submission")
        self.assertEqual(chain[0], "design")
        self.assertEqual(chain[-1], "submission")

    def test_unclassified_reported(self):
        r = impact.analyze(["random/foo.txt"])
        self.assertIn("random/foo.txt", r["unclassified_paths"])
        self.assertEqual(r["roots"], [])

    def test_multiple_roots(self):
        r = impact.analyze(["design.json", "evidence.json"])
        root_nodes = {x["node"] for x in r["roots"]}
        self.assertEqual(root_nodes, {"design", "evidence"})
        # earliest rollback stage among roots is P2 (evidence)
        self.assertEqual(r["rollback_to_stage"], "P2")

    def test_every_affected_node_has_action(self):
        r = impact.analyze(["design.json"])
        for d in r["affected"]:
            self.assertTrue(d["action"])
            self.assertEqual(d["stage"], impact.NODES[d["node"]][0])


if __name__ == "__main__":
    unittest.main()
