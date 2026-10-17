import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import availability  # noqa: E402
import progress  # noqa: E402


def public_item(locator, *, version=None):
    item = {
        "route": "public",
        "locator": locator,
        "access_conditions": "Repository terms recorded in the manuscript.",
        "logged_out_check": {
            "status": "passed",
            "checked_at": "2026-10-17T10:30:00+08:00",
            "checked_by": "author",
        },
    }
    if version is not None:
        item["version"] = version
        item["persistent_id"] = "archive:example-release-v1.0"
    return item


def valid_manifest():
    return {
        "schema_version": "1.0",
        "data": public_item("doi:10.0000/example.synthetic"),
        "code": public_item(
            "https://example.invalid/project/releases/tag/v1.0",
            version="v1.0",
        ),
        "claims_fully_reproducible": False,
    }


class AvailabilityContractTests(unittest.TestCase):
    def test_public_material_requires_locator_and_logged_out_check(self):
        payload = valid_manifest()
        payload["data"].pop("locator")
        payload["code"]["logged_out_check"]["status"] = "not_checked"

        result = availability.audit_manifest(payload)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("DATA_LOCATOR", result["blockers"])
        self.assertIn("CODE_LOGGED_OUT_CHECK_STATUS", result["blockers"])

    def test_restricted_material_requires_reason_route_and_conditions(self):
        payload = valid_manifest()
        payload["data"] = {"route": "restricted"}

        result = availability.audit_manifest(payload)

        self.assertIn("DATA_RESTRICTION_REASON", result["blockers"])
        self.assertIn("DATA_REQUEST_ROUTE", result["blockers"])
        self.assertIn("DATA_ACCESS_CONDITIONS", result["blockers"])

    def test_not_applicable_requires_a_specific_rationale(self):
        payload = valid_manifest()
        payload["code"] = {"route": "not_applicable", "rationale": "N/A"}

        result = availability.audit_manifest(payload)

        self.assertIn("CODE_NOT_APPLICABLE_RATIONALE", result["blockers"])

    def test_fully_reproducible_claim_requires_independent_rerun_record(self):
        payload = valid_manifest()
        payload["claims_fully_reproducible"] = True

        result = availability.audit_manifest(payload)

        self.assertIn("INDEPENDENT_RERUN_EVIDENCE", result["blockers"])

    def test_complete_manifest_passes_contract_without_certifying_science(self):
        payload = valid_manifest()

        result = availability.audit_manifest(payload)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["blockers"], [])
        self.assertIn("does not prove", result["important_limit"])

    def test_template_exposes_fields_for_all_four_routes(self):
        payload = availability.template()

        for name in ("data", "code"):
            self.assertIn("restriction_reason", payload[name])
            self.assertIn("request_route", payload[name])
            self.assertIn("route_check", payload[name])
            self.assertIn("locations", payload[name])
            self.assertIn("rationale", payload[name])
        self.assertIn("independent_rerun", payload)

    def test_check_command_writes_a_machine_readable_pass_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest = root / "availability-manifest.json"
            report = root / "audit" / "availability.json"
            manifest.write_text(json.dumps(valid_manifest()), encoding="utf-8")

            exit_code = availability.main(["check", str(manifest), "--out", str(report)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["status"], "PASS")

    def test_p6_gate_requires_passing_availability_audit(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            checks = progress.check_p6(workspace, {})
            availability_checks = [x for x in checks if x[1] == "数据/代码可用性审计通过"]
            self.assertEqual(len(availability_checks), 1)
            self.assertFalse(availability_checks[0][0])

            report = availability.audit_manifest(valid_manifest())
            target = workspace / "audit" / "availability.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report), encoding="utf-8")
            checks = progress.check_p6(workspace, {})
            availability_checks = [x for x in checks if x[1] == "数据/代码可用性审计通过"]
            self.assertTrue(availability_checks[0][0])


if __name__ == "__main__":
    unittest.main()
