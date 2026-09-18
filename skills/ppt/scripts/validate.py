#!/usr/bin/env python3
"""Unified local schema, layout and theme checks; never publishes a slide."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def issue(code, message, level="error", stage="schema"):
    return {"level": level, "code": code, "message": message, "stage": stage, "element": ""}


class SchemaCheck:
    """Validate slide fragments in the official presentation container, without rewriting input."""

    def __init__(self, path):
        from lxml import etree
        self.etree = etree
        self.path = Path(path)
        self.parser = etree.XMLParser(resolve_entities=False, no_network=True)
        self.document = etree.parse(str(self.path), self.parser)
        if self.document.docinfo.doctype:
            raise ValueError("DTD is not supported in schema files")
        self.schema = etree.XMLSchema(self.document)
        self.namespace = self.document.getroot().get("targetNamespace", "")
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def review(self, path, width=960, height=540):
        try:
            tree = self.etree.parse(str(path), self.parser)
            if tree.docinfo.doctype:
                return [issue("unsupported_doctype", "DTD/entity declarations are not supported")]
            root = tree.getroot()
            qname = self.etree.QName(root)
            if qname.localname == "slide" and qname.namespace == self.namespace:
                # SML declares slide inside presentation, not as a global XSD root.
                wrapper = self.etree.Element(f"{{{self.namespace}}}presentation",
                                            width=str(width), height=str(height))
                wrapper.append(root)
                tree = wrapper
            if self.schema.validate(tree):
                return []
            return [issue("schema_invalid", str(error)) for error in self.schema.error_log]
        except (OSError, self.etree.Error) as exc:
            return [issue("schema_input_invalid", str(exc))]


def run_checks(files, tokens_path=None, assets_dir=None, schema_path=None,
               require_schema=False, strict_warnings=False):
    from sml import load_tokens
    from review_layout import review_slide as layout_review
    from review_design import review_slide as design_review

    results = []
    global_issues = []
    tokens = None
    try:
        tokens = load_tokens(tokens_path)
    except (ValueError, OSError) as exc:
        global_issues.append(issue("invalid_tokens", str(exc), stage="configuration"))
    schema = None
    schema_state = "not_run"
    if schema_path:
        try:
            schema = SchemaCheck(schema_path)
        except Exception as exc:
            schema_state = "failed"
            global_issues.append(issue("schema_unavailable", str(exc)))
    elif require_schema:
        global_issues.append(issue("schema_required", "Supply --schema with an official SML XSD file"))
    if not files:
        global_issues.append(issue("no_inputs", "No XML input files found", stage="input"))

    if tokens:
        canvas = tokens["validation"]["canvas"]
        for path in files:
            issues = []
            if schema:
                schema_issues = schema.review(path, canvas["width"], canvas["height"])
                issues.extend(schema_issues)
                if schema_issues:
                    schema_state = "failed"
                elif schema_state == "not_run":
                    schema_state = "passed"
            for name, check in (("layout", layout_review), ("design", design_review)):
                try:
                    result = check(Path(path), tokens=tokens, assets_dir=assets_dir)
                    issues.extend({**item, "stage": name} for item in result["issues"])
                except (OSError, ValueError) as exc:
                    issues.append(issue("check_failed", str(exc), stage=name))
            results.append({"file": str(path), "issues": issues})
    all_issues = global_issues + [i for r in results for i in r["issues"]]
    errors = sum(i["level"] == "error" for i in all_issues)
    warnings = sum(i["level"] == "warning" for i in all_issues)
    blocked = bool(errors or (strict_warnings and warnings))
    status = "failed" if blocked else "incomplete" if schema_state == "not_run" else "needs_review" if warnings else "passed"
    return {
        "status": status,
        "summary": {"files": len(files), "errors": errors, "warnings": warnings},
        "schema": {"status": schema_state, "loaded": schema is not None, "path": str(schema_path) if schema_path else None,
                   "sha256": schema.sha256 if schema else None},
        "render_verified": False,
        "content_verified": False,
        "global_issues": global_issues,
        "results": results,
        "exit_code": 1 if blocked else 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, action="append", help="Repeat for explicit XML inputs")
    source.add_argument("--dir", type=Path, help="Checks all *.xml immediately inside directory")
    parser.add_argument("--tokens", type=Path)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--schema", type=Path, help="Official SML XSD, obtained from your installed CLI")
    parser.add_argument("--require-schema", action="store_true")
    parser.add_argument("--strict-warnings", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    files = args.input if args.input is not None else sorted(args.dir.glob("*.xml"))
    try:
        report = run_checks(files, args.tokens, args.assets_dir, args.schema,
                            args.require_schema, args.strict_warnings)
    except ImportError as exc:
        report = {"status": "failed", "summary": {"files": len(files), "errors": 1, "warnings": 0},
                  "global_issues": [issue("missing_dependency", str(exc), stage="configuration")],
                  "results": [], "exit_code": 1}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in report["global_issues"]:
            print(f"[{item['level']}] {item['code']}: {item['message']}")
        for result in report["results"]:
            print(result["file"])
            for item in result["issues"]:
                print(f"  [{item['level']}] {item['stage']}:{item['code']}: {item['message']}")
        print(json.dumps({k: v for k, v in report.items() if k not in {"results", "global_issues"}}, ensure_ascii=False))
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
