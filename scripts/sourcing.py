#!/usr/bin/env python3
"""Target-journal PDF sourcing: plan, track, and route to the manual fallback.

This does NOT download anything. Downloads already have a safe implementation in
corpus.py (HTTPS only, explicit host allowlist, no redirect following, PDF magic
check, and a mandatory authorization + access_basis declaration). Re-implementing
that here would duplicate the security-critical part, so this module only:

  plan    -> turn candidate metadata into an acquisition plan + a manual checklist
  record  -> record what actually happened for one item
  list    -> show what still needs a human

Access rule, enforced by what the plan is allowed to say: only open access or
user-authorized copies. Paywalls, logins and captchas are never circumvented,
and an item that was not obtained is never marked as read.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

STATUSES = ("pending", "fetched", "manual_download_required", "not_accessible", "failed")
CLOSED = ("fetched", "not_accessible", "failed")
INBOX = "private-corpus/inbox"
ACCESS_RULE = ("Open access or explicitly user-authorized copies only. "
               "Never bypass a paywall, login or captcha. An item that was not "
               "obtained stays marked; it is never reported as read.")


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _year(record):
    date = str(record.get("first_available_date") or "")
    match = re.match(r"(\d{4})", date)
    return int(match.group(1)) if match else 0


def _slug(text, limit=48):
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return slug[:limit] or "paper"


def _filename(record, ident):
    authors = record.get("authors") or []
    first = ""
    if authors and isinstance(authors[0], dict):
        first = authors[0].get("family") or authors[0].get("name") or ""
    year = _year(record) or ""
    return "%s-%s-%s.pdf" % (_slug(first, 24), year or "noyear", _slug(record.get("title"), 40))


def matches_journal(record, target):
    if not target:
        return True
    a, b = _norm(record.get("journal")), _norm(target)
    return bool(a) and bool(b) and (a in b or b in a)


def select(records, journal=None, since_year=None, top=None, types=None):
    rows = [r for r in records if matches_journal(r, journal)]
    if since_year:
        rows = [r for r in rows if _year(r) >= since_year]
    if types:
        wanted = {t.lower() for t in types}
        rows = [r for r in rows if str(r.get("type", "")).lower() in wanted]
    rows.sort(key=lambda r: (-_year(r), str(r.get("title", ""))))
    return rows[:top] if top else rows


def build_plan(records, journal, direction, since_year=None, top=None, types=None):
    picked = select(records, journal, since_year, top, types)
    items = []
    for index, record in enumerate(picked, start=1):
        ident = "P%03d" % index
        items.append({
            "id": ident,
            "title": record.get("title", ""),
            "doi": record.get("doi", ""),
            "journal": record.get("journal", ""),
            "type": record.get("type", ""),
            "year": _year(record),
            "landing_url": record.get("url", ""),
            "abstract_available": bool(record.get("abstract_available")),
            "attempt": "auto_fetch_via_corpus_then_ocr_or_page_render",
            "expected_access": "unverified_pending_check",
            "status": "pending",
            "note": "",
            "manual": {
                "suggested_filename": _filename(record, ident),
                "where_to_put": INBOX,
                "after_download": "python scripts/corpus.py ingest <manifest.json> <new-corpus-dir>",
            },
        })
    return {
        "journal": journal or "",
        "direction": direction or "",
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "access_rule": ACCESS_RULE,
        "selection": {"since_year": since_year, "top": top, "types": list(types or []),
                      "candidates_considered": len(records), "selected": len(items)},
        "counts": {s: 0 for s in STATUSES},
        "items": items,
    }


def recount(plan):
    counts = {s: 0 for s in STATUSES}
    for item in plan["items"]:
        counts[item.get("status", "pending")] = counts.get(item.get("status", "pending"), 0) + 1
    plan["counts"] = counts
    return plan


def record_status(plan, ident, status, note=""):
    if status not in STATUSES:
        raise ValueError("status must be one of: " + ", ".join(STATUSES))
    for item in plan["items"]:
        if item["id"] == ident:
            item["status"] = status
            if note:
                item["note"] = note
            return recount(plan)
    raise ValueError("unknown item id: " + ident)


def render_checklist(plan):
    """Human-facing fallback list: exactly what to download and where to put it."""
    needs = [i for i in plan["items"] if i["status"] not in ("fetched",)]
    lines = []
    lines.append("# 目标期刊范文获取清单")
    lines.append("")
    lines.append("- 目标期刊：%s" % (plan.get("journal") or "(未指定)"))
    lines.append("- 研究方向：%s" % (plan.get("direction") or "(未指定)"))
    lines.append("- 生成时间：%s" % plan.get("generated", ""))
    lines.append("- 计划条目：%d ｜ 仍需处理：%d" % (len(plan["items"]), len(needs)))
    lines.append("")
    lines.append("> %s" % plan.get("access_rule", ACCESS_RULE))
    lines.append("")
    lines.append("## 一、自动获取（先试这条）")
    lines.append("")
    lines.append("仅对开放获取或你已授权的副本有效。命令：")
    lines.append("")
    lines.append("```bash")
    lines.append("python scripts/corpus.py download private/downloads.json private/download-v1 --allow-host AUTHORIZED-HOST")
    lines.append("```")
    lines.append("")
    lines.append("`downloads.json` 每项必须写明 `authorization`（open_access_verified 或 user_authorized）"
                 "与 `access_basis`。脚本拒绝私网地址、非 HTTPS、伪 PDF 与超大文件，且不绕过登录、验证码或付费墙。")
    lines.append("")
    lines.append("## 二、人工下载兜底（自动获取失败时走这条）")
    lines.append("")
    lines.append("把下列 PDF 下载到 `%s/`，文件名用「建议文件名」一列，然后一次性导入。" % INBOX)
    lines.append("")
    lines.append("| ID | 状态 | 建议文件名 | 标题 | 期刊 | 年 | DOI / 链接 |")
    lines.append("|---|---|---|---|---|---|---|")
    for item in needs:
        link = item.get("doi") or item.get("landing_url") or ""
        if item.get("doi"):
            link = "https://doi.org/" + item["doi"]
        lines.append("| %s | %s | `%s` | %s | %s | %s | %s |" % (
            item["id"], item["status"], item["manual"]["suggested_filename"],
            item["title"].replace("|", "/"), item["journal"].replace("|", "/"),
            item["year"] or "", link))
    lines.append("")
    lines.append("导入命令（先写 manifest.json，再 ingest）：")
    lines.append("")
    lines.append("```bash")
    lines.append("python scripts/corpus.py ingest private/manifest.json private/extracted-v1")
    lines.append("```")
    lines.append("")
    lines.append("`full_text_read` / `visual_checked` / `metadata_verified` 默认都是 false。"
                 "只有真正读完并看过图表之后才能改成 true；**提取成功不等于读过**。")
    lines.append("")
    lines.append("## 三、拿到之后")
    lines.append("")
    lines.append("1. 逐篇核验身份（标题/作者/年/刊/卷期页/DOI），判定见 [文献真实性](../modules/evidence-integrity.md)。")
    lines.append("2. 按 `split` 划分 train / heldout，按**作者组**划分，避免同团队泄漏。")
    lines.append("3. 做风格提炼与留出评测，见 [期刊语料学习](../modules/journal-distillation.md)。")
    lines.append("")
    lines.append("## 四、不要做的事")
    lines.append("")
    lines.append("- 不要绕过付费墙、登录或验证码去拿 PDF。")
    lines.append("- 不要因为拿到摘要就当成读过全文。")
    lines.append("- 不要把「无法获取」写成「无需处理」。")
    return "\n".join(lines) + "\n"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Target-journal PDF sourcing plan and fallback checklist")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plan", help="build an acquisition plan from a search.json")
    p.add_argument("search_json")
    p.add_argument("--journal", default="")
    p.add_argument("--direction", default="")
    p.add_argument("--since-year", type=int, default=None)
    p.add_argument("--top", type=int, default=None)
    p.add_argument("--type", action="append", default=None, help="repeatable, e.g. --type journal-article")
    p.add_argument("--out", required=True, help="plan json path; checklist is written beside it")

    r = sub.add_parser("record", help="record the real outcome for one item")
    r.add_argument("plan_json")
    r.add_argument("item_id")
    r.add_argument("--status", required=True, choices=STATUSES)
    r.add_argument("--note", default="")

    l = sub.add_parser("list", help="show items still needing a human")
    l.add_argument("plan_json")

    args = ap.parse_args(argv)
    try:
        if args.command == "plan":
            data = read_json(args.search_json)
            records = data.get("records", data if isinstance(data, list) else [])
            if not records:
                raise ValueError("no records found in " + args.search_json)
            plan = build_plan(records, args.journal, args.direction,
                              args.since_year, args.top, args.type)
            plan = recount(plan)
            out = Path(args.out)
            write_json(out, plan)
            checklist = out.with_name(out.stem.replace("sourcing-plan", "sourcing") + "-checklist.md")
            if checklist == out:
                checklist = out.with_suffix(".checklist.md")
            checklist.write_text(render_checklist(plan), encoding="utf-8")
            print("plan: %s" % out)
            print("checklist: %s" % checklist)
            print("selected %d of %d candidates for journal '%s'"
                  % (plan["selection"]["selected"], plan["selection"]["candidates_considered"],
                     plan["journal"] or "(any)"))
            return 0

        if args.command == "record":
            plan = read_json(args.plan_json)
            plan = record_status(plan, args.item_id, args.status, args.note)
            write_json(args.plan_json, plan)
            print("%s -> %s" % (args.item_id, args.status))
            print("counts: " + ", ".join("%s=%d" % (k, v) for k, v in plan["counts"].items()))
            return 0

        plan = read_json(args.plan_json)
        pending = [i for i in plan["items"] if i["status"] not in CLOSED]
        if not pending:
            print("nothing pending")
            return 0
        for item in pending:
            print("%s  %-26s %s" % (item["id"], item["status"],
                                    item["title"][:70] or "(untitled)"))
        print("\n%d item(s) still need attention" % len(pending))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
