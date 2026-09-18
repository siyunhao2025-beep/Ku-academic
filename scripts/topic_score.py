#!/usr/bin/env python3
"""
研究方向五维打分（与 modules/topic-evaluation.md 严格对齐）

用法：
  python scripts/topic_score.py init  <workspace> [--names "方向A,方向B"]
        生成 topic-evaluation.json 打分模板（客观字段留空，附填写说明）
  python scripts/topic_score.py score <workspace>
        计算客观分；主观分（风险/资源）缺失时，列出必须你和导师确认的项，
        不替你拍板；全部填完才给排名、淘汰标记和推荐。

原则：客观分从检索数据算，主观分必须本人填并写理由。脚本不编造任何分数。
"""
import argparse
import json
import sys
from pathlib import Path

WEIGHTS = {"feasibility": 0.30, "innovation": 0.25, "value": 0.20,
           "risk": 0.15, "resource": 0.10}
ELIMINATE = 3.0          # 低于此分淘汰
CHOOSE_FEASIBILITY = 3.5  # 多个方向高于此分时，选可行性最高的

DATA_MAP = {"ready": 5, "partial": 3, "unavailable": 1}
METHOD_MAP = {"mature": 5, "need_learn": 3, "unused": 1}


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def band(value, cuts, scores):
    """按切点分档：cuts 为上界列表，scores 为对应分。value<cuts[0]→scores[0] ..."""
    for c, s in zip(cuts, scores):
        if value < c:
            return s
    return scores[-1]


def score_innovation(hits, ratio, gap_reviews):
    """创新性：近10年命中数 + 近3年占比；5分需≥3篇高被引综述明确提到缺口"""
    if hits is None or ratio is None:
        return None, "缺命中数或近3年占比"
    heat = band(hits, [100, 501], [5, 3, 1])            # <100→5, 100-500→3, >500→1
    crowd = band(ratio, [0.30, 0.601], [5, 3, 1])       # <30%→5, 30-60%→3, >60%→1
    raw = (heat + crowd) / 2
    note = f"命中{hits}篇(热度{heat})，近3年占比{ratio:.0%}(拥挤{crowd})"
    if raw >= 4.5 and (gap_reviews is None or gap_reviews < 3):
        return 3.0, note + "；但高被引综述提到该缺口<3篇，按死路保护封顶3分"
    return raw, note


def score_feasibility(inp):
    data = DATA_MAP.get(inp.get("data_available"))
    method = METHOD_MAP.get(inp.get("method_mature"))
    months = inp.get("first_result_months")
    if data is None or method is None or months is None:
        return None, "缺数据可得性/方法成熟度/出首个结果时间"
    time_score = 5 if months <= 3 else (3 if months <= 6 else 1)
    return (data + method + time_score) / 3, f"数据{data}·方法{method}·时间{time_score}"


def score_value(inp):
    hc = inp.get("high_cited_count")
    apps = inp.get("applications_or_projects")
    if hc is None or apps is None:
        return None, "缺高被引数或应用/项目数"
    hc_s = band(hc, [1, 6], [1, 3, 5])          # 0→1, 1-5→3, >5→5
    ap_s = band(apps, [1, 3], [1, 3, 5])        # 0→1, 1-2→3, >=3→5
    return (hc_s + ap_s) / 2, f"高被引{hc}({hc_s})，应用/项目{apps}({ap_s})"


def cmd_init(ws, names):
    ws.mkdir(parents=True, exist_ok=True)
    target = ws / "topic-evaluation.json"
    if target.exists():
        print(f"已存在 {target}，不覆盖。要重填请先删除。")
        return
    names = [n.strip() for n in (names or "方向1,方向2").split(",") if n.strip()]
    blank_in = {
        "total_hits_10y": None, "recent3_ratio": None,
        "high_cited_reviews_mentioning_gap": None,
        "high_cited_count": None, "applications_or_projects": None,
        "data_available": None, "method_mature": None,
        "first_result_months": None,
    }
    obj = {
        "_填写说明": {
            "total_hits_10y": "近10年检索命中总数（整数）",
            "recent3_ratio": "近3年文献占比，0-1 小数，如 0.45",
            "high_cited_reviews_mentioning_gap": "明确提到该缺口的高被引综述篇数",
            "high_cited_count": "该方向高被引文献数",
            "applications_or_projects": "近5年相关实际应用/项目数",
            "data_available": "ready=现成 / partial=需申请 / unavailable=拿不到",
            "method_mature": "mature=成熟 / need_learn=需要学 / unused=没人用过",
            "first_result_months": "预计几个月出第一个结果（整数）",
            "risk": "风险可控 1-5 分 + 一句话理由（和导师确认）",
            "resource": "资源匹配 1-5 分 + 一句话理由（和导师确认）",
        },
        "candidates": [
            {"name": n, "objective_inputs": dict(blank_in),
             "subjective_scores": {
                 "risk": {"score": None, "reason": None},
                 "resource": {"score": None, "reason": None}}}
            for n in names],
    }
    save(target, obj)
    print(f"已生成打分模板：{target}")
    print("请填入每个方向的【检索数据】（客观）和【风险/资源】分（和导师确认），再运行：")
    print(f"  python scripts/topic_score.py score {ws}")


def cmd_score(ws):
    target = ws / "topic-evaluation.json"
    obj = load(target)
    if not obj or "candidates" not in obj:
        print("找不到 topic-evaluation.json，先运行 init。")
        sys.exit(2)

    rows, missing = [], []
    for c in obj["candidates"]:
        inp = c.get("objective_inputs", {})
        inn, inn_note = score_innovation(inp.get("total_hits_10y"),
                                         inp.get("recent3_ratio"),
                                         inp.get("high_cited_reviews_mentioning_gap"))
        fea, fea_note = score_feasibility(inp)
        val, val_note = score_value(inp)
        risk = c.get("subjective_scores", {}).get("risk", {})
        res = c.get("subjective_scores", {}).get("resource", {})

        c["_objective_detail"] = {"innovation": inn_note, "feasibility": fea_note,
                                  "value": val_note}
        c["scores"] = {"innovation": inn, "feasibility": fea, "value": val,
                       "risk": risk.get("score"), "resource": res.get("score")}

        need = []
        if inn is None: need.append("创新性数据（命中数/近3年占比）")
        if fea is None: need.append("可行性数据（数据/方法/时间）")
        if val is None: need.append("价值数据（高被引/应用数）")
        if risk.get("score") is None or not risk.get("reason"):
            need.append("风险可控分+理由（和导师确认）")
        if res.get("score") is None or not res.get("reason"):
            need.append("资源匹配分+理由（和导师确认）")
        if need:
            missing.append((c["name"], need))
            continue

        total = (fea * WEIGHTS["feasibility"] + inn * WEIGHTS["innovation"]
                 + val * WEIGHTS["value"] + risk["score"] * WEIGHTS["risk"]
                 + res["score"] * WEIGHTS["resource"])
        c["total_score"] = round(total, 2)
        rows.append(c)

    if missing:
        print("⛔ 还不能排名，以下信息缺。客观项去检索平台数，主观项找导师聊：\n")
        for name, need in missing:
            print(f"【{name}】")
            for n in need:
                print(f"   - {n}")
            print()
        print("补齐后重新运行 score。脚本不会替你猜这些分。")
        save(target, obj)
        sys.exit(1)

    rows.sort(key=lambda c: c["total_score"], reverse=True)
    print("=" * 60)
    print("📊 方向五维打分结果（1-5 分，加权总分）")
    print("=" * 60)
    print(f"{'方向':<16}{'可行':>5}{'创新':>5}{'价值':>5}{'风险':>5}{'资源':>5}{'总分':>7}  结论")
    print("-" * 60)
    survivors = [c for c in rows if c["total_score"] >= ELIMINATE]
    for c in rows:
        s = c["scores"]
        verdict = "❌淘汰(<3.0)" if c["total_score"] < ELIMINATE else "保留"
        print(f"{c['name']:<16}{s['feasibility']:>5.1f}{s['innovation']:>5.1f}"
              f"{s['value']:>5.1f}{s['risk']:>5.1f}{s['resource']:>5.1f}"
              f"{c['total_score']:>7.2f}  {verdict}")
    print("-" * 60)

    if not survivors:
        rec = "所有方向都低于 3.0，一个都别选——回去多读综述再找方向。"
    elif len(survivors) == 1 or survivors[0]["total_score"] >= CHOOSE_FEASIBILITY \
            and (len(survivors) == 1 or survivors[0]["scores"]["feasibility"]
                 >= survivors[1]["scores"]["feasibility"]):
        top = survivors[0]
        high = [c for c in survivors if c["total_score"] >= CHOOSE_FEASIBILITY]
        if len(high) >= 2:
            best = max(high, key=lambda c: c["scores"]["feasibility"])
            rec = (f"有 {len(high)} 个方向≥{CHOOSE_FEASIBILITY}，按规则选可行性最高的："
                   f"【{best['name']}】。新手先求毕业，再谈理想。")
        else:
            rec = f"推荐【{top['name']}】（{top['total_score']} 分），唯一/最高且过线。"
    else:
        rec = f"推荐【{survivors[0]['name']}】，但分差不大，建议和导师再确认风险与资源。"
    print(f"\n👉 {rec}")
    print("\n选定后再问三件事：3个月能出小结果吗？失败有中间产出吗？导师支持吗？")

    obj["recommendation"] = rec
    obj["ranked"] = [c["name"] for c in rows]
    save(target, obj)
    print(f"\n已写回 {target}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("workspace")
    p_init.add_argument("--names", default=None)
    p_score = sub.add_parser("score")
    p_score.add_argument("workspace")
    a = ap.parse_args()
    ws = Path(a.workspace)
    if a.cmd == "init":
        cmd_init(ws, a.names)
    else:
        cmd_score(ws)


if __name__ == "__main__":
    main()
