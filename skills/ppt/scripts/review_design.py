#!/usr/bin/env python3
"""Review SML against the selected theme; errors block, warnings need review.

All theme rules come from tokens.yaml (or --tokens). Structural XML parsing
makes equivalent namespace, whitespace and attribute ordering behave alike.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

try:
    from .sml import (TokenError, child, children, color_tuple, descendants, element_paths,
                      load_tokens, local_name, make_issue, normalize_color,
                      number, paragraph_runs, read_slide, result, run_cli)
except ImportError:
    from sml import (TokenError, child, children, color_tuple, descendants, element_paths,
                     load_tokens, local_name, make_issue, normalize_color,
                     number, paragraph_runs, read_slide, result, run_cli)


def review_slide(path: Path, tokens=None, tokens_path=None, assets_dir=None) -> dict:
    root, issues = read_slide(path)
    if root is None:
        return result(path, issues, compatibility=True)
    try:
        tokens = load_tokens(tokens_path) if tokens is None else tokens
    except TokenError as exc:
        return result(path, [make_issue("error", "invalid_tokens", exc)], compatibility=True)
    rules = tokens["validation"]
    palette = tokens["normalized_colors"]
    allowed = set(tokens["allowed_colors"])
    paths = element_paths(root)
    # Speaker notes are retained in the XML but do not appear on the canvas.
    visible_elements = tuple(element for branch in root
                             if local_name(branch.tag) in ("data", "style")
                             for element in branch.iter())

    def visible_descendants(name):
        return (element for element in visible_elements if local_name(element.tag) == name)

    def issue(level, code, message, element=root):
        issues.append(make_issue(level, code, message, paths[element]))

    colors = {}
    for element in visible_elements:
        raw_color = element.get("color")
        if raw_color is None and local_name(element.tag) == "color":
            raw_color = element.get("value")
        if raw_color is None:
            continue
        try:
            value = normalize_color(raw_color)
        except ValueError as exc:
            issue("error", "invalid_color", str(exc), element)
            continue
        colors[element] = value
        if value not in allowed:
            issue("error", "color_not_in_palette", f"Color is outside the selected theme: {value}", element)

    # A chart theme is a candidate palette. Validate every defined color above,
    # but only count colors assigned to data series/slices as visible accents.
    theme_elements = {color for theme in visible_descendants("chartColorTheme") for color in descendants(theme, "color")}
    visible_colors = {value for element, value in colors.items() if element not in theme_elements}
    for chart in visible_descendants("chart"):
        theme = next(descendants(chart, "chartColorTheme"), None)
        data = child(chart, "chartData")
        if theme is None or data is None:
            continue
        dim1, dim2 = child(data, "dim1"), child(data, "dim2")
        series_count = len(children(dim2, "chartField")) if dim2 is not None else 0
        category_count = 0
        categories = child(dim1, "chartField") if dim1 is not None else None
        if categories is not None:
            try:
                category_count = len(next(csv.reader(["".join(categories.itertext()).strip()], strict=True)))
            except (csv.Error, StopIteration):
                pass  # Malformed chart data needs a schema/preview check.
        used_count = 0
        for plot in descendants(chart, "chartPlot"):
            if plot.get("type") in ("column", "line", "bar", "area", "scatter", "radar"):
                used_count = max(used_count, series_count)
            elif plot.get("type") in ("pie", "doughnut"):
                used_count = max(used_count, category_count)
        visible_colors.update(colors[color] for color in list(descendants(theme, "color"))[:used_count] if color in colors)
    accents = visible_colors.intersection(tokens["normalized_accent_colors"])
    if len(accents) > rules["max_accent_colors"]:
        issue("warning", "accent_overuse", f"{len(accents)} accent colors; theme recommends at most {rules['max_accent_colors']}")

    sizes = set()
    for content in visible_descendants("content"):
        for paragraph, runs in paragraph_runs(content):
            for text, attrs in runs:
                if not text.strip():
                    continue
                raw = attrs.get("fontSize")
                if raw is None:
                    issue("error", "missing_font_size", "Visible text needs an explicit inherited fontSize", paragraph)
                    break
                try:
                    size = number(raw)
                except (TypeError, ValueError):
                    issue("error", "invalid_font_size", f"Invalid fontSize: {raw}", paragraph)
                    break
                sizes.add(size)
                if size < rules["min_font_size"]:
                    issue("error", "font_below_min", f"Font size {size:g} is below theme minimum {rules['min_font_size']}", paragraph)
                    break
    if len(sizes) > rules["max_font_variants"]:
        issue("warning", "font_hierarchy_too_many", f"{len(sizes)} font sizes; theme recommends at most {rules['max_font_variants']}")

    def is_dark(value):
        red, green, blue, alpha = color_tuple(value)
        luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) * alpha + 255 * (1 - alpha)
        return luminance < rules["dark_luminance_threshold"]

    style = child(root, "style")
    background_colors = list(descendants(style, "fillColor")) if style is not None else []
    for background in background_colors:
        value = colors.get(background)
        if value is None:
            continue
        if rules["forbid_dark_page"] and is_dark(value):
            issue("error", "dark_page_banned", f"The selected theme forbids a dark page background: {value}", background)
        if rules["page_background"] is not None and value != palette[rules["page_background"]]:
            issue("error", "page_background_mismatch", f"Page background must be {palette[rules['page_background']]} in the selected theme", background)

    # Covers nested shape fills and table cell fills, not text/stroke colors.
    for fill in visible_descendants("fillColor"):
        if fill in background_colors:
            continue
        value = colors.get(fill)
        if value is not None and rules["forbid_dark_fills"] and is_dark(value):
            issue("error", "dark_fill_banned", f"The selected theme forbids dark shape/table fills: {value}", fill)

    pill = rules["bottom_pill_bar"]
    if pill["enabled"]:
        pill_colors = {palette[name] for name in pill["colors"]}
        for shape in visible_descendants("shape"):
            if shape.get("type") != "round-rect":
                continue
            try:
                y, width, height = (number(shape.get(name)) for name in ("topLeftY", "width", "height"))
            except (TypeError, ValueError):
                continue  # review_layout reports malformed geometry.
            fill = child(shape, "fill")
            values = {colors.get(element) for element in descendants(fill, "fillColor")} if fill is not None else set()
            if y > pill["min_y"] and width > pill["min_width"] and height <= pill["max_height"] and values.intersection(pill_colors):
                issue("error", "bottom_pill_bar", f"Bottom pill exceeds theme limits: y={y:g}, {width:g}x{height:g}", shape)

    return result(path, issues, compatibility=True)


def main(argv=None) -> int:
    return run_cli(review_slide, "Review slide design against an explicit theme", argv)


if __name__ == "__main__":
    sys.exit(main())
