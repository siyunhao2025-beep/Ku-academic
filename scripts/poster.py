#!/usr/bin/env python3
"""Poster creation with three mandatory upfront choices.

The flow mirrors the slide workflow, with one hard difference: nothing is produced
until the user has chosen (1) size, (2) language and (3) output form. `plan`
refuses to write a spec while any of the three is missing, and `choices` exists so
the agent has one canonical, quotable list to present instead of inventing options.

Output forms:
  image -> a print-ready SVG at exact physical dimensions (1 unit = 1 mm)
  ppt   -> a one-slide .pptx at the same physical size, via scripts/ooxml.py

Colour never carries information on its own: every palette is paired with a
rule that a second channel (label, rule line, weight) must also mark the same
distinction. A layout that overlaps is reported, never silently accepted.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ooxml  # noqa: E402

MM_PER_INCH = 25.4

SIZES = {
    "a0": {"label": "A0（841 × 1189 mm）", "mm": (841, 1189), "use": "标准学术海报，会场最常用"},
    "a1": {"label": "A1（594 × 841 mm）", "mm": (594, 841), "use": "场地较小或内容较少的海报"},
    "a2": {"label": "A2（420 × 594 mm）", "mm": (420, 594), "use": "组会、走廊展示"},
    "a3": {"label": "A3（297 × 420 mm）", "mm": (297, 420), "use": "打印店随手出，A3 打印机可出"},
    "a4": {"label": "A4（210 × 297 mm）", "mm": (210, 297), "use": "贴墙小样、打印预检，不是正式海报尺寸"},
    "conf-90x120": {"label": "大会标准竖版（900 × 1200 mm）", "mm": (900, 1200), "use": "国内学术会议常见竖版"},
    "conf-120x90": {"label": "大会标准横版（1200 × 900 mm）", "mm": (1200, 900), "use": "国内学术会议常见横版"},
    "screen-16x9": {"label": "屏幕 16:9（1920 × 1080 px 等效）", "mm": (338.7, 190.5), "use": "投屏、线上展示、社交媒体"},
}
ORIENTATIONS = ("auto", "portrait", "landscape")
LANGUAGES = {"zh": "中文", "en": "English"}
OUTPUTS = {
    "image": "直接输出图片（SVG，1 单位 = 1 mm，可直接送印）",
    "ppt": "输出为 PPT（单页 .pptx，尺寸与海报一致，便于继续编辑）",
}
PALETTES = {
    "research": {"bg": "FFFFFF", "band": "1B1035", "band_text": "FFFFFF",
                 "heading": "2A1B57", "body": "1F2430", "rule": "C9CEDB", "accent": "5B45D6"},
    "vivid": {"bg": "FFFFFF", "band": "2B1055", "band_text": "FFFFFF",
              "heading": "5B21B6", "body": "1F2430", "rule": "D8CCF5", "accent": "0EA5B7"},
    "minimal": {"bg": "FFFFFF", "band": "F2F4FA", "band_text": "1B1035",
                "heading": "1F2430", "body": "3A4155", "rule": "D5DAE6", "accent": "5B45D6"},
}
PLACEHOLDER_MARK = "⟨在此填写⟩"


def resolve_size(size, orientation):
    if size not in SIZES:
        raise ValueError("unknown size '%s'; choose one of: %s" % (size, ", ".join(sorted(SIZES))))
    if orientation not in ORIENTATIONS:
        raise ValueError("orientation must be one of: " + ", ".join(ORIENTATIONS))
    w, h = SIZES[size]["mm"]
    if orientation == "auto":
        # Respect the size as named: conf-120x90 is landscape, conf-90x120 is portrait.
        return float(w), float(h)
    if orientation == "landscape" and h > w:
        w, h = h, w
    elif orientation == "portrait" and w > h:
        w, h = h, w
    return float(w), float(h)


def scale_for(w, h):
    base = math.sqrt(841 * 1189)
    return max(0.35, min(1.2, math.sqrt(w * h) / base))


def default_blocks(lang, palette):
    zh = lang == "zh"
    return [
        {"role": "title", "text": PLACEHOLDER_MARK + "海报主标题" if zh else PLACEHOLDER_MARK + "Poster title"},
        {"role": "byline", "text": PLACEHOLDER_MARK + "作者 · 单位 · 邮箱" if zh
            else PLACEHOLDER_MARK + "Authors · Affiliation · Email"},
        {"role": "section", "heading": "研究问题" if zh else "Research question",
         "text": PLACEHOLDER_MARK + "一句话讲清你要回答什么。" if zh
            else PLACEHOLDER_MARK + "State the one question you answer."},
        {"role": "bullets", "heading": "方法" if zh else "Methods",
         "items": [PLACEHOLDER_MARK + "数据来源与范围", PLACEHOLDER_MARK + "处理与关键参数",
                   PLACEHOLDER_MARK + "不确定度口径"] if zh
            else [PLACEHOLDER_MARK + "Data source and coverage", PLACEHOLDER_MARK + "Processing and key parameters",
                  PLACEHOLDER_MARK + "Uncertainty definition"]},
        {"role": "section", "heading": "主要结果" if zh else "Key results",
         "text": PLACEHOLDER_MARK + "给出数值与条件，不要只给形容词。" if zh
            else PLACEHOLDER_MARK + "Give numbers and conditions, not adjectives."},
        {"role": "figure", "heading": "图 1" if zh else "Figure 1",
         "text": PLACEHOLDER_MARK + "把图放在这里；图注需自足。" if zh
            else PLACEHOLDER_MARK + "Place the figure here; the caption must stand alone."},
        {"role": "takeaway", "heading": "结论" if zh else "Takeaway",
         "text": PLACEHOLDER_MARK + "一句话结论，以及你没有回答什么。" if zh
            else PLACEHOLDER_MARK + "One-sentence conclusion, and what you did not answer."},
        {"role": "footer", "text": PLACEHOLDER_MARK + "致谢 · 数据与代码可得性" if zh
            else PLACEHOLDER_MARK + "Acknowledgements · Data and code availability"},
    ]


# ------------------------------------------------------------------- layout


def _wrap(text, box_w_mm, font_mm):
    """Rough CJK-aware wrap: CJK glyphs are ~1em wide, latin ~0.52em."""
    if not text:
        return 1
    per_line = max(8, int(box_w_mm / (font_mm * 0.95)))
    count, line = 0, 0.0
    for ch in text:
        cost = 1.0 if ord(ch) > 0x2E7F else 0.55
        if line + cost > per_line:
            count += 1
            line = cost
        else:
            line += cost
    return count + 1


def _block_height(block, box_w, s, fonts):
    pad = 4 * s
    if block["role"] == "title":
        return _wrap(block["text"], box_w, fonts["title"]) * fonts["title"] * 1.18 + pad * 2
    if block["role"] == "byline":
        return fonts["byline"] * 1.5 + pad
    if block["role"] == "footer":
        return fonts["footer"] * 1.6 + pad
    head = fonts["heading"] * 1.35 + 2 * s if block.get("heading") else 0
    if block["role"] == "bullets":
        item_h = sum(_wrap(i, box_w - 6 * s, fonts["body"]) * fonts["body"] * 1.32 + 2.4 * s
                     for i in block.get("items", []))
        return head + item_h + pad * 2
    body_h = _wrap(block.get("text", ""), box_w, fonts["body"]) * fonts["body"] * 1.32
    if block["role"] == "takeaway":
        body_h += 3 * s
    return head + body_h + pad * 2


def layout(spec):
    w, h = float(spec["width_mm"]), float(spec["height_mm"])
    s = scale_for(w, h)
    margin = max(12.0, 26.0 * s)
    fonts = {"title": 26 * s, "byline": 8.5 * s, "heading": 11 * s,
             "body": 7.2 * s, "footer": 5.6 * s}
    blocks = spec["blocks"]
    boxes = []

    i = 0
    if blocks and blocks[0]["role"] == "title":
        blk = blocks[0]
        bh = _block_height(blk, w - margin * 2, s, fonts)
        boxes.append({"block": blk, "x": 0, "y": 0, "w": w, "h": bh + margin * 0.6,
                      "font": fonts["title"], "role": "title"})
        i = 1
    if i < len(blocks) and blocks[i]["role"] == "byline":
        blk = blocks[i]
        bh = _block_height(blk, w - margin * 2, s, fonts)
        top = boxes[-1]["y"] + boxes[-1]["h"] if boxes else 0
        boxes.append({"block": blk, "x": 0, "y": top, "w": w, "h": bh,
                      "font": fonts["byline"], "role": "byline"})
        i += 1

    footer = None
    if blocks and blocks[-1]["role"] == "footer":
        footer = blocks[-1]
        end = len(blocks) - 1
    else:
        end = len(blocks)

    flow = [b for b in blocks[i:end] if b["role"] != "footer"]
    top = boxes[-1]["y"] + boxes[-1]["h"] + margin * 0.6 if boxes else margin
    footer_h = _block_height(footer, w - margin * 2, s, fonts) + margin * 0.5 if footer else 0
    avail_h = h - top - footer_h - margin * 0.5
    avail_w = w - margin * 2

    n_cols = 2 if avail_w / max(1e-6, avail_h) < 1.4 else 3
    if w > h * 1.15:
        n_cols = 3
    gap = margin * 0.5
    col_w = (avail_w - gap * (n_cols - 1)) / n_cols

    col_y = [top] * n_cols
    for blk in flow:
        bh = _block_height(blk, col_w - 8 * s, s, fonts)
        target = min(range(n_cols), key=lambda c: (col_y[c], c))
        boxes.append({"block": blk, "x": margin + target * (col_w + gap), "y": col_y[target],
                      "w": col_w, "h": bh, "font": fonts["body"], "role": blk["role"]})
        col_y[target] += bh + gap * 0.8

    if footer:
        boxes.append({"block": footer, "x": 0, "y": h - footer_h, "w": w, "h": footer_h,
                      "font": fonts["footer"], "role": "footer"})

    spec["_metrics"] = {"scale": round(s, 4), "columns": n_cols, "margin_mm": round(margin, 2),
                        "fonts_mm": {k: round(v, 2) for k, v in fonts.items()},
                        "content_bottom_mm": round(max(col_y), 2),
                        "usable_bottom_mm": round(h - footer_h - margin * 0.5, 2),
                        "fill_ratio": round(max(col_y) / max(1e-6, h - footer_h - margin * 0.5), 3)}
    return boxes


def _overlaps(boxes):
    pairs = []
    for a in range(len(boxes)):
        for b in range(a + 1, len(boxes)):
            p, q = boxes[a], boxes[b]
            if p["x"] < q["x"] + q["w"] and q["x"] < p["x"] + p["w"] and \
               p["y"] < q["y"] + q["h"] and q["y"] < p["y"] + p["h"]:
                pairs.append("%s x %s" % (p["role"], q["role"]))
    return pairs


def placeholders_remaining(spec):
    found = []
    for index, blk in enumerate(spec["blocks"]):
        texts = [blk.get("text", "")] + list(blk.get("items", []))
        if any(PLACEHOLDER_MARK in str(t) for t in texts):
            found.append(blk.get("heading") or blk.get("role") or ("block %d" % index))
    return found


# ------------------------------------------------------------------ render


def render_svg(spec, boxes, path):
    w, h = float(spec["width_mm"]), float(spec["height_mm"])
    pal = PALETTES[spec.get("palette", "research")]
    parts = ['%s<svg xmlns="http://www.w3.org/2000/svg" width="%smm" height="%smm" '
             'viewBox="0 0 %s %s" role="img" aria-label="%s">'
             % (ooxml.XML_HEAD, w, h, w, h, ooxml.esc(spec.get("title", "poster"))),
             '<rect width="%s" height="%s" fill="#%s"/>' % (w, h, pal["bg"])]
    font = ("Segoe UI, Microsoft YaHei, PingFang SC, Noto Sans CJK SC, "
            "Helvetica Neue, Arial, sans-serif")
    for box in boxes:
        blk, x, y, bw = box["block"], box["x"], box["y"], box["w"]
        pad = box["font"] * 0.5
        if box["role"] == "title":
            parts.append('<rect x="0" y="0" width="%s" height="%s" fill="#%s"/>'
                         % (w, box["h"] + box["y"], pal["band"]))
            parts.append('<text x="%s" y="%s" font-family="%s" font-size="%s" font-weight="700" '
                         'fill="#%s">%s</text>'
                         % (x + 26 * spec["_metrics"]["scale"], y + box["font"] * 1.15, font,
                            round(box["font"], 2), pal["band_text"], ooxml.esc(blk["text"])))
        elif box["role"] == "byline":
            parts.append('<text x="%s" y="%s" font-family="%s" font-size="%s" fill="#%s">%s</text>'
                         % (x + 26 * spec["_metrics"]["scale"], y + box["font"], font,
                            round(box["font"], 2), pal["body"], ooxml.esc(blk["text"])))
        else:
            cy = y + pad
            if blk.get("heading"):
                cy += box["font"] * 1.1
                parts.append('<text x="%s" y="%s" font-family="%s" font-size="%s" '
                             'font-weight="700" fill="#%s">%s</text>'
                             % (x + pad, cy, font, round(box["font"] * 1.32, 2),
                                pal["heading"], ooxml.esc(blk["heading"])))
                cy += box["font"] * 0.25
                parts.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="#%s" stroke-width="%s"/>'
                             % (x + pad, cy, x + bw - pad, cy, pal["rule"],
                                round(max(0.3, box["font"] * 0.08), 2)))
                cy += box["font"] * 0.85
            if box["role"] == "bullets":
                for item in blk.get("items", []):
                    parts.append('<circle cx="%s" cy="%s" r="%s" fill="#%s"/>'
                                 % (x + pad + box["font"] * 0.3, cy - box["font"] * 0.3,
                                    round(box["font"] * 0.16, 2), pal["accent"]))
                    parts.append('<text x="%s" y="%s" font-family="%s" font-size="%s" fill="#%s">%s</text>'
                                 % (x + pad + box["font"] * 0.85, cy, font,
                                    round(box["font"], 2), pal["body"], ooxml.esc(item)))
                    cy += box["font"] * 1.32 + 2.4 * spec["_metrics"]["scale"]
            else:
                if box["role"] == "takeaway":
                    parts.append('<rect x="%s" y="%s" width="%s" height="%s" fill="#%s" '
                                 'stroke="#%s" stroke-width="%s"/>'
                                 % (x + pad, y + pad * 0.5, bw - pad * 2, box["h"] - pad,
                                    pal["bg"], pal["accent"],
                                    round(max(0.4, box["font"] * 0.1), 2)))
                for line in _split_lines(blk.get("text", ""), bw - pad * 2, box["font"]):
                    parts.append('<text x="%s" y="%s" font-family="%s" font-size="%s" fill="#%s">%s</text>'
                                 % (x + pad, cy, font, round(box["font"], 2), pal["body"],
                                    ooxml.esc(line)))
                    cy += box["font"] * 1.32
    parts.append("</svg>")
    path = Path(path)
    if path.exists():
        raise FileExistsError("Refusing to overwrite existing file: %s" % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return path


def _split_lines(text, box_w_mm, font_mm):
    limit = max(8, int(box_w_mm / (font_mm * 0.95)))
    lines, line, width = [], "", 0.0
    for ch in str(text):
        cost = 1.0 if ord(ch) > 0x2E7F else 0.55
        if width + cost > limit:
            lines.append(line)
            line, width = ch, cost
        else:
            line += ch
            width += cost
    if line:
        lines.append(line)
    return lines or [""]


def render_pptx(spec, boxes, path):
    pal = PALETTES[spec.get("palette", "research")]
    s = spec["_metrics"]["scale"]
    out_boxes = []
    for box in boxes:
        blk = box["block"]
        paras = []
        if box["role"] == "title":
            paras.append({"text": blk["text"], "size": box["font"] * 72 / MM_PER_INCH,
                          "bold": True, "color": pal["band_text"], "align": "l", "line": 1.05})
        elif box["role"] == "byline":
            paras.append({"text": blk["text"], "size": box["font"] * 72 / MM_PER_INCH,
                          "color": pal["body"], "line": 1.1})
        else:
            if blk.get("heading"):
                paras.append({"text": blk["heading"], "size": box["font"] * 72 / MM_PER_INCH * 1.32,
                              "bold": True, "color": pal["heading"], "line": 1.1, "after": 3})
            if box["role"] == "bullets":
                for item in blk.get("items", []):
                    paras.append({"text": item, "size": box["font"] * 72 / MM_PER_INCH,
                                  "color": pal["body"], "bullet": True, "line": 1.2, "after": 4})
            else:
                paras.append({"text": blk.get("text", ""), "size": box["font"] * 72 / MM_PER_INCH,
                              "color": pal["body"], "line": 1.25})
        fill = None
        if box["role"] in ("title", "footer"):
            fill = pal["band"]
        out_boxes.append({
            "name": box["role"],
            "x": ooxml.mm_to_emu(box["x"]), "y": ooxml.mm_to_emu(box["y"]),
            "cx": ooxml.mm_to_emu(box["w"]), "cy": ooxml.mm_to_emu(box["h"]),
            "fill": fill, "paragraphs": paras,
        })
    spec_pptx = {
        "width_emu": ooxml.mm_to_emu(spec["width_mm"]),
        "height_emu": ooxml.mm_to_emu(spec["height_mm"]),
        "background": pal["bg"],
        "boxes": out_boxes,
    }
    return ooxml.write_pptx_slide(spec_pptx, path)


def choices_payload():
    return {
        "question_1_size": [{"id": k, "label": v["label"], "use": v["use"]}
                            for k, v in SIZES.items()],
        "question_1_orientation": list(ORIENTATIONS),
        "question_2_language": [{"id": k, "label": v} for k, v in LANGUAGES.items()],
        "question_3_output": [{"id": k, "label": v} for k, v in OUTPUTS.items()],
        "rule": ("All three must be chosen by the user before anything is produced. "
                 "Do not assume a default, and do not start rendering on a partial answer."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Poster creation (three upfront choices required)")
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("choices", help="print the three choice sets to present to the user")

    p = sub.add_parser("plan", help="build a poster spec; refuses while a choice is missing")
    p.add_argument("--size", default=None)
    p.add_argument("--orientation", default="auto")
    p.add_argument("--lang", default=None)
    p.add_argument("--output", default=None, choices=sorted(OUTPUTS))
    p.add_argument("--title", default="")
    p.add_argument("--palette", default="research", choices=sorted(PALETTES))
    p.add_argument("--content", default=None, help="optional JSON file overriding the block scaffold")
    p.add_argument("--out", required=True)

    r = sub.add_parser("render", help="render a spec to SVG or PPTX")
    r.add_argument("spec")
    r.add_argument("--out", required=True)
    r.add_argument("--strict", action="store_true", help="exit 2 if placeholders remain")

    args = ap.parse_args(argv)
    try:
        if args.command == "choices":
            print(json.dumps(choices_payload(), indent=2, ensure_ascii=False))
            return 0

        if args.command == "plan":
            missing = []
            if not args.size:
                missing.append("海报尺寸 (--size)")
            if not args.lang:
                missing.append("海报语言 (--lang)")
            if not args.output:
                missing.append("输出形式 (--output)")
            if missing:
                raise ValueError(
                    "three choices are required before any poster work starts; still missing: "
                    + "; ".join(missing)
                    + "\nRun `python scripts/poster.py choices` to see the canonical option list, "
                      "then ask the user to pick. Do not assume a default.")
            if args.lang not in LANGUAGES:
                raise ValueError("language must be one of: " + ", ".join(LANGUAGES))
            w, h = resolve_size(args.size, args.orientation)
            blocks = default_blocks(args.lang, args.palette)
            if args.content:
                override = json.loads(Path(args.content).read_text(encoding="utf-8"))
                blocks = override.get("blocks", blocks)
                if override.get("title"):
                    blocks[0]["text"] = override["title"]
            if args.title:
                blocks[0]["text"] = args.title
            spec = {
                "kind": "poster",
                "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "size_id": args.size,
                "orientation": args.orientation,
                "width_mm": w, "height_mm": h,
                "language": args.lang,
                "output": args.output,
                "palette": args.palette,
                "title": blocks[0]["text"],
                "blocks": blocks,
                "colour_rule": ("Palettes are print-safe and never encode information in hue alone: "
                                "every distinction is also carried by a label, rule line or weight."),
            }
            write_json(args.out, spec)
            print("spec: %s  (%s x %s mm, %s, %s -> %s)"
                  % (args.out, w, h, args.size, args.lang, args.output))
            return 0

        spec = read_json(args.spec)
        for key in ("size_id", "language", "output", "width_mm", "height_mm"):
            if not spec.get(key):
                raise ValueError("spec is missing required field: %s" % key)
        boxes = layout(spec)
        overlaps = _overlaps(boxes)
        missing = placeholders_remaining(spec)
        spec["_metrics"]["overlaps"] = overlaps
        spec["_metrics"]["placeholders_remaining"] = missing
        spec["_metrics"]["printed_mm"] = "%s x %s" % (spec["width_mm"], spec["height_mm"])

        target = Path(args.out)
        if spec["output"] == "image":
            render_svg(spec, boxes, target)
        else:
            render_pptx(spec, boxes, target)
        write_json(args.spec, spec)

        print("poster: %s" % target)
        print("size: %s mm (%s, %s) | columns: %d | palette: %s"
              % (spec["_metrics"]["printed_mm"], spec["size_id"], spec["language"],
                 spec["_metrics"]["columns"], spec["palette"]))
        print("output form: %s" % spec["output"])
        print("overlaps: %s" % (", ".join(overlaps) if overlaps else "none"))
        print("content bottom: %s mm / usable %s mm (fill %d%%)"
              % (spec["_metrics"]["content_bottom_mm"], spec["_metrics"]["usable_bottom_mm"],
                 round(spec["_metrics"]["fill_ratio"] * 100)))
        if spec["_metrics"]["fill_ratio"] < 0.7:
            print("NOTE: content fills only %d%% of the usable height; a real poster usually "
                  "carries more evidence per section." % round(spec["_metrics"]["fill_ratio"] * 100))
        if missing:
            print("WARNING: %d block(s) still hold placeholder text: %s"
                  % (len(missing), ", ".join(missing)))
            print("WARNING: this is a layout scaffold, not a finished poster. Fill it before use.")
            if args.strict:
                return 2
        if overlaps:
            print("WARNING: boxes overlap; adjust blocks or pick a larger size.")
            return 2
        return 0
    except (OSError, ValueError, KeyError, FileExistsError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
