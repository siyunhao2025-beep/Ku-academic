"""Tests for the figure guardrail (scripts/figures.py). No network.
Synthetic manifests and temp files only."""
import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import figures  # noqa: E402

HASH_X = hashlib.sha256(b"x").hexdigest()


def base_data_figure(**over):
    fig = {
        "id": "fig1", "type": "data",
        "source_data": ["analysis/results/r.csv"], "script": "figures/plot.py",
        "axes": {"x": "x (u)", "y": "y (u)"},
        "colors": {"palette": "okabe-ito", "n_series": 2,
                   "redundant_encoding": "marker shape"},
        "uncertainty": {"type": "SD", "sampling_unit": "per event"},
        "caption": "结果图。", "conceptual": False,
        "target_width_mm": 85.0,
        "outputs": ["figures/fig1.pdf", "figures/fig1.png"],
        "visual_review": {"status": "passed", "reviewed_by": "Zhang",
                          "reviewed_at": "2026-09-18T00:00:00Z",
                          "reviewed_width_mm": 85.0,
                          "output_sha256": {
                              "figures/fig1.pdf": HASH_X,
                              "figures/fig1.png": HASH_X,
                          }, "notes": ""},
    }
    fig.update(over)
    return fig


def make_workspace():
    tmp = tempfile.TemporaryDirectory()
    ws = Path(tmp.name)
    (ws / "analysis/results").mkdir(parents=True)
    (ws / "analysis/results/r.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    (ws / "figures").mkdir(parents=True)
    (ws / "figures/plot.py").write_text("# plot\n", encoding="utf-8")
    for n in ("fig1.pdf", "fig1.png"):
        (ws / "figures" / n).write_text("x", encoding="utf-8")
    return tmp, ws


class PaletteTests(unittest.TestCase):
    def test_okabe_ito_has_eight_colors(self):
        self.assertEqual(len(figures.PALETTES["okabe-ito"]), 8)

    def test_jet_and_rainbow_are_forbidden(self):
        self.assertIn("jet", figures.FORBIDDEN_PALETTES)
        self.assertIn("rainbow", figures.FORBIDDEN_PALETTES)


class InitManifestTests(unittest.TestCase):
    def test_init_exposes_final_size_review_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ws = Path(temp_dir)
            figures.cmd_init(ws)
            manifest = json.loads((ws / "figures/manifest.json").read_text(encoding="utf-8"))

        for fig in manifest["figures"]:
            self.assertIn("target_width_mm", fig)
            self.assertIn("reviewed_width_mm", fig["visual_review"])


class DataFigureRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ws = make_workspace()

    def tearDown(self):
        self.tmp.cleanup()

    def test_complete_data_figure_passes(self):
        errors, warnings = figures.check_one(self.ws, base_data_figure())
        self.assertEqual(errors, [], errors)

    def test_jet_palette_rejected(self):
        errors, _ = figures.check_one(self.ws, base_data_figure(
            colors={"palette": "jet", "n_series": 2,
                    "redundant_encoding": "marker shape"}))
        self.assertTrue(any("禁用色板" in e for e in errors))

    def test_multiple_series_need_redundant_channel(self):
        errors, _ = figures.check_one(self.ws, base_data_figure(
            colors={"palette": "okabe-ito", "n_series": 3}))
        self.assertTrue(any("冗余通道" in e for e in errors))

    def test_single_series_does_not_need_redundant_channel(self):
        errors, _ = figures.check_one(self.ws, base_data_figure(
            colors={"palette": "okabe-ito", "n_series": 1}))
        self.assertFalse(any("冗余通道" in e for e in errors))

    def test_more_than_six_series_must_split(self):
        errors, _ = figures.check_one(self.ws, base_data_figure(
            colors={"palette": "okabe-ito", "n_series": 7,
                    "redundant_encoding": "marker shape"}))
        self.assertTrue(any("拆图" in e for e in errors))

    def test_missing_vector_output_rejected(self):
        errors, _ = figures.check_one(self.ws, base_data_figure(
            outputs=["figures/fig1.png"]))
        self.assertTrue(any("矢量" in e for e in errors))

    def test_missing_source_data_rejected(self):
        errors, _ = figures.check_one(self.ws, base_data_figure(source_data=[]))
        self.assertTrue(any("source_data" in e for e in errors))

    def test_missing_uncertainty_rejected(self):
        errors, _ = figures.check_one(self.ws, base_data_figure(uncertainty={}))
        self.assertTrue(any("uncertainty" in e for e in errors))

    def test_passed_review_needs_reviewer_and_date(self):
        fig = base_data_figure()
        fig["visual_review"] = {"status": "passed"}
        errors, _ = figures.check_one(self.ws, fig)
        self.assertTrue(any("reviewed_by" in e for e in errors))

    def test_passed_review_needs_current_output_hashes(self):
        fig = base_data_figure()
        fig["visual_review"].pop("output_sha256")
        errors, _ = figures.check_one(self.ws, fig)
        self.assertTrue(any("output_sha256" in e for e in errors))

    def test_review_width_must_match_target_placement_width(self):
        fig = base_data_figure()
        fig["visual_review"]["reviewed_width_mm"] = 178.0
        errors, _ = figures.check_one(self.ws, fig)
        self.assertTrue(any("reviewed_width_mm" in e and "target_width_mm" in e
                            for e in errors))

    def test_pending_review_blocks(self):
        fig = base_data_figure()
        fig["visual_review"] = {"status": "pending"}
        errors, _ = figures.check_one(self.ws, fig)
        self.assertTrue(any("人眼视觉审查" in e for e in errors))

    def test_changed_output_invalidates_visual_review(self):
        reviewed = hashlib.sha256(b"reviewed version").hexdigest()
        fig = base_data_figure()
        fig["visual_review"]["output_sha256"] = {
            "figures/fig1.pdf": reviewed,
            "figures/fig1.png": reviewed,
        }
        for name in ("fig1.pdf", "fig1.png"):
            (self.ws / "figures" / name).write_bytes(b"changed after review")

        errors, _ = figures.check_one(self.ws, fig)
        self.assertTrue(any("审查后已变化" in e for e in errors))

    def test_malformed_output_entry_is_reported_without_crashing_hash_check(self):
        fig = base_data_figure(outputs=[{"unexpected": "object"}, "figures/fig1.pdf"])
        fig["visual_review"]["output_sha256"] = {"figures/fig1.pdf": HASH_X}
        errors, _ = figures.check_one(self.ws, fig)
        self.assertTrue(any("输出文件不存在" in e for e in errors))


class SchematicRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ws = make_workspace()
        (self.ws / "figures/sch.pdf").write_text("x", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _sch(self, conceptual, caption):
        return {"id": "s", "type": "schematic", "conceptual": conceptual,
                "caption": caption, "script": "figures/plot.py",
                "target_width_mm": 85.0,
                "outputs": ["figures/sch.pdf"],
                "visual_review": {"status": "passed", "reviewed_by": "Z",
                                  "reviewed_at": "2026-09-18T00:00:00Z",
                                  "reviewed_width_mm": 85.0,
                                  "output_sha256": {"figures/sch.pdf": HASH_X}}}

    def test_schematic_must_be_flagged_conceptual(self):
        errors, _ = figures.check_one(self.ws, self._sch(False, "机制图"))
        self.assertTrue(any("概念示意" in e for e in errors))

    def test_schematic_with_conceptual_marker_passes(self):
        errors, _ = figures.check_one(self.ws,
                                      self._sch(True, "概念示意 Conceptual illustration"))
        self.assertEqual(errors, [], errors)


class MissingFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ws = make_workspace()

    def tearDown(self):
        self.tmp.cleanup()

    def test_nonexistent_output_reported(self):
        errors, _ = figures.check_one(self.ws, base_data_figure(
            outputs=["figures/nope.pdf", "figures/nope.png"]))
        self.assertTrue(any("不存在" in e for e in errors))

    def test_path_outside_workspace_not_counted(self):
        errors, _ = figures.check_one(self.ws, base_data_figure(
            source_data=["../../../../etc/passwd"]))
        self.assertTrue(any("source_data" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
