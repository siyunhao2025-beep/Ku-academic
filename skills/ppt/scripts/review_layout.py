#!/usr/bin/env python3
"""Check local SML geometry/resources and report approximate text-layout risks.

Text warnings are estimates: font metrics, autoFit, and Lark rendering can
change the outcome. They do not substitute for a final rendered screenshot.
"""
from __future__ import annotations

import math
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

try:
    from .sml import (ROOT, TokenError, TableColumnSpanError, child, children, descendants, element_paths,
                      expanded_table_columns,
                      load_tokens, local_name, make_issue, normalize_color,
                      number, paragraph_runs, read_slide, result, run_cli)
except ImportError:
    from sml import (ROOT, TokenError, TableColumnSpanError, child, children, descendants, element_paths,
                     expanded_table_columns,
                     load_tokens, local_name, make_issue, normalize_color,
                     number, paragraph_runs, read_slide, result, run_cli)


def est_text_width(text: str, font_size: float) -> float:
    """Approximate advance widths; these are not measured font glyph metrics."""
    width = 0.0
    for char in text:
        if char in "\r\n" or unicodedata.combining(char):
            continue
        factor = 0.3 if char.isspace() else 1.0 if unicodedata.east_asian_width(char) in "WF" else 0.6 if char.isdigit() else 0.55
        width += font_size * factor
    return width


def parse_float(value, default=0.0):
    try:
        return number(value)
    except (TypeError, ValueError):
        return default


def resolve_image(src, xml_path, assets_dir=None):
    """Return (local_path, kind), resolving @ paths without fetching remote data."""
    if not src:
        return None, "missing"
    if urlparse(src).scheme in ("http", "https", "data"):
        return None, "remote"
    is_local = src.startswith(("@", "/", ".")) or Path(src).suffix.lower() in (".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".avif")
    if not is_local:
        return None, "token"
    relative = Path(src[1:] if src.startswith("@") else src)
    candidates = [relative] if relative.is_absolute() else [Path(xml_path).resolve().parent / relative]
    if assets_dir is not None:
        candidates.extend((Path(assets_dir) / relative, Path(assets_dir) / relative.name))
    # Bundled templates intentionally refer to the sibling assets directory.
    if Path(xml_path).resolve().is_relative_to(ROOT / "templates"):
        candidates.extend((ROOT / "assets" / relative, ROOT / "assets" / relative.name))
    return next((candidate for candidate in candidates if candidate.is_file()), None), "local"


def _estimate(content, width, default_font_size):
    total_height, maximum_width = 0.0, 0.0
    horizontal_overflow = False
    count_lines = 0
    for paragraph, runs in paragraph_runs(content):
        attrs = dict(content.attrib)
        attrs.update(paragraph.attrib)
        wrap = attrs.get("wrap", "true").lower() != "false"
        glyphs = [(char, parse_float(style.get("fontSize"), default_font_size)) for text, style in runs for char in text]
        lines = [(0.0, 0.0)]
        for char, font_size in glyphs:
            line_width, line_font = lines[-1]
            if char == "\n":
                lines.append((0.0, font_size))
                continue
            if char == "\r":
                continue
            advance = est_text_width(char, font_size)
            if wrap and line_width > 0 and line_width + advance > width:
                lines.append((advance, font_size))
            else:
                lines[-1] = (line_width + advance, max(line_font, font_size))
        spacing = attrs.get("lineSpacing", "multiple:1.2")
        mode, _, raw = spacing.partition(":")
        spacing_value = parse_float(raw, 1.2 if mode != "fixed" else default_font_size * 1.2)
        for line_width, font_size in lines:
            font_size = font_size or parse_float(attrs.get("fontSize"), default_font_size)
            line_height = spacing_value if mode == "fixed" else font_size * spacing_value
            total_height += line_height
            maximum_width = max(maximum_width, line_width)
            horizontal_overflow |= line_width > width + 0.5
            count_lines += 1
    return total_height, maximum_width, count_lines, horizontal_overflow


def review_slide(path: Path, tokens=None, tokens_path=None, assets_dir=None) -> dict:
    path = Path(path)
    root, issues = read_slide(path)
    if root is None:
        return result(path, issues)
    try:
        tokens = load_tokens(tokens_path) if tokens is None else tokens
    except TokenError as exc:
        return result(path, [make_issue("error", "invalid_tokens", exc)])
    paths = element_paths(root)
    canvas = tokens["validation"]["canvas"]

    def issue(level, code, message, element=root):
        issues.append(make_issue(level, code, message, paths[element]))

    boxes = {}
    for element in root.iter():
        name = local_name(element.tag)
        if name == "line":
            coordinates = ("startX", "startY", "endX", "endY")
            if any(element.get(attribute) is None for attribute in coordinates):
                issue("error", "missing_geometry", "Line needs startX, startY, endX and endY", element)
            else:
                try:
                    sx, sy, ex, ey = (number(element.get(attribute)) for attribute in coordinates)
                except ValueError:
                    issue("error", "invalid_geometry", "Line endpoints must be finite numbers", element)
                else:
                    if min(sx, sy, ex, ey) < 0:
                        issue("error", "negative_coord", "Line endpoint has a negative coordinate", element)
                    if max(sx, ex) > canvas["width"] + 0.01 or max(sy, ey) > canvas["height"] + 0.01:
                        issue("error", "out_of_bounds", "Line endpoint exceeds the slide canvas", element)
                    if sx == ex and sy == ey:
                        issue("error", "zero_size", "Line endpoints coincide", element)
        for attribute in ("topLeftX", "topLeftY", "width", "height"):
            raw = element.get(attribute)
            if raw is not None:
                try:
                    value = number(raw)
                    if attribute in ("width", "height") and value < 0:
                        raise ValueError("negative dimension")
                except ValueError:
                    issue("error", "invalid_geometry", f"{attribute} must be a finite {'nonnegative ' if attribute in ('width', 'height') else ''}number: {raw}", element)
        if name in ("shape", "img", "table", "chart"):
            if any(element.get(attribute) is None for attribute in ("topLeftX", "topLeftY", "width", "height")):
                issue("error", "missing_geometry", "Visible element needs topLeftX, topLeftY, width and height", element)
            else:
                try:
                    x, y, width, height = (number(element.get(attribute)) for attribute in ("topLeftX", "topLeftY", "width", "height"))
                except ValueError:
                    pass
                else:
                    if width >= 0 and height >= 0:
                        boxes[element] = (x, y, width, height)
                        if x < 0 or y < 0:
                            issue("error", "negative_coord", f"Negative coordinate ({x:g}, {y:g})", element)
                        if x + width > canvas["width"] + 0.01 or y + height > canvas["height"] + 0.01:
                            issue("error", "out_of_bounds", f"Box ({x:g},{y:g}) {width:g}x{height:g} exceeds {canvas['width']}x{canvas['height']}", element)
                        if (name != "shape" or element.get("type") == "text") and (width == 0 or height == 0):
                            issue("error", "zero_size", "Visible content has a zero-size box", element)
        raw_color = element.get("color")
        if raw_color is None and name == "color":
            raw_color = element.get("value")
        if raw_color is not None:
            try:
                normalize_color(raw_color)
            except ValueError as exc:
                issue("error", "invalid_color", str(exc), element)
        if name == "border" and element.get("width") is not None and not re.fullmatch(r"\+?\d+", element.get("width").strip()):
            issue("error", "border_width_invalid", "border width must be a nonnegative integer", element)
        if element.get("fontSize") is not None:
            raw = element.get("fontSize").strip()
            if not re.fullmatch(r"\+?\d+", raw) or int(raw) < 6:
                issue("error", "font_size_invalid", f"SML fontSize must be an integer >= 6: {raw}", element)
        if element.get("lineSpacing") is not None:
            mode, sep, amount = element.get("lineSpacing").partition(":")
            if sep != ":" or mode not in ("fixed", "multiple") or parse_float(amount, -1) <= 0:
                issue("error", "invalid_line_spacing", f"Use positive multiple:N or fixed:N: {element.get('lineSpacing')}", element)
        if name == "img":
            resolved, kind = resolve_image(element.get("src"), path, assets_dir)
            if kind in ("missing", "local") and resolved is None:
                issue("error", "missing_image", f"Local image does not exist: {element.get('src', '')}", element)
            elif kind in ("remote", "token"):
                issue("warning", "image_not_verified", f"Remote/token image was not fetched or verified locally: {element.get('src')}", element)

    text_boxes = []
    for shape in descendants(root, "shape"):
        if shape.get("type") != "text":
            continue
        content = child(shape, "content")
        runs = [run for _, values in paragraph_runs(content) for run in values] if content is not None else []
        text = "".join(value for value, _ in runs)
        if not text.strip():
            issue("error", "empty_text_shape", "Empty text shape can display an editor placeholder; remove the shape", shape)
            continue
        if any(attrs.get("fontSize") is None for value, attrs in runs if value.strip()):
            issue("error", "missing_font_size", "Visible text needs an explicit inherited fontSize", shape)
        for paragraph, values in paragraph_runs(content):
            if not "".join(value for value, _ in values).strip():
                issue("warning", "empty_paragraph", "Empty paragraph adds a line; verify that spacing is intentional", paragraph)
            elif any("\n" in value for value, _ in values) and not any(local_name(item.tag) in ("br", "break") for item in paragraph.iter()):
                issue("warning", "literal_newline", "Literal newline in text may render differently; use separate paragraphs", paragraph)
        if shape not in boxes:
            continue
        x, y, width, height = boxes[shape]
        if width <= 0 or height <= 0:
            continue
        estimated_height, estimated_width, lines, horizontal = _estimate(content, width, tokens["font_sizes"]["body"])
        auto_fit = content.get("autoFit", "unspecified")
        caveat = f"Static font estimate; autoFit={auto_fit}. Verify the rendered slide."
        if horizontal:
            issue("warning", "text_overflow_no_wrap", f"Estimated text width {estimated_width:.1f}px exceeds box {width:g}px. {caveat}", shape)
        if estimated_height > height + 0.5:
            issue("warning", "text_overflow_wrap", f"Estimated {lines} line(s) need {estimated_height:.1f}px; box height {height:g}px. {caveat}", shape)
        drawn_width, drawn_height = min(width, estimated_width), min(height, estimated_height)
        align = content.get("textAlign", "left")
        vertical = content.get("verticalAlign", "top")
        drawn_x = x + ((width - drawn_width) / 2 if align == "center" else width - drawn_width if align == "right" else 0)
        drawn_y = y + ((height - drawn_height) / 2 if vertical in ("middle", "center") else height - drawn_height if vertical == "bottom" else 0)
        text_boxes.append((shape, drawn_x, drawn_y, drawn_width, drawn_height, text[:24]))

    for index, (first, x1, y1, w1, h1, text1) in enumerate(text_boxes):
        for second, x2, y2, w2, h2, text2 in text_boxes[index + 1:]:
            ix = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
            iy = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
            if ix > 1 and iy > 1 and ix * iy > 10:
                issue("warning", "text_overlap", f"Estimated text regions overlap ({ix * iy:.1f}px²): {text1!r} / {text2!r} at {paths[second]}. Font metrics and autoFit may change this; inspect rendering.", first)

    for table in descendants(root, "table"):
        if table not in boxes:
            continue
        _, _, table_width, table_height = boxes[table]
        rows = children(table, "tr")
        try:
            columns = expanded_table_columns(table)
        except TableColumnSpanError as exc:
            issue("error", exc.code, str(exc), exc.column)
            continue
        dimensions_valid = True
        for dimension, elements, attr, expected in (("height", rows, "height", table_height), ("width", columns, "width", table_width)):
            values = [parse_float(element.get(attr), None) for element in elements]
            if not values or any(value is None or value <= 0 for value in values):
                dimensions_valid = False
                issue("error", "invalid_table_dimensions", f"Table requires positive {attr} for every {'row' if attr == 'height' else 'column'}", table)
            elif not math.isclose(sum(values), expected, abs_tol=0.01):
                issue("error", "table_dimension_mismatch", f"Table {dimension} {expected:g} differs from sum {sum(values):g}", table)
        if not dimensions_valid:
            continue
        row_heights = [number(row.get("height")) for row in rows]
        column_widths = [number(column.get("width")) for column in columns]
        occupied = set()
        for row_index, row in enumerate(rows):
            column_index = 0
            for cell in children(row, "td"):
                while (row_index, column_index) in occupied:
                    column_index += 1
                try:
                    colspan = int(cell.get("colSpan", cell.get("colspan", "1")))
                    rowspan = int(cell.get("rowSpan", cell.get("rowspan", "1")))
                    if colspan <= 0 or rowspan <= 0 or column_index + colspan > len(columns) or row_index + rowspan > len(rows):
                        raise ValueError("Cell span exceeds table dimensions")
                except ValueError as exc:
                    issue("error", "invalid_table_cell_span", str(exc), cell)
                    continue
                occupied.update((ri, ci) for ri in range(row_index, row_index + rowspan) for ci in range(column_index, column_index + colspan))
                width = sum(column_widths[column_index:column_index + colspan])
                height = sum(row_heights[row_index:row_index + rowspan])
                column_index += colspan
                content = child(cell, "content")
                if content is None or not "".join(content.itertext()).strip():
                    continue
                estimated_height, estimated_width, _, horizontal = _estimate(content, width, tokens["font_sizes"]["body"])
                if horizontal or estimated_height > height + 0.5:
                    issue("warning", "table_cell_text_overflow", f"Estimated text needs {estimated_width:.1f}x{estimated_height:.1f}px; cell is {width:g}x{height:g}px. Static font estimate without cell padding; autoFit={content.get('autoFit', 'unspecified')}. Verify rendering.", cell)

    return result(path, issues)


def main(argv=None) -> int:
    return run_cli(review_slide, "Review SML geometry, resources and estimated text layout", argv)


if __name__ == "__main__":
    sys.exit(main())
