"""Observable gate/CLI contracts, including optional official schema wrapping."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import preflight
import validate

XSD = '''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
 xmlns:s="https://www.larkoffice.com/sml/2.0" targetNamespace="https://www.larkoffice.com/sml/2.0"
 elementFormDefault="qualified"><xs:element name="presentation"><xs:complexType>
 <xs:sequence><xs:element name="slide"><xs:complexType><xs:sequence>
 <xs:element name="data" minOccurs="0"/></xs:sequence></xs:complexType></xs:element></xs:sequence>
 <xs:attribute name="width" type="xs:positiveInteger" use="required"/>
 <xs:attribute name="height" type="xs:positiveInteger" use="required"/>
 </xs:complexType></xs:element></xs:schema>'''


class GateTests(unittest.TestCase):
    def test_missing_input_is_error_and_json_matches_exit(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/validate.py"),
                                 "--input", "/does-not-exist/presentation.xml", "--json"],
                                capture_output=True, text=True)
        report = json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0)
        self.assertGreater(report["summary"]["errors"], 0)
        self.assertEqual(report["status"], "failed")

    def test_schema_wraps_fragment_without_changing_source(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            (path / "schema.xsd").write_text(XSD)
            xml = '<slide xmlns="https://www.larkoffice.com/sml/2.0"><data/></slide>'
            (path / "one.xml").write_text(xml)
            check = validate.SchemaCheck(path / "schema.xsd")
            self.assertEqual(check.review(path / "one.xml"), [])
            self.assertEqual((path / "one.xml").read_text(), xml)
            (path / "one.xml").write_text(xml.replace("<data/>", "<unknown/>"))
            self.assertTrue(check.review(path / "one.xml"))

    def test_schema_does_not_silently_rewrite_namespace(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            (path / "schema.xsd").write_text(XSD)
            (path / "one.xml").write_text('<slide xmlns="urn:wrong"><data/></slide>')
            self.assertTrue(validate.SchemaCheck(path / "schema.xsd").review(path / "one.xml"))

    def test_loaded_schema_is_not_passed_without_examining_any_input(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            (path / "schema.xsd").write_text(XSD)
            (path / "broken.yaml").write_text("schema_version: 999")
            empty = validate.run_checks([], schema_path=path / "schema.xsd")
            broken = validate.run_checks([ROOT / "templates/slide01.xml"],
                                        tokens_path=path / "broken.yaml", schema_path=path / "schema.xsd")
            for report in (empty, broken):
                self.assertTrue(report["schema"]["loaded"])
                self.assertEqual(report["schema"]["status"], "not_run")
                self.assertEqual(report["exit_code"], 1)

    def test_no_schema_is_distinct_from_verified_schema(self):
        report = validate.run_checks([ROOT / "templates/slide01.xml"])
        self.assertEqual(report["schema"]["status"], "not_run")
        self.assertNotEqual(report["status"], "passed")
        self.assertFalse(report["render_verified"])
        required = validate.run_checks([ROOT / "templates/slide01.xml"], require_schema=True)
        self.assertEqual(required["exit_code"], 1)
        self.assertIn("schema_required", [i["code"] for i in required["global_issues"]])

    def test_warning_policy_changes_exit_without_hiding_findings(self):
        import review_layout
        import review_design
        warning = {"file": "a.xml", "issues": [{"level": "warning", "code": "measure", "message": "review", "element": ""}]}
        with mock.patch.object(review_layout, "review_slide", return_value=warning), \
             mock.patch.object(review_design, "review_slide", return_value={"issues": []}):
            relaxed = validate.run_checks([Path("a.xml")])
            strict = validate.run_checks([Path("a.xml")], strict_warnings=True)
        self.assertEqual(relaxed["summary"]["warnings"], strict["summary"]["warnings"])
        self.assertEqual(relaxed["exit_code"], 0)
        self.assertEqual(strict["exit_code"], 1)


class PreflightTests(unittest.TestCase):
    def test_offline_mode_never_invokes_cli(self):
        with mock.patch.object(preflight.subprocess, "run") as run:
            report = preflight.inspect_environment()
        run.assert_not_called()
        self.assertFalse(report["cli"]["checked"])

    def test_cli_probes_only_help_and_version_and_detect_missing_flags(self):
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            # A CLI returning successful but generic help must not pass capability checks.
            return subprocess.CompletedProcess(command, 0, "lark-cli version 1.0.86\n", "")

        with mock.patch.object(preflight.shutil, "which", return_value="/fake/lark-cli"), \
             mock.patch.object(preflight.subprocess, "run", side_effect=run):
            report = preflight.inspect_environment(check_cli=True)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(calls)
        for command in calls:
            self.assertIn(command[-1], ("--help", "--version"))
        self.assertFalse(report["cli"]["authentication_checked"])


if __name__ == "__main__":
    unittest.main()
