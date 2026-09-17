#!/usr/bin/env python3
"""Minimal stdlib-only OOXML writers: .docx and .pptx.

Why hand-rolled instead of python-docx / python-pptx: both outputs are "put text
in boxes". A .docx is a zip of XML and a .pptx is the same with a fixed set of
boilerplate parts. Adding a dependency to emit paragraphs would be the wrong
trade, so this module writes the parts directly and verifies its own output.

Scope is deliberately narrow: headings, paragraphs, bullets, quotes, callouts,
tables and fixed text boxes. It does not attempt to be a general Office library,
and it never overwrites a file it did not create.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

EMU_PER_MM = 36000
EMU_PER_INCH = 914400
TWIPS_PER_MM = 1440 / 25.4
XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
STAMP = (2026, 1, 1, 0, 0, 0)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"

# ---------------------------------------------------------------- shared utils


def esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def mm_to_emu(mm):
    return int(round(float(mm) * EMU_PER_MM))


def mm_to_twips(mm):
    return int(round(float(mm) * TWIPS_PER_MM))


def slug(text, limit=48):
    out = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", str(text or "")).strip("-")
    return out[:limit] or "untitled"


def write_package(path, parts):
    """Write a deterministic OOXML zip. Refuses to clobber an existing file."""
    path = Path(path)
    if path.exists():
        raise FileExistsError("Refusing to overwrite existing file: %s" % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(parts):
            info = zipfile.ZipInfo(name, STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, parts[name].encode("utf-8"))
    return path


def verify(path):
    """Reopen the package and confirm every part is well-formed XML."""
    path = Path(path)
    problems = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "[Content_Types].xml" not in names:
            problems.append("missing [Content_Types].xml")
        for name in names:
            if not name.endswith((".xml", ".rels")):
                continue
            try:
                ElementTree.fromstring(z.read(name))
            except ElementTree.ParseError as exc:
                problems.append("%s: not well-formed (%s)" % (name, exc))
    return {"parts": len(names), "problems": problems, "ok": not problems}


# ---------------------------------------------------------------------- .docx


def _run(text, size=None, bold=False, italic=False, color=None, mono=False):
    props = []
    if bold:
        props.append("<w:b/>")
    if italic:
        props.append("<w:i/>")
    if color:
        props.append('<w:color w:val="%s"/>' % esc(color))
    if mono:
        props.append('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:eastAsia="Consolas"/>')
    if size:
        props.append('<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (size, size))
    rpr = "<w:rPr>%s</w:rPr>" % "".join(props) if props else ""
    return '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (rpr, esc(text))


def _para(text="", size=None, bold=False, italic=False, color=None, mono=False,
          align=None, before=0, after=120, indent=None, shade=None):
    ppr = ['<w:spacing w:before="%d" w:after="%d"/>' % (before, after)]
    if align:
        ppr.append('<w:jc w:val="%s"/>' % align)
    if indent:
        ppr.append('<w:ind w:left="%d"/>' % indent)
    if shade:
        ppr.append('<w:shd w:val="clear" w:fill="%s"/>' % esc(shade))
    body = _run(text, size, bold, italic, color, mono) if text != "" else ""
    return "<w:p><w:pPr>%s</w:pPr>%s</w:p>" % ("".join(ppr), body)


def _table(rows, widths=None):
    total = sum(widths) if widths else 9000
    borders = "".join(
        '<w:%s w:val="single" w:sz="4" w:space="0" w:color="C9CEDB"/>' % side
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"))
    out = ['<w:tbl><w:tblPr><w:tblW w:w="%d" w:type="dxa"/>'
           '<w:tblBorders>%s</w:tblBorders></w:tblPr>' % (total, borders)]
    if not widths:
        widths = [int(total / max(1, len(rows[0]))) for _ in rows[0]] if rows else []
    for r_index, row in enumerate(rows):
        out.append("<w:tr>")
        for c_index, cell in enumerate(row):
            width = widths[c_index] if c_index < len(widths) else widths[-1]
            shade = '<w:shd w:val="clear" w:fill="F2F4FA"/>' if r_index == 0 else ""
            out.append('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s</w:tcPr>%s</w:tc>' % (
                width, shade,
                _para(cell, size=20, bold=(r_index == 0), after=40)))
        out.append("</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


DOC_DEFAULTS = """<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Microsoft YaHei"/>
<w:sz w:val="21"/><w:szCs w:val="21"/><w:color w:val="1F2430"/>
</w:rPr></w:rPrDefault></w:docDefaults>"""


def write_docx(blocks, path, title=None):
    """blocks: list of dicts with 'kind' in title|h1|h2|h3|p|bullet|numbered|
    quote|callout|table|kv|spacer|pagebreak."""
    body = []
    if title:
        body.append(_para(title, size=40, bold=True, color="1B1035", after=200))
    for block in blocks:
        kind = block.get("kind", "p")
        text = block.get("text", "")
        if kind == "title":
            body.append(_para(text, size=36, bold=True, color="1B1035", before=180, after=160))
        elif kind == "h1":
            body.append(_para(text, size=30, bold=True, color="2A1B57", before=280, after=120))
        elif kind == "h2":
            body.append(_para(text, size=25, bold=True, color="3A2A6B", before=220, after=100))
        elif kind == "h3":
            body.append(_para(text, size=22, bold=True, color="4A3A7B", before=180, after=80))
        elif kind == "bullet":
            body.append(_para("\u2022  " + text, indent=340, after=70))
        elif kind == "numbered":
            body.append(_para("%s  " % block.get("marker", "-"), indent=340, after=70))
        elif kind == "quote":
            body.append(_para(text, italic=True, color="4A5266", indent=400, after=140))
        elif kind == "callout":
            body.append(_para(block.get("label", "提示") + "：" + text,
                              size=20, color="7A4A00", shade="FFF7E6",
                              indent=200, before=80, after=160))
        elif kind == "kv":
            body.append(_para("%s：%s" % (block.get("key", ""), text), after=70))
        elif kind == "table":
            body.append(_table(block.get("rows", []), block.get("widths")))
            body.append(_para("", after=120))
        elif kind == "spacer":
            body.append(_para("", after=200))
        elif kind == "pagebreak":
            body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        else:
            body.append(_para(text))
    body.append('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>')
    document = ('%s<w:document xmlns:w="%s">%s<w:body>%s</w:body></w:document>'
                % (XML_HEAD, W, "", "".join(body)))
    styles = ('%s<w:styles xmlns:w="%s">%s'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
              '<w:name w:val="Normal"/><w:qFormat/></w:style></w:styles>'
              % (XML_HEAD, W, DOC_DEFAULTS))
    parts = {
        "[Content_Types].xml": (
            '%s<Types xmlns="%s">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            '</Types>' % (XML_HEAD, CT)),
        "_rels/.rels": (
            '%s<Relationships xmlns="%s"><Relationship Id="rId1" Type="%s/officeDocument" '
            'Target="word/document.xml"/></Relationships>' % (XML_HEAD, PR, R)),
        "word/_rels/document.xml.rels": (
            '%s<Relationships xmlns="%s"><Relationship Id="rId1" Type="%s/styles" '
            'Target="styles.xml"/></Relationships>' % (XML_HEAD, PR, R)),
        "word/document.xml": document,
        "word/styles.xml": styles,
    }
    return write_package(path, parts)


# ---------------------------------------------------------------------- .pptx


THEME = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="%s" name="CoolAcademic">
<a:themeElements>
<a:clrScheme name="CoolAcademic">
<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>
<a:dk2><a:srgbClr val="1B1035"/></a:dk2>
<a:lt2><a:srgbClr val="F7F8FC"/></a:lt2>
<a:accent1><a:srgbClr val="5B45D6"/></a:accent1>
<a:accent2><a:srgbClr val="0EA5B7"/></a:accent2>
<a:accent3><a:srgbClr val="8B5CFF"/></a:accent3>
<a:accent4><a:srgbClr val="22D3EE"/></a:accent4>
<a:accent5><a:srgbClr val="4A3A7B"/></a:accent5>
<a:accent6><a:srgbClr val="6B7392"/></a:accent6>
<a:hlink><a:srgbClr val="0563C1"/></a:hlink>
<a:folHlink><a:srgbClr val="954F72"/></a:folHlink>
</a:clrScheme>
<a:fontScheme name="CoolAcademic">
<a:majorFont><a:latin typeface="Segoe UI"/><a:ea typeface="Microsoft YaHei"/></a:majorFont>
<a:minorFont><a:latin typeface="Segoe UI"/><a:ea typeface="Microsoft YaHei"/></a:minorFont>
</a:fontScheme>
<a:fmtScheme name="CoolAcademic">
<a:fillStyleLst>
<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
</a:fillStyleLst>
<a:lnStyleLst>
<a:ln w="6350" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>
<a:ln w="12700" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>
<a:ln w="19050" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>
</a:lnStyleLst>
<a:effectStyleLst>
<a:effectStyle><a:effectLst/></a:effectStyle>
<a:effectStyle><a:effectLst/></a:effectStyle>
<a:effectStyle><a:effectLst/></a:effectStyle>
</a:effectStyleLst>
<a:bgFillStyleLst>
<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
</a:bgFillStyleLst>
</a:fmtScheme>
</a:themeElements>
</a:theme>""" % A

MASTER = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="%s" xmlns:r="%s" xmlns:p="%s">
<p:cSld><p:spTree>
<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
</p:spTree></p:cSld>
<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2"
accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6"
hlink="hlink" folHlink="folHlink"/>
<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>
</p:sldMaster>""" % (A, R, P)

LAYOUT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="%s" xmlns:r="%s" xmlns:p="%s" type="blank" preserve="1">
<p:cSld name="Blank"><p:spTree>
<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
</p:spTree></p:cSld>
<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>""" % (A, R, P)


def _tx_body(paragraphs):
    out = ['<p:txBody><a:bodyPr wrap="square" lIns="45720" tIns="27432" '
           'rIns="45720" bIns="27432"><a:noAutofit/></a:bodyPr><a:lstStyle/>']
    for para in paragraphs:
        size = int(round(float(para.get("size", 18)) * 100))
        align = para.get("align", "l")
        rpr = ['<a:rPr lang="zh-CN" altLang="en-US" sz="%d" b="%d" dirty="0">'
               % (size, 1 if para.get("bold") else 0)]
        rpr.append('<a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
                   % esc(para.get("color", "1F2430")))
        rpr.append('<a:latin typeface="%s"/><a:ea typeface="%s"/></a:rPr>'
                   % (esc(para.get("font", "Segoe UI")), esc(para.get("font_ea", "Microsoft YaHei"))))
        bullet = '<a:buChar char="\u2022"/>' if para.get("bullet") else '<a:buNone/>'
        out.append('<a:p><a:pPr algn="%s"><a:lnSpc><a:spcPct val="%d"/></a:lnSpc>%s'
                   '<a:spcAft><a:spcPts val="%d"/></a:spcAft></a:pPr>'
                   '<a:r>%s<a:t>%s</a:t></a:r></a:p>'
                   % (align, int(float(para.get("line", 1.15)) * 100000), bullet,
                      int(float(para.get("after", 6)) * 100), "".join(rpr), esc(para["text"])))
    out.append("</p:txBody>")
    return "".join(out)


def _shape(shape_id, box):
    x, y = int(box["x"]), int(box["y"])
    cx, cy = int(box["cx"]), int(box["cy"])
    fill = box.get("fill")
    geom = box.get("geom", "rect")
    if fill:
        fill_xml = '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>' % esc(fill)
        geom_xml = '<a:prstGeom prst="%s"><a:avLst/></a:prstGeom>' % esc(geom)
    else:
        fill_xml = "<a:noFill/>"
        geom_xml = '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
    return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            '<p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>%s%s'
            '<a:ln><a:noFill/></a:ln></p:spPr>%s</p:sp>'
            % (shape_id, esc(box.get("name", "box%d" % shape_id)), x, y, cx, cy,
               geom_xml, fill_xml, _tx_body(box.get("paragraphs", []))))


def write_pptx_slide(spec, path):
    """spec: {width_emu, height_emu, background, boxes:[...]} - exactly one slide."""
    cw, ch = int(spec["width_emu"]), int(spec["height_emu"])
    bg = esc(spec.get("background", "FFFFFF"))
    shapes = "".join(_shape(i + 2, box) for i, box in enumerate(spec.get("boxes", [])))
    slide = ('%s<p:sld xmlns:a="%s" xmlns:r="%s" xmlns:p="%s"><p:cSld>'
             '<p:bg><p:bgPr><a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
             '<a:effectLst/></p:bgPr></p:bg><p:spTree>'
             '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
             '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
             '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
             '%s</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
             % (XML_HEAD, A, R, P, bg, shapes))
    presentation = ('%s<p:presentation xmlns:a="%s" xmlns:r="%s" xmlns:p="%s" saveSubsetFonts="1">'
                    '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
                    '<p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst>'
                    '<p:sldSz cx="%d" cy="%d"/><p:notesSz cx="6858000" cy="9144000"/>'
                    '</p:presentation>' % (XML_HEAD, A, R, P, cw, ch))
    parts = {
        "[Content_Types].xml": (
            '%s<Types xmlns="%s">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
            '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
            '<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
            '</Types>' % (XML_HEAD, CT)),
        "_rels/.rels": (
            '%s<Relationships xmlns="%s"><Relationship Id="rId1" Type="%s/officeDocument" '
            'Target="ppt/presentation.xml"/></Relationships>' % (XML_HEAD, PR, R)),
        "ppt/_rels/presentation.xml.rels": (
            '%s<Relationships xmlns="%s">'
            '<Relationship Id="rId1" Type="%s/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
            '<Relationship Id="rId2" Type="%s/slide" Target="slides/slide1.xml"/>'
            '<Relationship Id="rId3" Type="%s/theme" Target="theme/theme1.xml"/>'
            '</Relationships>' % (XML_HEAD, PR, R, R, R)),
        "ppt/slideMasters/_rels/slideMaster1.xml.rels": (
            '%s<Relationships xmlns="%s">'
            '<Relationship Id="rId1" Type="%s/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            '<Relationship Id="rId2" Type="%s/theme" Target="../theme/theme1.xml"/>'
            '</Relationships>' % (XML_HEAD, PR, R, R)),
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": (
            '%s<Relationships xmlns="%s">'
            '<Relationship Id="rId1" Type="%s/slideMaster" Target="../slideMasters/slideMaster1.xml"/>'
            '</Relationships>' % (XML_HEAD, PR, R)),
        "ppt/slides/_rels/slide1.xml.rels": (
            '%s<Relationships xmlns="%s">'
            '<Relationship Id="rId1" Type="%s/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            '</Relationships>' % (XML_HEAD, PR, R)),
        "ppt/presentation.xml": presentation,
        "ppt/slideMasters/slideMaster1.xml": MASTER,
        "ppt/slideLayouts/slideLayout1.xml": LAYOUT,
        "ppt/slides/slide1.xml": slide,
        "ppt/theme/theme1.xml": THEME,
    }
    return write_package(path, parts)


# ----------------------------------------------------------------------- CLI


def build_docx_from_spec(spec, out):
    blocks = spec.get("blocks", [])
    if not blocks:
        raise ValueError("spec has no blocks")
    return write_docx(blocks, out, title=spec.get("title"))


def build_pptx_from_spec(spec, out):
    return write_pptx_slide(spec, out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Minimal stdlib OOXML writers")
    sub = ap.add_subparsers(dest="command", required=True)

    d = sub.add_parser("docx", help="build a .docx from a spec")
    d.add_argument("spec")
    d.add_argument("out")

    p = sub.add_parser("pptx", help="build a one-slide .pptx from a spec")
    p.add_argument("spec")
    p.add_argument("out")

    v = sub.add_parser("verify", help="check a built package is well-formed")
    v.add_argument("target")

    args = ap.parse_args(argv)
    try:
        if args.command == "docx":
            spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
            target = build_docx_from_spec(spec, args.out)
            print("wrote %s" % target)
            print(json.dumps(verify(target), indent=2))
            return 0
        if args.command == "pptx":
            spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
            target = build_pptx_from_spec(spec, args.out)
            print("wrote %s" % target)
            print(json.dumps(verify(target), indent=2))
            return 0
        print(json.dumps(verify(args.target), indent=2))
        return 0
    except (OSError, ValueError, KeyError, FileExistsError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
