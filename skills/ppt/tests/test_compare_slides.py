import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_slides.py"
SPEC = importlib.util.spec_from_file_location("compare_slides", SCRIPT)
compare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compare)


def slide(sid="s1", a="原始 A", b="原始 B", image="token-original"):
    return f'<slide id="{sid}"><style/><data><shape id="a" type="text"><content><p>{a}</p></content></shape><shape id="b"><content><p>{b}</p></content></shape><img id="im" src="{image}" width="100"/></data></slide>'


def deck(*pages):
    return '<presentation xmlns="urn:test">' + "".join(pages) + "</presentation>"


class CompareSlidesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def snapshots(self, baseline, working=None, remote=None):
        paths = []
        for name, content in (("baseline", baseline), ("working", working or baseline), ("remote", remote or baseline)):
            path = self.root / f"{name}.xml"
            path.write_text(content, encoding="utf-8")
            paths.append(path)
        return paths

    def report(self, baseline, working=None, remote=None):
        return compare.compare(*self.snapshots(baseline, working, remote))

    def test_independent_block_edits_are_recorded_without_conflict(self):
        report = self.report(deck(slide()), deck(slide(a="本地 A")), deck(slide(b="远端 B")))
        self.assertEqual(report["status"], "no_conflicts")
        self.assertEqual({c["relation"] for c in report["changes"]}, {"working_only", "remote_only"})
        self.assertFalse(report["safe_to_overwrite"])
        self.assertFalse(report["server_concurrency_safe"])

    def test_same_block_divergent_edits_conflict(self):
        report = self.report(deck(slide()), deck(slide(a="本地 A")), deck(slide(a="远端 A")))
        self.assertEqual(report["status"], "conflicts")
        self.assertEqual(report["summary"]["conflict_count"], 1)
        change = report["changes"][0]
        self.assertEqual(change["block_id"], "a")
        self.assertEqual(change["remote"]["text"], ["远端 A"])

    def test_same_change_on_both_sides_is_distinguished(self):
        report = self.report(deck(slide()), deck(slide(a="共同改动")), deck(slide(a="共同改动")))
        self.assertEqual(report["status"], "no_conflicts")
        self.assertEqual(report["changes"][0]["relation"], "same_change")

    def test_images_and_geometry_appear_in_report(self):
        report = self.report(deck(slide()), remote=deck(slide(image="new-user-image")))
        change = next(c for c in report["changes"] if c["block_id"] == "im")
        self.assertEqual(change["remote"]["images"][0]["src"], "new-user-image")
        self.assertEqual(change["remote"]["images"][0]["geometry"], {"width": "100"})

    def test_remote_reorder_retained_in_report(self):
        report = self.report(deck(slide("s1"), slide("s2")), remote=deck(slide("s2"), slide("s1")))
        self.assertEqual(report["status"], "no_conflicts")
        change = next(c for c in report["changes"] if c["kind"] == "slide_order")
        self.assertEqual(change["relation"], "remote_only")
        self.assertEqual(change["remote"], ["s2", "s1"])

    def test_incompatible_reorders_conflict(self):
        report = self.report(deck(slide("s1"), slide("s2"), slide("s3")),
                             deck(slide("s2"), slide("s1"), slide("s3")),
                             deck(slide("s1"), slide("s3"), slide("s2")))
        self.assertEqual(report["status"], "conflicts")
        self.assertEqual(report["changes"][0]["kind"], "slide_order")

    def test_missing_or_duplicate_ids_require_manual_review(self):
        for xml, expected in ((deck(slide().replace(' id="s1"', "")), "missing_slide_id"),
                              (deck(slide().replace(' id="a"', "")), "missing_block_id"),
                              (deck(slide().replace(' id="b"', ' id="a"')), "duplicate_block_id"),
                              (deck(slide(), slide()), "duplicate_slide_id")):
            with self.subTest(expected=expected):
                report = self.report(xml)
                self.assertEqual(report["status"], "manual_review")
                self.assertIn(expected, {p["code"] for p in report["manual_review"]})
                self.assertEqual(report["changes"], [])

    def test_delete_vs_edit_conflicts(self):
        report = self.report(deck(slide("s1"), slide("s2")), deck(slide("s2")), deck(slide("s1", a="远端编辑"), slide("s2")))
        self.assertEqual(report["status"], "conflicts")
        self.assertTrue(any(c["kind"] == "slide_presence" and c["conflict"] for c in report["changes"]))

    def test_xml_prefix_attributes_and_indentation_are_equivalent(self):
        baseline = deck(slide())
        root = compare.ET.fromstring(baseline)
        compare.ET.register_namespace("s", "urn:test")
        compare.ET.indent(root)
        formatted = compare.ET.tostring(root, encoding="unicode")
        formatted = formatted.replace('id="a" type="text"', 'type="text" id="a"')
        report = self.report(baseline, formatted)
        self.assertEqual(report["status"], "no_conflicts")
        self.assertEqual(report["changes"], [])

    def test_missing_baseline_cli_fails_closed_as_json(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = compare.main(["--working", "working.xml", "--remote", "remote.xml"])
        self.assertEqual(code, 2)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "error")
        self.assertIn("baseline", report["error"])
        self.assertFalse(report["safe_to_overwrite"])

    def test_report_cannot_overwrite_a_snapshot(self):
        paths = self.snapshots(deck(slide()))
        before = paths[0].read_bytes()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = compare.main(["--baseline", str(paths[0]), "--working", str(paths[1]), "--remote", str(paths[2]), "--output", str(paths[0])])
        self.assertEqual(code, 2)
        self.assertEqual(before, paths[0].read_bytes())


if __name__ == "__main__":
    unittest.main()
