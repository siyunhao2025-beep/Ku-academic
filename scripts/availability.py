#!/usr/bin/env python3
"""Validate the P6 data/code availability and reproducibility-claim contract.

The validator checks declared evidence and workflow fields.  It does not open
repositories, decide whether sharing is ethically lawful, or prove that a study
can be reproduced.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys


ROUTES = {"public", "restricted", "in_manuscript", "not_applicable"}
DOI = re.compile(r"(?:doi\s*:\s*|https?://doi\.org/)10\.\d{4,9}/\S+", re.I)
ACCESSION = re.compile(
    r"\b(?:GSE\d+|GSM\d+|SR[APRX]\d+|ERR\d+|PRJ(?:NA|EB|DB)\d+|"
    r"PDB\s*:?[A-Za-z0-9]{4}|E-MTAB-\d+)\b",
    re.I,
)
URL = re.compile(r"^https?://\S+$", re.I)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("availability manifest must be a JSON object")
    return value


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def useful_text(value, minimum: int = 8) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    return len(text) >= minimum and text.lower() not in {"n/a", "na", "none", "unknown", "tbd"}


def aware_timestamp(value) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def concrete_locator(value) -> bool:
    return isinstance(value, str) and bool(URL.match(value.strip()) or DOI.search(value) or ACCESSION.search(value))


def persistent_identifier(item: dict) -> bool:
    locator = item.get("locator", "")
    declared = item.get("persistent_id")
    return bool(DOI.search(str(locator)) or ACCESSION.search(str(locator)) or useful_text(declared, 6))


def add_check(checks: list[dict], code: str, ok: bool, detail: str) -> None:
    checks.append({"id": code, "status": "PASS" if ok else "BLOCKED", "detail": detail})


def check_verification(checks: list[dict], prefix: str, record, label: str) -> None:
    record = record if isinstance(record, dict) else {}
    add_check(
        checks,
        f"{prefix}_{label}_STATUS",
        record.get("status") == "passed",
        "record an actual passed check; not_checked or planned is not evidence",
    )
    add_check(
        checks,
        f"{prefix}_{label}_TIME",
        aware_timestamp(record.get("checked_at")),
        "the check needs an ISO-8601 timestamp with timezone",
    )
    add_check(
        checks,
        f"{prefix}_{label}_ACTOR",
        useful_text(record.get("checked_by"), 3),
        "identify who performed the check",
    )


def check_material(checks: list[dict], name: str, item) -> None:
    prefix = name.upper()
    if not isinstance(item, dict):
        add_check(checks, f"{prefix}_ENTRY", False, f"{name} must be an object")
        return
    route = item.get("route")
    add_check(checks, f"{prefix}_ROUTE", route in ROUTES, f"route must be one of {sorted(ROUTES)}")
    if route not in ROUTES:
        return

    if route == "public":
        add_check(
            checks,
            f"{prefix}_LOCATOR",
            concrete_locator(item.get("locator")),
            "public material needs a concrete URL, DOI or repository accession",
        )
        add_check(
            checks,
            f"{prefix}_PERSISTENT_ID",
            persistent_identifier(item),
            "record a DOI/accession or an explicit persistent_id; a mutable landing page is insufficient",
        )
        add_check(
            checks,
            f"{prefix}_ACCESS_CONDITIONS",
            useful_text(item.get("access_conditions")),
            "record the license, terms or other access conditions",
        )
        if name == "code":
            add_check(
                checks,
                "CODE_VERSION",
                useful_text(item.get("version"), 2),
                "bind public code to the release, tag, commit or archived version used in the paper",
            )
        check_verification(checks, prefix, item.get("logged_out_check"), "LOGGED_OUT_CHECK")
        return

    if route == "restricted":
        add_check(
            checks,
            f"{prefix}_RESTRICTION_REASON",
            useful_text(item.get("restriction_reason"), 16),
            "state the concrete ethical, legal, consent, privacy or licensing restriction",
        )
        add_check(
            checks,
            f"{prefix}_REQUEST_ROUTE",
            useful_text(item.get("request_route"), 8),
            "name a usable committee, application page or contact route",
        )
        add_check(
            checks,
            f"{prefix}_ACCESS_CONDITIONS",
            useful_text(item.get("access_conditions")),
            "state review criteria, agreement or other conditions instead of saying only 'on request'",
        )
        check_verification(checks, prefix, item.get("route_check"), "ROUTE_CHECK")
        return

    if route == "in_manuscript":
        locations = item.get("locations")
        valid = isinstance(locations, list) and bool(locations) and all(useful_text(x, 3) for x in locations)
        add_check(
            checks,
            f"{prefix}_MANUSCRIPT_LOCATIONS",
            valid,
            "list the exact source-data, table, figure or supplement locations",
        )
        return

    add_check(
        checks,
        f"{prefix}_NOT_APPLICABLE_RATIONALE",
        useful_text(item.get("rationale"), 16),
        "not_applicable needs a specific rationale; N/A is not a rationale",
    )


def check_independent_rerun(checks: list[dict], payload: dict) -> None:
    if payload.get("claims_fully_reproducible") is not True:
        return
    record = payload.get("independent_rerun")
    record = record if isinstance(record, dict) else {}
    ok = (
        record.get("status") == "passed"
        and record.get("independent_of_authors") is True
        and useful_text(record.get("performed_by"), 3)
        and aware_timestamp(record.get("completed_at"))
        and useful_text(record.get("evidence_locator"), 6)
    )
    add_check(
        checks,
        "INDEPENDENT_RERUN_EVIDENCE",
        ok,
        "'fully reproducible' requires a passed non-author rerun with actor, time and evidence locator",
    )


def audit_manifest(payload: dict) -> dict:
    checks: list[dict] = []
    add_check(
        checks,
        "SCHEMA_VERSION",
        payload.get("schema_version") == "1.0",
        "schema_version must be 1.0",
    )
    check_material(checks, "data", payload.get("data"))
    check_material(checks, "code", payload.get("code"))
    check_independent_rerun(checks, payload)
    blockers = [item["id"] for item in checks if item["status"] == "BLOCKED"]
    return {
        "schema_version": "1.0",
        "status": "PASS" if not blockers else "BLOCKED",
        "checks": checks,
        "blockers": blockers,
        "important_limit": (
            "This contract checks the recorded access route and verification evidence. "
            "It does not prove scientific validity, legal permission, artifact completeness, "
            "or reproducibility."
        ),
    }


def template() -> dict:
    def route_fields() -> dict:
        return {
            "locator": None,
            "persistent_id": None,
            "access_conditions": None,
            "logged_out_check": {"status": "not_checked", "checked_at": None, "checked_by": None},
            "restriction_reason": None,
            "request_route": None,
            "route_check": {"status": "not_checked", "checked_at": None, "checked_by": None},
            "locations": [],
            "rationale": None,
        }

    return {
        "schema_version": "1.0",
        "data": {
            "route": "public | restricted | in_manuscript | not_applicable",
            **route_fields(),
        },
        "code": {
            "route": "public | restricted | in_manuscript | not_applicable",
            "version": None,
            **route_fields(),
        },
        "claims_fully_reproducible": False,
        "independent_rerun": {
            "status": "not_checked",
            "independent_of_authors": False,
            "performed_by": None,
            "completed_at": None,
            "evidence_locator": None,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="write a neutral availability-manifest template")
    init.add_argument("manifest")
    check = sub.add_parser("check", help="validate a completed availability manifest")
    check.add_argument("manifest")
    check.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    if args.command == "init":
        target = Path(args.manifest)
        if target.exists():
            print(f"refusing to overwrite existing manifest: {target}", file=sys.stderr)
            return 2
        write_json(target, template())
        print(f"availability manifest template -> {target}")
        return 0

    try:
        result = audit_manifest(read_json(Path(args.manifest)))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"availability manifest error: {exc}", file=sys.stderr)
        return 2
    write_json(Path(args.out), result)
    print(f"availability audit: {result['status']} ({len(result['blockers'])} blocker(s)) -> {args.out}")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
