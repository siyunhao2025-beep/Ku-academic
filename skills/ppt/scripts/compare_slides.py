#!/usr/bin/env python3
"""Report a conservative, offline three-way comparison of Slides XML.

This tool never generates merged XML or performs network operations. IDs must
come from actual readback snapshots. A conflict-free report does not authorize
overwriting a whole remote page and provides no server concurrency guarantee.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def local(tag):
    return tag.rsplit("}", 1)[-1]


def canonical(node, in_text=False):
    """Ignore prefix/attribute order and layout whitespace, preserve text runs."""
    if node is None:
        return None
    textual = in_text or local(node.tag) in {"p", "span", "chartField"}
    def text_value(value, preserve):
        if value is None:
            return ""
        return value if preserve or value.strip() else ""
    return (node.tag, tuple(sorted(node.attrib.items())), text_value(node.text, textual),
            tuple((canonical(child, textual), text_value(child.tail, textual)) for child in node))


def describe(node):
    if node is None:
        return None
    return {"type": local(node.tag), "attributes": dict(sorted(node.attrib.items())),
            "colors": [{"element": local(n.tag), "attribute": key, "value": value}
                       for n in node.iter() for key, value in n.attrib.items() if key in {"color", "backgroundColor"}],
            "text": ["".join(n.itertext()) for n in node.iter() if local(n.tag) == "p"],
            "images": [{"src": n.get("src", ""), "id": n.get("id"),
                        "geometry": {k: n.get(k) for k in ("topLeftX", "topLeftY", "width", "height") if k in n.attrib}}
                       for n in node.iter() if local(n.tag) == "img"],
            "chart_data": [{"name": n.get("name"), "value": "".join(n.itertext())}
                           for n in node.iter() if local(n.tag) == "chartField"]}


def identifier(node):
    return node.get("id") or node.get("slide_id") or node.get("slideId")


def load_snapshot(path, label):
    root = ET.parse(path).getroot()
    slide_nodes = [n for n in root.iter() if local(n.tag) == "slide"]
    if not slide_nodes:
        raise ValueError(f"{label}: no slide elements found")
    slides, order, problems, summaries = {}, [], [], []
    for position, slide in enumerate(slide_nodes, 1):
        sid = identifier(slide)
        order.append(sid)
        data = [n for n in slide if local(n.tag) == "data"]
        if len(data) != 1:
            problems.append({"snapshot": label, "slide_id": sid, "code": "ambiguous_data_container", "position": position})
        blocks, block_order = {}, []
        for container in data:
            for child in container:
                bid = child.get("id")
                block_order.append(bid)
                if not bid:
                    problems.append({"snapshot": label, "slide_id": sid, "code": "missing_block_id", "type": local(child.tag), "position": len(block_order)})
                elif bid in blocks:
                    problems.append({"snapshot": label, "slide_id": sid, "block_id": bid, "code": "duplicate_block_id"})
                else:
                    blocks[bid] = child
        metadata = ET.Element(slide.tag, {k: v for k, v in slide.attrib.items() if k not in {"revision_id", "revisionId"}})
        for child in slide:
            if local(child.tag) != "data":
                metadata.append(child)
            else:
                metadata.append(ET.Element(child.tag, child.attrib))
        summary = {"slide_id": sid, "block_order": block_order, **describe(slide)}
        summaries.append(summary)
        if not sid:
            problems.append({"snapshot": label, "code": "missing_slide_id", "position": position})
        elif sid in slides:
            problems.append({"snapshot": label, "slide_id": sid, "code": "duplicate_slide_id"})
        else:
            slides[sid] = {"node": slide, "metadata": metadata, "blocks": blocks, "block_order": block_order}
    return {"slides": slides, "order": order, "problems": problems,
            "summary": {"path": str(Path(path).resolve()), "slide_order": order, "slides": summaries}}


def relation(baseline, working, remote):
    wc, rc = working != baseline, remote != baseline
    if not wc and not rc:
        return "unchanged"
    if wc and not rc:
        return "working_only"
    if rc and not wc:
        return "remote_only"
    return "same_change" if working == remote else "conflict"


def compare(baseline_path, working_path, remote_path):
    snapshots = {name: load_snapshot(path, name) for name, path in
                 (("baseline", baseline_path), ("working", working_path), ("remote", remote_path))}
    b, w, r = [snapshots[name] for name in ("baseline", "working", "remote")]
    problems = [p for snap in snapshots.values() for p in snap["problems"]]
    changes = []

    def record(kind, sid, bid, before, working, remote, describe_nodes=True):
        values = [canonical(x) for x in (before, working, remote)] if describe_nodes else [before, working, remote]
        rel = relation(*values)
        if rel == "unchanged":
            return
        entry = {"kind": kind, "slide_id": sid, "block_id": bid, "relation": rel,
                 "conflict": rel == "conflict"}
        for name, value in zip(("baseline", "working", "remote"), (before, working, remote)):
            entry[name] = describe(value) if describe_nodes else value
        changes.append(entry)

    # Missing/duplicate IDs cannot be made safe by comparing array positions.
    # Still provide summaries, but no block-based conclusions for ambiguous input.
    if not problems:
        record("slide_order", None, None, b["order"], w["order"], r["order"], False)
        for sid in sorted(set(b["slides"]) | set(w["slides"]) | set(r["slides"])):
            pages = [snap["slides"].get(sid) for snap in (b, w, r)]
            if any(page is None for page in pages):
                record("slide_presence", sid, None, *[p["node"] if p else None for p in pages])
                continue
            bp, wp, rp = pages
            record("slide_metadata", sid, None, *[p["metadata"] for p in pages])
            record("block_order", sid, None, *[p["block_order"] for p in pages], describe_nodes=False)
            for bid in sorted(set(bp["blocks"]) | set(wp["blocks"]) | set(rp["blocks"])):
                record("block", sid, bid, *[p["blocks"].get(bid) for p in pages])
    conflicts = [c for c in changes if c["conflict"]]
    status = "manual_review" if problems else "conflicts" if conflicts else "no_conflicts"
    return {"schema_version": 1, "status": status, "safe_to_overwrite": False,
            "server_concurrency_safe": False,
            "limitations": ["Comparison report only: no merged XML is produced.",
                            "No server transaction or concurrency guarantee; remote content may change after readback.",
                            "Preserve remote content and order. Review reported working changes before choosing narrowly scoped edits.",
                            "Top-level data blocks are comparison units; concurrent changes inside the same group/table are conservatively conflicting."],
            "summary": {"change_count": len(changes), "conflict_count": len(conflicts), "manual_review_count": len(problems)},
            "changes": changes, "manual_review": problems,
            "snapshots": {name: snap["summary"] for name, snap in snapshots.items()}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    # Handled below rather than argparse required=True, to return machine JSON.
    parser.add_argument("--baseline", help="Last verified online readback; mandatory, never a template")
    parser.add_argument("--working", help="Locally edited XML based on baseline")
    parser.add_argument("--remote", help="Fresh online readback saved as XML")
    parser.add_argument("--output", help="Optional report JSON file; never an XML merge result")
    args = parser.parse_args(argv)
    try:
        missing = [name for name in ("baseline", "working", "remote") if not getattr(args, name)]
        if missing:
            raise ValueError("Missing required snapshots: " + ", ".join(missing))
        report = compare(args.baseline, args.working, args.remote)
        code = 0 if report["status"] == "no_conflicts" else 1
    except (OSError, ValueError, ET.ParseError) as exc:
        report = {"schema_version": 1, "status": "error", "safe_to_overwrite": False,
                  "server_concurrency_safe": False, "error": str(exc)}
        code = 2
    if args.output:
        try:
            output = Path(args.output).resolve()
            inputs = {Path(p).resolve() for p in (args.baseline, args.working, args.remote) if p}
            if output in inputs:
                raise ValueError("Report output must not overwrite an input XML snapshot")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except (OSError, ValueError) as exc:
            report = {"schema_version": 1, "status": "error", "safe_to_overwrite": False,
                      "server_concurrency_safe": False, "error": str(exc)}
            code = 2
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
