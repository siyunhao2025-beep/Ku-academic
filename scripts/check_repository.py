#!/usr/bin/env python3
"""Check distribution paths, UTF-8 documents and relative Markdown links."""
from __future__ import annotations
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
from build_distribution import ROOT, source_files

# Vendored third-party trees. Their content is preserved verbatim, so their links
# are not ours to repair: where a target is absent, the absence is declared in
# skills/ppt/MISSING_DEPENDENCIES.md instead of being silently rewritten here.
# Link validation is therefore skipped below these prefixes, on purpose.
VENDOR_PREFIXES = ("skills/",)
VENDOR_REQUIRED = ("skills/ppt/SKILL.md", "skills/ppt/MISSING_DEPENDENCIES.md")


def _is_vendor(name: str) -> bool:
    return name.startswith(VENDOR_PREFIXES)


def check(root: Path = ROOT) -> list[str]:
    errors = []
    try:
        files = source_files(root)
    except (OSError, ValueError, KeyError) as exc:
        return [str(exc)]
    names = {name for name, _ in files}
    required = {"SKILL.md", "README.md", "LICENSE", "requirements.txt", "START_WINDOWS.bat",
                "docs/GETTING_STARTED.md", "docs/USE_CASES.md", "modules/workflow.md"}
    required |= set(VENDOR_REQUIRED)
    errors.extend(f"Required distribution file missing: {name}" for name in sorted(required - names))
    for name, path in files:
        if path.suffix != ".md" or _is_vendor(name):
            continue
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", text):
            if urlsplit(target).scheme or target.startswith(("#", "//")):
                continue
            relative = unquote(target.split("#", 1)[0])
            if relative and not (path.parent / relative).exists():
                errors.append(f"{name}: missing linked path {target}")
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    if not skill.startswith("---\n") or "name: research-mother\n" not in skill:
        errors.append("Skill frontmatter or compatibility name changed")
    return errors


def main() -> int:
    errors = check()
    for error in errors:
        print(error, file=sys.stderr)
    print("Repository checks: " + ("FAIL" if errors else "PASS"))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
