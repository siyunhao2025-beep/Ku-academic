#!/usr/bin/env python3
"""Build an explicit, reproducible Skill distribution; no private data or vendor archives."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.4.0"
ASSET = "Cool-Academic-v%s-skill.zip" % VERSION


def source_files(root: Path = ROOT) -> list[tuple[str, Path]]:
    entries = json.loads((root / "config/distribution-files.json").read_text(encoding="utf-8"))["files"]
    if len(entries) != len(set(entries)):
        raise ValueError("Distribution manifest contains duplicates")
    files = []
    for name in sorted(entries):
        rel = PurePosixPath(name)
        if not name or rel.is_absolute() or ".." in rel.parts or "\\" in name:
            raise ValueError(f"Unsafe distribution path: {name}")
        path = root.joinpath(*rel.parts)
        if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError(f"Missing file or symlink in distribution: {name}")
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Distribution path leaves root: {name}")
        files.append((name, path))
    return files


def build(output: Path, root: Path = ROOT) -> dict:
    output = Path(output)
    targets = [output / n for n in (ASSET, "SHA256SUMS.txt", "build.json")]
    if any(p.exists() for p in targets):
        raise FileExistsError("Distribution output already exists; choose a new directory")
    files = source_files(root)
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(targets[0], "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in files:
            info = zipfile.ZipInfo("research-mother/" + name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    checksum = hashlib.sha256(targets[0].read_bytes()).hexdigest()
    targets[1].write_text(f"{checksum}  {ASSET}\n", encoding="utf-8")
    result = {"asset": ASSET, "sha256": checksum, "files": len(files),
              "bytes": targets[0].stat().st_size, "skill_id": "research-mother",
              "version": VERSION, "scope": "source_and_documentation_only"}
    targets[2].write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("dist"))
    args = parser.parse_args(argv)
    try:
        print(json.dumps(build(args.out), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
