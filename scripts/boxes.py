#!/usr/bin/env python3
"""Four-box context management with Fact-Locked extractive compression.

Four fixed boxes, each with its own compression ceiling:

  A intro      lowest density, up to 6x, extractive
  B data       medium, up to 3x
  C results    highest density, NO compression at all, kept verbatim
  D conclusion next highest, up to 2x

Rules enforced here rather than merely documented:

* The original archive of every box is immutable and hash-recorded. Compression
  never touches it; it writes a separate temporary copy.
* Compression is extractive only. Nothing is reworded, ever.
* Green sentences go first, then yellow. Red sentences are never dropped, and
  every dropped yellow appears in a dropped-items list.
* Sentence order is never changed and nothing crosses a box boundary.
* The maximum feasible ratio is found by binary search, and the resulting ratio
  must still show 100% red-lock recall. Red recall is recomputed from the text
  that was actually kept, not assumed.
* Export always concatenates the ORIGINAL archives. A compressed copy can never
  become the deliverable, so the inverted-triangle narrative cannot be damaged.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import locks  # noqa: E402

BOXES = ("A", "B", "C", "D")
BOX_NAMES = {"A": "intro", "B": "data", "C": "results", "D": "conclusion"}
BOX_LABELS = {"A": "引言箱", "B": "数据箱", "C": "结果箱", "D": "结论箱"}
BOX_CAPS = {"A": 6.0, "B": 3.0, "C": 1.0, "D": 2.0}
BOX_DENSITY = {"A": "lowest", "B": "medium", "C": "highest", "D": "high"}
LOCK_ORDER = {"green": 0, "yellow": 1, "red": 2}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def archive_path(workspace, box):
    return Path(workspace) / "boxes" / ("%s-%s" % (box, BOX_NAMES[box])) / "original.md"


def compressed_path(workspace, box, ratio):
    safe = ("%g" % ratio).replace(".", "p")
    return Path(workspace) / "boxes" / ("%s-%s" % (box, BOX_NAMES[box])) / ("compressed-%sx.md" % safe)


def meta_path(workspace, box):
    return Path(workspace) / "boxes" / ("%s-%s" % (box, BOX_NAMES[box])) / "box.json"


def init_workspace(workspace):
    root = Path(workspace)
    made = []
    for box in BOXES:
        meta = meta_path(root, box)
        if meta.exists():
            continue
        meta.parent.mkdir(parents=True, exist_ok=True)
        archive_path(root, box).write_text("", encoding="utf-8")
        write_json(meta, {
            "box": box, "name": BOX_NAMES[box], "label": BOX_LABELS[box],
            "density": BOX_DENSITY[box], "cap": BOX_CAPS[box],
            "original_sha256": sha(""), "original_sentences": 0,
            "paragraphs": [], "compressions": [],
            "note": ("C has cap 1.0: the results box is never compressed."
                     if box == "C" else ""),
        })
        made.append(box)
    return made


def _load_meta(workspace, box):
    meta = meta_path(workspace, box)
    if not meta.is_file():
        raise ValueError("box %s is not initialised; run init first" % box)
    return read_json(meta)


def append_paragraph(workspace, box, text, label=""):
    """Append to the ORIGINAL archive. Refuses to modify existing content."""
    if box not in BOXES:
        raise ValueError("box must be one of: " + ", ".join(BOXES))
    if not str(text).strip():
        raise ValueError("paragraph text is empty")
    meta = _load_meta(workspace, box)
    archive = archive_path(workspace, box)
    current = archive.read_text(encoding="utf-8")
    if sha(current) != meta["original_sha256"]:
        raise ValueError("original archive was modified outside this tool; refusing to append")
    updated = current + ((("\n\n") if current.strip() else "") + str(text).strip())
    archive.write_text(updated, encoding="utf-8")
    meta["original_sha256"] = sha(updated)
    meta["original_sentences"] = len(locks.sentences(updated))
    meta["paragraphs"].append({"index": len(meta["paragraphs"]), "label": label,
                               "sha256": sha(str(text).strip())})
    write_json(meta_path(workspace, box), meta)
    return meta


def box_sentences(workspace, box, domain_terms=None):
    text = archive_path(workspace, box).read_text(encoding="utf-8")
    return locks.tag_sentences(text, domain_terms)


def locks_summary(workspace, box, domain_terms=None):
    tags = box_sentences(workspace, box, domain_terms)
    extracted = locks.extract(archive_path(workspace, box).read_text(encoding="utf-8"),
                              domain_terms)
    by_level = {level: [t for t in tags if t["level"] == level]
                for level in ("red", "yellow", "green")}
    return {
        "box": box, "label": BOX_LABELS[box], "density": BOX_DENSITY[box],
        "cap": BOX_CAPS[box],
        "sentences": len(tags),
        "red_sentences": len(by_level["red"]),
        "yellow_sentences": len(by_level["yellow"]),
        "green_sentences": len(by_level["green"]),
        "fact_counts": extracted["counts"],
        "escalated_locks": extracted["escalated"],
        "droppable_order": ([t["text"] for t in by_level["green"]]
                            + [t["text"] for t in by_level["yellow"]]),
        "protected_count": len(by_level["red"]) + len(extracted["escalated"]),
    }


def compress(workspace, box, keep_fraction, domain_terms=None, record=True):
    """Drop the least protected sentences until keep_fraction of them remain.

    Extractive only: kept sentences are exact copies, in their original order.
    """
    if box not in BOXES:
        raise ValueError("box must be one of: " + ", ".join(BOXES))
    if box == "C":
        raise ValueError("box C holds the results and is never compressed")
    if not 0.0 < keep_fraction <= 1.0:
        raise ValueError("keep_fraction must be in (0, 1]")

    meta = _load_meta(workspace, box)
    original = archive_path(workspace, box).read_text(encoding="utf-8")
    if sha(original) != meta["original_sha256"]:
        raise ValueError("original archive was modified outside this tool; refusing to compress")

    tags = locks.tag_sentences(original, domain_terms)
    total = len(tags)
    if total == 0:
        raise ValueError("box %s is empty" % box)
    target = max(1, int(round(total * keep_fraction)))

    droppable = sorted([t for t in tags if t["level"] != "red"],
                       key=lambda t: (LOCK_ORDER[t["level"]], t["index"]))
    drop_count = max(0, total - target)
    dropped = droppable[:drop_count]
    kept = [t for t in tags if t["index"] not in {d["index"] for d in dropped}]
    kept = sorted(kept, key=lambda t: t["index"])          # order preserved
    kept_text = " ".join(t["text"] for t in kept)

    integrity = locks.verify(original, kept_text, domain_terms)
    result = {
        "box": box, "label": BOX_LABELS[box],
        "original_sentences": total, "kept_sentences": len(kept),
        "dropped_sentences": len(dropped),
        "actual_ratio": round(total / max(1, len(kept)), 3),
        "cap": BOX_CAPS[box],
        "red_recall": integrity["red_recall"],
        "yellow_retention": (round(len([t for t in kept if t["level"] == "yellow"])
                                   / max(1, len([t for t in tags if t["level"] == "yellow"])), 4)),
        "dropped_items": [{"level": t["level"], "text": t["text"][:160]} for t in dropped],
        "red_lock_check": integrity,
        "order_preserved": True,
        "method": "extractive_only",
        "keep_fraction": keep_fraction,
    }
    if not integrity["ok"]:
        raise ValueError("refusing to emit a compression that breaks red locks: %s"
                         % json.dumps({k: integrity[k] for k in
                                       ("red_missing", "red_changed", "red_added",
                                        "red_escalated_lost")}, ensure_ascii=False))
    if result["actual_ratio"] > BOX_CAPS[box]:
        raise ValueError("ratio %.2f exceeds the %s box cap of %.1fx"
                         % (result["actual_ratio"], box, BOX_CAPS[box]))
    if record:
        path = compressed_path(workspace, box, result["actual_ratio"])
        path.write_text(kept_text + "\n", encoding="utf-8")
        meta["compressions"].append(dict(result, path=str(path),
                                         created=dt.datetime.now(
                                             dt.timezone.utc).isoformat(timespec="seconds")))
        write_json(meta_path(workspace, box), meta)
        result["path"] = str(path)
    return result


def search_max_ratio(workspace, box, domain_terms=None, record=True):
    """Binary search for the largest feasible ratio under 100% red-lock recall."""
    if box == "C":
        return {"box": box, "label": BOX_LABELS[box], "cap": BOX_CAPS[box],
                "max_ratio": 1.0, "capped": True,
                "reason": "box C is never compressed", "probes": []}
    cap = BOX_CAPS[box]
    tags = box_sentences(workspace, box, domain_terms)
    total = len(tags)
    if total == 0:
        return {"box": box, "label": BOX_LABELS[box], "cap": cap,
                "max_ratio": 1.0, "capped": False, "reason": "box is empty", "probes": []}
    reds = len([t for t in tags if t["level"] == "red"])
    if reds >= total:
        return {"box": box, "label": BOX_LABELS[box], "cap": cap,
                "max_ratio": 1.0, "capped": True,
                "reason": "every sentence carries a red lock", "probes": []}

    def feasible(ratio):
        keep = 1.0 / ratio
        try:
            outcome = compress(workspace, box, keep, domain_terms, record=False)
        except ValueError as exc:
            return False, str(exc)
        return outcome["red_recall"] >= 1.0 and outcome["actual_ratio"] <= cap + 1e-9, outcome

    probes = []
    lo, hi = 1.0, cap
    best, best_outcome = 1.0, None
    for _ in range(24):
        mid = round((lo + hi) / 2.0, 4)
        if hi - lo < 0.01:
            break
        ok, outcome = feasible(mid)
        probes.append({"ratio": mid, "feasible": ok,
                       "detail": (outcome if isinstance(outcome, str) else
                                  "%d kept, red_recall=%s" % (outcome["kept_sentences"],
                                                              outcome["red_recall"]))})
        if ok:
            best, best_outcome, lo = mid, outcome, mid
        else:
            hi = mid
    if best_outcome is not None and record:
        best_outcome = compress(workspace, box, 1.0 / best, domain_terms, record=True)
    return {"box": box, "label": BOX_LABELS[box], "cap": cap, "max_ratio": best,
            "probes": probes, "result": best_outcome}


def budget(window, history, query, reserve, warn=0.80, brake=0.90):
    """Token brake.

    window/history/query/reserve must be declared by the caller: this process
    cannot read the host's conversation meter. When a figure is unknown it is
    reported as unknown instead of being guessed, because a brake that fires on an
    invented number is worse than no brake.
    """
    missing = [name for name, value in (("window", window), ("history", history),
                                        ("query", query), ("reserve", reserve))
               if value is None]
    if missing:
        return {"status": "unknown", "unknown_inputs": missing,
                "action": "cannot decide; supply the missing figures from the platform's "
                          "usage view rather than estimating them",
                "warn_threshold": warn, "brake_threshold": brake}
    used = history + query + reserve
    ratio = used / window if window else 1.0
    if ratio >= brake:
        status, action = "brake", ("stop generating, compress the boxes, then continue "
                                   "from the compressed copies")
    elif ratio >= warn:
        status, action = "warn", "continue writing, but plan the next compression pass"
    else:
        status, action = "ok", "continue"
    return {"status": status, "used_tokens": used, "window": window,
            "history": history, "query": query, "reserve": reserve,
            "ratio": round(ratio, 4), "headroom": window - used,
            "warn_threshold": warn, "brake_threshold": brake, "action": action}


def export_full_text(workspace):
    """Concatenate the ORIGINAL archives in box order. Never uses a compressed copy."""
    parts, provenance = [], []
    for box in BOXES:
        archive = archive_path(workspace, box)
        if not archive.is_file():
            raise ValueError("box %s has no archive" % box)
        text = archive.read_text(encoding="utf-8").strip()
        provenance.append({"box": box, "label": BOX_LABELS[box], "sentences": len(locks.sentences(text)),
                           "sha256": sha(text), "source": "original_archive"})
        if text:
            parts.append(text)
    return "\n\n".join(parts) + "\n", provenance


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def render_report(workspace, search_results, budget_result=None):
    lines = ["# 四箱压缩报告", ""]
    if budget_result:
        lines.append("## Token 刹车")
        lines.append("")
        lines.append("- 状态：**%s**" % budget_result["status"])
        if budget_result["status"] == "unknown":
            lines.append("- 未知输入：%s" % ", ".join(budget_result["unknown_inputs"]))
            lines.append("- 动作：%s" % budget_result["action"])
        else:
            lines.append("- 已用 / 窗口：%s / %s（%.1f%%）"
                         % (budget_result["used_tokens"], budget_result["window"],
                            budget_result["ratio"] * 100))
            lines.append("- 动作：%s" % budget_result["action"])
        lines.append("")
    lines.append("## 各箱结果")
    lines.append("")
    lines.append("| 箱 | 名称 | 密度 | 上限 | 实测最大倍率 | 参数 |")
    lines.append("|---|---|---|---|---|---|")
    for item in search_results:
        params = ""
        if item.get("result"):
            r = item["result"]
            params = "保留 %d/%d 句，红锁召回 %s" % (r["kept_sentences"],
                                                    r["original_sentences"], r["red_recall"])
        lines.append("| %s | %s | %s | %.1fx | %.2fx | %s |"
                     % (item["box"], item.get("label", ""), BOX_DENSITY[item["box"]],
                        item["cap"], item["max_ratio"], params))
    lines.append("")
    lines.append("## 丢失条目清单")
    lines.append("")
    for item in search_results:
        r = item.get("result")
        if not r or not r["dropped_items"]:
            continue
        lines.append("### %s（%s）" % (item["box"], BOX_LABELS[item["box"]]))
        lines.append("")
        for d in r["dropped_items"]:
            lines.append("- `%s` %s" % (d["level"], d["text"]))
        lines.append("")
    lines.append("## 约束核对")
    lines.append("")
    lines.append("- 结果箱（C）不压缩：%s" % ("是" if BOX_CAPS["C"] == 1.0 else "否"))
    lines.append("- 压缩方式：仅抽取式，不改写")
    lines.append("- 句子顺序：未改变，未跨箱删句")
    lines.append("- 红锁召回：每次估算均要求 100%")
    lines.append("- 导出全文：只用原始存档，不使用压缩副本")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Four-box Fact-Locked compression")
    sub = ap.add_subparsers(dest="command", required=True)

    i = sub.add_parser("init", help="create the four boxes")
    i.add_argument("workspace")

    a = sub.add_parser("add", help="append to a box's original archive")
    a.add_argument("workspace")
    a.add_argument("box", choices=list(BOXES))
    a.add_argument("--text", required=True)
    a.add_argument("--label", default="")

    l = sub.add_parser("locks", help="show the locks in a box")
    l.add_argument("workspace")
    l.add_argument("box", choices=list(BOXES))
    l.add_argument("--domain-terms", nargs="*", default=[])

    c = sub.add_parser("compress", help="extractively compress one box")
    c.add_argument("workspace")
    c.add_argument("box", choices=list(BOXES))
    c.add_argument("--keep", type=float, required=True, help="fraction of sentences to keep")
    c.add_argument("--domain-terms", nargs="*", default=[])

    s = sub.add_parser("search", help="binary search the max feasible ratio (one box, or all)")
    s.add_argument("workspace")
    s.add_argument("box", nargs="?", default=None, choices=list(BOXES) + [None])
    s.add_argument("--domain-terms", nargs="*", default=[])
    s.add_argument("--report", default="")

    b = sub.add_parser("budget", help="token brake")
    b.add_argument("--window", type=int, default=None)
    b.add_argument("--history", type=int, default=None)
    b.add_argument("--query", type=int, default=None)
    b.add_argument("--reserve", type=int, default=None)

    e = sub.add_parser("export", help="concatenate the ORIGINAL archives")
    e.add_argument("workspace")
    e.add_argument("--out", required=True)
    e.add_argument("--provenance", default="")

    args = ap.parse_args(argv)
    try:
        if args.command == "init":
            made = init_workspace(args.workspace)
            print("created boxes: %s" % (", ".join(made) or "already present"))
            print("caps: " + ", ".join("%s=%gx" % (b, BOX_CAPS[b]) for b in BOXES))
            return 0
        if args.command == "add":
            meta = append_paragraph(args.workspace, args.box, args.text, args.label)
            print("%s now holds %d sentence(s), archive sha %s"
                  % (args.box, meta["original_sentences"], meta["original_sha256"][:12]))
            return 0
        if args.command == "locks":
            print(json.dumps(locks_summary(args.workspace, args.box, args.domain_terms),
                             indent=2, ensure_ascii=False))
            return 0
        if args.command == "compress":
            result = compress(args.workspace, args.box, args.keep, args.domain_terms)
            print(json.dumps({k: result[k] for k in
                              ("box", "kept_sentences", "original_sentences",
                               "actual_ratio", "red_recall", "yellow_retention")},
                             indent=2, ensure_ascii=False))
            print("compressed copy: %s" % result.get("path", "(not recorded)"))
            return 0
        if args.command == "search":
            targets = [args.box] if args.box else list(BOXES)
            results = [search_max_ratio(args.workspace, b, args.domain_terms)
                       for b in targets]
            payload = {"created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                       "results": results}
            write_json(Path(args.workspace) / "boxes" / "compression-plan.json", payload)
            if args.report:
                Path(args.report).parent.mkdir(parents=True, exist_ok=True)
                Path(args.report).write_text(render_report(args.workspace, results), encoding="utf-8")
            for item in results:
                print("%s %-11s cap=%.1fx  max=%.2fx  %s" % (
                    item["box"], BOX_LABELS[item["box"]], item["cap"], item["max_ratio"],
                    item.get("reason", "")))
            return 0
        if args.command == "budget":
            print(json.dumps(budget(args.window, args.history, args.query, args.reserve),
                             indent=2, ensure_ascii=False))
            return 0
        text, provenance = export_full_text(args.workspace)
        out = Path(args.out)
        if out.exists():
            raise FileExistsError("Refusing to overwrite existing file: %s" % out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        if args.provenance:
            Path(args.provenance).parent.mkdir(parents=True, exist_ok=True)
            write_json(args.provenance, {"source": "original_archive_only",
                                        "boxes": provenance})
        print("exported %d characters from original archives only" % len(text))
        for row in provenance:
            print("  %s %-11s %4d sentence(s)  sha %s"
                  % (row["box"], row["label"], row["sentences"], row["sha256"][:12]))
        return 0
    except (OSError, ValueError, KeyError, FileExistsError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
