#!/usr/bin/env python3
"""Research Mother v0.1: auditable utilities; scientific judgements remain agent tasks."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0"


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
    p = (root / rel).resolve()
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
    init.add_argument("target"); init.add_argument("--domain", default=str(ROOT / "domains/space-weather-mlt/domain.json"))
    init.add_argument("--kind", choices=["original", "review"], default="original")
    s = sub.add_parser("search")
    s.add_argument("--query", required=True); s.add_argument("--since", required=True)
    s.add_argument("--until", default=dt.date.today().isoformat()); s.add_argument("--out", required=True)
    s.add_argument("--pages", type=int, default=2); s.add_argument("--rows", type=int, default=50)
    s.add_argument("--mode", choices=["published", "indexed"], default="published")
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
