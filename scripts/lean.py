#!/usr/bin/env python3
"""Token accounting for lean mode.

Stdlib-only. Uses tiktoken when it happens to be installed (exact BPE counts),
otherwise falls back to a published character heuristic. The method actually
used is always recorded in the output, because a measured number and an
estimated number must never be presented as if they were the same thing.

Scope limit, stated up front: this measures the token size of FILES. It cannot
see the model's own conversation meter, because no host here exposes it. That
number is reported as not_measurable rather than guessed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = "audit/token-ledger.json"
TEXT_EXT = {".md", ".py", ".json", ".txt", ".bat", ".yml", ".yaml", ".toml", ".cfg", ".html", ".tex"}

# CJK ideographs, kana, fullwidth forms and CJK punctuation. These tokenize far
# heavier than Latin text, which is why a plain bytes/4 estimate is wrong here.
_CJK = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")

HEURISTIC = "heuristic:cjk*1.05+other/3.8"
NOT_MEASURABLE = "not_measurable_from_here"


def load_encoder():
    """Return (encoder, method_label). Encoder is None when tiktoken is absent."""
    try:
        import tiktoken  # noqa: PLC0415
    except Exception:
        return None, HEURISTIC
    try:
        return tiktoken.get_encoding("cl100k_base"), "tiktoken:cl100k_base"
    except Exception:
        return None, HEURISTIC


def estimate_tokens(text, encoder=None):
    """Token count for text. Exact when an encoder is given, else documented estimate."""
    if encoder is not None:
        return len(encoder.encode(text))
    cjk = len(_CJK.findall(text))
    other = len(text) - cjk
    return int(round(cjk * 1.05 + other / 3.8))


def measure_file(path, encoder=None, root=None):
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    name = str(path)
    if root is not None:
        try:
            name = path.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            name = path.as_posix()
    return {
        "path": name,
        "bytes": path.stat().st_size,
        "chars": len(text),
        "tokens": estimate_tokens(text, encoder),
    }


def collect(targets, allow_dirs=True):
    """Expand files and directories into a sorted list of measurable text files."""
    out = []
    for target in targets:
        p = Path(target)
        if p.is_dir():
            if not allow_dirs:
                raise ValueError(f"Directory not allowed here: {target}")
            for child in sorted(p.rglob("*")):
                if child.is_file() and child.suffix.lower() in TEXT_EXT:
                    out.append(child)
        elif p.is_file():
            out.append(p)
        else:
            raise ValueError(f"Missing path: {target}")
    seen, unique = set(), []
    for p in out:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def measure(targets, encoder=None, root=None):
    files = collect(targets)
    items = [measure_file(f, encoder, root) for f in files]
    return items, sum(i["tokens"] for i in items)


def read_ledger(workspace):
    p = Path(workspace) / LEDGER
    if not p.is_file():
        return {"method": None, "scope": "artifact_files_only",
                "conversation_tokens": NOT_MEASURABLE, "entries": [],
                "cumulative_tokens": 0}
    return json.loads(p.read_text(encoding="utf-8"))


def write_ledger(workspace, ledger):
    p = Path(workspace) / LEDGER
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)


def add_entry(workspace, step, artifacts, note="", encoder=None, method=None, root=None):
    """Append one step to the ledger. Artifacts are measured, not supplied."""
    if not step:
        raise ValueError("step is required")
    items, subtotal = measure(artifacts, encoder, root)
    ledger = read_ledger(workspace)
    ledger["method"] = method or ledger.get("method") or HEURISTIC
    ledger["scope"] = "artifact_files_only"
    ledger["conversation_tokens"] = NOT_MEASURABLE
    step_total = round(ledger.get("cumulative_tokens", 0) + subtotal)
    ledger["entries"].append({
        "step": step,
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "artifacts": items,
        "subtotal_tokens": subtotal,
        "cumulative_tokens": step_total,
        "note": note,
    })
    ledger["cumulative_tokens"] = step_total
    write_ledger(workspace, ledger)
    return ledger


def format_report(ledger):
    lines = []
    lines.append(f"method: {ledger.get('method')}")
    lines.append(f"scope:  {ledger.get('scope')} (文件产出物；不含对话本身)")
    lines.append("")
    lines.append(f"{'step':<14}{'files':>6}{'tokens':>12}{'cumulative':>13}")
    lines.append("-" * 45)
    for entry in ledger.get("entries", []):
        lines.append(f"{entry['step']:<14}{len(entry['artifacts']):>6}"
                     f"{entry['subtotal_tokens']:>12,}{entry['cumulative_tokens']:>13,}")
    lines.append("-" * 45)
    lines.append(f"{'TOTAL':<14}{'':>6}{'':>12}{ledger.get('cumulative_tokens', 0):>13,}")
    lines.append("")
    lines.append(f"conversation tokens: {ledger.get('conversation_tokens')}")
    return "\n".join(lines)


def render_html(ledger):
    """Self-contained dashboard. No JS, no external assets, works offline."""
    entries = ledger.get("entries", [])
    total = ledger.get("cumulative_tokens", 0)
    peak = max([e["subtotal_tokens"] for e in entries] or [1]) or 1
    method = html.escape(str(ledger.get("method")))
    conv = html.escape(str(ledger.get("conversation_tokens")))

    bars = []
    for e in entries:
        pct = max(2, round(e["subtotal_tokens"] * 100 / peak))
        bars.append(
            '<div class="row"><div class="lbl">{step}</div>'
            '<div class="track"><div class="bar" style="width:{pct}%"></div></div>'
            '<div class="val">{sub:,}</div><div class="val dim">{cum:,}</div></div>'.format(
                step=html.escape(str(e["step"])), pct=pct,
                sub=e["subtotal_tokens"], cum=e["cumulative_tokens"]))

    rows = []
    for e in entries:
        rows.append("<tr><td>{s}</td><td class='n'>{f}</td><td class='n'>{sub:,}</td>"
                    "<td class='n'>{cum:,}</td><td>{ts}</td><td>{note}</td></tr>".format(
                        s=html.escape(str(e["step"])), f=len(e["artifacts"]),
                        sub=e["subtotal_tokens"], cum=e["cumulative_tokens"],
                        ts=html.escape(str(e.get("ts", ""))[:19]),
                        note=html.escape(str(e.get("note", "")))))
    if not rows:
        rows.append("<tr><td colspan='6' class='dim'>尚无记录</td></tr>")

    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Token 台账</title>
<style>
:root{{--bg:#f7f8fc;--card:#ffffff;--ink:#1c2033;--dim:#6b7392;--line:#e4e7f2;
--accent:#5b45d6;--accent2:#0ea5b7}}
*{{box-sizing:border-box}}
body{{margin:0;padding:28px;background:var(--bg);color:var(--ink);
font-family:"Segoe UI","Microsoft YaHei","PingFang SC",Helvetica,Arial,sans-serif}}
.wrap{{max-width:920px;margin:0 auto}}
h1{{font-size:22px;margin:0 0 4px}}
.sub{{color:var(--dim);font-size:13px;margin-bottom:20px}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:14px 18px;min-width:150px;flex:1}}
.card .k{{font-size:12px;color:var(--dim);margin-bottom:6px}}
.card .v{{font-size:26px;font-weight:700;letter-spacing:-.5px}}
.card .v.small{{font-size:14px;font-weight:600;color:var(--accent)}}
.panel{{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:18px;margin-bottom:18px}}
.row{{display:grid;grid-template-columns:150px 1fr 90px 100px;gap:10px;
align-items:center;margin:8px 0;font-size:13px}}
.lbl{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.track{{background:#eef0f8;border-radius:6px;height:16px;overflow:hidden}}
.bar{{height:100%;border-radius:6px;
background:linear-gradient(90deg,var(--accent),var(--accent2))}}
.val{{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}}
.val.dim{{color:var(--dim);font-weight:400}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}}
th{{color:var(--dim);font-weight:600;font-size:12px}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.dim{{color:var(--dim)}}
.warn{{border-left:4px solid #d97706;background:#fffbeb;border-radius:8px;
padding:12px 14px;font-size:13px;line-height:1.6}}
.warn b{{color:#92400e}}
code{{background:#eef0f8;padding:1px 6px;border-radius:4px;font-size:12px}}
</style></head><body><div class="wrap">
<h1>Token 台账 · 产出物口径</h1>
<div class="sub">method: <code>{method}</code> ｜ scope: <code>artifact_files_only</code></div>

<div class="cards">
  <div class="card"><div class="k">累计（口径 A 写入量）</div><div class="v">{total:,}</div></div>
  <div class="card"><div class="k">记录步数</div><div class="v">{steps}</div></div>
  <div class="card"><div class="k">单步最大</div><div class="v">{peak:,}</div></div>
  <div class="card"><div class="k">对话本身 token</div>
    <div class="v small">{conv}</div></div>
</div>

<div class="panel">
  <div class="row" style="color:var(--dim);font-size:12px">
    <div class="lbl">步骤</div><div>占单步最大值比例</div>
    <div class="val">本步</div><div class="val">累计</div></div>
  {bars}
</div>

<div class="panel">
  <table><thead><tr><th>步骤</th><th class="n">文件</th><th class="n">本步 token</th>
  <th class="n">累计 token</th><th>时间 (UTC)</th><th>说明</th></tr></thead>
  <tbody>{rows}</tbody></table>
</div>

<div class="warn">
  <b>这个数不是账单。</b> 它只统计<b>产出物文件</b>的 token，不含对话输入输出、系统提示、工具返回与模型推理。
  对话本身的用量在本机没有记录（已排查 <code>~/.claude/projects/</code> 与 WorkBuddy 日志目录），
  因此状态为 <code>{conv}</code>。真实计费请以平台用量页为准。
  口径定义与估算公式见 <code>docs/TOKEN_ACCOUNTING.md</code>。
</div>
</div></body></html>
""".format(method=method, total=total, steps=len(entries), peak=peak, conv=conv,
           bars="\n".join(bars), rows="\n".join(rows))


def main() -> int:
    ap = argparse.ArgumentParser(description="Token accounting (artifact files only)")
    sub = ap.add_subparsers(dest="command", required=True)

    m = sub.add_parser("measure", help="measure files or directories")
    m.add_argument("targets", nargs="+")
    m.add_argument("--root", default=None, help="print paths relative to this directory")
    m.add_argument("--heuristic", action="store_true", help="force the character heuristic")
    m.add_argument("--json", action="store_true")

    a = sub.add_parser("ledger", help="append a measured step to the ledger")
    a.add_argument("workspace")
    a.add_argument("step")
    a.add_argument("--artifacts", nargs="+", required=True)
    a.add_argument("--note", default="")
    a.add_argument("--root", default=None)
    a.add_argument("--heuristic", action="store_true")

    r = sub.add_parser("report", help="print the running total")
    r.add_argument("workspace")
    r.add_argument("--json", action="store_true")
    r.add_argument("--html", default=None, help="write a self-contained HTML dashboard here")

    args = ap.parse_args()
    try:
        if args.command == "measure":
            encoder, method = (None, HEURISTIC) if args.heuristic else load_encoder()
            items, total = measure(args.targets, encoder, args.root)
            if args.json:
                print(json.dumps({"method": method, "items": items, "total_tokens": total},
                                 indent=2, ensure_ascii=False))
            else:
                print(f"method: {method}")
                for i in items:
                    print(f"{i['tokens']:>9,}  {i['path']}")
                print("-" * 40)
                print(f"{total:>9,}  TOTAL ({len(items)} files)")
            return 0

        if args.command == "ledger":
            encoder, method = (None, HEURISTIC) if args.heuristic else load_encoder()
            ledger = add_entry(args.workspace, args.step, args.artifacts,
                               args.note, encoder, method, args.root)
            print(f"step '{args.step}': "
                  f"+{ledger['entries'][-1]['subtotal_tokens']:,} tokens, "
                  f"cumulative {ledger['cumulative_tokens']:,}")
            print(format_report(ledger))
            return 0

        ledger = read_ledger(args.workspace)
        if args.json:
            print(json.dumps(ledger, indent=2, ensure_ascii=False))
        else:
            print(format_report(ledger))
        if args.html:
            target = Path(args.html)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render_html(ledger), encoding="utf-8")
            print("dashboard: %s" % target)
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
