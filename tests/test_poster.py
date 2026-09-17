"""Tests for the poster flow.

The point of most of these: the three choices are mandatory, and a layout
scaffold must never be reported as a finished poster.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import poster


def seven(value):
    return ",".join([str(value)] * 7)


class ChoiceTests(unittest.TestCase):
    def test_choices_payload_has_all_three_questions(self):
        payload = poster.choices_payload()
        self.assertIn("question_1_size", payload)
        self.assertIn("question_2_language", payload)
        self.assertIn("question_3_output", payload)
        self.assertGreaterEqual(len(payload["question_1_size"]), 5)
        self.assertEqual([o["id"] for o in payload["question_3_output"]], ["image", "ppt"])

    def test_rule_forbids_defaults(self):
        self.assertIn("Do not assume a default", poster.choices_payload()["rule"])


class PlanTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_refuses_when_all_choices_missing(self):
        out = self.dir / 'p.json'
        self.assertEqual(poster.main(["plan", "--out", str(out)]), 2)
        self.assertFalse(out.exists())

    def test_refuses_on_partial_choices(self):
        for args in (["--size", "a0"], ["--size", "a0", "--lang", "zh"],
                     ["--lang", "zh", "--output", "image"],
                     ["--size", "a0", "--output", "image"]):
            out = self.dir / 'q.json'
            self.assertEqual(poster.main(["plan", *args, "--out", str(out)]), 2, args)
            self.assertFalse(out.exists(), args)

    def test_accepts_when_all_three_given(self):
        out = self.dir / 'ok.json'
        code = poster.main(["plan", "--size", "a0", "--lang", "zh", "--output", "image",
                            "--out", str(out)])
        self.assertEqual(code, 0)
        spec = json.loads(out.read_text(encoding='utf-8'))
        self.assertEqual(spec["size_id"], "a0")
        self.assertEqual(spec["language"], "zh")
        self.assertEqual(spec["output"], "image")
        self.assertEqual(spec["blocks"][0]["role"], "title")

    def test_rejects_unknown_language_and_size(self):
        self.assertEqual(poster.main(["plan", "--size", "a0", "--lang", "fr",
                                      "--output", "image", "--out", str(self.dir / 'a.json')]), 2)
        self.assertEqual(poster.main(["plan", "--size", "zz", "--lang", "zh",
                                      "--output", "image", "--out", str(self.dir / 'b.json')]), 2)

    def test_scaffold_is_marked_as_placeholder_in_both_languages(self):
        for lang in ("zh", "en"):
            out = self.dir / ('%s.json' % lang)
            poster.main(["plan", "--size", "a0", "--lang", lang, "--output", "image",
                         "--out", str(out)])
            spec = json.loads(out.read_text(encoding='utf-8'))
            self.assertTrue(poster.placeholders_remaining(spec))
            self.assertGreaterEqual(len(poster.placeholders_remaining(spec)), 5)


class SizeTests(unittest.TestCase):
    def test_auto_respects_named_orientation(self):
        self.assertEqual(poster.resolve_size("conf-120x90", "auto"), (1200.0, 900.0))
        self.assertEqual(poster.resolve_size("conf-90x120", "auto"), (900.0, 1200.0))

    def test_explicit_orientation_overrides(self):
        self.assertEqual(poster.resolve_size("a0", "landscape"), (1189.0, 841.0))
        self.assertEqual(poster.resolve_size("a0", "portrait"), (841.0, 1189.0))

    def test_unknown_orientation_rejected(self):
        with self.assertRaises(ValueError):
            poster.resolve_size("a0", "sideways")


class LayoutTests(unittest.TestCase):
    def make(self, size="a0", lang="zh", n_sections=4):
        spec = {"size_id": size, "language": lang, "output": "image",
                "width_mm": 841.0, "height_mm": 1189.0, "title": "T",
                "blocks": [{"role": "title", "text": "T"},
                           {"role": "byline", "text": "A"}]
                + [{"role": "section", "heading": "H%d" % i, "text": "body " * 40}
                   for i in range(n_sections)]
                + [{"role": "footer", "text": "F"}]}
        return spec

    def test_no_overlap_for_default_layout(self):
        spec = self.make()
        boxes = poster.layout(spec)
        self.assertEqual(poster._overlaps(boxes), [])

    def test_boxes_stay_inside_the_page(self):
        spec = self.make()
        boxes = poster.layout(spec)
        for box in boxes:
            self.assertGreaterEqual(box["x"], -0.01)
            self.assertGreaterEqual(box["y"], -0.01)
            self.assertLessEqual(box["x"] + box["w"], spec["width_mm"] + 0.01)
            self.assertLessEqual(box["y"] + box["h"], spec["height_mm"] + 0.01)

    def test_wide_poster_uses_more_columns(self):
        tall = self.make("a0")
        wide = self.make("conf-120x90")
        wide["width_mm"], wide["height_mm"] = 1200.0, 900.0
        self.assertGreaterEqual(poster.layout(wide) and wide["_metrics"]["columns"],
                                poster.layout(tall) and tall["_metrics"]["columns"])

    def test_overlap_detection_actually_detects(self):
        boxes = [{"role": "a", "x": 0, "y": 0, "w": 10, "h": 10, "block": {}, "font": 1},
                 {"role": "b", "x": 5, "y": 5, "w": 10, "h": 10, "block": {}, "font": 1}]
        self.assertEqual(poster._overlaps(boxes), ["a x b"])


class RenderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _render(self, output, name, strict=False):
        spec_path = self.dir / ('%s.json' % name)
        poster.main(["plan", "--size", "a0", "--lang", "zh", "--output", output,
                     "--out", str(spec_path)])
        target = self.dir / name
        args = ["render", str(spec_path), "--out", str(target)]
        if strict:
            args.append("--strict")
        code = poster.main(args)
        return code, target, spec_path

    def test_image_output_is_an_svg_at_physical_size(self):
        code, target, _ = self._render("image", "p.svg")
        self.assertEqual(code, 0)
        text = target.read_text(encoding='utf-8')
        self.assertIn('<svg', text)
        self.assertIn('width="841.0mm"', text)
        self.assertIn('height="1189.0mm"', text)

    def test_ppt_output_is_a_valid_pptx(self):
        code, target, _ = self._render("ppt", "p.pptx")
        self.assertEqual(code, 0)
        import ooxml
        self.assertEqual(ooxml.verify(target)['problems'], [])

    def test_strict_mode_fails_while_placeholders_remain(self):
        code, _, _ = self._render("image", "strict.svg", strict=True)
        self.assertEqual(code, 2)

    def test_metrics_are_recorded_back_into_the_spec(self):
        code, _, spec_path = self._render("image", "m.svg")
        spec = json.loads(spec_path.read_text(encoding='utf-8'))
        self.assertIn("fill_ratio", spec["_metrics"])
        self.assertIn("columns", spec["_metrics"])
        self.assertEqual(spec["_metrics"]["overlaps"], [])
        self.assertTrue(spec["_metrics"]["placeholders_remaining"])

    def test_refuses_to_overwrite_an_existing_poster(self):
        code, target, spec_path = self._render("image", "dup.svg")
        self.assertEqual(code, 0)
        self.assertEqual(poster.main(["render", str(spec_path), "--out", str(target)]), 2)

    def test_render_rejects_spec_missing_a_choice(self):
        spec_path = self.dir / "broken.json"
        spec_path.write_text(json.dumps({"blocks": [], "width_mm": 1, "height_mm": 1}),
                             encoding='utf-8')
        self.assertEqual(poster.main(["render", str(spec_path),
                                      "--out", str(self.dir / "x.svg")]), 2)


if __name__ == '__main__':
    unittest.main()
