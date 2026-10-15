"""Tests for the figure guardrail (scripts/figures.py). No network.
Synthetic manifests and temp files only."""
import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import figures  # noqa: E402


def base_data_figure(**over):
    fig = {
        "id": "fig1", "type": "data",
        "source_data": ["analysis/results/r.csv"], "script": "figures/plot.py",
        "axes": {"x": "x (u)", "y": "y (u)"},
        "colors": {"palette": "okabe-ito", "n_series": 2,
                   "redundant_encoding": "marker shape"},
        "uncertainty": {"type": "SD", "sampling_unit": "per event"},
        "caption": "结果图。", "conceptual": False,
        "outputs": ["figures/fig1.pdf", "figures/fig1.png"],
        "visual_review": {"status": "passed", "reviewed_by": "Zhang",
                          "reviewed_at": "2026-09-18T00:00:00Z", "notes": ""},
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


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def with_release_contract(ws, fig):
    fig = dict(fig)
    sources = fig.get("source_data") or []
    outputs = fig.get("outputs") or []
    fig["provenance"] = {
        "source_data": {rel: _digest(ws / rel) for rel in sources},
        "script": _digest(ws / fig["script"]),
        "outputs": {rel: _digest(ws / rel) for rel in outputs},
    }
    fig["final_size"] = {
        "slot_class": "single-column",
        "width_mm": 85.0,
        "height_mm": 60.0,
    }
    fig["editability"] = {
        "class": "live-vector-text",
        "notes": "Vector marks and text remain editable.",
    }
    fig["visual_review"] = {
        **fig["visual_review"],
        "at_width_mm": 85.0,
        "at_height_mm": 60.0,
        "container": "manuscript single-column slot",
        "editability_checked": True,
    }
    return fig


class PaletteTests(unittest.TestCase):
    def test_okabe_ito_has_eight_colors(self):
        self.assertEqual(len(figures.PALETTES["okabe-ito"]), 8)

    def test_jet_and_rainbow_are_forbidden(self):
        self.assertIn("jet", figures.FORBIDDEN_PALETTES)
        self.assertIn("rainbow", figures.FORBIDDEN_PALETTES)


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

    def test_pending_review_blocks(self):
        fig = base_data_figure()
        fig["visual_review"] = {"status": "pending"}
        errors, _ = figures.check_one(self.ws, fig)
        self.assertTrue(any("人眼视觉审查" in e for e in errors))

    def test_release_contract_accepts_current_dependencies_and_final_size_review(self):
        fig = with_release_contract(self.ws, base_data_figure())
        errors, _ = figures.check_one(self.ws, fig, require_release_provenance=True)
        self.assertEqual(errors, [], errors)

    def test_release_contract_rejects_stale_source_hash(self):
        fig = with_release_contract(self.ws, base_data_figure())
        (self.ws / "analysis/results/r.csv").write_text("x,y\n1,3\n", encoding="utf-8")
        errors, _ = figures.check_one(self.ws, fig, require_release_provenance=True)
        self.assertTrue(any("source_data SHA-256" in e for e in errors), errors)

    def test_release_contract_rejects_unknown_editability_and_wrong_review_size(self):
        fig = with_release_contract(self.ws, base_data_figure())
        fig["editability"]["class"] = "fully-editable-somehow"
        fig["visual_review"]["at_width_mm"] = 170.0
        errors, _ = figures.check_one(self.ws, fig, require_release_provenance=True)
        self.assertTrue(any("editability.class" in e for e in errors), errors)
        self.assertTrue(any("最终宽度" in e for e in errors), errors)


class SchematicRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ws = make_workspace()
        (self.ws / "figures/sch.pdf").write_text("x", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _sch(self, conceptual, caption):
        return {"id": "s", "type": "schematic", "conceptual": conceptual,
                "caption": caption, "script": "figures/plot.py",
                "outputs": ["figures/sch.pdf"],
                "visual_review": {"status": "passed", "reviewed_by": "Z",
                                  "reviewed_at": "2026-09-18T00:00:00Z"}}

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


class ConsoleEncodingTests(unittest.TestCase):
    def test_cli_survives_dynamic_emoji_under_gbk(self):
        tmp, ws = make_workspace()
        self.addCleanup(tmp.cleanup)
        manifest = {
            "schematic_not_needed_reason": "not needed 🧪",
            "figures": [base_data_figure(
                id="result-🧪",
                source_data=["analysis/results/missing-🧪.csv"],
            )],
        }
        (ws / "figures/manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8",
        )
        repo = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "gbk"
        completed = subprocess.run(
            [sys.executable, str(repo / "scripts" / "figures.py"), "check", str(ws)],
            cwd=repo, capture_output=True, text=True, encoding="gbk", env=env,
        )
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 1, output)
        self.assertNotIn("UnicodeEncodeError", output)
        output.encode("gbk")


if __name__ == "__main__":
    unittest.main()
