#!/usr/bin/env python3
"""Validate an evidence ledger for choosing a manuscript's target journal.

The validator checks declared search coverage, topical evidence, official
journal checks and author constraints. It does not search the web, estimate
acceptance probability, rank journal prestige, or certify that a venue is safe
or appropriate.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys


BANDS = {"strong_fit", "plausible", "stretch", "blocked"}
EVIDENCE_CHANNELS = {"bibliography", "recent_similarity_search", "citation_neighbor"}
SCOPE_STATUSES = {"fit", "mismatch", "unverified"}
ARTICLE_TYPE_STATUSES = {"accepted", "not_accepted", "unverified"}
CONSTRAINT_STATUSES = {"met", "conflict", "unknown"}
SEARCH_STATUSES = {"completed", "failed"}
URL = re.compile(r"^https?://\S+$", re.I)
DOI = re.compile(r"^(?:doi\s*:\s*|https?://doi\.org/)?10\.\d{4,9}/\S+$", re.I)
PMID = re.compile(r"^(?:pmid\s*:\s*)?\d{4,}$", re.I)
FORBIDDEN_KEYS = {
    "acceptance_probability",
    "acceptance_odds",
    "acceptance_score",
    "weighted_score",
    "ranking_score",
}


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("journal-match ledger must be a JSON object")
    return value


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def useful_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().lower() not in {
        "n/a",
        "na",
        "none",
        "unknown",
        "tbd",
    }


def aware_timestamp(value) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def source_record_valid(record) -> bool:
    return (
        isinstance(record, dict)
        and URL.match(str(record.get("source_url", "")).strip()) is not None
        and aware_timestamp(record.get("checked_at"))
    )


def stable_paper_locator(value) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    return bool(URL.match(text) or DOI.match(text) or PMID.match(text))


def add_check(checks: list[dict], code: str, ok: bool, detail: str) -> None:
    checks.append({"id": code, "status": "PASS" if ok else "BLOCKED", "detail": detail})


def walk_forbidden_keys(value, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}.{key}"
            if str(key).casefold() in FORBIDDEN_KEYS:
                found.append(child)
            found.extend(walk_forbidden_keys(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(walk_forbidden_keys(item, f"{prefix}[{index}]"))
    return found


def check_searches(checks: list[dict], searches) -> None:
    valid_list = isinstance(searches, list) and bool(searches)
    add_check(checks, "SEARCH_LOG", valid_list, "record at least one bounded candidate search")
    if not valid_list:
        return
    for index, search in enumerate(searches, 1):
        prefix = f"SEARCH_{index}"
        search = search if isinstance(search, dict) else {}
        add_check(checks, f"{prefix}_QUERY", useful_text(search.get("query")), "record the exact query")
        add_check(checks, f"{prefix}_SOURCE", useful_text(search.get("source")), "name the database or search source")
        status = search.get("status")
        add_check(
            checks,
            f"{prefix}_STATUS",
            status in SEARCH_STATUSES,
            f"status must be one of {sorted(SEARCH_STATUSES)}; a failed search is not zero hits",
        )
        add_check(
            checks,
            f"{prefix}_TIME",
            aware_timestamp(search.get("searched_at")),
            "searched_at needs an ISO-8601 timestamp with timezone",
        )
        limit = search.get("limit")
        add_check(
            checks,
            f"{prefix}_LIMIT",
            isinstance(limit, int) and not isinstance(limit, bool) and limit > 0,
            "record the positive result/page cap so coverage is auditable",
        )
        hits = search.get("hits")
        if status == "completed":
            add_check(
                checks,
                f"{prefix}_HITS",
                isinstance(hits, int) and not isinstance(hits, bool) and hits >= 0,
                "a completed search needs its non-negative hit count",
            )
        elif status == "failed":
            add_check(checks, f"{prefix}_FAILED_HITS", hits is None, "a failed search must not be recorded as zero hits")
            add_check(
                checks,
                f"{prefix}_FAILURE_REASON",
                useful_text(search.get("failure_reason")),
                "record why the search failed",
            )


def check_official(checks: list[dict], prefix: str, official, key: str, allowed: set[str]) -> str | None:
    record = official.get(key) if isinstance(official, dict) else None
    record = record if isinstance(record, dict) else {}
    status = record.get("status")
    add_check(checks, f"{prefix}_{key.upper()}_STATUS", status in allowed, f"status must be one of {sorted(allowed)}")
    if status and status != "unverified":
        add_check(
            checks,
            f"{prefix}_{key.upper()}_SOURCE",
            source_record_valid(record),
            "a verified official check needs its journal URL and a timezone-aware check time",
        )
    return status


def check_evidence(checks: list[dict], prefix: str, evidence, venue_name) -> set[str]:
    if not isinstance(evidence, list):
        add_check(checks, f"{prefix}_EVIDENCE_LIST", False, "topic_evidence must be a list")
        return set()
    add_check(checks, f"{prefix}_EVIDENCE_LIST", True, "topic_evidence is a list")
    channels: set[str] = set()
    locators: set[str] = set()
    for index, item in enumerate(evidence, 1):
        item_prefix = f"{prefix}_EVIDENCE_{index}"
        item = item if isinstance(item, dict) else {}
        channel = item.get("channel")
        channel_ok = channel in EVIDENCE_CHANNELS
        add_check(
            checks,
            f"{item_prefix}_CHANNEL",
            channel_ok,
            f"channel must be one of {sorted(EVIDENCE_CHANNELS)}",
        )
        if channel_ok:
            channels.add(channel)
        add_check(checks, f"{item_prefix}_TITLE", useful_text(item.get("title")), "record the paper title")
        evidence_venue = item.get("venue")
        same_venue = (
            isinstance(evidence_venue, str)
            and isinstance(venue_name, str)
            and evidence_venue.strip().casefold() == venue_name.strip().casefold()
        )
        add_check(
            checks,
            f"{item_prefix}_VENUE",
            same_venue,
            "the paper's verified venue must match this candidate journal",
        )
        locator = item.get("locator")
        normalized_locator = locator.strip().casefold() if isinstance(locator, str) else ""
        add_check(checks, f"{item_prefix}_LOCATOR", stable_paper_locator(locator), "record a DOI, PMID or stable URL")
        add_check(
            checks,
            f"{item_prefix}_UNIQUE",
            bool(normalized_locator) and normalized_locator not in locators,
            "the same paper cannot count twice under different discovery channels",
        )
        if normalized_locator:
            locators.add(normalized_locator)
        year = item.get("year")
        add_check(
            checks,
            f"{item_prefix}_YEAR",
            isinstance(year, int) and not isinstance(year, bool) and 1800 <= year <= datetime.now().year + 1,
            "record a plausible publication year",
        )
    return channels


def check_constraints(checks: list[dict], prefix: str, constraints) -> tuple[bool, bool, set[str]]:
    if not isinstance(constraints, list):
        add_check(checks, f"{prefix}_CONSTRAINT_LIST", False, "constraint_checks must be a list")
        return False, False, set()
    add_check(checks, f"{prefix}_CONSTRAINT_LIST", True, "constraint_checks is a list")
    has_conflict = False
    has_unknown = False
    names: set[str] = set()
    for index, item in enumerate(constraints, 1):
        item_prefix = f"{prefix}_CONSTRAINT_{index}"
        item = item if isinstance(item, dict) else {}
        name = item.get("name")
        normalized = name.strip().casefold() if isinstance(name, str) else ""
        add_check(checks, f"{item_prefix}_NAME", useful_text(name), "name the manuscript or author constraint")
        add_check(checks, f"{item_prefix}_UNIQUE", bool(normalized) and normalized not in names, "constraint names must be unique per venue")
        if normalized:
            names.add(normalized)
        status = item.get("status")
        add_check(
            checks,
            f"{item_prefix}_STATUS",
            status in CONSTRAINT_STATUSES,
            f"status must be one of {sorted(CONSTRAINT_STATUSES)}",
        )
        has_conflict = has_conflict or status == "conflict"
        has_unknown = has_unknown or status == "unknown"
        if status in {"met", "conflict"}:
            add_check(
                checks,
                f"{item_prefix}_SOURCE",
                source_record_valid(item),
                "met/conflict needs an official source URL and timezone-aware check time",
            )
        if status in {"conflict", "unknown"}:
            add_check(
                checks,
                f"{item_prefix}_REASON",
                useful_text(item.get("reason")),
                "conflict/unknown needs a specific reason",
            )
    return has_conflict, has_unknown, names


def check_venue(
    checks: list[dict],
    venue,
    index: int,
    names: set[str],
    manuscript_constraints: set[str],
) -> None:
    prefix = f"VENUE_{index}"
    venue = venue if isinstance(venue, dict) else {}
    name = venue.get("name")
    normalized = name.strip().casefold() if isinstance(name, str) else ""
    add_check(checks, f"{prefix}_NAME", useful_text(name), "record the journal name")
    add_check(checks, f"{prefix}_UNIQUE", bool(normalized) and normalized not in names, "journal names must be unique")
    if normalized:
        names.add(normalized)

    band = venue.get("band")
    add_check(checks, f"{prefix}_BAND", band in BANDS, f"band must be one of {sorted(BANDS)}")
    add_check(checks, f"{prefix}_REASON", useful_text(venue.get("reason")), "explain the band in manuscript-specific terms")

    evidence = venue.get("topic_evidence")
    channels = check_evidence(checks, prefix, evidence, name)
    evidence_count = len(evidence) if isinstance(evidence, list) else 0
    official = venue.get("official_checks")
    scope = check_official(checks, prefix, official, "scope", SCOPE_STATUSES)
    article_type = check_official(checks, prefix, official, "article_type", ARTICLE_TYPE_STATUSES)
    has_conflict, has_unknown, checked_constraints = check_constraints(checks, prefix, venue.get("constraint_checks"))
    missing_constraints = sorted(manuscript_constraints - checked_constraints)
    add_check(
        checks,
        f"{prefix}_CONSTRAINT_COVERAGE",
        not missing_constraints,
        "check every manuscript-level constraint; missing: " + (", ".join(missing_constraints) if missing_constraints else "none"),
    )
    hard_block = has_conflict or scope == "mismatch" or article_type == "not_accepted"

    if band == "strong_fit":
        add_check(
            checks,
            f"{prefix}_STRONG_EVIDENCE",
            evidence_count >= 2 and len(channels) >= 2,
            "strong_fit needs at least two papers from two independent discovery channels",
        )
        add_check(checks, f"{prefix}_STRONG_SCOPE", scope == "fit", "strong_fit requires official scope=fit")
        add_check(
            checks,
            f"{prefix}_STRONG_ARTICLE_TYPE",
            article_type == "accepted",
            "strong_fit requires official article_type=accepted",
        )
        add_check(
            checks,
            f"{prefix}_STRONG_CONSTRAINTS",
            not has_conflict and not has_unknown,
            "strong_fit cannot contain conflict or unknown author constraints",
        )
    elif band == "plausible":
        add_check(checks, f"{prefix}_PLAUSIBLE_EVIDENCE", evidence_count >= 1, "plausible needs at least one located paper")
        add_check(checks, f"{prefix}_PLAUSIBLE_NO_BLOCK", not hard_block, "a mismatch or conflict must be banded blocked")
    elif band == "stretch":
        add_check(checks, f"{prefix}_STRETCH_NO_BLOCK", not hard_block, "a mismatch or conflict must be banded blocked")
    elif band == "blocked":
        add_check(
            checks,
            f"{prefix}_BLOCK_REASON",
            hard_block,
            "blocked needs an official scope/article-type mismatch or an explicit constraint conflict",
        )


def audit_ledger(payload: dict) -> dict:
    checks: list[dict] = []
    add_check(checks, "SCHEMA_VERSION", payload.get("schema_version") == "1.0", "schema_version must be 1.0")
    add_check(checks, "CAPTURED_AT", aware_timestamp(payload.get("captured_at")), "captured_at needs an ISO-8601 timestamp with timezone")

    manuscript = payload.get("manuscript")
    manuscript = manuscript if isinstance(manuscript, dict) else {}
    add_check(checks, "MANUSCRIPT_TITLE", useful_text(manuscript.get("title")), "record the manuscript title or working title")
    add_check(checks, "MANUSCRIPT_ARTICLE_TYPE", useful_text(manuscript.get("article_type")), "record the intended article type")
    terms = manuscript.get("scope_terms")
    add_check(
        checks,
        "MANUSCRIPT_SCOPE_TERMS",
        isinstance(terms, list) and bool(terms) and all(useful_text(term) for term in terms),
        "record at least one manuscript-specific scope term",
    )
    declared_constraints = manuscript.get("constraints")
    constraints_valid = isinstance(declared_constraints, list) and all(useful_text(item) for item in declared_constraints)
    normalized_constraints = {
        item.strip().casefold() for item in declared_constraints
    } if constraints_valid else set()
    add_check(
        checks,
        "MANUSCRIPT_CONSTRAINTS",
        constraints_valid and len(normalized_constraints) == len(declared_constraints),
        "constraints must be a list of unique names; use an empty list when none are declared",
    )

    forbidden = walk_forbidden_keys(payload)
    add_check(
        checks,
        "NO_ACCEPTANCE_OR_RANKING_SCORE",
        not forbidden,
        "do not store acceptance probability or an automatic weighted/ranking score: " + (", ".join(forbidden) if forbidden else "none found"),
    )
    check_searches(checks, payload.get("searches"))

    venues = payload.get("venues")
    valid_venues = isinstance(venues, list) and bool(venues)
    add_check(checks, "VENUE_LIST", valid_venues, "record at least one candidate venue")
    if valid_venues:
        names: set[str] = set()
        for index, venue in enumerate(venues, 1):
            check_venue(checks, venue, index, names, normalized_constraints)

    blockers = [item["id"] for item in checks if item["status"] == "BLOCKED"]
    bands = {band: 0 for band in sorted(BANDS)}
    if isinstance(venues, list):
        for venue in venues:
            if isinstance(venue, dict) and venue.get("band") in bands:
                bands[venue["band"]] += 1
    return {
        "schema_version": "1.0",
        "status": "PASS" if not blockers else "BLOCKED",
        "checks": checks,
        "blockers": blockers,
        "venue_counts": bands,
        "important_limit": (
            "This contract checks the recorded search, paper evidence, official checks and constraints. "
            "It does not search journals, measure prestige, estimate acceptance, detect predatory venues, "
            "or replace author/editor judgment."
        ),
    }


def template() -> dict:
    return {
        "schema_version": "1.0",
        "captured_at": None,
        "manuscript": {"title": None, "article_type": None, "scope_terms": [], "constraints": []},
        "searches": [
            {
                "query": None,
                "source": None,
                "status": "completed | failed",
                "searched_at": None,
                "limit": None,
                "hits": None,
                "failure_reason": None,
            }
        ],
        "venues": [
            {
                "name": None,
                "band": "stretch",
                "reason": None,
                "topic_evidence": [
                    {"channel": "bibliography", "title": None, "venue": None, "year": None, "locator": None}
                ],
                "official_checks": {
                    "scope": {"status": "unverified", "source_url": None, "checked_at": None},
                    "article_type": {"status": "unverified", "source_url": None, "checked_at": None},
                },
                "constraint_checks": [],
            }
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="write a neutral journal-match ledger template")
    init.add_argument("ledger")
    check = sub.add_parser("check", help="validate a completed journal-match ledger")
    check.add_argument("ledger")
    check.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    if args.command == "init":
        target = Path(args.ledger)
        if target.exists():
            print(f"refusing to overwrite existing ledger: {target}", file=sys.stderr)
            return 2
        write_json(target, template())
        print(f"journal-match ledger template -> {target}")
        return 0

    try:
        result = audit_ledger(read_json(Path(args.ledger)))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"journal-match ledger error: {exc}", file=sys.stderr)
        return 2
    write_json(Path(args.out), result)
    print(f"journal-match audit: {result['status']} ({len(result['blockers'])} blocker(s)) -> {args.out}")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
