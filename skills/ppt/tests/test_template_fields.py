import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "template_fields.py"
SPEC = importlib.util.spec_from_file_location("template_fields", SCRIPT)
fields = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fields)


class TemplateFieldsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.templates = self.root / "templates"
        self.templates.mkdir()
        (self.root / "assets").mkdir()
        (self.root / "assets" / "cherry-logo.png").write_bytes(b"test-local-asset")
        self.source = self.templates / "slide01.xml"
        self.source.write_text('''<s:slide xmlns:s="urn:test"><s:style/><s:data>
        <s:img src="@./cherry-logo.png"/>
        <s:shape type="text" width="160" topLeftY="27"><s:content fontSize="12"><s:p>Cherry Studio</s:p></s:content></s:shape>
        <s:shape type="text" width="400" topLeftY="80"><s:content fontSize="30"><s:p>示例<span xmlns="urn:test" bold="true">标题</span>尾巴</s:p></s:content></s:shape>
        <s:table><s:tr><s:td><s:content><s:p>第一格</s:p></s:content></s:td><s:td><s:content><s:p>第二格</s:p></s:content></s:td></s:tr></s:table>
        <s:chart><s:chartData><s:dim1><s:chartField name="月份" valueType="string">一,二</s:chartField></s:dim1><s:dim2><s:chartField name="数值" valueType="number">1,2</s:chartField></s:dim2></s:chartData></s:chart>
        </s:data></s:slide>''', encoding="utf-8")
        self.index = self.templates / "fields.json"
        self.built = fields.build_index(self.templates)
        fields.write_json(self.index, self.built)

    def args(self, **kwargs):
        values = dict(index=str(self.index), template="slide01", templates_dir=None,
                      bindings=None, output_dir=str(self.root / "output"), allow_draft=False, force=False)
        values.update(kwargs)
        return argparse.Namespace(**values)

    def complete_bindings(self):
        draft = fields.draft_bindings(self.built["templates"][0])
        for field in draft["fields"]:
            if not field["required"]:
                continue
            if field["kind"] == "chart_data":
                value = [5, 7] if field["value_type"] == "number" else ["甲", "乙"]
            else:
                value = "真实内容 & <甲> " + field["id"]
            draft["values"][field["id"]] = value
        target = self.root / "bindings.json"
        fields.write_json(target, draft)
        return target, draft

    def test_namespace_fields_include_rich_text_table_chart_and_images(self):
        template = self.built["templates"][0]
        self.assertEqual(template["field_count"], 9)
        entries = template["fields"]
        self.assertEqual(next(f for f in entries if f["role"] == "title")["example"], "示例标题尾巴")
        cells = [f for f in entries if f["role"] == "table_cell"]
        self.assertEqual(len(cells), 2)
        self.assertNotEqual(cells[0]["path"], cells[1]["path"])
        root = ET.parse(self.source).getroot()
        self.assertEqual("".join(fields.resolve(root, cells[1]["path"]).itertext()), "第二格")
        self.assertTrue(all(step["tag"].startswith("{urn:test}") for f in entries for step in f["path"]))

    def test_prepare_xml_escapes_and_targets_individual_cells(self):
        bindings, draft = self.complete_bindings()
        report, code = fields.prepare(self.args(bindings=str(bindings)))
        self.assertEqual(code, 0)
        self.assertTrue(report["complete"])
        self.assertEqual(report["completion_scope"], "field_bindings_only")
        self.assertEqual(report["xml_sha256"], fields.digest(report["xml_path"]))
        self.assertFalse(report["publication_ready"])
        root = ET.parse(report["xml_path"]).getroot()
        for field in draft["fields"]:
            if field["required"] and field["kind"] == "text":
                self.assertEqual("".join(fields.resolve(root, field["path"]).itertext()), draft["values"][field["id"]])
        self.assertIn("&amp;", Path(report["xml_path"]).read_text())
        self.assertEqual((self.root / "output/assets/cherry-logo.png").read_bytes(), b"test-local-asset")

    def test_incomplete_requires_explicit_draft(self):
        report, code = fields.prepare(self.args())
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "incomplete")
        self.assertIsNone(report["xml_path"])
        self.assertFalse((self.root / "output/slide01.xml").exists())
        self.assertTrue((self.root / "output/bindings.draft.json").is_file())
        report, code = fields.prepare(self.args(allow_draft=True))
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "draft")
        self.assertFalse(report["complete"])

    def test_prepared_pages_start_with_slide_for_lark_cli(self):
        # The source may be a full XML document, but the CLI accepts only a
        # slide fragment and rejects declarations before the opening tag.
        self.source.write_text('<?xml version="1.0" encoding="utf-8"?>\n' + self.source.read_text(), encoding="utf-8")
        self.built = fields.build_index(self.templates)
        fields.write_json(self.index, self.built)
        bindings, _ = self.complete_bindings()
        for draft in (False, True):
            with self.subTest(draft=draft):
                report, code = fields.prepare(self.args(
                    bindings=None if draft else str(bindings), allow_draft=draft,
                    output_dir=str(self.root / ("draft" if draft else "final"))))
                self.assertEqual(code, 0)
                payload = Path(report["xml_path"]).read_bytes()
                self.assertTrue(payload.startswith(b"<slide "), payload[:100])
                self.assertEqual(ET.fromstring(payload).tag, "{urn:test}slide")
                self.assertEqual(report["xml_sha256"], fields.digest(report["xml_path"]))

    def test_unchanged_example_needs_confirmation(self):
        path, draft = self.complete_bindings()
        target = next(f for f in draft["fields"] if f["required"] and f["kind"] == "text")
        draft["values"][target["id"]] = target["example"]
        fields.write_json(path, draft)
        report, code = fields.prepare(self.args(bindings=str(path)))
        self.assertEqual(code, 1)
        self.assertEqual(report["unfinished_fields"][0]["reason"], "unchanged_example_not_confirmed")
        draft["values"][target["id"]] = {"value": target["example"], "confirmed": True}
        fields.write_json(path, draft)
        self.assertEqual(fields.prepare(self.args(bindings=str(path)))[1], 0)

    def test_stale_index_and_bindings_fail_closed(self):
        path, draft = self.complete_bindings()
        draft["source_sha256"] = "wrong"
        fields.write_json(path, draft)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            fields.prepare(self.args(bindings=str(path)))
        self.source.write_text(self.source.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "Stale fields"):
            fields.prepare(self.args())

    def test_unknown_blank_and_missing_image_rejected(self):
        path, draft = self.complete_bindings()
        draft["values"]["bogus"] = "bad"
        fields.write_json(path, draft)
        with self.assertRaisesRegex(ValueError, "Unknown binding"):
            fields.prepare(self.args(bindings=str(path)))
        del draft["values"]["bogus"]
        target = next(f for f in draft["fields"] if f["kind"] == "text" and f["required"])
        draft["values"][target["id"]] = ""
        fields.write_json(path, draft)
        with self.assertRaisesRegex(ValueError, "blank values"):
            fields.prepare(self.args(bindings=str(path)))
        path, draft = self.complete_bindings()
        draft["values"]["image_0001"] = "@missing.png"
        fields.write_json(path, draft)
        with self.assertRaisesRegex(ValueError, "does not exist"):
            fields.prepare(self.args(bindings=str(path)))

    def test_local_image_binding_relative_to_bindings_file(self):
        path, draft = self.complete_bindings()
        (self.root / "replacement.png").write_bytes(b"replacement-asset")
        draft["values"]["image_0001"] = "@replacement.png"
        fields.write_json(path, draft)
        report, code = fields.prepare(self.args(bindings=str(path)))
        self.assertEqual(code, 0)
        self.assertIn("assets/replacement.png", report["copied_assets"])

    def test_numeric_chart_data_and_external_image_rejected(self):
        path, draft = self.complete_bindings()
        target = next(f for f in draft["fields"] if f["kind"] == "chart_data" and f["value_type"] == "number")
        draft["values"][target["id"]] = [1, "NaN"]
        fields.write_json(path, draft)
        with self.assertRaisesRegex(ValueError, "finite numbers"):
            fields.prepare(self.args(bindings=str(path)))
        path, draft = self.complete_bindings()
        draft["values"]["image_0001"] = "https://example.com/image.png"
        fields.write_json(path, draft)
        with self.assertRaisesRegex(ValueError, "external URLs"):
            fields.prepare(self.args(bindings=str(path)))

    def test_source_template_cannot_be_overwritten(self):
        path, _ = self.complete_bindings()
        before = self.source.read_bytes()
        with self.assertRaisesRegex(ValueError, "source template"):
            fields.prepare(self.args(bindings=str(path), output_dir=str(self.templates), force=True))
        self.assertEqual(before, self.source.read_bytes())

    def test_all_repository_templates_are_indexable(self):
        index = fields.build_index(SCRIPT.parents[1] / "templates")
        self.assertEqual(index["template_count"], 51)
        for template in index["templates"]:
            self.assertGreater(template["field_count"], 0)
            root = ET.parse(SCRIPT.parents[1] / "templates" / template["file"]).getroot()
            self.assertEqual(len([f for f in template["fields"] if f["kind"] == "text"]), len([n for n in root.iter() if fields.local(n.tag) == "p"]))
            self.assertTrue(all(f["required"] for f in template["fields"] if f["role"] == "page_number"))

    def test_real_metric_template_distinguishes_values_from_page_title(self):
        template = fields.index_template(SCRIPT.parents[1] / "templates/slide19.xml")
        metrics = [f for f in template["fields"] if f["role"] == "metric_value"]
        self.assertEqual({f["example"] for f in metrics}, {"72%", "4.8", "36h", "2.4×"})
        self.assertTrue(all(f["required"] and f["capacity_hint"] for f in metrics))
        self.assertEqual([f["example"] for f in template["fields"] if f["role"] == "title"], ["关键指标一览"])
        # Geometry and numeric form, rather than the filename, determine role.
        shape = ET.Element("shape", topLeftY="200", topLeftX="40")
        content = ET.Element("content", fontSize="32")
        self.assertEqual(fields.text_role("2小时", [shape, content])[0], "metric_value")
        self.assertEqual(fields.text_role("季度服务回顾", [shape, content])[0], "title")
        shape.set("topLeftY", "76")
        self.assertEqual(fields.text_role("2026", [shape, content])[0], "title")

    def test_cli_works_from_another_directory_and_checks_staleness(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "index", "--templates-dir", str(self.templates), "--output", str(self.index), "--check"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["checked"])
        self.source.write_text(self.source.read_text() + "\n")
        result = subprocess.run([sys.executable, str(SCRIPT), "index", "--templates-dir", str(self.templates), "--output", str(self.index), "--check"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "error")

    def test_edited_draft_is_never_reset_on_force(self):
        fields.prepare(self.args())
        draft_path = self.root / "output/bindings.draft.json"
        draft_path.write_text('{"my_edits": true}')
        fields.prepare(self.args(allow_draft=True, force=True))
        self.assertEqual(json.loads(draft_path.read_text()), {"my_edits": True})

    def test_same_template_two_named_pages_share_assets(self):
        _, binding = self.complete_bindings()
        reports = []
        for name in ("page01", "page02"):
            binding["output_name"] = name
            path = self.root / (name + ".json")
            fields.write_json(path, binding)
            report, code = fields.prepare(self.args(bindings=str(path), name=name))
            self.assertEqual(code, 0)
            self.assertEqual(Path(report["xml_path"]).name, name + ".xml")
            self.assertTrue((self.root / "output" / (name + ".bindings.draft.json")).is_file())
            self.assertTrue((self.root / "output" / (name + ".prepare-report.json")).is_file())
            reports.append(report)
        self.assertEqual(reports[0]["copied_assets"], ["assets/cherry-logo.png"])
        self.assertEqual(reports[1]["copied_assets"], [])
        self.assertEqual(reports[1]["reused_assets"], ["assets/cherry-logo.png"])
        self.assertEqual(len(list((self.root / "output/assets").iterdir())), 1)

    def test_named_page_rejects_traversal_and_wrong_page_binding(self):
        for name in ("../escaped", "x/y", "x\\y", ".", "/absolute", "page.xml"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "safe filename"):
                fields.prepare(self.args(name=name, allow_draft=True))
        path, binding = self.complete_bindings()
        binding["output_name"] = "page01"
        fields.write_json(path, binding)
        with self.assertRaisesRegex(ValueError, "output_name mismatch"):
            fields.prepare(self.args(name="page02", bindings=str(path)))

    def test_different_images_with_same_basename_do_not_overwrite(self):
        _, binding = self.complete_bindings()
        reports = []
        for name, payload in (("page01", b"first image"), ("page02", b"second image")):
            directory = self.root / name
            directory.mkdir()
            (directory / "custom.png").write_bytes(payload)
            binding["output_name"] = name
            binding["values"]["image_0001"] = "@custom.png"
            path = directory / "bindings.json"
            fields.write_json(path, binding)
            report, code = fields.prepare(self.args(bindings=str(path), name=name))
            self.assertEqual(code, 0)
            reports.append(report)
        self.assertNotEqual(reports[0]["copied_assets"], reports[1]["copied_assets"])
        self.assertEqual((self.root / "output/assets/custom.png").read_bytes(), b"first image")
        self.assertEqual(len(list((self.root / "output/assets").iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
