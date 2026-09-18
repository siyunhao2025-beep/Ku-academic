#!/usr/bin/env python3
"""Index template fields and prepare explicit, local-only XML working copies.

Paths use expanded XML names and sibling indexes, so namespace prefixes and
repeated table cells cannot accidentally target a different field. Bindings are
bound to a source hash; this is an editing helper, not a publication validator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1


def local(tag):
    return tag.rsplit("}", 1)[-1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def walk(root):
    """Yield each node, its namespace-aware path and its ancestors."""
    def visit(node, path, ancestors):
        yield node, path, ancestors
        counts = {}
        for child in node:
            counts[child.tag] = counts.get(child.tag, 0) + 1
            yield from visit(child, path + [{"tag": child.tag, "index": counts[child.tag]}], ancestors + [node])
    yield from visit(root, [], [])


def resolve(root, path):
    node = root
    for step in path:
        matches = [child for child in node if child.tag == step["tag"]]
        node = matches[step["index"] - 1]
    return node


def number(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def text_role(text, ancestors):
    shape = next((n for n in reversed(ancestors) if local(n.tag) == "shape"), None)
    if text.strip() == "Cherry Studio":
        return "brand", False
    if "Internal Template" in text or "[替换" in text or "占位" in text:
        return "template_annotation", True
    if shape is not None:
        y, x = number(shape.get("topLeftY")), number(shape.get("topLeftX"))
        if y >= 500 and x >= 800 and text.strip().isdigit():
            return "page_number", True
        if y >= 500:
            return "footer", True
        if y < 55:
            return "header_annotation", True
        content = next((n for n in ancestors if local(n.tag) == "content"), None)
        if content is not None and number(content.get("fontSize")) >= 24:
            # Large values in the content area are metrics, while the same
            # number in the page's title area may genuinely be its heading.
            numeric_value = re.fullmatch(
                r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
                r"(?:%|％|×|[xXkKmMbB]|ms|s|h|天|小时|分钟|秒|个|项|万|亿)?",
                text.strip(),
            )
            if y >= 166 and numeric_value:
                return "metric_value", True
            return "title", True
    if any(local(n.tag) == "td" for n in ancestors):
        return "table_cell", True
    if "@" in text:
        return "contact", True
    return "body", True


def text_capacity(ancestors):
    shape = next((n for n in reversed(ancestors) if local(n.tag) in {"shape", "td"}), None)
    content = next((n for n in reversed(ancestors) if local(n.tag) == "content"), None)
    if shape is None or content is None:
        return None
    width, size = number(shape.get("width")), number(content.get("fontSize"))
    if width <= 0 or size <= 0:
        return None
    return {"estimated_cjk_chars_per_line": max(1, int(width / size)),
            "advisory": "Approximation only; edit, split or select another layout, then run layout checks and review a screenshot."}


def index_template(path):
    root = ET.parse(path).getroot()
    if local(root.tag) != "slide":
        raise ValueError(f"Expected one slide XML template: {path}")
    fields = []
    counts = {}

    def add(kind, node_path, example, role, required, **extra):
        counts[kind] = counts.get(kind, 0) + 1
        fields.append({"id": f"{kind}_{counts[kind]:04d}", "kind": kind,
                       "path": node_path, "example": example, "role": role,
                       "required": required, **extra})

    for node, node_path, ancestors in walk(root):
        tag = local(node.tag)
        if tag == "p":
            text = "".join(node.itertext())
            role, required = text_role(text, ancestors)
            add("text", node_path, text, role, required,
                rich_text=bool(list(node)), capacity_hint=text_capacity(ancestors))
        elif tag == "chartField":
            add("chart_data", node_path, "".join(node.itertext()), "chart_data", True,
                value_type=node.get("valueType", "string"))
            if "name" in node.attrib:
                add("chart_name", node_path, node.get("name"), "chart_series_name", True, attribute="name")
        elif tag == "img":
            src = node.get("src", "")
            brand = Path(src).name == "cherry-logo.png"
            add("image", node_path, src, "brand_asset" if brand else "image", not brand, attribute="src")
    return {"id": path.stem, "file": path.name, "source_sha256": digest(path),
            "root_tag": root.tag, "field_count": len(fields), "fields": fields}


def build_index(directory):
    directory = Path(directory).resolve()
    files = sorted(directory.glob("slide*.xml"))
    if not files:
        raise ValueError(f"No slide*.xml templates found in {directory}")
    return {"schema_version": SCHEMA_VERSION, "path_format": "expanded_tag_and_one_based_sibling_index",
            "template_count": len(files), "templates": [index_template(p) for p in files]}


def draft_bindings(template, output_name=None):
    return {"schema_version": SCHEMA_VERSION, "template": template["id"],
            "output_name": output_name,
            "source_sha256": template["source_sha256"],
            "instructions": "Fill values by field id. Null means unfinished. Optional brand fields may be omitted; page numbers must be filled or confirmed for this deck. To intentionally use an unchanged true value, supply {\"value\": ..., \"confirmed\": true}. Text replaces a whole paragraph and preserves paragraph attributes, not individual span styling. Local image paths start with @ and are resolved relative to this bindings file. No network fetching occurs.",
            "values": {f["id"]: None for f in template["fields"] if f["required"]},
            "fields": template["fields"]}


def binding_value(raw, field):
    confirmed = False
    if isinstance(raw, dict):
        if set(raw) - {"value", "confirmed"} or "value" not in raw:
            raise ValueError(f"{field['id']}: expected value and optional confirmed")
        confirmed = raw.get("confirmed") is True
        raw = raw["value"]
    if raw is None:
        return None, confirmed
    if field["kind"] == "chart_data" and isinstance(raw, list):
        if not raw or any(isinstance(x, (list, dict, bool)) or x is None or "," in str(x) for x in raw):
            raise ValueError(f"{field['id']}: chart data must be a nonempty list of scalar values without commas")
        raw = ",".join(str(x) for x in raw)
    if not isinstance(raw, str):
        raise ValueError(f"{field['id']}: expected a string (chart data also accepts arrays)")
    if not raw.strip():
        raise ValueError(f"{field['id']}: blank values are not complete content; remove the unused XML element deliberately")
    if field["kind"] == "chart_data":
        parts = [p.strip() for p in raw.split(",")]
        if any(not part for part in parts):
            raise ValueError(f"{field['id']}: chart data contains an empty value")
        if field.get("value_type") == "number":
            try:
                valid = all(math.isfinite(float(p)) for p in parts)
            except ValueError:
                valid = False
            if not valid:
                raise ValueError(f"{field['id']}: numeric chart data must contain finite numbers")
    return raw, confirmed


def find_asset(src, search_dirs):
    relative = Path(src[1:])
    if relative.is_absolute():
        candidate = relative.resolve()
        if candidate.is_file():
            return candidate
    else:
        for directory in search_dirs:
            candidate = (directory / relative).resolve()
            if candidate.is_file():
                return candidate
    raise ValueError(f"Local image does not exist: {src}")


def prepare(args):
    output_name = getattr(args, "name", None)
    if output_name is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", output_name):
        raise ValueError("--name must be a safe filename stem containing letters, digits, underscores or hyphens; no path separators or dots")
    output = Path(args.output_dir).resolve()
    index_path = Path(args.index).resolve()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported fields index schema version; rebuild the index")
    template_id = Path(args.template).stem
    matches = [t for t in index["templates"] if t["id"] == template_id]
    if len(matches) != 1:
        raise ValueError(f"Template not found or duplicated in index: {template_id}")
    template = matches[0]
    template_path = (Path(args.templates_dir).resolve() if args.templates_dir else index_path.parent) / template["file"]
    if digest(template_path) != template["source_sha256"]:
        raise ValueError("Stale fields index: template source hash differs; rebuild index and review bindings")
    # Check the actual paths/roles too, not only the stored source hash.
    if index_template(template_path) != template:
        raise ValueError("Stale or altered fields index: rebuild the index")
    values, binding_dir = {}, Path.cwd()
    if args.bindings:
        binding_path = Path(args.bindings).resolve()
        binding_dir = binding_path.parent
        bindings = json.loads(binding_path.read_text(encoding="utf-8"))
        if bindings.get("template") != template_id or bindings.get("source_sha256") != template["source_sha256"]:
            raise ValueError("Bindings template/source_sha256 mismatch; regenerate and review bindings")
        if bindings.get("output_name") != output_name:
            raise ValueError("Bindings output_name mismatch; use the named page's own bindings draft")
        values = bindings.get("values")
        if not isinstance(values, dict):
            raise ValueError("Bindings values must be an object keyed by field id")
    unknown = set(values) - {f["id"] for f in template["fields"]}
    if unknown:
        raise ValueError(f"Unknown binding fields: {', '.join(sorted(unknown))}")
    root = ET.parse(template_path).getroot()
    unfinished, applied, warnings, assets = [], [], [], {}
    for field in template["fields"]:
        value, confirmed = binding_value(values.get(field["id"]), field)
        if field["required"] and (value is None or (value == field["example"] and not confirmed)):
            unfinished.append({"id": field["id"], "role": field["role"],
                               "reason": "not_supplied" if value is None else "unchanged_example_not_confirmed"})
        node = resolve(root, field["path"])
        if value is not None:
            if field.get("attribute"):
                node.set(field["attribute"], value)
            else:
                for child in list(node):
                    node.remove(child)
                node.text = value
            applied.append(field["id"])
            hint = field.get("capacity_hint")
            if hint and len(value) > hint["estimated_cjk_chars_per_line"]:
                warnings.append({"field": field["id"], "code": "text_capacity_review", "message": hint["advisory"]})
        if field["kind"] == "image":
            src = node.get("src", "")
            if src.startswith(("http://", "https://", "data:")) or not src:
                raise ValueError(f"{field['id']}: image needs a local @path or a Feishu file token; external URLs are not supported")
            if src.startswith("@"):
                search = [binding_dir] if value is not None else [template_path.parent, template_path.parent.parent / "assets", ROOT / "assets"]
                asset = find_asset(src, search)
                asset_hash = digest(asset)
                target = Path("assets") / asset.name
                existing = assets.get(target) or (output / target if (output / target).exists() else None)
                if existing is not None and digest(existing) != asset_hash:
                    target = Path("assets") / (asset_hash + "-" + asset.name)
                    existing = assets.get(target) or (output / target if (output / target).exists() else None)
                    if existing is not None and digest(existing) != asset_hash:
                        raise ValueError(f"Conflicting asset output: {target}")
                assets[target] = asset
                node.set("src", "@./" + target.as_posix())
    status = "draft" if unfinished and args.allow_draft else "incomplete" if unfinished else "ready_for_validation"
    report = {"schema_version": SCHEMA_VERSION, "status": status,
              "template": template_id, "output_name": output_name,
              "source_sha256": template["source_sha256"],
              "complete": not unfinished, "completion_scope": "field_bindings_only",
              "applied_fields": applied, "unfinished_fields": unfinished,
              "warnings": warnings, "copied_assets": [], "reused_assets": [], "xml_path": None, "xml_sha256": None,
              "validation_required": True, "publication_ready": False}
    should_write = not unfinished or args.allow_draft
    xml_path = output / (output_name + ".xml" if output_name else template["file"])
    draft_path = output / (output_name + ".bindings.draft.json" if output_name else "bindings.draft.json")
    report_path = output / (output_name + ".prepare-report.json" if output_name else "prepare-report.json")
    if xml_path.resolve() == template_path.resolve():
        raise ValueError("Output directory must not overwrite the source template")
    pending_paths = [xml_path] if should_write else []
    if not args.force and any(p.exists() for p in pending_paths):
        raise ValueError("Output XML already exists; choose another name/directory or pass --force")
    output.mkdir(parents=True, exist_ok=True)
    # Never replace an edited bindings draft, even when XML replacement is forced.
    if not draft_path.exists():
        write_json(draft_path, draft_bindings(template, output_name))
    if should_write:
        for relative, source in assets.items():
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if digest(target) != digest(source):
                    raise ValueError(f"Asset changed during preparation: {target}; retry after inspection")
                report["reused_assets"].append(relative.as_posix())
            else:
                shutil.copy2(source, target)
                report["copied_assets"].append(relative.as_posix())
        if root.tag.startswith("{"):
            ET.register_namespace("", root.tag[1:].split("}", 1)[0])
        # lark-cli requires a <slide> fragment and rejects XML declarations.
        ET.ElementTree(root).write(xml_path, encoding="utf-8", xml_declaration=False)
        report["xml_path"] = str(xml_path)
        report["xml_sha256"] = digest(xml_path)
    write_json(report_path, report)
    return report, 1 if unfinished and not args.allow_draft else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index", help="Generate or verify the complete fields index")
    index.add_argument("--templates-dir", default=str(ROOT / "templates"))
    index.add_argument("--output", default=str(ROOT / "templates" / "fields.json"))
    index.add_argument("--check", action="store_true", help="Do not write; fail if the current index is stale")
    prep = commands.add_parser("prepare", help="Prepare one local template with hash-bound bindings")
    prep.add_argument("--template", required=True, help="Template id, e.g. slide01")
    prep.add_argument("--index", default=str(ROOT / "templates" / "fields.json"))
    prep.add_argument("--templates-dir", help="Override where indexed XML files are located")
    prep.add_argument("--bindings", help="JSON produced from bindings.draft.json")
    prep.add_argument("--name", help="Output page stem, e.g. page01; also names the page's bindings draft/report")
    prep.add_argument("--output-dir", required=True)
    prep.add_argument("--allow-draft", action="store_true", help="Explicitly allow unfinished XML for further editing")
    prep.add_argument("--force", action="store_true", help="Replace existing output XML; shared assets are never overwritten")
    args = parser.parse_args(argv)
    try:
        if args.command == "index":
            built = build_index(args.templates_dir)
            if args.check:
                stored = json.loads(Path(args.output).read_text(encoding="utf-8"))
                if stored != built:
                    raise ValueError("Fields index is stale; run index without --check")
            else:
                write_json(args.output, built)
            report, code = {"schema_version": SCHEMA_VERSION, "status": "ok", "template_count": built["template_count"],
                            "field_count": sum(t["field_count"] for t in built["templates"]), "output": str(Path(args.output).resolve()), "checked": args.check}, 0
        else:
            report, code = prepare(args)
    except (OSError, ValueError, KeyError, IndexError, TypeError, ET.ParseError) as exc:
        report, code = {"schema_version": SCHEMA_VERSION, "status": "error", "error": str(exc)}, 2
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
