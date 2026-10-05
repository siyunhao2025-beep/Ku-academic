#!/usr/bin/env python3
"""Research Mother v0.1: auditable utilities; scientific judgements remain agent tasks."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.5.0"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def safe_path(root, relative):
    root = Path(root).resolve()
    rel = Path(relative)
    if rel.is_absolute() or not relative or "\\" in str(relative):
        raise ValueError("Use a nonempty relative POSIX path")
    # Re-resolve every component explicitly. Path.resolve() alone is not enough:
    # on Windows a component may be a reparse point (symlink or junction) that
    # resolve() follows without the intermediate component ever being compared
    # against the workspace root, and os.path.islink() can miss junctions.
    candidate = root
    for part in rel.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError("Path escapes workspace")
        candidate = candidate / part
        if candidate.exists() or os.path.islink(candidate) or os.path.lexists(candidate):
            resolved = candidate.resolve()
            if not resolved.is_relative_to(root):
                raise ValueError("Path escapes workspace")
            candidate = resolved
    p = candidate.resolve()
    if not p.is_relative_to(root):
        raise ValueError("Path escapes workspace")
    return p


def doi(value):
    text = str(value or "").strip()
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text, flags=re.I)
    return urllib.parse.unquote(text).lower()


def date_parts(item, field):
    values = item.get(field, {}).get("date-parts", [[]])[0]
    return "-".join(str(v) if i == 0 else f"{v:02d}" for i, v in enumerate(values))


def normalise(item):
    ident = doi(item.get("DOI"))
    dates = {k: date_parts(item, k) for k in ("published-online", "published-print", "published", "issued")}
    chosen = next((dates[k] for k in dates if dates[k]), "")
    title = " ".join(item.get("title", []))
    fallback = hashlib.sha256((title + chosen).encode()).hexdigest()[:16]
    return {"id": ident or "metadata:" + fallback, "doi": ident, "title": title,
            "journal": " ".join(item.get("container-title", [])), "type": item.get("type", ""),
            "authors": item.get("author", []), "dates": dates, "first_available_date": chosen,
            "indexed_at": item.get("indexed", {}).get("date-time", ""),
            "created_at": item.get("created", {}).get("date-time", ""),
            "url": item.get("URL", ""), "links": item.get("link", []),
            "updates": item.get("update-to", []), "relations": item.get("relation", {}),
            "evidence_level": "metadata_only", "relevance": "unreviewed",
            "publication_status": "unverified", "abstract_available": bool(item.get("abstract"))}


def get_json(url, retries=2):
    req = urllib.request.Request(url, headers={"User-Agent": "ResearchMother/" + VERSION,
                                               "Accept": "application/json"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                raw = response.read(20_000_001)
                if len(raw) > 20_000_000:
                    raise ValueError("Metadata response exceeds 20 MB")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            if attempt == retries or exc.code not in (429, 500, 502, 503, 504):
                detail = exc.read(4096).decode("utf-8", errors="replace")
                raise RuntimeError(f"Crossref HTTP {exc.code}: {detail}") from exc
            wait = exc.headers.get("Retry-After", "")
            if wait.isdigit() and int(wait) > 60:
                raise RuntimeError("Rate limited: Retry-After exceeds bounded retry budget") from exc
            time.sleep(int(wait) if wait.isdigit() else 2 ** (attempt + 1))
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError("Unreachable retry state")


def search(query, since, until, output, pages=2, rows=50, mode="published", fetch=get_json):
    """Bounded candidate discovery, not exhaustive review or DOI-to-claim validation."""
    if dt.date.fromisoformat(since) > dt.date.fromisoformat(until):
        raise ValueError("since must not follow until")
    if not 1 <= pages <= 100 or not 1 <= rows <= 1000:
        raise ValueError("pages: 1..100; rows: 1..1000")
    if mode not in {"published", "indexed"}:
        raise ValueError("Unknown search mode")
    out = Path(output)
    if out.exists():
        raise FileExistsError("Use a new search directory to preserve previous snapshots")
    out.mkdir(parents=True)
    prefix = "pub" if mode == "published" else "index"
    cursor, records, snapshots, complete = "*", {}, [], False
    report = {"version": VERSION, "retrieved_at": utc(), "provider": "Crossref",
              "query": query, "since": since, "until": until, "mode": mode,
              "status": "running", "server_sort": "indexed", "coverage": "bounded_single_provider_candidates",
              "records": [], "requests": snapshots}
    try:
        for page in range(pages):
            params = {"query.bibliographic": query, "filter": f"from-{prefix}-date:{since},until-{prefix}-date:{until}",
                      "rows": rows, "cursor": cursor, "sort": "indexed", "order": "desc"}
            url = "https://api.crossref.org/v1/works?" + urllib.parse.urlencode(params)
            report["last_requested_url"] = url
            data = fetch(url)
            name = f"raw-{page + 1:03d}.json"
            write(out / name, data)
            msg = data["message"]
            items = msg["items"]
            if not isinstance(items, list):
                raise ValueError("Invalid Crossref items")
            snapshots.append({"url": url, "file": name, "sha256": sha(out / name), "count": len(items),
                              "reported_total": msg.get("total-results"), "at": utc()})
            for item in items:
                record = normalise(item)
                records[record["id"]] = record
            next_cursor = msg.get("next-cursor")
            if len(items) < rows or not next_cursor:
                complete = True
                break
            # Some servers keep the same opaque cursor; only an empty/short page proves exhaustion.
            cursor = next_cursor
        report.update(status="ok", records=list(records.values()), provider_query_exhausted=complete,
                      truncated=not complete)
    except Exception as exc:
        report.update(status="error", error_type=type(exc).__name__, error=str(exc), records=list(records.values()),
                      provider_query_exhausted=False, truncated=True)
        write(out / "search.json", report)
        raise
    write(out / "search.json", report)
    return report


def assess_search_progress(rounds, budget, patience, min_new):
    """Apply a bounded, evidence-matrix-aware stopping rule to search rounds.

    This is an engineering control for search effort. It never establishes that
    the literature is exhaustive or that admitted sources support a claim.
    """
    if not isinstance(rounds, list) or not rounds:
        raise ValueError("rounds must be a non-empty array")
    if not all(isinstance(x, int) and x >= 1 for x in (budget, patience, min_new)):
        raise ValueError("budget, patience and min_new must be positive integers")

    required = {"round", "queries", "new_deduped_records", "admitted_sources",
                "matrix_changing_sources", "open_required_gaps"}
    trajectory = []
    for index, entry in enumerate(rounds):
        if not isinstance(entry, dict) or not required.issubset(entry):
            raise ValueError(f"round {index} is missing required fields")
        if entry["round"] != index:
            raise ValueError("round identifiers must be contiguous and start at 0")
        if not isinstance(entry["queries"], list) or not entry["queries"] or not all(
                isinstance(query, str) and query.strip() for query in entry["queries"]):
            raise ValueError(f"round {index} needs at least one non-empty query")
        counts = [entry["new_deduped_records"], entry["admitted_sources"],
                  entry["matrix_changing_sources"]]
        if not all(isinstance(value, int) and value >= 0 for value in counts):
            raise ValueError(f"round {index} counts must be non-negative integers")
        if entry["matrix_changing_sources"] > entry["admitted_sources"]:
            raise ValueError(f"round {index} cannot change the matrix with more sources than it admitted")
        if not isinstance(entry["open_required_gaps"], list) or not all(
                isinstance(gap, str) and gap.strip() for gap in entry["open_required_gaps"]):
            raise ValueError(f"round {index} open_required_gaps must be an array of non-empty strings")
        trajectory.append(entry["matrix_changing_sources"])

    dry_streak = 0
    for count in reversed(trajectory):
        if count >= min_new:
            break
        dry_streak += 1
    open_gaps = list(dict.fromkeys(rounds[-1]["open_required_gaps"]))
    budget_reached = len(rounds) >= budget
    if budget_reached and open_gaps:
        decision = "AUTHOR_ACTION_REQUIRED"
        reason = "budget reached while required coverage gaps remain"
    elif budget_reached:
        decision = "STOP_BUDGET"
        reason = "configured search-round budget reached"
    elif dry_streak >= patience and open_gaps:
        decision = "CONTINUE_FOR_COVERAGE"
        reason = "yield is dry but required coverage gaps remain"
    elif dry_streak >= patience:
        decision = "STOP_SATURATED"
        reason = "matrix-changing yield stayed below the configured minimum for the configured patience"
    else:
        decision = "CONTINUE"
        reason = "neither the saturation nor budget stop is met"

    return {"decision": decision, "reason": reason, "rounds_completed": len(rounds),
            "budget": budget, "patience": patience, "min_new": min_new,
            "dry_streak": dry_streak, "trajectory": trajectory,
            "open_required_gaps": open_gaps, "coverage_note_required": True,
            "exhaustiveness_claim_allowed": False,
            "important_limit": "This stopping rule limits search effort; it does not prove exhaustive coverage or citation support."}


def search_progress(ledger, output, budget, patience, min_new):
    out = Path(output)
    if out.exists():
        raise FileExistsError("Use a new output path to preserve previous progress decisions")
    payload = read(ledger)
    result = assess_search_progress(payload.get("rounds") if isinstance(payload, dict) else None,
                                    budget, patience, min_new)
    write(out, result)
    return result


def assess_seed_coverage(payload):
    """Audit known-study retrieval and declared citation-chain channels.

    The caller decides which chain directions are required. This function
    validates the ledger and distinguishes a successful zero-hit query from a
    failed or missing query; it does not search, screen, or prove exhaustiveness.
    """
    if not isinstance(payload, dict):
        raise ValueError("seed coverage ledger must be an object")
    if "required_chain_directions" not in payload:
        raise ValueError("required_chain_directions must be explicit, including []")
    required_directions = payload["required_chain_directions"]
    allowed_directions = {"backward", "forward"}
    if (not isinstance(required_directions, list)
            or any(direction not in allowed_directions for direction in required_directions)
            or len(required_directions) != len(set(required_directions))):
        raise ValueError("required_chain_directions must be a unique array of backward/forward")

    seeds = payload.get("seeds")
    if not isinstance(seeds, list) or not seeds:
        raise ValueError("seeds must be a non-empty array")
    allowed_identity = {"VERIFIED", "MISMATCH", "UNRESOLVED", "RETRACTED"}
    allowed_search = {"FOUND", "NOT_FOUND", "FAILED"}
    seed_ids = set()
    for index, seed in enumerate(seeds):
        if not isinstance(seed, dict):
            raise ValueError(f"seed {index} must be an object")
        ident = seed.get("id")
        if not isinstance(ident, str) or not ident.strip():
            raise ValueError(f"seed {index} needs a non-empty id")
        if ident in seed_ids:
            raise ValueError("duplicate seed id: " + ident)
        seed_ids.add(ident)
        if seed.get("identity_status") not in allowed_identity:
            raise ValueError(f"seed {ident} has an invalid identity_status")
        if seed.get("search_status") not in allowed_search:
            raise ValueError(f"seed {ident} has an invalid search_status")
        if not isinstance(seed.get("locator"), str) or not seed["locator"].strip():
            raise ValueError(f"seed {ident} needs a DOI, PMID, title or other locator")

    chains = payload.get("citation_chains")
    if not isinstance(chains, list):
        raise ValueError("citation_chains must be an array")
    allowed_chain_status = {"COMPLETE", "ZERO_HITS", "FAILED"}
    by_channel = {}
    for index, chain in enumerate(chains):
        if not isinstance(chain, dict):
            raise ValueError(f"citation chain {index} must be an object")
        seed_id = chain.get("seed_id")
        direction = chain.get("direction")
        status = chain.get("status")
        count = chain.get("new_deduped_records")
        if seed_id not in seed_ids:
            raise ValueError(f"citation chain {index} references an unknown seed")
        if direction not in allowed_directions:
            raise ValueError(f"citation chain {index} has an invalid direction")
        if status not in allowed_chain_status:
            raise ValueError(f"citation chain {index} has an invalid status")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"citation chain {index} needs a non-negative integer count")
        if status == "ZERO_HITS" and count != 0:
            raise ValueError("ZERO_HITS cannot report new records")
        if not isinstance(chain.get("source"), str) or not chain["source"].strip():
            raise ValueError(f"citation chain {index} needs a source")
        key = (seed_id, direction)
        if key in by_channel:
            raise ValueError(f"duplicate citation-chain channel: {seed_id}/{direction}")
        by_channel[key] = chain

    verified_found = [seed["id"] for seed in seeds
                      if seed["identity_status"] == "VERIFIED" and seed["search_status"] == "FOUND"]
    missing_verified = [seed["id"] for seed in seeds
                        if seed["identity_status"] == "VERIFIED" and seed["search_status"] == "NOT_FOUND"]
    failed_seed_searches = [seed["id"] for seed in seeds if seed["search_status"] == "FAILED"]
    identity_review = [seed["id"] for seed in seeds if seed["identity_status"] != "VERIFIED"]

    failed_channels = []
    zero_hit_channels = []
    for (seed_id, direction), chain in by_channel.items():
        item = {"seed_id": seed_id, "direction": direction}
        if chain["status"] == "FAILED":
            failed_channels.append(item)
        elif chain["status"] == "ZERO_HITS":
            zero_hit_channels.append(item)

    missing_required = []
    for seed_id in verified_found:
        for direction in required_directions:
            if (seed_id, direction) not in by_channel:
                missing_required.append({"seed_id": seed_id, "direction": direction})

    if failed_seed_searches or failed_channels:
        decision = "AUTHOR_ACTION_REQUIRED"
        reason = "one or more declared retrieval channels failed; retry, replace the source, or record an accepted limit"
    elif identity_review:
        decision = "IDENTITY_REVIEW_REQUIRED"
        reason = "one or more seeds are not identity-verified"
    elif missing_verified:
        decision = "SEARCH_GAP"
        reason = "the search did not retrieve one or more verified seed studies"
    elif missing_required:
        decision = "CONTINUE"
        reason = "a project-required citation-chain direction has not been audited"
    else:
        decision = "PASS"
        reason = "verified seeds were found and every declared required chain channel has a visible outcome"

    return {
        "decision": decision,
        "reason": reason,
        "scope": "seed_and_declared_citation_chain_audit",
        "covered_verified_seeds": verified_found,
        "missing_verified_seeds": missing_verified,
        "failed_seed_searches": failed_seed_searches,
        "identity_review_seeds": identity_review,
        "failed_channels": failed_channels,
        "zero_hit_channels": zero_hit_channels,
        "missing_required_channels": missing_required,
        "required_chain_directions": required_directions,
        "exhaustiveness_claim_allowed": False,
        "important_limit": "Seed recovery and declared citation-chain checks are sensitivity diagnostics; they do not prove exhaustive literature coverage or citation support.",
    }


def seed_coverage(ledger, output):
    out = Path(output)
    if out.exists():
        raise FileExistsError("Use a new output path to preserve previous seed-coverage decisions")
    result = assess_seed_coverage(read(ledger))
    write(out, result)
    return result


def init_project(target, domain, kind):
    target = Path(target)
    if (target / "project.json").exists():
        raise FileExistsError("Project already exists; no overwrite performed")
    config = read(domain)
    for directory in ("inputs", "evidence", "analysis", "figures", "manuscript", "audit", "private-corpus"):
        (target / directory).mkdir(parents=True, exist_ok=True)
    write(target / "domain.json", config)
    write(target / "project.json", {"version": VERSION, "kind": kind, "domain_id": config["id"],
          "created_at": utc(), "journal": None, "research_question": None,
          "stage": "scope", "completed_stages": {}, "status": "needs_inputs"})
    return {"project": str(target), "status": "needs_inputs"}


def checkpoint(project, stage, inputs, outputs):
    root = Path(project)
    state = read(root / "project.json")
    if not inputs or not outputs:
        raise ValueError("A checkpoint needs input and output artifacts")
    snapshots = {}
    for name in inputs + outputs:
        path = safe_path(root, name)
        if not path.is_file():
            raise ValueError("Missing artifact: " + name)
        snapshots[name] = sha(path)
    entry = {"at": utc(), "inputs": inputs, "outputs": outputs, "hashes": snapshots,
             "status": "artifacts_recorded_not_scientifically_validated"}
    state["completed_stages"][stage] = entry
    write(root / "project.json", state)
    with (root / "audit" / "checkpoints.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"stage": stage, **entry}, ensure_ascii=False) + "\n")
    return entry


def check_project(project):
    root = Path(project)
    state = read(root / "project.json")
    invalid = []
    for stage, entry in state["completed_stages"].items():
        for name, expected in entry["hashes"].items():
            p = safe_path(root, name)
            if not p.is_file() or sha(p) != expected:
                invalid.append({"stage": stage, "changed_artifact": name})
    # Propagate invalidation when downstream stages consume an invalid stage's outputs.
    bad_stages = {x["stage"] for x in invalid}
    changed = True
    while changed:
        changed = False
        bad_outputs = {f for s in bad_stages for f in state["completed_stages"][s]["outputs"]}
        for stage, entry in state["completed_stages"].items():
            if stage not in bad_stages and bad_outputs.intersection(entry["inputs"]):
                bad_stages.add(stage)
                invalid.append({"stage": stage, "reason": "upstream_stage_invalid"})
                changed = True
    return {"status": "stale" if invalid else "hashes_current", "scientific_validation": "not_implied",
            "invalidated": invalid}


def validate_changes(changes, evidence):
    """Check evidence contracts; entailment and non-defensive writing require human/agent review."""
    if not isinstance(changes, list) or not isinstance(evidence, list):
        raise ValueError("Expected two arrays")
    sources = {x["id"]: x for x in evidence}
    if len(sources) != len(evidence):
        raise ValueError("Duplicate evidence IDs")
    allowed = {"comparison", "method_basis", "mechanism_constraint", "context", "correction"}
    errors = []
    for n, change in enumerate(changes):
        label = change.get("id", str(n))
        if change.get("decision") != "accept":
            continue
        for key in ("location", "before", "after", "contribution", "reason", "claim_level", "evidence_ids"):
            if key not in change or (key != "before" and not change[key]):
                errors.append(f"{label}: missing {key}")
        if change.get("contribution") not in allowed:
            errors.append(f"{label}: no substantive contribution category")
        if change.get("claim_level") not in {"observation", "association", "inference", "bibliographic"}:
            errors.append(f"{label}: invalid claim level")
        for ident in change.get("evidence_ids", []):
            source = sources.get(ident)
            if not source:
                errors.append(f"{label}: unknown evidence {ident}")
                continue
            if not source.get("locator") or not source.get("source"):
                errors.append(f"{label}: evidence lacks source/locator")
            level = source.get("evidence_level")
            required = {"full_text", "project_result"}
            if change.get("claim_level") == "bibliographic":
                required.add("metadata_only")
            if level not in required:
                errors.append(f"{label}: insufficient evidence level {level}")
        if change.get("semantic_review") != "passed":
            errors.append(f"{label}: source-to-claim semantic review missing")
    return {"status": "fail" if errors else "contract_pass", "errors": errors,
            "scope": "contract_check_only; does not itself verify entailment or authenticity"}


def compile_journal(cards, journal, article_type, minimum=20):
    """Compile audited paper cards, not PDFs: leave-held-out groups out of all rule counts."""
    if minimum < 2:
        raise ValueError("minimum must be at least two")
    ids, by_group, training, heldout = set(), {}, [], []
    for card in cards:
        ident = card["id"]
        if ident in ids:
            raise ValueError("Duplicate paper ID; merge versions first")
        ids.add(ident)
        if card["journal"] != journal or card["article_type"] != article_type:
            raise ValueError("Journal/article type mismatch: " + ident)
        if card.get("split") not in {"train", "heldout"}:
            raise ValueError("Unknown split")
        group = card["author_group"]
        if not group:
            raise ValueError("Missing independent author group")
        if group in by_group and by_group[group] != card["split"]:
            raise ValueError("Author-group leakage across train/heldout")
        by_group[group] = card["split"]
        if card.get("full_text_read") is not True or card.get("visual_checked") is not True:
            raise ValueError("Unread text or unreviewed layout: " + ident)
        if not card.get("source") or not card.get("sha256") or not card.get("metadata_verified"):
            raise ValueError("Missing source, hash or metadata verification")
        (training if card["split"] == "train" else heldout).append(card)
    if len(training) < minimum or len({c["author_group"] for c in training}) < 3 or not heldout:
        raise ValueError("Insufficient training papers/groups or no held-out group")
    patterns = {}
    for card in training:
        for p in card.get("patterns", []):
            if not p.get("locator") or not p.get("description") or not p.get("id"):
                raise ValueError("Pattern must retain description and page/section locator")
            row = patterns.setdefault(p["id"], {"description": p["description"], "papers": set(), "groups": set(), "evidence": []})
            if row["description"] != p["description"]:
                raise ValueError("Pattern ID has conflicting definitions; reconcile before compile")
            row["papers"].add(card["id"])
            row["groups"].add(card["author_group"])
            row["evidence"].append({"paper": card["id"], "locator": p["locator"]})
    learned = []
    for ident, p in patterns.items():
        learned.append({"id": ident, "description": p["description"], "support_papers": len(p["papers"]),
                        "support_groups": len(p["groups"]), "train_denominator": len(training),
                        "evidence": p["evidence"], "kind": "observed_tendency_not_journal_requirement"})
    return {"journal": journal, "article_type": article_type, "status": "draft_needs_heldout_evaluation",
            "minimum_is_engineering_setting_not_journal_rule": minimum,
            "training_ids": [c["id"] for c in training], "heldout_ids": [c["id"] for c in heldout],
            "rules": learned, "official_rules": [], "created_at": utc()}


def overlap(text, source, n=12):
    if n < 5:
        raise ValueError("Use n >= 5; overlap flags require manual review")
    a, b = re.findall(r"[\w'-]+", text.lower()), re.findall(r"[\w'-]+", source.lower())
    spans = {tuple(b[i:i+n]) for i in range(max(0, len(b)-n+1))}
    return sorted({" ".join(a[i:i+n]) for i in range(max(0, len(a)-n+1)) if tuple(a[i:i+n]) in spans})


def package(output):
    """Allowlisted source-only build. No user corpora, runs, vendor downloads or credentials."""
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError("Package exists; choose a new output path")
    output.parent.mkdir(parents=True, exist_ok=True)
    allow_dirs = {"scripts", "modules", "domains", "config", "docs", "tests"}
    allow_files = {"SKILL.md", "README.md", "LICENSE", "requirements.txt", ".gitignore"}
    files = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if p.is_symlink() or not p.is_file() or p.suffix not in {".md", ".py", ".json", ".txt"} and p.name not in allow_files:
            continue
        if "__pycache__" in rel.parts or not (rel.parts[0] in allow_dirs or str(rel) in allow_files):
            continue
        files.append((p, rel))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p, rel in files:
            info = zipfile.ZipInfo("research-mother/" + rel.as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, p.read_bytes())
    return {"file": str(output), "sha256": sha(output), "files": len(files), "bytes": output.stat().st_size}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    init = sub.add_parser("init")
    init.add_argument("target"); init.add_argument("--domain", default=str(ROOT / "domains/example-domain/domain.json"))
    init.add_argument("--kind", choices=["original", "review"], default="original")
    s = sub.add_parser("search")
    s.add_argument("--query", required=True); s.add_argument("--since", required=True)
    s.add_argument("--until", default=dt.date.today().isoformat()); s.add_argument("--out", required=True)
    s.add_argument("--pages", type=int, default=2); s.add_argument("--rows", type=int, default=50)
    s.add_argument("--mode", choices=["published", "indexed"], default="published")
    sp = sub.add_parser("search-progress")
    sp.add_argument("--ledger", required=True)
    sp.add_argument("--out", required=True)
    sp.add_argument("--budget", type=int, required=True)
    sp.add_argument("--patience", type=int, required=True)
    sp.add_argument("--min-new", type=int, required=True)
    sc = sub.add_parser("seed-coverage")
    sc.add_argument("--ledger", required=True)
    sc.add_argument("--out", required=True)
    ch = sub.add_parser("checkpoint"); ch.add_argument("project"); ch.add_argument("stage")
    ch.add_argument("--inputs", nargs="+", required=True); ch.add_argument("--outputs", nargs="+", required=True)
    check = sub.add_parser("check"); check.add_argument("project")
    vc = sub.add_parser("check-changes"); vc.add_argument("changes"); vc.add_argument("evidence")
    j = sub.add_parser("journal"); j.add_argument("cards"); j.add_argument("--journal", required=True)
    j.add_argument("--article-type", required=True); j.add_argument("--minimum", type=int, default=20)
    j.add_argument("--out", required=True)
    ov = sub.add_parser("overlap"); ov.add_argument("draft"); ov.add_argument("source")
    pk = sub.add_parser("package"); pk.add_argument("output")
    args = p.parse_args(argv)
    try:
        if args.command == "doctor":
            import importlib.util
            result = {"version": VERSION, "python": sys.version.split()[0],
                      "pypdf_available": importlib.util.find_spec("pypdf") is not None,
                      "network": "not_tested", "gpt_installation": "not_verifiable_from_local_files",
                      "upstream_status": "see config/upstream.lock.json; registration_is_not_installation"}
        elif args.command == "init": result = init_project(args.target, args.domain, args.kind)
        elif args.command == "search":
            result = search(args.query, args.since, args.until, args.out, args.pages, args.rows, args.mode)
        elif args.command == "search-progress":
            result = search_progress(args.ledger, args.out, args.budget, args.patience, args.min_new)
        elif args.command == "seed-coverage":
            result = seed_coverage(args.ledger, args.out)
        elif args.command == "checkpoint": result = checkpoint(args.project, args.stage, args.inputs, args.outputs)
        elif args.command == "check": result = check_project(args.project)
        elif args.command == "check-changes": result = validate_changes(read(args.changes), read(args.evidence))
        elif args.command == "journal":
            result = compile_journal(read(args.cards), args.journal, args.article_type, args.minimum)
            write(args.out, result)
        elif args.command == "overlap":
            result = {"review_flags": overlap(Path(args.draft).read_text(encoding="utf-8"), Path(args.source).read_text(encoding="utf-8")),
                      "scope": "lexical_overlap_only_not_plagiarism_or_AI_detection"}
        else: result = package(args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get("status") in {"fail", "stale", "error"} else 0
    except Exception as exc:
        print(json.dumps({"status": "error", "type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
