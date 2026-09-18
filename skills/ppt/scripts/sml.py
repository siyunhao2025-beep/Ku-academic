"""Shared SML parsing, theme configuration and validator reporting helpers.

This is a local structural check, not an implementation of the complete Lark
schema or a font renderer. Namespaces are compared by local name throughout.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TOKENS = ROOT / "tokens.yaml"


class TokenError(ValueError):
    """The selected theme cannot be read or is internally inconsistent."""


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1]


def children(element, name):
    return [child for child in element if local_name(child.tag) == name]


def child(element, name):
    return next((item for item in element if local_name(item.tag) == name), None)


def descendants(element, name):
    return (item for item in element.iter() if local_name(item.tag) == name)


def element_paths(root):
    paths = {root: "/" + local_name(root.tag)}

    def visit(parent):
        counts = {}
        for item in parent:
            name = local_name(item.tag)
            counts[name] = counts.get(name, 0) + 1
            paths[item] = f"{paths[parent]}/{name}[{counts[name]}]"
            visit(item)

    visit(root)
    return paths


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Non-finite number: {value}")
    return result


MAX_EXPANDED_TABLE_COLUMNS = 4096  # Local tool resource budget, not an SML limit.


class TableColumnSpanError(ValueError):
    """A column definition cannot describe a finite whole number of columns."""

    def __init__(self, column, message=None, code="invalid_table_column_span"):
        self.column = column
        self.code = code
        super().__init__(message or f"Column span must be a finite positive whole number: {column.get('span')!r}")


def expanded_table_columns(table):
    """Expand col span, retaining each logical column's original definition.

    SML declares span as PositiveSize (xs:double), so integral numeric forms
    such as 3.0 and 3e0 are valid counts. Fractional columns have no geometry.
    Width defaults/validation stay with the caller. Expansion is capped at the
    local resource budget above, independently of SML schema validity.
    """
    group = child(table, "colgroup")
    columns = []
    for column in children(group, "col") if group is not None else []:
        try:
            raw = column.get("span", "1").strip()
            if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", raw):
                raise ValueError("Not an SML numeric value")
            span = number(raw)
            if span <= 0 or not span.is_integer():
                raise ValueError("Not a positive whole number")
        except ValueError as exc:
            raise TableColumnSpanError(column) from exc
        if span > MAX_EXPANDED_TABLE_COLUMNS - len(columns):
            raise TableColumnSpanError(
                column,
                f"Table exceeds the local expansion limit of {MAX_EXPANDED_TABLE_COLUMNS} columns; "
                "this is a tool resource limit, not an SML schema restriction.",
                "table_column_limit_exceeded")
        columns.extend([column] * int(span))
    return columns


def color_tuple(value: str):
    """Parse RGB/RGBA/hex into an RGBA tuple; reject malformed/out-of-range values."""
    if not isinstance(value, str):
        raise ValueError("Color must be a string")
    value = value.strip().lower()
    value = {"transparent": "#00000000", "white": "#ffffff", "black": "#000000"}.get(value, value)
    if value.startswith("#"):
        digits = value[1:]
        if len(digits) in (3, 4):
            digits = "".join(ch * 2 for ch in digits)
        if len(digits) not in (6, 8) or not re.fullmatch(r"[0-9a-f]+", digits):
            raise ValueError(f"Invalid hex color: {value}")
        rgb = tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))
        alpha = int(digits[6:8], 16) / 255 if len(digits) == 8 else 1.0
    else:
        match = re.fullmatch(r"(rgba?)\s*\(([^()]*)\)", value)
        if match is None:
            raise ValueError(f"Unsupported or invalid color: {value}")
        parts = [part.strip() for part in match.group(2).split(",")]
        if len(parts) != (4 if match.group(1) == "rgba" else 3):
            raise ValueError(f"Invalid color channel count: {value}")
        rgb = tuple(number(part[:-1]) * 255 / 100 if part.endswith("%") else number(part) for part in parts[:3])
        alpha = (number(parts[3][:-1]) / 100 if parts[3].endswith("%") else number(parts[3])) if len(parts) == 4 else 1.0
    if any(channel < 0 or channel > 255 for channel in rgb) or not 0 <= alpha <= 1:
        raise ValueError(f"Color channel out of range: {value}")
    return (*rgb, alpha)


def normalize_color(value: str) -> str:
    return "rgba(" + ",".join(format(channel, ".8g") for channel in color_tuple(value)) + ")"


def load_tokens(path: Path | str | None = None) -> dict:
    """Read the entire selected theme. Never silently fall back to other rules."""
    path = Path(path) if path is not None else DEFAULT_TOKENS
    try:
        import yaml
    except ImportError as exc:
        raise TokenError("PyYAML is required; install the repository requirements.") from exc
    class UniqueKeyLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            keys = set()
            for key_node, _ in node.value:
                key = self.construct_object(key_node, deep=deep)
                try:
                    duplicate = key in keys
                    keys.add(key)
                except TypeError as exc:
                    raise yaml.constructor.ConstructorError(None, None, "Mapping key must be scalar", key_node.start_mark) from exc
                if duplicate:
                    raise yaml.constructor.ConstructorError(None, None, f"Duplicate key: {key}", key_node.start_mark)
            return super().construct_mapping(node, deep=deep)

    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise TokenError(f"Cannot load tokens {path}: {exc}") from exc
    try:
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise ValueError("schema_version must be 1")
        for name in ("colors", "font_sizes", "radii", "spacing", "components", "validation"):
            if not isinstance(data.get(name), dict) or not data[name]:
                raise ValueError(f"{name} must be a nonempty mapping")
        data = copy.deepcopy(data)
        palette = {}
        for name, entry in data["colors"].items():
            if not isinstance(name, str) or not isinstance(entry, dict) or "rgba" not in entry:
                raise ValueError(f"colors.{name} must define rgba")
            palette[name] = normalize_color(entry["rgba"])
            if "hex" in entry and normalize_color(entry["hex"]) != palette[name]:
                raise ValueError(f"colors.{name}: hex and rgba disagree")
        for section in ("font_sizes", "radii", "spacing"):
            for name, value in data[section].items():
                if isinstance(value, bool) or not isinstance(value, (int, float)) or number(value) < 0:
                    raise ValueError(f"{section}.{name} must be a nonnegative finite number")
        if not isinstance(data.get("accent_colors"), list) or any(name not in palette for name in data["accent_colors"]):
            raise ValueError("accent_colors must reference color names")
        rules = data["validation"]
        required = {"canvas", "min_font_size", "max_font_variants", "max_accent_colors", "page_background",
                    "forbid_dark_page", "forbid_dark_fills", "dark_luminance_threshold", "bottom_pill_bar"}
        if required - rules.keys():
            raise ValueError(f"validation missing required keys: {sorted(required - rules.keys())}")
        if not isinstance(rules.get("canvas"), dict):
            raise ValueError("validation.canvas must be a mapping")
        for name in ("width", "height"):
            if isinstance(rules["canvas"].get(name), bool) or number(rules["canvas"].get(name)) <= 0:
                raise ValueError(f"canvas.{name} must be positive")
        for name in ("min_font_size", "max_font_variants", "max_accent_colors"):
            if type(rules.get(name)) is not int or rules[name] <= 0:
                raise ValueError(f"validation.{name} must be a positive integer")
        if rules["min_font_size"] < 6:
            raise ValueError("validation.min_font_size must respect SML's minimum 6")
        for name, value in data["font_sizes"].items():
            if type(value) is not int or value < rules["min_font_size"]:
                raise ValueError(f"font_sizes.{name} must be an integer >= validation.min_font_size")
        for name in ("forbid_dark_page", "forbid_dark_fills"):
            if type(rules.get(name)) is not bool:
                raise ValueError(f"validation.{name} must be boolean")
        if rules.get("page_background") is not None and rules["page_background"] not in palette:
            raise ValueError("validation.page_background must be a color name or null")
        threshold = rules.get("dark_luminance_threshold")
        if isinstance(threshold, bool) or not 0 <= number(threshold) <= 255:
            raise ValueError("validation.dark_luminance_threshold must be between 0 and 255")
        pill = rules.get("bottom_pill_bar")
        if not isinstance(pill, dict) or type(pill.get("enabled")) is not bool:
            raise ValueError("validation.bottom_pill_bar must contain enabled:boolean")
        for name in ("min_y", "min_width", "max_height"):
            if isinstance(pill.get(name), bool) or number(pill.get(name)) < 0:
                raise ValueError(f"bottom_pill_bar.{name} must be nonnegative")
        if not isinstance(pill.get("colors"), list) or any(name not in palette for name in pill["colors"]):
            raise ValueError("bottom_pill_bar.colors must reference color names")
        for name, component in data["components"].items():
            if not isinstance(component, dict):
                raise ValueError(f"components.{name} must be a mapping")
            for field, value in component.items():
                if field in ("fill", "border", "text_color") and value not in palette:
                    raise ValueError(f"components.{name}.{field} must reference a color name")
                if field in ("width", "height", "radius", "font_size", "max_per_page", "max_width", "size", "y"):
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or number(value) < 0:
                        raise ValueError(f"components.{name}.{field} must be a nonnegative finite number")
        if "body" not in data["font_sizes"] or data["font_sizes"]["body"] < rules["min_font_size"]:
            raise ValueError("font_sizes.body must meet validation.min_font_size")
        data["allowed_colors"] = sorted(set(palette.values()))
        data["normalized_colors"] = palette
        data["normalized_accent_colors"] = [palette[name] for name in data["accent_colors"]]
        return data
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise TokenError(f"Invalid tokens {path}: {exc}") from exc


def make_issue(level, code, message, element=""):
    return {"level": level, "code": code, "message": str(message), "element": element}


def result(path, issues, compatibility=False):
    data = {"file": str(path), "issues": issues}
    if compatibility:
        data.update(errors=[item for item in issues if item["level"] == "error"],
                    warnings=[item for item in issues if item["level"] == "warning"])
    return data


def read_slide(path):
    try:
        source = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return None, [make_issue("error", "read_failed", f"Cannot read XML: {exc}")]
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        return None, [make_issue("error", "invalid_xml", f"XML parse failed: {exc}")]
    if local_name(root.tag) != "slide":
        return None, [make_issue("error", "invalid_root", "Expected a slide root element")]
    return root, []


def text_runs(element, inherited=None):
    """Yield (text, inherited attributes), preserving nested spans and their tails."""
    attrs = dict(inherited or {})
    attrs.update(element.attrib)
    if element.text:
        yield element.text, attrs
    for item in element:
        if local_name(item.tag) in ("br", "break"):
            yield "\n", attrs
        else:
            yield from text_runs(item, attrs)
        if item.tail:
            yield item.tail, attrs


def paragraph_runs(content):
    paragraphs = children(content, "p")
    if not paragraphs:
        return [(content, list(text_runs(content)))]
    return [(paragraph, list(text_runs(paragraph, content.attrib))) for paragraph in paragraphs]


def build_report(results, file_count=None):
    canonical = [{"file": item["file"], "issues": item["issues"]} for item in results]
    return {"summary": {"files": len(canonical) if file_count is None else file_count,
                        "errors": sum(issue["level"] == "error" for item in canonical for issue in item["issues"]),
                        "warnings": sum(issue["level"] == "warning" for item in canonical for issue in item["issues"])},
            "results": canonical}


def run_cli(review, description, argv=None):
    parser = argparse.ArgumentParser(description=description)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--input", type=Path, help="One XML slide")
    selection.add_argument("--dir", type=Path, help="All *.xml slides in a directory")
    parser.add_argument("--json", action="store_true", help="Print only the JSON report")
    parser.add_argument("--tokens", type=Path, help="Use an explicit theme YAML")
    parser.add_argument("--assets-dir", type=Path, help="Additional local image directory")
    parser.add_argument("--strict-warnings", action="store_true", help="Also fail on warnings")
    args = parser.parse_args(argv)
    files = [args.input] if args.input else sorted(args.dir.glob("*.xml")) if args.dir and args.dir.is_dir() else []
    if not files:
        report = build_report([result(args.dir or "", [make_issue("error", "no_input_files", "Select --input or an existing --dir containing *.xml files")])], 0)
    else:
        try:
            tokens = load_tokens(args.tokens)
        except TokenError as exc:
            report = build_report([result(path, [make_issue("error", "invalid_tokens", exc)]) for path in files])
        else:
            report = build_report([review(path, tokens=tokens, assets_dir=args.assets_dir) for path in files])
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in report["results"]:
            errors = sum(issue["level"] == "error" for issue in item["issues"])
            warnings = sum(issue["level"] == "warning" for issue in item["issues"])
            print(f"{Path(item['file']).name}: {errors} error(s), {warnings} warning(s)")
            for issue in item["issues"]:
                print(f"  [{issue['level']}] {issue['code']}: {issue['message']} {issue['element']}")
        print(json.dumps(report["summary"], ensure_ascii=False))
    return int(bool(report["summary"]["errors"] or (args.strict_warnings and report["summary"]["warnings"])))
