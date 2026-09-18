#!/usr/bin/env python3
"""
变更影响分析：上游产物一变，自动算出下游哪些东西必须重做、回退到哪一站。

现有 research.py check 只能报 stale（哪个登记文件哈希变了），不告诉人后果。
本脚本在它之上，用七阶段标准产物依赖图做正向传播，回答三件事：
  1. 这次变更的根因文件是什么；
  2. 哪些下游产物被污染、各自要做什么动作（重跑/重画/重写/重核）；
  3. 建议回退到哪个阶段，哪些产物仍可安全保留。

用法：
  python scripts/impact.py graph
  python scripts/impact.py analyze <workspace> [--changed rel ...] [--strict]
        不给 --changed 时，调用 research.check_project 从 checkpoint 哈希推断根因；
        --strict 时若已有下游产物被污染，退出码=1（用于闸门/CI）。

注意：依赖图覆盖“已登记的产物级依赖”；纯语义影响（一句话改动动摇论证）仍需人判，
报告里会显式声明这一边界，不假装脚本穷尽了所有影响。
"""
import argparse
import json
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import research  # 复用 read/write/check_project
except Exception:  # pragma: no cover
    research = None

# ---------- 七阶段标准产物依赖图 ----------
# node: (阶段, 中文名, 被污染后的动作)
NODES = {
    "prepped":       ("P0", "入门准备产物", "重新对齐方向与计划"),
    "topic":         ("P1", "方向评估表", "重新评估方向选择"),
    "scope":         ("P1", "研究问题/范围 scope.json", "重写主问题与子问题"),
    "glossary":      ("P1", "术语表", "统一术语与同义词"),
    "search_log":    ("P1", "范围检索日志", "按新问题重新检索"),
    "evidence":      ("P2", "证据矩阵/精读卡片", "补检索、补精读、重核引用"),
    "references":    ("P2", "参考文献库", "重新核对引用条目"),
    "gaps":          ("P2", "研究缺口", "重新归纳缺口与证据"),
    "data_audit":    ("P3", "数据审计", "重新审计数据可用性"),
    "confounds":     ("P3", "混淆因素清单", "补混淆处置策略"),
    "design":        ("P3", "实验设计 design.json", "改设计/参数/替代设置并留版"),
    "env":           ("P4", "运行环境快照", "补记录环境与版本"),
    "run_log":       ("P4", "运行日志", "重新运行并留档（含失败）"),
    "results":       ("P4", "结果文件", "重新计算，禁止手改数字"),
    "robustness":    ("P4", "稳健性对比", "重跑替代设置并记录差异"),
    "methods_map":   ("P5", "方法-代码对应", "核对方法描述与实际运行"),
    "figures":       ("P5", "图件与 manifest", "用新结果重画图并重过人眼审查"),
    "claim_map":     ("P5", "论点-证据对应表", "重建论点到证据/图/章节的链接"),
    "manuscript":    ("P5", "稿件正文", "按新证据/结果改写受影响章节"),
    "changes":       ("P5", "补稿修订记录", "登记有证据的改动"),
    "conclusion":    ("P6", "结论", "把结论收回到新结果支持的范围"),
    "gates":         ("P5", "五道写作关卡", "对受影响段落重跑五道关卡"),
    "panel":         ("P6", "审稿人面板", "重新模拟审稿"),
    "citation_final": ("P6", "引用终检", "对受影响引用重跑两道核验"),
    "response":      ("P6", "返修回应信", "更新逐条回应与位置"),
    "submission":    ("P6", "投稿自查/投稿", "投稿前最终自查后再投"),
}

# 上游 -> 直接下游（科学流水线方向）
EDGES = {
    "prepped": ["scope"],
    "topic": ["scope"],
    "scope": ["search_log", "glossary", "design", "evidence", "manuscript"],
    "glossary": ["evidence", "manuscript"],
    "search_log": ["evidence"],
    "evidence": ["gaps", "design", "claim_map", "citation_final", "manuscript", "references"],
    "references": ["citation_final", "manuscript"],
    "gaps": ["design", "manuscript"],
    "data_audit": ["design", "results"],
    "confounds": ["design", "results", "manuscript"],
    "design": ["env", "run_log", "methods_map", "figures", "claim_map", "manuscript"],
    "env": ["run_log"],
    "run_log": ["results", "methods_map"],
    "results": ["robustness", "figures", "claim_map", "manuscript"],
    "robustness": ["figures", "claim_map", "manuscript"],
    "methods_map": ["manuscript"],
    "figures": ["manuscript"],
    "changes": ["manuscript"],
    "claim_map": ["manuscript", "conclusion", "gates", "citation_final"],
    "manuscript": ["gates", "conclusion"],
    "conclusion": ["gates", "panel", "citation_final"],
    "gates": ["panel", "citation_final"],
    "citation_final": ["response", "submission"],
    "panel": ["response", "submission"],
    "response": ["submission"],
}

# 变更文件路径 -> 节点（按特异性从高到低匹配）
PATH_RULES = [
    ("topic-evaluation.json", "topic"),
    ("prep-checklist.md", "prepped"), ("domain-map.md", "prepped"), ("plan.md", "prepped"),
    ("scope.json", "scope"), ("glossary.md", "glossary"),
    ("search-log.json", "search_log"),
    ("evidence.json", "evidence"), ("reading-cards/", "evidence"),
    ("references.bib", "references"), ("gaps.json", "gaps"),
    ("data-audit.md", "data_audit"), ("confounds.json", "confounds"),
    ("design.json", "design"),
    ("analysis/env.json", "env"), ("analysis/run-log.json", "run_log"),
    ("analysis/results/", "results"),
    ("robustness.json", "robustness"),
    ("methods-map.json", "methods_map"),
    ("figures/manifest.json", "figures"), ("figures/", "figures"),
    ("claim-map.json", "claim_map"),
    ("manuscript/changes.json", "changes"),
    ("manuscript/conclusion.md", "conclusion"),
    ("manuscript/", "manuscript"),
    ("review/gates.json", "gates"),
    ("audit/citation-final.json", "citation_final"),
    ("review/panel.json", "panel"),
    ("audit/response-letter.md", "response"),
    ("submission-checklist.md", "submission"),
]


def classify(path):
    """把一个工作区相对路径映射到依赖图节点；无法识别返回 None。"""
    p = str(path).replace("\\", "/")
    for needle, node in PATH_RULES:
        if needle.endswith("/"):
            if needle in p:
                return node
        elif p.endswith(needle) or p == needle:
            return node
    return None


def propagate(roots):
    """从根节点正向传播，返回 {受影响节点: 第一个触达它的直接上游}（不含根本身）。"""
    affected = {}
    q = deque(roots)
    seen = set(roots)
    while q:
        cur = q.popleft()
        for down in EDGES.get(cur, []):
            if down not in seen:
                seen.add(down)
                affected[down] = cur
                q.append(down)
    return affected


def shortest_chain(root, target):
    """BFS 求 root->target 的一条最短传导链，用于解释‘为什么它受影响’。"""
    q = deque([(root, [root])])
    seen = {root}
    while q:
        cur, chain = q.popleft()
        if cur == target:
            return chain
        for down in EDGES.get(cur, []):
            if down not in seen:
                seen.add(down)
                q.append((down, chain + [down]))
    return None


def stage_order(node):
    return NODES[node][0]


def analyze(changed_paths):
    """返回结构化影响分析结果。"""
    roots, unknown = [], []
    for p in changed_paths:
        node = classify(p)
        if node:
            roots.append((p, node))
        else:
            unknown.append(p)
    root_nodes = []
    for _, n in roots:
        if n not in root_nodes:
            root_nodes.append(n)
    affected = propagate(root_nodes)

    # 每个受影响节点配一条最短链（取任一能到达它的根）
    details = []
    for node in sorted(affected, key=lambda n: (stage_order(n), n)):
        chain = None
        for rn in root_nodes:
            chain = shortest_chain(rn, node)
            if chain:
                break
        stage, name, action = NODES[node]
        details.append({"node": node, "stage": stage, "artifact": name,
                        "action": action, "chain": chain or [node]})

    rollback_nodes = set(root_nodes) | set(affected)
    rollback_stage = min((stage_order(n) for n in rollback_nodes), default=None,
                         key=lambda s: int(s[1:]))
    safe = [n for n in NODES if n not in affected and n not in root_nodes]
    return {"roots": [{"path": p, "node": n} for p, n in roots],
            "unclassified_paths": unknown,
            "affected": details,
            "rollback_to_stage": rollback_stage,
            "safe_nodes": safe}


def roots_from_checkpoints(ws):
    """从 research checkpoint 哈希推断变更文件（需要已跑过 checkpoint）。"""
    if research is None:
        raise RuntimeError("无法导入 research.py")
    report = research.check_project(str(ws))
    changed = []
    for item in report.get("invalidated", []):
        if item.get("changed_artifact"):
            changed.append(item["changed_artifact"])
    return changed, report.get("status")


def cmd_graph(_):
    print("七阶段标准产物依赖图（上游 -> 直接下游）：\n")
    for node in NODES:
        downs = EDGES.get(node, [])
        if downs:
            print(f"  {NODES[node][0]} {node:<14} -> {', '.join(downs)}")
    print("\n变更某个产物时，沿箭头正向可达的所有下游都要复核；用 analyze 看具体后果。")


def cmd_analyze(ws, changed, strict):
    if not changed:
        changed, status = roots_from_checkpoints(ws)
        if not changed:
            print(f"checkpoint 状态：{status}。没有检测到已登记产物变更。")
            print("若你确实改了东西，用 --changed <相对路径> 显式指定，例如：")
            print(f"  python scripts/impact.py analyze {ws} --changed design.json")
            sys.exit(0)
    result = analyze(changed)
    if not result["roots"]:
        print("⛔ 这些路径无法映射到七阶段产物，无法分析：")
        for p in result["unclassified_paths"]:
            print(f"   - {p}")
        print("请用 phases.md 列出的标准产物路径，或先在 checkpoint 登记。")
        sys.exit(2)

    # 写报告
    out = ws / "audit" / "impact-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=" * 64)
    print("🔁 变更影响分析")
    print("=" * 64)
    print("\n根因变更：")
    for r in result["roots"]:
        print(f"   • {r['path']}  → {r['node']}（{NODES[r['node']][1]}）")
    if result["unclassified_paths"]:
        print("   （未识别路径，未纳入传播：%s）" % ", ".join(result["unclassified_paths"]))

    if result["affected"]:
        rb = result["rollback_to_stage"]
        print(f"\n受影响下游（建议回退到 {rb} 阶段重做）：")
        cur_stage = None
        for d in result["affected"]:
            if d["stage"] != cur_stage:
                cur_stage = d["stage"]
                print(f"  {cur_stage}")
            chain = " → ".join(d["chain"])
            print(f"     - {d['artifact']}：{d['action']}")
            print(f"         传导链：{chain}")
        print("\n可安全保留（本次变更不直接波及，但重跑后仍建议抽查）：")
        safe_by_stage = {}
        for n in result["safe_nodes"]:
            safe_by_stage.setdefault(stage_order(n), []).append(NODES[n][1])
        for st in sorted(safe_by_stage, key=lambda s: int(s[1:])):
            print(f"  {st}：{('、'.join(safe_by_stage[st]))}")
    else:
        print("\n✅ 没有登记在案的下游产物受影响。")

    print("\n边界：以上是产物级依赖传播；一句话改动是否动摇论证，属语义影响，仍需人工判断。")
    print(f"报告已写入 {out}")
    if strict and result["affected"]:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("graph")
    a = sub.add_parser("analyze")
    a.add_argument("workspace")
    a.add_argument("--changed", nargs="*", default=[])
    a.add_argument("--strict", action="store_true")
    ns = ap.parse_args()
    if ns.cmd == "graph":
        cmd_graph(None)
    else:
        cmd_analyze(Path(ns.workspace), ns.changed, ns.strict)


if __name__ == "__main__":
    main()
