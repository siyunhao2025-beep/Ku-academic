#!/usr/bin/env python3
"""Render SML slides as self-contained, approximate SVG previews.

Relative images (@./foo.png or foo.png) resolve against the XML directory first,
then --assets-dir (default: this installed skill's assets directory). Absolute
paths are used as-is. URLs and Feishu tokens are not fetched. Text metrics,
auto-fit, font substitution and exact chart layout require Feishu screenshots.
"""
from __future__ import annotations

import argparse
import base64
import csv
from decimal import Decimal, ROUND_HALF_UP
import json
import math
import re
import sys
import unicodedata
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from .sml import TableColumnSpanError, expanded_table_columns
except ImportError:
    # Also retain direct-file API loading from arbitrary working directories.
    # Resolve the sibling explicitly instead of modifying the caller's sys.path.
    import importlib.util
    _sml_spec = importlib.util.spec_from_file_location("_preview_sml", Path(__file__).with_name("sml.py"))
    _sml = importlib.util.module_from_spec(_sml_spec)
    _sml_spec.loader.exec_module(_sml)
    TableColumnSpanError = _sml.TableColumnSpanError
    expanded_table_columns = _sml.expanded_table_columns

W, H = 960, 540
SKILL_ROOT = Path(__file__).resolve().parent.parent
FONT = "'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif"
APPROXIMATION = "Approximate preview: estimated text wrapping; no auto-fit or exact Feishu font/chart layout. Final acceptance requires Feishu screenshots."
GEOMETRY = {"topLeftX", "topLeftY", "width", "height"}
LINE_ENDPOINTS = ("startX", "startY", "endX", "endY")
TEXT_ATTRS = {"fontSize", "fontFamily", "color", "bold", "italic", "underline", "strikethrough", "textAlign", "verticalAlign", "lineSpacing", "wrap", "autoFit"}
PADDING_ATTRS = {"paddingLeft", "paddingRight", "paddingTop", "paddingBottom"}
COLOR_PATTERN = re.compile(r"rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+(?:\s*,\s*[\d.]+)?\s*\)|#[0-9a-fA-F]{3,4}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}")
# Unknown elements/attributes are reported; identity metadata is intentionally ignored.
SUPPORTED = {
    "slide": {"width", "height"}, "data": set(), "style": set(),
    "shape": GEOMETRY | {"type", "radius", "presetHandlers"},
    "line": set(LINE_ENDPOINTS) | {"type", "alpha"},
    "startArrow": {"type", "widthScale", "heightScale"},
    "endArrow": {"type", "widthScale", "heightScale"},
    "content": TEXT_ATTRS | PADDING_ATTRS, "p": TEXT_ATTRS, "span": TEXT_ATTRS, "br": set(),
    "fill": set(), "fillColor": {"color"}, "border": {"color", "width"},
    "img": GEOMETRY | {"src"}, "table": GEOMETRY, "colgroup": set(),
    "col": {"width", "span"}, "tr": {"height"}, "td": set(), "chart": GEOMETRY,
    "chartPlotArea": set(), "chartPlot": {"type"}, "chartExtra": set(),
    "chartSmooth": set(), "chartAxes": set(), "chartAxis": {"type", "position", "min", "max"},
    "chartBars": {"color", "width", "gap"},
    "chartLabels": {"position", "value", "fontSize", "color", "series", "category", "percentage", "format"},
    "chartGridLine": {"color", "width"}, "chartLabel": {"fontSize", "color", "format", "angle"},
    "chartData": set(), "dim1": set(), "dim2": set(),
    "chartField": {"name", "valueType"}, "chartStyle": set(),
    "chartBackground": {"color"}, "chartBorder": {"color", "width"},
    "chartColorTheme": set(), "color": {"value"}, "chartLegend": {"position", "fontSize"},
}


def esc(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def children(elem, tag):
    return [] if elem is None else [child for child in elem if local_name(child.tag) == tag]


def find(elem, path):
    for name in path.split("/"):
        elem = next(iter(children(elem, name)), None)
        if elem is None:
            break
    return elem


def parse_float(value, default=0):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def rgba_to_hex(color):
    """Accept CSS rgb/rgba, hex and transparent, preserving alpha."""
    color = (color or "").strip()
    match = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)", color)
    if match:
        result = "#" + "".join(f"{min(255,int(match[i])):02X}" for i in (1, 2, 3))
        alpha = parse_float(match[4], 1)
        return result + (f"{round(max(0,min(1,alpha))*255):02X}" if alpha < 1 else "")
    if re.fullmatch(r"#[0-9a-fA-F]{3,4}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}", color):
        return color
    return {"transparent": "#00000000", "white": "#FFFFFF", "black": "#000000", "none": "none"}.get(color, "#000000")


def geometry(elem):
    return tuple(parse_float(elem.get(key), default) for key, default in
                 (("topLeftX", 0), ("topLeftY", 0), ("width", 100), ("height", 20)))


def glyph_width(char, style):
    factor = 0 if unicodedata.combining(char) else (1 if unicodedata.east_asian_width(char) in "WF" else 0.55)
    if char.isspace():
        factor = 0.33
    return factor * parse_float(style.get("fontSize"), 14)


def chart_number(value, format_code=""):
    """Bounded native count/one-decimal formatting, or the plain value."""
    if format_code == "0":
        return format(Decimal(str(value)).to_integral_value(rounding=ROUND_HALF_UP), "f")
    if format_code == "0.0":
        return format(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), ".1f")
    return f"{value:g}"


class Renderer:
    def __init__(self, xml_path, assets_dir=None, diagnostics=None):
        self.xml_path = Path(xml_path).resolve()
        self.base_dir = self.xml_path.parent
        self.assets_dir = Path(assets_dir).resolve() if assets_dir else SKILL_ROOT / "assets"
        self.issues = diagnostics if diagnostics is not None else []
        self.seen = set()
        self.chart_count = 0

    def issue(self, code, message, elem=None, severity="warning"):
        element = local_name(elem.tag) if elem is not None else "slide"
        key = (code, message, element)
        if key not in self.seen:
            self.seen.add(key)
            self.issues.append({"severity": severity, "code": code, "element": element, "message": message})

    def audit(self, root):
        def visual_tree(elem):
            # Speaker notes and their formatting are intentionally outside the
            # rendered slide. Do not report their text/style as visual omissions.
            if local_name(elem.tag) == "note":
                return
            yield elem
            for child in elem:
                yield from visual_tree(child)

        visual_elements = list(visual_tree(root))
        # Solid fill overrides apply to bars/columns. Do not make series styling
        # on other chart kinds silently appear supported.
        bar_overrides = {}
        for plot in visual_elements:
            if local_name(plot.tag) == "chartPlot" and plot.get("type") in {"bar", "column"}:
                for series_list in children(plot, "chartSeriesList"):
                    bar_overrides[series_list] = set()
                    for series in children(series_list, "chartSeries"):
                        bar_overrides[series] = {"index"}
                        for labels in children(series, "chartLabels"):
                            self.issue("unsupported_series_chart_labels",
                                       "Series-level chartLabels overrides are not rendered; preview uses plot-level labels.", labels)
                        for bars in children(series, "chartBars"):
                            bar_overrides[bars] = {"color"}
                            for bar in children(bars, "chartBar"):
                                bar_overrides[bar] = {"index", "color"}

        for elem in visual_elements:
            tag = local_name(elem.tag)
            supported = bar_overrides.get(elem, SUPPORTED.get(tag))
            if supported is None:
                self.issue("unsupported_element", f"<{tag}> has no SVG renderer; its appearance is omitted.", elem)
                continue
            for key, value in elem.attrib.items():
                if local_name(key) not in supported | {"id", "name"}:
                    self.issue("unsupported_attribute", f"<{tag}> attribute {key}={value!r} is not rendered.", elem)
                if key == "color" or (tag == "color" and key == "value"):
                    if not COLOR_PATTERN.fullmatch(value.strip()) and value not in {"transparent", "white", "black", "none"}:
                        self.issue("unsupported_color", f"Color {value!r} is unsupported; preview uses black. Use hex, rgb or rgba.", elem)
                if key in GEOMETRY or key == "fontSize":
                    numeric = parse_float(value, None)
                    size = key in {"width", "height", "fontSize"}
                    border_width = tag in {"border", "chartBorder", "chartGridLine", "chartBars"} and key == "width"
                    invalid_size = size and (numeric is not None) and (numeric < 0 if border_width else numeric <= 0)
                    if numeric is None or invalid_size:
                        constraint = " nonnegative." if border_width else (" greater than zero." if size else ".")
                        self.issue("invalid_numeric_attribute", f"<{tag}> {key}={value!r} must be a finite number" + constraint, elem, "error")
            if tag in {"content", "p", "span"}:
                for key, allowed in {"textAlign": {"left", "center", "right"}, "verticalAlign": {"top", "middle", "bottom"}, "autoFit": {"normal-auto-fit", "none", "no-auto-fit"}}.items():
                    if key in elem.attrib and elem.get(key) not in allowed:
                        self.issue("unsupported_attribute_value", f"<{tag}> {key}={elem.get(key)!r} uses default preview behavior.", elem)
                if "lineSpacing" in elem.attrib and not re.fullmatch(r"(?:multiple|points):[\d.]+", elem.get("lineSpacing")):
                    self.issue("unsupported_line_spacing", f"lineSpacing={elem.get('lineSpacing')!r} uses 1.35 line spacing.", elem)
            if tag == "chartSmooth":
                self.issue("chart_smoothing_approximation", "Smooth curves use straight segments through the actual data points.", elem)
            if tag == "chartAxis" and (elem.get("type") not in {"x", "y"} or elem.get("position", "left") not in {"left", "bottom"}):
                self.issue("unsupported_chart_axis", "Only a bottom category axis and a left numeric axis are rendered.", elem)
            if tag == "chartAxis" and elem.get("type") != "y" and any(key in elem.attrib for key in ("min", "max")):
                self.issue("unsupported_axis_range", "Axis min/max are supported only on the left numeric Y axis; category-axis limits are not applied.", elem)
            if tag == "chartLegend" and elem.get("position", "bottom") != "bottom":
                self.issue("legend_position_approximation", "Legend position is approximated at the bottom of the chart.", elem)
            if tag == "chartLabel":
                if elem.get("format", "") not in {"", "0"}:
                    self.issue("unsupported_axis_format", "Only the plain value and integer format=0 are supported for numeric axis labels.", elem)
                if parse_float(elem.get("angle", "0"), None) != 0:
                    self.issue("unsupported_axis_label_angle", "Axis label angle is supported only at 0 degrees; labels remain horizontal.", elem)

    def fill(self, elem, default="#FFFFFF"):
        color = find(elem, "fill/fillColor")
        return rgba_to_hex(color.get("color")) if color is not None else default

    def border(self, elem, child="border", default=""):
        border = find(elem, child)
        if border is None:
            return default
        return f' stroke="{esc(rgba_to_hex(border.get("color", "#000000")))}" stroke-width="{parse_float(border.get("width"),1):g}"'

    def placeholder(self, elem, label):
        x, y, w, h = geometry(elem)
        return (f'<g data-preview-placeholder="true"><rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" '
                f'fill="#FFF4F4" stroke="#C62828" stroke-dasharray="4 3"/>'
                f'<text x="{x+4:g}" y="{y+min(h-2,14):g}" font-size="10" fill="#A01010">{esc(label)}</text></g>')

    def collect_runs(self, elem, inherited):
        style = {**inherited, **elem.attrib}
        runs = [(elem.text, style)] if elem.text else []
        for child in elem:
            runs.extend([("\n", style)] if local_name(child.tag) == "br" else self.collect_runs(child, style))
            if child.tail:
                runs.append((child.tail, style))
        return runs

    def text(self, elem):
        x, y, w, h = geometry(elem)
        content = find(elem, "content")
        if content is None:
            return ""
        padding = {key: parse_float(content.get(key, "0"), None) for key in PADDING_ATTRS}
        if any(value is None or not 0 <= value <= 1584 for value in padding.values()):
            self.issue("invalid_text_padding", "Content padding must be finite pixel values in [0,1584].", content, "error")
            return self.placeholder(elem, "Invalid text padding")
        x, y = x+padding["paddingLeft"], y+padding["paddingTop"]
        w, h = w-padding["paddingLeft"]-padding["paddingRight"], h-padding["paddingTop"]-padding["paddingBottom"]
        if w <= 0 or h <= 0:
            self.issue("invalid_text_padding", "Content padding leaves no text area; enlarge the box or reduce padding.", content, "error")
            return self.placeholder(elem, "Padding exceeds text box")
        base = {"fontSize": "14", "fontFamily": "思源黑体", "color": "#171717", **content.attrib}
        blocks = []
        if children(content, "p"):
            if content.text and content.text.strip():
                blocks.append(([(content.text, base)], base))
            for child in content:
                blocks.append((self.collect_runs(child, base), {**base, **child.attrib}))
                if child.tail and child.tail.strip():
                    blocks.append(([(child.tail, base)], base))
        else:
            blocks = [(self.collect_runs(content, base), base)]
        lines = []
        for runs, style in blocks:
            current, width = [], 0
            for text, run_style in runs:
                for char in text.replace("\r\n", "\n").replace("\r", "\n"):
                    advance = glyph_width(char, run_style)
                    if char == "\n" or (style.get("wrap", "true") != "false" and current and width+advance > w):
                        lines.append((current, style))
                        current, width = [], 0
                    if char != "\n":
                        current.append((char, run_style))
                        width += advance
            lines.append((current, style))
        heights, sizes = [], []
        for line, style in lines:
            size = max([parse_float(s.get("fontSize"),14) for _,s in line] or [parse_float(style.get("fontSize"),14)])
            spacing = style.get("lineSpacing", "multiple:1.35")
            value = parse_float(spacing.split(":")[-1],1.35)
            heights.append(value if spacing.startswith("points:") else size*value)
            sizes.append(size)
        total_h = sum(heights)
        top = y + {"middle": (h-total_h)/2, "bottom": h-total_h}.get(base.get("verticalAlign"),0)
        parts = ['<g data-preview-text="true">']
        for index, (line, style) in enumerate(lines):
            align = style.get("textAlign", "left")
            anchor = {"left": "start", "center": "middle", "right": "end"}.get(align, "start")
            tx = {"left": x, "center": x+w/2, "right": x+w}.get(align,x)
            line_parts = [f'<text x="{tx:g}" y="{top+sizes[index]*0.85:g}" text-anchor="{anchor}" xml:space="preserve">']
            groups = []
            for char, run_style in line:
                if groups and groups[-1][1] == run_style:
                    groups[-1] = (groups[-1][0]+char,run_style)
                else:
                    groups.append((char,run_style))
            for text, run_style in groups:
                family = run_style.get("fontFamily", "思源黑体") + ", " + FONT
                decoration = " ".join(name for key,name in (("underline","underline"),("strikethrough","line-through")) if run_style.get(key) == "true") or "none"
                line_parts.append(f'<tspan font-family="{esc(family)}" font-size="{parse_float(run_style.get("fontSize"),14):g}" '
                             f'fill="{esc(rgba_to_hex(run_style.get("color")))}" font-weight="{"bold" if run_style.get("bold") == "true" else "normal"}" '
                             f'font-style="{"italic" if run_style.get("italic") == "true" else "normal"}" text-decoration="{decoration}">{esc(text)}</tspan>')
            parts.append("".join(line_parts+["</text>"]))
            top += heights[index]
        return "\n".join(parts+["</g>"])

    def shape(self, elem):
        x,y,w,h = geometry(elem)
        kind = elem.get("type")
        if kind == "text":
            return self.text(elem)
        attrs = f'fill="{self.fill(elem)}"{self.border(elem)}'
        if kind in {"rect","round-rect"}:
            radius = parse_float(elem.get("radius",elem.get("presetHandlers")),min(16,h/2)) if kind == "round-rect" else 0
            return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{max(0,min(radius,h/2,w/2)):g}" {attrs}/>'
        if kind == "ellipse":
            return f'<ellipse cx="{x+w/2:g}" cy="{y+h/2:g}" rx="{w/2:g}" ry="{h/2:g}" {attrs}/>'
        if kind == "diamond":
            return f'<polygon points="{x+w/2:g},{y:g} {x+w:g},{y+h/2:g} {x+w/2:g},{y+h:g} {x:g},{y+h/2:g}" {attrs}/>'
        self.issue("unsupported_shape",f"Shape type {kind!r} is not rendered.",elem)
        return self.placeholder(elem,f"Unsupported shape: {kind}")

    def line(self, elem):
        """Render native SML absolute endpoints, preserving document paint order."""
        if elem.get("type", "straight-connector1") not in {"line", "straight-connector1"}:
            self.issue("unsupported_line", f"Line type {elem.get('type')!r} is not rendered.", elem)
            return self.placeholder(elem, "Unsupported line")
        points = [parse_float(elem.get(key), None) for key in LINE_ENDPOINTS]
        if any(value is None for value in points):
            self.issue("invalid_line_geometry", "Line requires four finite startX/startY/endX/endY coordinates.", elem, "error")
            return self.placeholder(elem, "Invalid line endpoints")
        x1, y1, x2, y2 = points
        dx, dy = x2-x1, y2-y1
        length = math.hypot(dx, dy)
        if not math.isfinite(length) or length == 0:
            self.issue("invalid_line_geometry", "Line endpoints must define a finite, nonzero-length line.", elem, "error")
            return self.placeholder(elem, "Invalid line endpoints")
        border = find(elem, "border")
        if border is None:
            self.issue("missing_line_border", "Native SML line requires a border element.", elem, "error")
            return self.placeholder(elem, "Missing line border")
        width = parse_float(border.get("width"), 2.0 if border.get("width") is None else None)
        alpha = parse_float(elem.get("alpha"), 1 if elem.get("alpha") is None else None)
        if width is None or width < 0 or not width.is_integer() or alpha is None or not 0 <= alpha <= 1:
            self.issue("invalid_line_style", "Line border width must be a nonnegative integer; alpha must be between 0 and 1.", elem, "error")
            return self.placeholder(elem, "Invalid line style")
        color = esc(rgba_to_hex(border.get("color", "rgba(43, 47, 54, 1)")))
        parts = [f'<g data-preview-line="true" opacity="{alpha:g}">',
                 f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" fill="none" stroke="{color}" stroke-width="{width:g}"/>']
        for child, position, tip, direction in (("startArrow", "start", (x1, y1), (-dx/length, -dy/length)),
                                                 ("endArrow", "end", (x2, y2), (dx/length, dy/length))):
            arrow = find(elem, child)
            if arrow is not None:
                parts.append(self.line_arrow(arrow, position, tip, direction, width, color))
        return "\n".join(parts+["</g>"])

    def line_arrow(self, elem, position, tip, direction, width, color):
        """Approximate basic/filled triangle arrow sizes in the line's direction."""
        kind = elem.get("type", "none")
        if kind == "none":
            return ""
        if kind not in {"arrow", "solid-triangle"}:
            self.issue("unsupported_arrow", f"Arrow type {kind!r} is not rendered.", elem)
            return ""
        scales = {"sm": 3, "med": 4, "lg": 5}
        sizes = []
        for key in ("heightScale", "widthScale"):
            scale = elem.get(key, "med")
            if scale not in scales:
                self.issue("unsupported_attribute_value", f"<{local_name(elem.tag)}> {key}={scale!r} uses medium arrow size.", elem)
            sizes.append(scales.get(scale, scales["med"])*width)
        if width == 0:
            return ""
        arrow_length, arrow_width = sizes
        x, y = tip
        ux, uy = direction
        bx, by = x-ux*arrow_length, y-uy*arrow_length
        left = (bx-uy*arrow_width/2, by+ux*arrow_width/2)
        right = (bx+uy*arrow_width/2, by-ux*arrow_width/2)
        attrs = f'data-preview-arrow="{position}" stroke="{color}" stroke-width="{width:g}" stroke-linejoin="round"'
        if kind == "solid-triangle":
            return f'<polygon {attrs} points="{x:g},{y:g} {left[0]:g},{left[1]:g} {right[0]:g},{right[1]:g}" fill="{color}"/>'
        return f'<path {attrs} d="M {left[0]:g},{left[1]:g} L {x:g},{y:g} L {right[0]:g},{right[1]:g}" fill="none"/>'

    def image(self, elem):
        src = elem.get("src", "")
        path = Path(src[1:] if src.startswith("@") else src)
        candidates = [path] if path.is_absolute() else [self.base_dir/path,self.assets_dir/path]
        full = next((candidate for candidate in candidates if candidate.is_file()),None)
        if not src or "://" in src or full is None:
            self.issue("missing_image",f"Image {src!r} is unavailable; searched XML directory then {self.assets_dir}. Remote URLs/tokens are not fetched.",elem,"error")
            return self.placeholder(elem,"Missing image / 缺图")
        mime = {".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".gif":"image/gif",".webp":"image/webp",".svg":"image/svg+xml"}.get(full.suffix.lower())
        if mime is None:
            self.issue("unsupported_image",f"Image format {full.suffix!r} is unsupported; use PNG, JPEG, GIF, WebP or SVG.",elem,"error")
            return self.placeholder(elem,"Unsupported image format")
        try:
            encoded = base64.b64encode(full.read_bytes()).decode("ascii")
        except OSError as exc:
            self.issue("image_read_error",f"Cannot read image {src!r}: {exc}",elem,"error")
            return self.placeholder(elem,"Unreadable image")
        x,y,w,h = geometry(elem)
        return f'<image href="data:{mime};base64,{encoded}" x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" preserveAspectRatio="xMidYMid meet"/>'

    def table(self, elem):
        x,y,w,_ = geometry(elem)
        try:
            columns = expanded_table_columns(elem)
        except TableColumnSpanError as exc:
            self.issue(exc.code, str(exc), exc.column, "error")
            message = "Table column limit exceeded" if exc.code == "table_column_limit_exceeded" else "Invalid table column span"
            return self.placeholder(elem, message)
        widths = [parse_float(col.get("width"),100) for col in columns]
        parts = []
        for row in children(elem,"tr"):
            height = parse_float(row.get("height"),40)
            cells, cx = children(row,"td"), x
            for index,cell in enumerate(cells):
                width = widths[index] if index < len(widths) else w/max(1,len(cells))
                border = self.border(cell,default=' stroke="#DDDDDD" stroke-width="0.5"')
                parts.append(f'<rect x="{cx:g}" y="{y:g}" width="{width:g}" height="{height:g}" fill="{self.fill(cell)}"{border}/>')
                content = find(cell,"content")
                if content is not None:
                    copy = ET.fromstring(ET.tostring(content))
                    copy.attrib.setdefault("fontSize","12")
                    copy.attrib.setdefault("verticalAlign","middle")
                    for key in PADDING_ATTRS:
                        copy.attrib.setdefault(key, "8")
                    shape = ET.Element("shape",{"topLeftX":str(cx),"topLeftY":str(y),"width":str(width),"height":str(height)})
                    shape.append(copy)
                    parts.append(self.text(shape))
                cx += width
            y += height
        return "\n".join(parts)

    def chart(self, elem):
        x,y,w,h = geometry(elem)
        plots = children(find(elem,"chartPlotArea"),"chartPlot")
        kind = plots[0].get("type") if plots else None
        if len(plots) != 1 or kind not in {"column","bar","line","pie"}:
            self.issue("unsupported_chart","Only one column, bar, line or pie plot per chart is supported; combined plots are not rendered.",elem)
            return self.placeholder(elem,f"Unsupported chart: {kind}")
        categories_fields = children(find(elem,"chartData/dim1"),"chartField")
        fields = children(find(elem,"chartData/dim2"),"chartField")
        try:
            if len(categories_fields) != 1 or not fields:
                raise ValueError("Chart requires one category field and at least one numeric series")
            categories = next(csv.reader(["".join(categories_fields[0].itertext())]))
            series = [(field.get("name",""),[float(v.strip()) for v in next(csv.reader(["".join(field.itertext())]))]) for field in fields]
            if not categories or any(len(values) != len(categories) for _,values in series):
                raise ValueError("Chart category and series lengths must match")
            if not all(math.isfinite(v) for _,values in series for v in values):
                raise ValueError("Chart values must be finite numbers")
            if kind == "pie" and (len(series) != 1 or min(series[0][1]) < 0 or sum(series[0][1]) <= 0):
                raise ValueError("Pie requires one nonnegative series with a positive total")
            if w < 80 or h < 60:
                raise ValueError("Chart box must be at least 80 × 60 for this preview")
        except (ValueError,StopIteration) as exc:
            self.issue("invalid_chart_data",str(exc),elem,"error")
            return self.placeholder(elem,"Invalid chart data")
        plot = plots[0]
        bars = find(plot, "chartBars")
        data_labels = find(plot, "chartLabels")
        if bars is not None and kind not in {"column", "bar"}:
            self.issue("unsupported_chart_bars", "Global chartBars are rendered only for column and bar plots.", bars)
        label_size, label_color, label_format, show_values = 12, "#171717", "", False
        hide_labels = data_labels is not None and all(data_labels.get(key) in {"false", "0"} for key in ("series", "category", "percentage", "value"))
        if hide_labels and kind == "pie":
            self.issue("native_label_visibility_unverified",
                       "This local preview hides pie labels for four explicit false toggles, but Feishu has been observed restoring default percentages for this input. Those labels can overlap; verify an actual Feishu screenshot before accepting the slide.",
                       data_labels)
        if data_labels is not None:
            supported_labels = hide_labels or (kind in {"column", "bar"} and data_labels.get("position", "outside") == "outside"
                                and all(data_labels.get(key, "false") in {"false", "0"} for key in ("series", "category", "percentage"))
                                and data_labels.get("format", "") in {"", "0", "0.0"}
                                and not (set(data_labels.attrib) - SUPPORTED["chartLabels"] - {"id", "name"}))
            if not supported_labels:
                self.issue("unsupported_chart_labels", "Only global column/bar labels with position=outside and plain numeric values or format=0/0.0 are rendered; this label variant is omitted.", data_labels)
            elif data_labels.get("value", "true") not in {"true", "1", "false", "0"}:
                self.issue("invalid_chart_labels", "chartLabels value must be a boolean.", data_labels, "error")
                return self.placeholder(elem, "Invalid chart labels")
            else:
                show_values = data_labels.get("value", "true") in {"true", "1"}
                raw_size = data_labels.get("fontSize", "12")
                if not re.fullmatch(r"\+?\d+", raw_size) or int(raw_size) < 6:
                    self.issue("invalid_chart_labels", "chartLabels fontSize must be an integer >= 6.", data_labels, "error")
                    return self.placeholder(elem, "Invalid chart labels")
                label_size = int(raw_size)
                label_color = rgba_to_hex(data_labels.get("color", "#171717"))
                label_format = data_labels.get("format", "")
        colors = [rgba_to_hex(c.get("value")) for c in children(find(elem,"chartStyle/chartColorTheme"),"color")]
        colors = colors or ["#FF5A5F","#589EF7","#2BC9D1","#A66BEA","#F6B73C"]
        parts = [f'<g data-preview-chart="{kind}" transform="translate({x:g} {y:g})">']
        background = find(elem,"chartStyle/chartBackground")
        bg = rgba_to_hex(background.get("color")) if background is not None else "none"
        border = self.border(find(elem,"chartStyle"),"chartBorder")
        parts.append(f'<rect width="{w:g}" height="{h:g}" fill="{bg}"{border}/>')
        legend = find(elem,"chartLegend")
        labels = categories if kind == "pie" else [name for name,_ in series]
        legend_size = parse_float(legend.get("fontSize"),11) if legend is not None else 11
        rows, row, row_width = [], [], 0
        if legend is not None:
            for index,label in enumerate(labels):
                iw = 22+sum(glyph_width(c,{"fontSize":str(legend_size)}) for c in label)
                if row and row_width+iw > w-12:
                    rows.append((row,row_width))
                    row,row_width = [],0
                row.append((index,label,iw))
                row_width += iw
            if row:
                rows.append((row,row_width))
        legend_h = len(rows)*(legend_size+9)
        if legend_h > h-50:
            self.issue("chart_legend_overflow", "Legend leaves insufficient plot space; enlarge the chart or shorten labels.", elem, "error")
            return self.placeholder(elem,"Chart legend exceeds box")
        bar_legend_colors = []
        if kind == "bar":
            horizontal = self.horizontal_bars(elem, plot, categories, series, colors, w, h, legend_h,
                                              show_values, label_size, label_color, label_format)
            if horizontal is None:
                return self.placeholder(elem, "Invalid horizontal bars")
            bar_parts, bar_legend_colors = horizontal
            parts.extend(bar_parts)
        elif kind == "pie":
            if any(any(key in axis.attrib for key in ("min", "max")) for axis in children(find(elem, "chartPlotArea/chartAxes"), "chartAxis")):
                self.issue("unsupported_axis_range", "Axis limits are not applied to pie charts.", elem)
            radius = min(w/2-12,(h-legend_h)/2-10)
            cx,cy,total,angle = w/2,(h-legend_h)/2,sum(series[0][1]),-math.pi/2
            for index,value in enumerate(series[0][1]):
                sweep = value/total*2*math.pi
                if value == 0:
                    continue
                color = colors[index%len(colors)]
                title = f"{categories[index]}: {value:g} ({value/total:.1%})"
                if math.isclose(sweep,2*math.pi):
                    parts.append(f'<circle data-chart-mark="slice" cx="{cx:g}" cy="{cy:g}" r="{radius:g}" fill="{color}"><title>{esc(title)}</title></circle>')
                else:
                    start = (cx+radius*math.cos(angle),cy+radius*math.sin(angle))
                    end = (cx+radius*math.cos(angle+sweep),cy+radius*math.sin(angle+sweep))
                    parts.append(f'<path data-chart-mark="slice" d="M {cx:g},{cy:g} L {start[0]:g},{start[1]:g} A {radius:g},{radius:g} 0 {int(sweep>math.pi)} 1 {end[0]:g},{end[1]:g} Z" fill="{color}" stroke="#FFFFFF" stroke-width="1"><title>{esc(title)}</title></path>')
                mid = angle+sweep/2
                if value/total >= 0.06 and not hide_labels:
                    parts.append(f'<text x="{cx+radius*.67*math.cos(mid):g}" y="{cy+radius*.67*math.sin(mid)+4:g}" text-anchor="middle" font-size="12" fill="#171717">{value/total:.0%}</text>')
                angle += sweep
        else:
            values = [value for _,numbers in series for value in numbers]
            left, top, pw = 42, max(12, label_size+8) if show_values else 12, w-54
            bottom = h-30-legend_h-(label_size+7 if show_values and min(values) < 0 else 0)
            ph = bottom-top
            if ph <= 0:
                self.issue("chart_labels_overflow", "The labels leave insufficient plot height; enlarge the chart.", elem, "error")
                return self.placeholder(elem, "Chart labels exceed box")
            low,high = min(0,min(values)),max(0,max(values))
            if low == high:
                high = low+1
            high += (high-low)*.08
            axes = children(find(elem,"chartPlotArea/chartAxes"),"chartAxis")
            ya = next((axis for axis in axes if axis.get("type") == "y" and axis.get("position", "left") == "left"),None)
            xa = next((axis for axis in axes if axis.get("type") == "x"),None)
            if kind == "line" or kind == "column":
                for key in ("min", "max"):
                    raw = ya.get(key) if ya is not None else None
                    if raw is not None:
                        bound = parse_float(raw, None)
                        if not re.fullmatch(r"[+-]?\d+", raw.strip()) or bound is None:
                            self.issue("invalid_axis_range", f"Y axis {key} must be a finite integer.", ya, "error")
                            return self.placeholder(elem, "Invalid axis range")
                        if key == "min":
                            low = bound
                        else:
                            high = bound
            if low >= high:
                self.issue("invalid_axis_range", "Y axis min must be less than max.", ya, "error")
                return self.placeholder(elem, "Invalid axis range")
            if any(value < low or value > high for value in values):
                self.issue("chart_data_clipped", "Data outside the configured Y-axis range is clipped; outside-range value labels are omitted.", elem)
            py = lambda value: top+ph*(high-value)/(high-low)
            baseline = py(min(high, max(low, 0)))
            ylabel,xlabel = find(ya,"chartLabel"),find(xa,"chartLabel")
            yfs = parse_float(ylabel.get("fontSize"),10) if ylabel is not None else 10
            xfs = parse_float(xlabel.get("fontSize"),10) if xlabel is not None else 10
            yc = rgba_to_hex(ylabel.get("color","#696970")) if ylabel is not None else "#696970"
            xc = rgba_to_hex(xlabel.get("color","#696970")) if xlabel is not None else "#696970"
            grid = find(ya,"chartGridLine")
            gc = rgba_to_hex(grid.get("color")) if grid is not None else "#DDDDDD"
            gw = parse_float(grid.get("width"),.5) if grid is not None else .5
            yformat = ylabel.get("format", "") if ylabel is not None else ""
            ticks = [low+(high-low)*tick/4 for tick in range(5)]
            if yformat == "0":
                # Choose readable integer ticks; preserve configured domain endpoints.
                target = max(1, (high-low)/4)
                magnitude = 10**math.floor(math.log10(target))
                tick_step = next(multiplier*magnitude for multiplier in (1, 2, 5, 10) if multiplier*magnitude >= target)
                ticks = [low]
                tick = (math.floor(low/tick_step)+1)*tick_step
                while tick < high:
                    ticks.append(tick)
                    tick += tick_step
                ticks.append(high)
            for value in ticks:
                yy = py(value)
                parts.append(f'<line x1="{left}" y1="{yy:g}" x2="{left+pw:g}" y2="{yy:g}" stroke="{gc}" stroke-width="{gw:g}"/>')
                tick_text = chart_number(value, yformat) if yformat == "0" else f"{value:.3g}"
                parts.append(f'<text data-chart-axis="y" data-axis-value="{value:g}" x="{left-6}" y="{yy+3:g}" text-anchor="end" font-size="{yfs:g}" fill="{yc}">{tick_text}</text>')
            parts.append(f'<line x1="{left}" y1="{baseline:g}" x2="{left+pw:g}" y2="{baseline:g}" stroke="#999999"/>')
            step = pw/len(categories)
            xs = [left+step*(i+.5) for i in range(len(categories))]
            for index,label in enumerate(categories):
                parts.append(f'<text data-chart-axis="x" x="{xs[index]:g}" y="{h-legend_h-13:g}" text-anchor="middle" font-size="{xfs:g}" fill="{xc}">{esc(label)}</text>')
            # Explicit width is in SVG pixels. Gap is relative to bar width within
            # each category group; automatic width also reserves that ratio between
            # adjacent groups. Uniform category centers remain fixed.
            bw, bar_gap, group_width = step*.72/len(series)*.92, step*.72/len(series)*.08, step*.72
            bar_color = None
            if bars is not None and kind == "column":
                raw_width, raw_gap = bars.get("width"), bars.get("gap")
                ratio = parse_float(raw_gap, None) if raw_gap is not None else 0
                explicit_width = parse_float(raw_width, None) if raw_width is not None else None
                if (ratio is None or not 0 <= ratio <= 1 or
                        (raw_width is not None and (explicit_width is None or not re.fullmatch(r"\+?\d+", raw_width.strip())))):
                    self.issue("invalid_chart_bars", "chartBars width must be a nonnegative integer and gap a finite ratio in [0,1].", bars, "error")
                    return self.placeholder(elem, "Invalid chart bars")
                if raw_width is not None or raw_gap is not None:
                    bw = explicit_width if raw_width is not None else step/(len(series)*(1+ratio))
                    bar_gap = bw*ratio
                    group_width = len(series)*bw+(len(series)-1)*bar_gap
                    if group_width > step+1e-8:
                        self.issue("chart_bars_overflow", "Configured bar widths and gaps exceed their category slot; reduce width or gap.", bars, "error")
                        return self.placeholder(elem, "Chart bars exceed category slot")
                    if raw_width is not None and raw_gap is not None and len(series) == 1:
                        self.issue("chart_bar_gap_approximation", "With explicit width and one series, category centers remain uniform; gap has no within-category pair to separate. Native inter-category spacing requires a Feishu screenshot.", bars)
                if bars.get("color"):
                    bar_color = rgba_to_hex(bars.get("color"))
            column_colors, column_points = colors, {}
            if kind == "column":
                resolved = self.bar_colors(plot, len(series), len(categories), colors, bar_color)
                if resolved is None:
                    return self.placeholder(elem, "Invalid column colors")
                column_colors, column_points = resolved
            self.chart_count += 1
            clip_id = f"preview-chart-clip-{self.chart_count}"
            parts.append(f'<defs><clipPath id="{clip_id}"><rect x="{left:g}" y="{top:g}" width="{pw:g}" height="{ph:g}"/></clipPath></defs>')
            parts.append(f'<g data-chart-marks="true" clip-path="url(#{clip_id})">')
            value_labels = []
            for si,(name,numbers) in enumerate(series):
                color = column_colors[si] if kind == "column" else colors[si%len(colors)]
                if kind == "column":
                    for index,value in enumerate(numbers):
                        bx = xs[index]-group_width/2+si*(bw+bar_gap)
                        by = py(min(high, max(low, value)))
                        point_color = column_points.get((si, index), color)
                        parts.append(f'<rect data-chart-mark="bar" x="{bx:g}" y="{min(by,baseline):g}" width="{bw:g}" height="{abs(by-baseline):g}" fill="{point_color}"><title>{esc(name)} / {esc(categories[index])}: {value:g}</title></rect>')
                        if show_values and low <= value <= high:
                            ly = by-5 if value >= 0 else by+label_size+4
                            value_labels.append(f'<text data-chart-value="{value:g}" x="{bx+bw/2:g}" y="{ly:g}" text-anchor="middle" font-size="{label_size:g}" fill="{label_color}">{chart_number(value,label_format)}</text>')
                else:
                    points = " ".join(f"{xx:g},{py(value):g}" for xx,value in zip(xs,numbers))
                    parts.append(f'<polyline data-chart-mark="line" points="{points}" fill="none" stroke="{color}" stroke-width="2.5"/>')
                    for index,value in enumerate(numbers):
                        parts.append(f'<circle data-chart-mark="point" cx="{xs[index]:g}" cy="{py(value):g}" r="3.5" fill="{color}"><title>{esc(name)} / {esc(categories[index])}: {value:g}</title></circle>')
            parts.append("</g>")
            parts.extend(value_labels)
        for ri,(row,row_width) in enumerate(rows):
            lx,ly = max(6,(w-row_width)/2),h-legend_h+ri*(legend_size+9)+legend_size
            for index,label,iw in row:
                legend_color = (bar_legend_colors[index] if kind == "bar" else
                                column_colors[index] if kind == "column" else colors[index%len(colors)])
                parts.append(f'<rect x="{lx:g}" y="{ly-8:g}" width="8" height="8" fill="{legend_color}"/><text x="{lx+12:g}" y="{ly:g}" font-size="{legend_size:g}" fill="#48484E">{esc(label)}</text>')
                lx += iw
        return "\n".join(parts+["</g>"])

    def bar_colors(self, plot, series_count, category_count, colors, global_color=None):
        """Resolve global, series and one-based point solid colors without other styles."""
        series_colors = [rgba_to_hex(global_color) if global_color else colors[i%len(colors)] for i in range(series_count)]
        point_colors = {}
        for config in children(find(plot, "chartSeriesList"), "chartSeries"):
            raw_index = config.get("index", "")
            if not re.fullmatch(r"\+?[1-9]\d*", raw_index) or int(raw_index) > series_count:
                self.issue("invalid_chart_series", "chartSeries index must identify an existing series, starting at 1.", config, "error")
                return None
            si = int(raw_index)-1
            settings = find(config, "chartBars")
            if settings is not None and settings.get("color"):
                series_colors[si] = rgba_to_hex(settings.get("color"))
            for point in children(settings, "chartBar"):
                raw_index = point.get("index", "")
                if not re.fullmatch(r"\+?[1-9]\d*", raw_index) or int(raw_index) > category_count:
                    self.issue("invalid_chart_bar", "chartBar index must identify an existing category, starting at 1.", point, "error")
                    return None
                if point.get("color"):
                    point_colors[si, int(raw_index)-1] = rgba_to_hex(point.get("color"))

        return series_colors, point_colors

    def horizontal_bars(self, elem, plot, categories, series, colors, w, h, legend_h,
                        show_values, label_size, label_color, label_format):
        """Approximate unstacked horizontal bars; SML x stays category, y numeric.

        Text placement, category spacing and automatic ticks are local estimates,
        not a reproduction of Feishu's chart engine. Solid fill overrides use the
        schema's one-based series/bar indices; unrelated series styles stay warned.
        """
        if find(plot, "chartExtra/chartStack") is not None:
            self.issue("unsupported_chart", "Stacked horizontal bars are not rendered by this preview.", plot)
            return None
        values = [v for _, numbers in series for v in numbers]
        axes = children(find(elem, "chartPlotArea/chartAxes"), "chartAxis")
        xa = next((a for a in axes if a.get("type") == "x"), None)
        ya = next((a for a in axes if a.get("type") == "y"), None)
        category_style, numeric_style = find(xa, "chartLabel"), find(ya, "chartLabel")
        cfs = parse_float(category_style.get("fontSize"), 10) if category_style is not None else 10
        nfs = parse_float(numeric_style.get("fontSize"), 10) if numeric_style is not None else 10
        cc = rgba_to_hex(category_style.get("color", "#696970")) if category_style is not None else "#696970"
        nc = rgba_to_hex(numeric_style.get("color", "#696970")) if numeric_style is not None else "#696970"
        numeric_format = numeric_style.get("format", "") if numeric_style is not None else ""
        low, high = min(0, min(values)), max(0, max(values))
        if low == high:
            high = low + 1
        target = (high-low)/5
        magnitude = 10**math.floor(math.log10(target))
        tick_step = next(m*magnitude for m in (1, 2, 5, 10) if m*magnitude >= target)
        low, high = math.floor(low/tick_step)*tick_step, math.ceil(high/tick_step)*tick_step
        for key in ("min", "max"):
            raw = ya.get(key) if ya is not None else None
            if raw is not None:
                bound = parse_float(raw, None)
                if bound is None or not re.fullmatch(r"[+-]?\d+", raw.strip()):
                    self.issue("invalid_axis_range", f"Y axis {key} must be a finite integer.", ya, "error")
                    return None
                if key == "min":
                    low = bound
                else:
                    high = bound
        if low >= high:
            self.issue("invalid_axis_range", "Y axis min must be less than max.", ya, "error")
            return None
        # Recompute after explicit limits so even a very wide configured domain
        # has a bounded number of ticks, and integer labels do not repeat zeros.
        target = (high-low)/5
        if numeric_format == "0":
            target = max(1, target)
        magnitude = 10**math.floor(math.log10(target))
        tick_step = next(m*magnitude for m in (1, 2, 5, 10) if m*magnitude >= target)
        if any(v < low or v > high for v in values):
            self.issue("chart_data_clipped", "Data outside the configured Y-axis range is clipped; outside-range value labels are omitted.", elem)

        text_width = lambda text, size: sum(glyph_width(c, {"fontSize": str(size)}) for c in text)
        value_width = max(text_width(chart_number(v, label_format), label_size) for v in values) if show_values else 0
        negative_space = value_width+8 if show_values and min(values) < 0 else 0
        positive_space = value_width+8 if show_values and max(values) >= 0 else 0
        category_width = max(text_width(c, cfs) for c in categories)
        left, top = max(42, category_width+12)+negative_space, 12
        pw, ph = w-left-12-positive_space, h-top-30-legend_h
        if pw <= 0 or ph <= 0:
            self.issue("chart_labels_overflow", "Horizontal category/value labels leave insufficient plot space; enlarge the chart or shorten labels.", elem, "error")
            return None
        step = ph/len(categories)
        thickness, gap = step*.72/len(series)*.92, step*.72/len(series)*.08
        global_bars = find(plot, "chartBars")
        if global_bars is not None:
            raw_width, raw_gap = global_bars.get("width"), global_bars.get("gap")
            width = parse_float(raw_width, None) if raw_width is not None else None
            ratio = parse_float(raw_gap, None) if raw_gap is not None else 0
            if ratio is None or not 0 <= ratio <= 1 or (raw_width is not None and
                    (width is None or not re.fullmatch(r"\+?\d+", raw_width.strip()))):
                self.issue("invalid_chart_bars", "chartBars width must be a nonnegative integer and gap a finite ratio in [0,1].", global_bars, "error")
                return None
            if raw_width is not None or raw_gap is not None:
                thickness = width if raw_width is not None else step/(len(series)*(1+ratio))
                gap = thickness*ratio
                if raw_width is not None and raw_gap is not None and len(series) == 1:
                    self.issue("chart_bar_gap_approximation", "With explicit width and one series, category centers remain uniform; exact native inter-category spacing requires a Feishu screenshot.", global_bars)
        group_height = len(series)*thickness+(len(series)-1)*gap
        if group_height > step+1e-8:
            self.issue("chart_bars_overflow", "Configured bar widths and gaps exceed their category slot; reduce width or gap.", global_bars, "error")
            return None

        global_color = global_bars.get("color") if global_bars is not None else None
        resolved = self.bar_colors(plot, len(series), len(categories), colors, global_color)
        if resolved is None:
            return None
        series_colors, point_colors = resolved

        px = lambda value: left+pw*(value-low)/(high-low)
        baseline = px(min(high, max(low, 0)))
        grid = find(ya, "chartGridLine")
        grid_color = rgba_to_hex(grid.get("color", "#DDDDDD")) if grid is not None else "#DDDDDD"
        grid_width = parse_float(grid.get("width"), .5) if grid is not None else .5
        ticks = [low]
        tick = (math.floor(low/tick_step)+1)*tick_step
        while tick < high:
            ticks.append(tick)
            tick += tick_step
        ticks.append(high)
        parts = []
        for value in ticks:
            xx = px(value)
            parts.append(f'<line x1="{xx:g}" y1="{top:g}" x2="{xx:g}" y2="{top+ph:g}" stroke="{grid_color}" stroke-width="{grid_width:g}"/>')
            label = chart_number(value, numeric_format) if numeric_format == "0" else f"{value:.3g}"
            parts.append(f'<text data-chart-axis="y" data-axis-value="{value:g}" x="{xx:g}" y="{top+ph+nfs+7:g}" text-anchor="middle" font-size="{nfs:g}" fill="{nc}">{label}</text>')
        parts.append(f'<line data-chart-zero-baseline="true" x1="{baseline:g}" y1="{top:g}" x2="{baseline:g}" y2="{top+ph:g}" stroke="#999999"/>')
        centers = [top+step*(i+.5) for i in range(len(categories))]
        for index, category in enumerate(categories):
            parts.append(f'<text data-chart-axis="x" x="{left-negative_space-8:g}" y="{centers[index]+cfs*.35:g}" text-anchor="end" font-size="{cfs:g}" fill="{cc}">{esc(category)}</text>')
        self.chart_count += 1
        clip_id = f"preview-chart-clip-{self.chart_count}"
        parts.append(f'<defs><clipPath id="{clip_id}"><rect x="{left:g}" y="{top:g}" width="{pw:g}" height="{ph:g}"/></clipPath></defs>')
        parts.append(f'<g data-chart-marks="true" clip-path="url(#{clip_id})">')
        labels = []
        for si, (name, numbers) in enumerate(series):
            for index, value in enumerate(numbers):
                end = px(min(high, max(low, value)))
                yy = centers[index]-group_height/2+si*(thickness+gap)
                color = point_colors.get((si, index), series_colors[si])
                parts.append(f'<rect data-chart-mark="bar" data-chart-orientation="horizontal" x="{min(end,baseline):g}" y="{yy:g}" width="{abs(end-baseline):g}" height="{thickness:g}" fill="{color}"><title>{esc(name)} / {esc(categories[index])}: {value:g}</title></rect>')
                if show_values and low <= value <= high:
                    lx, anchor = (end+6, "start") if value >= 0 else (end-6, "end")
                    labels.append(f'<text data-chart-value="{value:g}" x="{lx:g}" y="{yy+thickness/2+label_size*.35:g}" text-anchor="{anchor}" font-size="{label_size:g}" fill="{label_color}">{chart_number(value,label_format)}</text>')
        parts.append("</g>")
        parts.extend(labels)
        return parts, series_colors

    def render(self):
        root = ET.parse(self.xml_path).getroot()
        if local_name(root.tag) != "slide" or find(root,"data") is None:
            raise ValueError("Expected a <slide> root with a <data> child")
        self.audit(root)
        width,height = parse_float(root.get("width"),W),parse_float(root.get("height"),H)
        if width <= 0 or height <= 0:
            raise ValueError("Slide dimensions must be positive")
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:g}" height="{height:g}" viewBox="0 0 {width:g} {height:g}" data-preview-approximate="true">',
                 f'<title>{esc(self.xml_path.stem)} — 近似预览 / Approximate preview</title>',f'<desc>{esc(APPROXIMATION)}</desc>',
                 f'<rect width="{width:g}" height="{height:g}" fill="{self.fill(find(root,"style"))}"/>']
        for elem in find(root,"data"):
            method = {"shape":self.shape,"line":self.line,"img":self.image,"table":self.table,"chart":self.chart}.get(local_name(elem.tag))
            parts.append(method(elem) if method else self.placeholder(elem,f"Unsupported: {local_name(elem.tag)}"))
        parts.append(f'<text x="{width-8:g}" y="{height-3:g}" text-anchor="end" font-family="{FONT}" font-size="8" fill="#696970">近似预览 · 以飞书截图为准</text>')
        parts.append("<metadata>"+esc(json.dumps({"approximate":True,"issues":self.issues},ensure_ascii=False))+"</metadata>")
        return "\n".join(parts+["</svg>"])


def xml_to_svg(xml_path, out_path=None, *, assets_dir=None, diagnostics=None):
    """Compatible string-returning API; collect issues explicitly or emit to stderr."""
    renderer = Renderer(xml_path,assets_dir=assets_dir,diagnostics=diagnostics)
    svg = renderer.render()
    if out_path is not None:
        output = Path(out_path)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(svg,encoding="utf-8")
    if diagnostics is None:
        for issue in renderer.issues:
            print(f"{xml_path}: {issue['severity']}: {issue['code']}: {issue['message']}",file=sys.stderr)
    return svg


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input",type=Path,help="One SML XML slide")
    source.add_argument("--dir",type=Path,help="Directory of XML slides (non-recursive, any *.xml name)")
    parser.add_argument("--output-dir",type=Path,default=Path("preview-svg"),help="SVG output directory (default: ./preview-svg)")
    parser.add_argument("--assets-dir",type=Path,default=SKILL_ROOT/"assets",help="Fallback image root after the XML directory")
    parser.add_argument("--json",action="store_true",help="One JSON report on stdout, without mixed log output")
    args = parser.parse_args(argv)
    files = [args.input] if args.input else sorted(args.dir.glob("*.xml"))
    results = []
    if not files:
        results.append({"file":str(args.dir),"output":None,"issues":[{"severity":"error","code":"input_error","element":"slide","message":"Input directory does not exist or contains no XML files."}]})
    for xml_path in files:
        issues = []
        output = args.output_dir/(xml_path.stem+".svg")
        try:
            xml_to_svg(xml_path,output,assets_dir=args.assets_dir,diagnostics=issues)
        except (OSError,ET.ParseError,ValueError) as exc:
            issues.append({"severity":"error","code":"input_or_output_error","element":"slide","message":str(exc)})
            output = None
        results.append({"file":str(xml_path.resolve()),"output":str(output.resolve()) if output else None,"issues":issues})
    errors = sum(issue["severity"] == "error" for result in results for issue in result["issues"])
    warnings = sum(issue["severity"] == "warning" for result in results for issue in result["issues"])
    report = {"tool":"xml2svg","approximate":True,"passed":errors == 0,
              "summary":{"files":len(results),"errors":errors,"warnings":warnings},"results":results}
    if args.json:
        print(json.dumps(report,ensure_ascii=False,indent=2))
    else:
        for result in results:
            for issue in result["issues"]:
                print(f"{result['file']}: {issue['severity']}: {issue['code']}: {issue['message']}",file=sys.stderr)
        print(f"近似预览：{sum(result['output'] is not None for result in results)} SVG；{errors} errors, {warnings} warnings. Final visual acceptance requires Feishu screenshots.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
