#!/usr/bin/env python3
"""One-time import of pinned Research Mother sources. Never overwrite modified code."""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def install(data: bytes, root: Path = ROOT) -> dict:
    lock = json.loads((root / "config/migration-source.json").read_text(encoding="utf-8"))
    prefix = lock["repository"].split("/")[1] + "-" + lock["commit"] + "/" + lock["subdirectory"] + "/"
    planned = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name, expected in lock["files"].items():
            rel = PurePosixPath(name)
            if rel.is_absolute() or ".." in rel.parts or "\\" in name:
                raise ValueError("Unsafe source path")
            payload = archive.read(prefix + name)
            if hashlib.sha256(payload).hexdigest() != expected:
                raise ValueError("Source hash mismatch: " + name)
            target = root.joinpath(*rel.parts)
            if target.is_symlink() or any(p.is_symlink() for p in target.parents):
                raise ValueError("Symlink destination: " + name)
            if not target.resolve().is_relative_to(root.resolve()):
                raise ValueError("Destination leaves repository")
            if name in lock["preserve_destination"]:
                if not target.is_file():
                    raise ValueError("Expected standalone replacement is missing: " + name)
                continue
            if target.exists() and target.read_bytes() != payload:
                raise FileExistsError("Refusing to replace edited destination: " + name)
            planned.append((target, payload))
    for target, payload in planned:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(payload)
    report = {"source_repository": lock["repository"], "source_commit": lock["commit"],
              "source_files_verified": len(lock["files"]), "unchanged_source_files_present": len(planned),
              "standalone_replacements": lock["preserve_destination"],
              "scope": "byte_integrity_and_migration_only_not_research_validation"}
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs/MIGRATION_IMPORT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    lock = json.loads((ROOT / "config/migration-source.json").read_text(encoding="utf-8"))
    if lock["repository"] != "siyunhao2025-beep/math-modeling-to-sci-skill" or lock["commit"] != "3d044caf26d602ba08eddc93397b3923397b82bc":
        raise ValueError("Unexpected migration source; review this importer before changing it")
    url = f'https://codeload.github.com/{lock["repository"]}/zip/{lock["commit"]}'
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(10_000_001)
    if len(data) > 10_000_000:
        raise ValueError("Source archive exceeds 10 MB")
    print(json.dumps(install(data), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
