#!/usr/bin/env python3
"""Stage pinned upstream source archives without executing installers or registering GPT skills."""
from __future__ import annotations
import argparse
import io
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import urllib.request
import zipfile
from research import ROOT, read, sha, utc, write


def check_members(z):
    total = 0
    for item in z.infolist():
        path = PurePosixPath(item.filename)
        mode = item.external_attr >> 16
        if path.is_absolute() or ".." in path.parts or "\\" in item.filename or ":" in item.filename or stat.S_ISLNK(mode):
            raise ValueError("Unsafe archive member: " + item.filename)
        total += item.file_size
        if total > 1_000_000_000 or item.file_size > 100_000_000:
            raise ValueError("Expanded archive exceeds bounds: " + item.filename)
    return total


def stage(entry, target):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", entry["repository"]):
        raise ValueError("Invalid repository")
    if not re.fullmatch(r"[a-f0-9]{40}", entry["commit"]):
        raise ValueError("A full pinned commit is required")
    target = Path(target)
    if target.exists():
        raise FileExistsError("Already staged; preserve previous source")
    url = f'https://codeload.github.com/{entry["repository"]}/zip/{entry["commit"]}'
    req = urllib.request.Request(url, headers={"User-Agent": "ResearchMother/0.1"})
    with urllib.request.urlopen(req, timeout=60) as response:
        data = response.read(300_000_001)
    if len(data) > 300_000_000:
        raise ValueError("Archive exceeds 300 MB")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        check_members(z)
        target.mkdir(parents=True)
        # Archives remain zipped: even their instruction files are quarantined until review.
        (target / "source.zip").write_bytes(data)
        skills = [p for p in z.namelist() if p.endswith("/SKILL.md") or p.endswith("/paper-miner.md")]
    record = {**entry, "status": "source_staged_quarantined", "archive_sha256": sha(target / "source.zip"),
              "source_url": url, "at": utc(), "entrypoints_discovered": skills,
              "gpt_installed": False, "installers_executed": False}
    write(target / "status.json", record)
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    p.add_argument("--source", help="One registry ID; omit to stage all five")
    a = p.parse_args()
    entries = read(ROOT / "config/upstream.lock.json")["sources"]
    if a.source:
        entries = [x for x in entries if x["id"] == a.source]
        if not entries:
            p.error("Unknown source ID")
    rows = []
    for entry in entries:
        try:
            rows.append(stage(entry, Path(a.out) / entry["id"] / entry["commit"]))
        except Exception as exc:
            rows.append({"id": entry["id"], "status": "failed", "error_type": type(exc).__name__, "error": str(exc)})
    write(Path(a.out) / "stage-report.json", rows)
    print("Source staging only; GPT account installation is a separate host action.")
    for row in rows:
        print(row["id"], row["status"], row.get("error", ""))
    return 2 if any(r["status"] == "failed" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
