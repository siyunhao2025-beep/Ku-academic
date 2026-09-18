#!/usr/bin/env python3
"""Read-only local dependency and optional CLI capability checks. No auth or writes."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
CAPABILITIES = {
    "+create": ("--slide ", "--as "),
    "+add-slide": ("--slide ", "--presentation ", "--as "),
    "+xml-get": ("--raw", "--slide-id", "--presentation"),
    "+screenshot": ("--content", "--presentation"),
    "+replace-slide": ("--parts", "--revision-id", "--as "),
    "+update-slide": ("--content", "--revision-id", "--as "),
}


def inspect_environment(check_cli=False, schema=None, cli="lark-cli"):
    checks = []

    def add(name, ok, message):
        checks.append({"name": name, "status": "passed" if ok else "failed", "message": message})

    add("python", sys.version_info >= (3, 10), sys.version.split()[0] + "; requires >=3.10")
    for package in ("PyYAML", "lxml"):
        try:
            version = importlib.metadata.version(package)
            major = int(version.split(".")[0])
            supported = major == 6 if package == "PyYAML" else 5 <= major < 7
            add(package, supported, version)
        except (importlib.metadata.PackageNotFoundError, ValueError):
            add(package, False, "Install requirements.txt with the same Python interpreter")
    for path in ("tokens.yaml", "templates/INDEX.md", "templates/fields.json", "assets/cherry-logo.png"):
        add(path, (ROOT / path).is_file(), str(ROOT / path))
    try:
        from sml import load_tokens
        load_tokens()
        add("theme_config", True, "Theme configuration is valid")
    except (ImportError, ValueError, OSError) as exc:
        add("theme_config", False, str(exc))

    schema_status = "not_checked"
    if schema:
        try:
            from lxml import etree
            parser = etree.XMLParser(resolve_entities=False, no_network=True)
            etree.XMLSchema(etree.parse(str(schema), parser))
            schema_status = "available"
            add("schema", True, str(Path(schema).resolve()))
        except Exception as exc:
            schema_status = "failed"
            add("schema", False, str(exc))

    cli_version = None
    if check_cli:
        executable = shutil.which(cli)
        add("cli_executable", executable is not None, executable or f"{cli} not found")
        if executable:
            commands = [("version", ["--version"], ())]
            commands += [(name, ["slides", name, "--help"], flags) for name, flags in CAPABILITIES.items()]
            for name, args, flags in commands:
                try:
                    result = subprocess.run([executable, *args], capture_output=True, text=True, timeout=15)
                    output = result.stdout + result.stderr
                    missing = [flag.strip() for flag in flags if flag not in output]
                    ok = result.returncode == 0 and not missing
                    if name == "version" and ok:
                        cli_version = output.strip()
                    add("cli:" + name, ok, ("missing flags: " + ", ".join(missing)) if missing else
                        (output.strip()[:300] if name == "version" or not ok else "Required flags available"))
                except (OSError, subprocess.TimeoutExpired) as exc:
                    add("cli:" + name, False, str(exc))
    return {
        "status": "passed" if all(c["status"] == "passed" for c in checks) else "failed",
        "checks": checks,
        "schema": schema_status,
        "cli": {"checked": check_cli, "version": cli_version, "authentication_checked": False,
                "live_render_or_write_tested": False},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-cli", action="store_true", help="Run only --version/--help probes")
    parser.add_argument("--cli", default="lark-cli", help="CLI executable name or path")
    parser.add_argument("--schema", type=Path, help="Optional official SML XSD path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = inspect_environment(args.check_cli, args.schema, args.cli)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for check in report["checks"]:
            print(f"[{check['status']}] {check['name']}: {check['message']}")
        print("CLI probes do not verify authentication, live rendering or write behavior.")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
