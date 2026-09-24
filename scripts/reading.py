#!/usr/bin/env python3
"""
文献三遍精读卡片：生成骨架 -> 校验完整度 -> 同步进 evidence.json

用法：
  python scripts/reading.py card <workspace> --title "标题" [--author 第一作者]
                                  [--year 2024] [--journal ...] [--doi 10.xxx] [--file paper.pdf]
        生成 reading-cards/<作者><年份>.md 卡片骨架（三遍法字段）
  python scripts/reading.py list  <workspace>      列出全部卡片与完成度
  python scripts/reading.py check <workspace>      校验卡片，不完整逐条列出（退出码1）
  python scripts/reading.py sync  <workspace>      把完整卡片写入 evidence.json
                                                  （is_core_reading / full_text / claim_level）

铁律（见 modules/paper-reading-guide.md）：
- 没填卡片的文献只算"下载过"，不算读过；
- 卡片不代替引用身份核验，sync 后 citation_verdict=UNRESOLVED，须另跑核验；
- metadata_only 只能支撑 bibliographic 层；精读全文的卡片才允许 observation 及以上。
"""
import argparse
import json
import re
import sys
from pathlib import Path

CARD_DIR = "reading-cards"
STRENGTH_MAP = {"观测事实": "observation", "统计关联": "association", "机制假设": "inference"}
RELATION_MAP = {
    "支持我的假设": "SUPPORTS",
    "反对我的假设": "CONTRADICTS_MY_HYPOTHESIS",
    "条件不同，不能直接比": "CONDITION_MISMATCH",
    "方法可以参考": "METHOD_REFERENCE",
}

# 卡片里需要人填的关键字段（完整度判定）
REQUIRED = ["research_question", "core_conclusion", "data_methods",
            "key_results", "claim_strength", "relation", "doubts"]


def configure_console_output():
    """Keep dynamic user text printable on legacy Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="backslashreplace")
        except (OSError, ValueError):
            pass


def load(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def slug(author, year, title):
    base = (author or "paper").strip().split()[-1] if author else "paper"
    base = re.sub(r"[^\w一-鿿-]", "", base) or "paper"
    return f"{base}{year or 'n.d.'}"


def card_path(ws, name):
    d = ws / CARD_DIR
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.md"
    return p


def cmd_card(ws, a):
    name = slug(a.author, a.year, a.title)
    p = card_path(ws, name)
    if p.exists():
        print(f"卡片已存在：{p}（要重做请先删除）")
        return
    meta = {
        "id": None, "title": a.title or "", "first_author": a.author or "",
        "year": a.year, "journal": a.journal or "", "doi": a.doi or "",
        "pdf": a.file or "",
        "research_question": "", "hypothesis": "", "data_methods": "",
        "key_results": [], "claim_strength": "", "relation": "",
        "doubts": "", "unclear_terms": [],
        "pass1_birdview": {"relevant": "", "decision": ""},
        "pass3_critique": {"assumptions": "", "confounds": "", "avoided": "", "my_take": ""},
        "synced": False,
    }
    body = f"""# 精读卡片：{a.title or '（填标题）'}

<!-- META（脚本读取此 JSON 块，请勿删除这两行注释）
{json.dumps(meta, ensure_ascii=False, indent=2)}
-->

> 三遍法协议见 modules/paper-reading-guide.md。带 [必填] 标记的是必填，填不出来就是没读懂，回去重读。

## 第一遍 · 鸟瞰（10-15 分钟，只看标题/摘要/图表标题/结论段）
- 和我的方向直接相关吗：
- 一句话核心结论 [必填]：
- 用了什么数据/方法：
- 处置（精读 / 泛读 / 跳过）：

## 第二遍 · 拆解（1-2 小时，逐节填）
- **研究问题** [必填]（具体到"什么条件下、什么量、和什么的关系"）：
- **核心假设**（作者预期什么）：
- **数据与方法** [必填]（仪器/样本量/时间范围/分析方法）：
- **关键结果** [必填]（最多3条，每条必须带具体数字）：
  1.
  2.
  3.
- **结论强度** [必填]（三选一，在前面 [ ] 里填 x，不许混）：
  - [ ] 观测事实（我们看到了X）
  - [ ] 统计关联（X和Y相关）
  - [ ] 机制假设（推测因为Z）
- **和我研究的关系** [必填]（四选一填 x）：
  - [ ] 支持我的假设
  - [ ] 反对我的假设
  - [ ] 条件不同，不能直接比
  - [ ] 方法可以参考
- **存疑的地方** [必填]（漏洞/过度推导/没说清的）：
- **没懂的术语/方法**（记下来查或问导师）：

## 第三遍 · 批判（30-60 分钟，挑毛病）
1. 作者没说出口的前提假设：
2. 数据方法真能支撑结论吗？漏掉什么混淆因素：
3. 讨论里回避了什么：
4. 换我来做，哪里不一样：

## 读完自测（合上书，用自己的话讲给外行听）
- 一句话复述：
"""
    p.write_text(body, encoding="utf-8")
    print(f"已生成卡片骨架：{p}")
    print("按三遍法填写，带 [必填] 标记的字段必须填写。填完运行：")
    print(f"  python scripts/reading.py check {ws}")


def parse_card(p: Path):
    text = p.read_text(encoding="utf-8")
    m = re.search(r"<!-- META.*?\n(.*?)\n-->", text, re.S)
    meta = json.loads(m.group(1)) if m else {}
    # 以正文勾选/内容为准，回填几个关键字段（防止只改了 markdown 没改 JSON）
    sm = re.search(r"结论强度.*?\n((?:\s*- \[.\][^\n]*\n){3})", text, re.S)
    if sm:
        for line, key in zip(re.findall(r"- \[(.)\]\s*([^\n]*)", sm.group(1)),
                             ("观测事实", "统计关联", "机制假设")):
            if line[0].lower() == "x":
                meta["claim_strength"] = key
    rm = re.search(r"和我研究的关系.*?\n((?:\s*- \[.\][^\n]*\n){4})", text, re.S)
    if rm:
        for mark, key in zip(re.findall(r"- \[(.)\]\s*([^\n]*)", rm.group(1)),
                             ("支持我的假设", "反对我的假设", "条件不同，不能直接比", "方法可以参考")):
            if mark[0].lower() == "x":
                meta["relation"] = key
    # 关键结果：数"1. 2. 3."后面非空的行
    kr = re.search(r"关键结果.*?\n((?:\s*\d\.[^\n]*\n){1,3})", text, re.S)
    if kr:
        items = [re.sub(r"^\s*\d\.\s*", "", x).strip()
                 for x in kr.group(1).splitlines()]
        items = [x for x in items if x]
        if items:
            meta["key_results"] = items
    # 自由文本字段：取同一行冒号后内容（[ \t] 不跨行，避免吃到下一行标签）
    def after(label):
        mm = re.search(re.escape(label) + r"[^：\n]*：[ \t]*([^\n]*)", text)
        return mm.group(1).strip() if mm and mm.group(1).strip() else meta.get(label, "")
    meta["research_question"] = after("**研究问题**") or meta.get("research_question", "")
    meta["core_conclusion"] = after("一句话核心结论") or meta.get("core_conclusion", "")
    meta["data_methods"] = after("**数据与方法**") or meta.get("data_methods", "")
    meta["doubts"] = after("**存疑的地方**") or meta.get("doubts", "")
    return meta


def completeness(meta):
    missing = []
    if not meta.get("research_question"):
        missing.append("研究问题")
    if not meta.get("core_conclusion"):
        missing.append("一句话核心结论")
    if not meta.get("data_methods"):
        missing.append("数据与方法")
    kr = meta.get("key_results") or []
    if not kr:
        missing.append("关键结果（至少1条且带数字）")
    elif not any(re.search(r"\d", str(x)) for x in kr):
        missing.append("关键结果必须带具体数字")
    if meta.get("claim_strength") not in STRENGTH_MAP:
        missing.append("结论强度三选一")
    if meta.get("relation") not in RELATION_MAP:
        missing.append("和我研究的关系四选一")
    if not meta.get("doubts"):
        missing.append("存疑的地方")
    return missing


def collect(ws):
    d = ws / CARD_DIR
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.md")):
        try:
            meta = parse_card(p)
        except (json.JSONDecodeError, re.error):
            meta = {"_parse_error": True}
        meta["_file"] = p.relative_to(ws).as_posix()
        out.append(meta)
    return out


def cmd_list(ws):
    cards = collect(ws)
    if not cards:
        print("还没有精读卡片。用 card 命令生成：")
        print(f"  python scripts/reading.py card {ws} --title \"论文标题\"")
        return
    print(f"共 {len(cards)} 张精读卡片：\n")
    for m in cards:
        if m.get("_parse_error"):
            print(f"  [WARN] {m['_file']} META 块损坏，无法解析")
            continue
        miss = completeness(m)
        tag = "[OK] 完整" if not miss else f"[进行中] 缺{len(miss)}项"
        title = m.get("title") or m.get("_file")
        synced = "已同步" if m.get("synced") else "未同步"
        print(f"  {tag} [{synced}] {m.get('first_author','?')}{m.get('year','')} {title[:34]}")
        if miss:
            print(f"        缺：{'、'.join(miss)}")


def cmd_check(ws):
    cards = collect(ws)
    bad = [(m, completeness(m)) for m in cards if not m.get("_parse_error")]
    bad = [(m, x) for m, x in bad if x]
    corrupted = [m for m in cards if m.get("_parse_error")]
    if not cards:
        print("[ERROR] 没有任何精读卡片。P0 至少精读 2 篇代表作。")
        sys.exit(1)
    if corrupted:
        for m in corrupted:
            print(f"[WARN] META 块损坏：{m['_file']}")
    if bad:
        print("[ERROR] 以下卡片不完整，没填完不算读过：\n")
        for m, miss in bad:
            print(f"  {m.get('_file')}：缺 {'、'.join(miss)}")
        sys.exit(1)
    print(f"[OK] {len(cards)} 张卡片全部完整。可运行 sync 同步进 evidence.json。")


def cmd_sync(ws):
    cards = collect(ws)
    complete = [m for m in cards if not m.get("_parse_error") and not completeness(m)]
    if not complete:
        print("没有完整卡片可同步，先运行 check 看缺什么。")
        sys.exit(1)

    ev_path = ws / "evidence.json"
    ev = load(ev_path, default={})
    if isinstance(ev, list):
        ev = {"evidence": ev}
    ev.setdefault("evidence", [])
    records = ev["evidence"]

    # 复用现有最大编号
    existing_doi = {r.get("doi") or r.get("source"): r for r in records if isinstance(r, dict)}
    n_new = n_upd = 0
    for m in complete:
        key = m.get("doi") or m.get("pdf") or m.get("title")
        old = existing_doi.get(key)
        claim_level = STRENGTH_MAP[m["claim_strength"]]
        entry = {
            "source": m.get("doi") or m.get("pdf") or m.get("title"),
            "title": m.get("title"), "first_author": m.get("first_author"),
            "year": m.get("year"), "journal": m.get("journal"), "doi": m.get("doi"),
            "locator": "精读卡片，见 reading_card",
            "evidence_level": "full_text",
            "is_core_reading": True,
            "reading_card": m["_file"],
            "claim": m.get("core_conclusion"),
            "claim_level": claim_level,
            "relation_to_my_work": RELATION_MAP[m["relation"]],
            "key_results": m.get("key_results"),
            # 卡片不代替身份核验：同步后必须另跑引用核验
            "citation_verdict": "UNRESOLVED",
            "support_status": None,
        }
        if old:
            old.update({k: v for k, v in entry.items() if v})
            n_upd += 1
        else:
            entry["id"] = f"E{len(records) + 1}"
            records.append(entry)
            existing_doi[key] = entry
            n_new += 1
        # 标记卡片已同步
        cp = ws / m["_file"]
        txt = cp.read_text(encoding="utf-8")
        txt = re.sub(r'("synced":\s*)false', r'\g<1>true', txt)
        cp.write_text(txt, encoding="utf-8")

    save(ev_path, ev)
    print(f"[OK] 同步完成：新增 {n_new} 条，更新 {n_upd} 条 -> {ev_path}")
    print("[WARN] 这些条目 citation_verdict=UNRESOLVED、support_status 为空；")
    print("   精读不等于核验，接下来必须跑引用身份+支持两道核验才能计入 Gate 2。")


def main():
    configure_console_output()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("card")
    pc.add_argument("workspace")
    pc.add_argument("--title"); pc.add_argument("--author")
    pc.add_argument("--year"); pc.add_argument("--journal")
    pc.add_argument("--doi"); pc.add_argument("--file")
    for name in ("list", "check", "sync"):
        p = sub.add_parser(name); p.add_argument("workspace")
    a = ap.parse_args()
    ws = Path(a.workspace)
    if a.cmd == "card":
        cmd_card(ws, a)
    elif a.cmd == "list":
        cmd_list(ws)
    elif a.cmd == "check":
        cmd_check(ws)
    else:
        cmd_sync(ws)


if __name__ == "__main__":
    main()
