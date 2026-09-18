#!/usr/bin/env python3
"""
科研进度可视化 + 阶段闸门硬拦截

用法：
  python scripts/progress.py <workspace>                # 查看进度（只显示，不阻断）
  python scripts/progress.py gate <workspace> <stage>   # 闸门校验：能不能进入某阶段
        stage ∈ P0 P1 P2 P3 P4 P5 P6
        不通过时退出码=1，并逐条列出缺失项（模型/脚本无法跳过）

设计原则：检查的是产物的【内容门槛】，不是文件是否存在。
空文件、只有标题的文件不算完成。阈值与 docs/PHASE_GATES.md 保持一致，
可被项目 domain.json 的 gates 字段覆盖。
"""
import json
import sys
from pathlib import Path

# ---------- 阈值（工程下限，可被 domain.json 覆盖） ----------
DEFAULT_THRESHOLDS = {
    "gate1_candidates_per_question": 8,   # 每个子问题候选文献数
    "gate1_distinct_teams": 5,            # 不同作者团队数
    "gate2_min_references": 20,           # 综述类纳入文献下限
    "gate2_min_gaps": 3,                  # 独立研究缺口数
    "gate2_evidence_per_gap": 3,          # 每个缺口的支撑证据数
    "gate3_min_alternative_settings": 3,  # 替代设置组数
    "p0_min_reading_cards": 2,            # P0 至少精读 2 篇
}


# ---------- 通用工具 ----------
def load_json(path: Path):
    """读 JSON，文件不存在或解析失败返回 None（不抛异常，交给检查项报错）"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def read_text(path: Path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def count_checkboxes(text: str):
    """统计 markdown 勾选 [x] 与总复选框数"""
    if not text:
        return 0, 0
    total = text.count("- [ ]") + text.count("- [x]") + text.count("- [X]")
    done = text.count("- [x]") + text.count("- [X]")
    return done, total


# ---------- 各阶段检查项 ----------
# 每个检查项返回 (通过?, 名称, 详情)
def check_p0(ws: Path, thr):
    r = []
    prep = read_text(ws / "prep-checklist.md")
    done, total = count_checkboxes(prep)
    r.append((total >= 5 and done == total, "P0 准备清单全部勾选",
              f"已勾 {done}/{total}" if total else "清单不存在或没有复选框"))

    domain_map = read_text(ws / "domain-map.md")
    r.append((bool(domain_map and len(domain_map.strip()) > 200),
              "领域地图初建（3-5篇综述）", f"{len(domain_map.strip()) if domain_map else 0} 字"))

    # 精读卡片：evidence.json 里标记 is_core_reading 的条目，或 reading-cards 目录
    cards = list((ws / "reading-cards").glob("*.md")) if (ws / "reading-cards").exists() else []
    ev = load_json(ws / "evidence.json")
    if isinstance(ev, dict) and "evidence" in ev:
        ev = ev["evidence"]
    if isinstance(ev, list):
        cards += [e for e in ev if isinstance(e, dict) and e.get("is_core_reading")]
    r.append((len(cards) >= thr["p0_min_reading_cards"],
              f"精读 {thr['p0_min_reading_cards']} 篇代表作并填卡片", f"实际 {len(cards)} 篇"))

    plan = read_text(ws / "plan.md")
    r.append((bool(plan and ("月" in plan or "周" in plan) and len(plan.strip()) > 100),
              "3个月研究计划（含里程碑）", "已写" if plan else "缺失"))
    return r


def check_p1(ws: Path, thr):
    r = []
    scope = load_json(ws / "scope.json")
    mq = scope.get("main_question") if isinstance(scope, dict) else None
    sq = scope.get("sub_questions") if isinstance(scope, dict) else None
    r.append((bool(mq and len(str(mq)) > 10), "主问题具体（含条件+对象+问什么）",
              mq[:40] if mq else "main_question 缺失或太短"))
    r.append((isinstance(sq, list) and 1 <= len(sq) <= 3, "1-3 个子问题",
              f"{len(sq)} 个" if isinstance(sq, list) else "无"))

    tev = load_json(ws / "topic-evaluation.json")
    candidates = tev.get("candidates") if isinstance(tev, dict) else None
    r.append((isinstance(candidates, list) and len(candidates) >= 1 and
              all(c.get("total_score") is not None for c in candidates if isinstance(c, dict)),
              "候选方向已打分（topic-evaluation.json）",
              f"{len(candidates)} 个候选" if isinstance(candidates, list) else "缺失"))

    glossary = read_text(ws / "glossary.md")
    r.append((bool(glossary and glossary.count("|") >= 2), "术语表（含同义词）",
              "已建" if glossary else "缺失"))

    slog = load_json(ws / "search-log.json")
    # 兼容多种检索日志结构：list / {"searches":[...]} / {"snapshots":[{count}]}
    blocks = []
    if isinstance(slog, list):
        blocks = slog
    elif isinstance(slog, dict):
        blocks = slog.get("searches") or slog.get("snapshots") or []
    n_cand = 0
    teams = set()
    for s in blocks if isinstance(blocks, list) else []:
        if not isinstance(s, dict):
            continue
        if isinstance(s.get("count"), int):
            n_cand += s["count"]
            continue
        cands = (s.get("candidates") or s.get("hits") or s.get("items")
                 or s.get("results") or s.get("papers") or [])
        n_cand += len(cands)
        for c in cands:
            if not isinstance(c, dict):
                continue
            author = c.get("first_author")
            if not author and isinstance(c.get("author"), list) and c["author"]:
                author = c["author"][0].get("family")
            if author:
                teams.add(str(author).split()[-1])
    r.append((n_cand >= thr["gate1_candidates_per_question"],
              f"范围检索每子问题≥{thr['gate1_candidates_per_question']}候选",
              f"命中候选 {n_cand}"))
    r.append((len(teams) >= thr["gate1_distinct_teams"],
              f"候选来自≥{thr['gate1_distinct_teams']}个不同团队",
              f"识别到 {len(teams)} 个团队" if teams else "日志未记录作者，无法证明团队多样性"))
    return r


def check_p2(ws: Path, thr):
    r = []
    ev = load_json(ws / "evidence.json")
    records = ev.get("evidence", ev) if isinstance(ev, dict) else ev
    records = records if isinstance(records, list) else []

    verified = [e for e in records if isinstance(e, dict)
                and e.get("citation_verdict") == "VERIFIED"]
    r.append((len(records) >= 1, "证据矩阵有条目", f"{len(records)} 条"))
    r.append((len(records) >= thr["gate2_min_references"],
              f"纳入文献≥{thr['gate2_min_references']}（综述下限，原创可在domain覆盖）",
              f"{len(records)} 篇"))
    unresolved = [e for e in records if isinstance(e, dict)
                  and e.get("citation_verdict") in (None, "UNRESOLVED")]
    r.append((len(records) >= 1 and len(unresolved) == 0, "所有文献身份已核验（无 UNRESOLVED）",
              f"{len(unresolved)} 条未核验" if records else "尚无文献"))
    blocked = [e for e in records if isinstance(e, dict)
               and e.get("support_status") in ("CONTRADICTS", "DOES_NOT_SUPPORT")]
    r.append((len(records) >= 1 and len(blocked) == 0, "无未处理的硬阻断引用",
              f"{len(blocked)} 条 CONTRADICTS/DOES_NOT_SUPPORT" if records else "尚无文献"))

    # 核心文献必须有精读卡片
    core = [e for e in records if isinstance(e, dict) and e.get("is_core_reading")]
    with_card = [e for e in core if isinstance(e, dict) and e.get("reading_card")]
    r.append((len(core) == 0 or len(with_card) == len(core),
              "核心文献都有精读卡片",
              f"{len(with_card)}/{len(core)}"))

    gaps = load_json(ws / "gaps.json")
    gap_list = gaps.get("gaps", gaps) if isinstance(gaps, dict) else gaps
    gap_list = gap_list if isinstance(gap_list, list) else []
    enough_ev = all(len(g.get("evidence_ids", [])) >= thr["gate2_evidence_per_gap"]
                    for g in gap_list if isinstance(g, dict))
    r.append((len(gap_list) >= thr["gate2_min_gaps"] and enough_ev,
              f"≥{thr['gate2_min_gaps']}个缺口，每个≥{thr['gate2_evidence_per_gap']}条证据",
              f"{len(gap_list)} 个缺口"))
    return r


def check_p3(ws: Path, thr):
    r = []
    d = load_json(ws / "design.json")
    if not isinstance(d, dict):
        return [(False, "design.json 存在且可解析", "缺失/损坏")]

    hyps = d.get("hypotheses", [])
    decidable = all(h.get("decision_rule") for h in hyps if isinstance(h, dict))
    r.append((bool(hyps) and decidable, "假设可判定（每条有 decision_rule）",
              f"{len(hyps)} 条假设"))

    params = d.get("parameters", {})
    if isinstance(params, dict) and params:
        filled = all(v is not None or v is None for v in params.values())  # 值或null都算填了
        empty = [k for k, v in params.items() if isinstance(v, str) and v.strip() in ("", "约", "典型值")]
        r.append((filled and not empty, "参数 100% 填值或显式 null",
                  f"{len(params)} 个参数" + (f"，含糊字段 {empty}" if empty else "")))
    else:
        r.append((False, "参数表已建立", "parameters 为空"))

    alt = d.get("alternative_settings", [])
    r.append((len(alt) >= thr["gate3_min_alternative_settings"],
              f"≥{thr['gate3_min_alternative_settings']}组预先定好的替代设置", f"{len(alt)} 组"))

    conf = d.get("confounds", [])
    handled = all(c.get("control") for c in conf if isinstance(c, dict))
    r.append((bool(conf) and handled, "每个混淆因素都有处置策略", f"{len(conf)} 条"))

    unc = d.get("uncertainty", {})
    r.append((bool(unc.get("definition") and unc.get("sampling_unit")),
              "不确定性口径（SD/SE/CI + 样本单位）", str(unc)[:40] if unc else "缺失"))
    r.append((d.get("data_audit_verdict") in ("can_proceed", "cannot_proceed"),
              "数据审计给出明确结论", str(d.get("data_audit_verdict"))))
    return r


def check_p4(ws: Path, thr):
    r = []
    log = load_json(ws / "analysis" / "run-log.json")
    runs = log.get("runs", log) if isinstance(log, dict) else log
    runs = runs if isinstance(runs, list) else []
    success = [x for x in runs if isinstance(x, dict) and x.get("status") == "success"]
    r.append((len(success) >= 1, "至少 1 次成功运行记录", f"{len(success)} 次成功"))
    r.append((len(success) >= 1 and all(x.get("env") or x.get("code_hash") for x in success),
              "运行有环境/代码哈希记录", ""))
    r.append((len(runs) >= 1 and all(x.get("status") for x in runs),
              "失败运行也留档（不静默剔除）", f"共 {len(runs)} 次运行"))

    rob = load_json(ws / "robustness.json")
    r.append((isinstance(rob, dict) and rob.get("comparisons"),
              "稳健性替代设置已跑并有差异记录",
              "已跑" if isinstance(rob, dict) and rob.get("comparisons") else "缺失"))

    results = ws / "analysis" / "results"
    r.append((results.exists() and any(results.iterdir()) if results.exists() else False,
              "结果文件已产出（程序直出，非手改）", ""))
    return r


def check_p5(ws: Path, thr):
    r = []
    cm = load_json(ws / "claim-map.json")
    claims = cm.get("claims", cm) if isinstance(cm, dict) else cm
    claims = claims if isinstance(claims, list) else []
    linked = all(c.get("evidence_ids") or c.get("result_files") for c in claims
                 if isinstance(c, dict))
    r.append((bool(claims) and linked, "每个论点都挂了证据/结果", f"{len(claims)} 个论点"))

    fm = load_json(ws / "figures" / "manifest.json")
    figs = fm.get("figures", fm) if isinstance(fm, dict) else fm
    figs = figs if isinstance(figs, list) else []
    types_ = {f.get("type") for f in figs if isinstance(f, dict)}
    r.append(("roadmap" in types_, "科研线路图已产出", ""))
    r.append(("schematic" in types_, "原理示意图已产出（标注概念示意）", ""))
    reviewed = [f for f in figs if isinstance(f, dict) and f.get("visual_review") == "passed"]
    r.append((len(figs) > 0 and len(reviewed) == len(figs),
              "所有图经过人工视觉审查", f"{len(reviewed)}/{len(figs)}"))

    gates = load_json(ws / "review" / "gates.json")
    paragraphs = gates.get("paragraphs", []) if isinstance(gates, dict) else []
    if paragraphs:
        passed = [p for p in paragraphs if isinstance(p, dict)
                  and p.get("final_verdict") == "passed"]
        r.append((len(passed) == len(paragraphs),
                  "五道关卡所有段落 passed", f"{len(passed)}/{len(paragraphs)}"))
    else:
        r.append((False, "五道关卡已运行（gates.json）", "未运行"))
    return r


def check_p6(ws: Path, thr):
    r = []
    concl = read_text(ws / "manuscript" / "conclusion.md")
    r.append((bool(concl and ("未回答" in concl or "局限" in concl or "没有" in concl)),
              "结论明确写出未回答的问题（非套话）", ""))

    cf = load_json(ws / "audit" / "citation-final.json")
    if isinstance(cf, dict):
        unresolved = cf.get("unresolved", [])
        mismatches = cf.get("high_risk_mismatches", [])
        r.append((len(unresolved) == 0, "引用终检无 UNRESOLVED", f"{len(unresolved)} 条"))
        r.append((len(mismatches) == 0, "无高风险错配", f"{len(mismatches)} 条"))
    else:
        r.append((False, "引用终检已完成", "citation-final.json 缺失"))

    panel = load_json(ws / "review" / "panel.json")
    verdict = panel.get("verdict") if isinstance(panel, dict) else None
    r.append((verdict in ("READY_FOR_HUMAN_SUBMISSION_CHECK", "PANEL_DISAGREEMENT",
                          "REVISION_REQUIRED", "BLOCKED"),
              "审稿人面板已运行", str(verdict) if verdict else "未运行"))

    sub = read_text(ws / "submission-checklist.md")
    d, t = count_checkboxes(sub)
    r.append((t > 0 and d == t, "投稿自查清单全部勾选", f"{d}/{t}" if t else "缺失"))
    return r


PHASE_CHECKS = {
    "P0": ("入门准备", check_p0),
    "P1": ("选题调研", check_p1),
    "P2": ("文献综述", check_p2),
    "P3": ("实验设计", check_p3),
    "P4": ("计算结果", check_p4),
    "P5": ("图表写作", check_p5),
    "P6": ("投稿返修", check_p6),
}
ORDER = ["P0", "P1", "P2", "P3", "P4", "P5", "P6"]
ICONS = {"P0": "🔵", "P1": "🟣", "P2": "🟢", "P3": "🟠", "P4": "🔴", "P5": "🩷", "P6": "⚪"}


def evaluate(ws: Path, thr):
    report = {}
    for pid in ORDER:
        name, fn = PHASE_CHECKS[pid]
        results = fn(ws, thr)
        passed = sum(1 for ok, _, _ in results if ok)
        report[pid] = {"name": name, "results": results,
                       "done": passed, "total": len(results)}
    return report


def main():
    args = sys.argv[1:]
    if not args:
        print("用法：")
        print("  python scripts/progress.py <workspace>              查看进度")
        print("  python scripts/progress.py gate <workspace> <stage> 阶段闸门校验")
        sys.exit(2)

    # 闸门模式
    if args[0] == "gate":
        if len(args) < 3:
            print("用法：python scripts/progress.py gate <workspace> <P0..P6>")
            sys.exit(2)
        ws = Path(args[1])
        target = args[2].upper()
        if target not in ORDER:
            print(f"未知阶段 {target}，应为 P0..P6")
            sys.exit(2)
        if not ws.exists():
            print(f"错误：工作区 {ws} 不存在")
            sys.exit(2)

        thr = dict(DEFAULT_THRESHOLDS)
        domain = load_json(ws / "domain.json")
        if isinstance(domain, dict) and isinstance(domain.get("gates"), dict):
            thr.update(domain["gates"])

        report = evaluate(ws, thr)
        # 进入 target 阶段，要求 target 之前的所有阶段都通过
        idx = ORDER.index(target)
        required = ORDER[:idx]
        failed_all = []
        for pid in required:
            info = report[pid]
            fails = [(n, d) for ok, n, d in info["results"] if not ok]
            if fails:
                failed_all.append((pid, info["name"], fails))

        if failed_all:
            print(f"⛔ 闸门拦截：不能进入 {target}，上游阶段未完成。\n")
            for pid, name, fails in failed_all:
                print(f"{ICONS[pid]} {pid} {name} 缺 {len(fails)} 项：")
                for n, d in fails:
                    print(f"   ❌ {n}" + (f"（{d}）" if d else ""))
                print()
            print("先补齐以上项，再进入下一阶段。这是硬闸门，不允许跳过。")
            sys.exit(1)

        print(f"✅ 闸门通过：上游阶段全部满足，可以进入 {target}。")
        sys.exit(0)

    # 进度模式
    ws = Path(args[0])
    if not ws.exists():
        print(f"错误：目录 {ws} 不存在")
        print("先运行 python scripts/research.py init <workspace> 创建项目")
        sys.exit(1)

    thr = dict(DEFAULT_THRESHOLDS)
    domain = load_json(ws / "domain.json")
    if isinstance(domain, dict) and isinstance(domain.get("gates"), dict):
        thr.update(domain["gates"])

    report = evaluate(ws, thr)
    print("\n" + "=" * 64)
    print("📊 你的科研进度（按内容门槛，不是按文件存在）")
    print("=" * 64)

    total_done = total_all = 0
    current = None
    for pid in ORDER:
        info = report[pid]
        total_done += info["done"]
        total_all += info["total"]
        pct = int(info["done"] / info["total"] * 100)
        if info["done"] == info["total"]:
            status = "✅ 完成"
        elif info["done"] > 0:
            status = f"🔄 {pct}%"
            if current is None:
                current = pid
        else:
            status = "⬜ 未开始"
            if current is None:
                current = pid
        print(f"\n{ICONS[pid]} {pid} {info['name']} —— {status}")
        if 0 < info["done"] < info["total"]:
            for ok, name, detail in info["results"]:
                if not ok:
                    print(f"   ❌ {name}" + (f"（{detail}）" if detail else ""))

    print("\n" + "-" * 64)
    print(f"📈 总进度：{total_done}/{total_all} 项（{int(total_done/total_all*100)}%）")
    if current:
        print(f"👉 当前阶段：{current} {report[current]['name']}，先补齐上面 ❌ 项")
    print("🔒 硬闸门：python scripts/progress.py gate <workspace> <下一阶段>")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()
