#!/usr/bin/env python3
"""
科研进度可视化脚本
用法：python scripts/progress.py <workspace目录>

每周跑一次，清清楚楚知道自己走到哪了、还差什么。
"""

import json
import sys
from pathlib import Path

# 每个阶段的检查项，和phases.md里的检查清单一一对应
PHASES = [
    {
        "id": "P0",
        "name": "入门准备",
        "color": "🔵",
        "checks": [
            ("能力盘点完成", "prep-checklist.md"),
            ("工具链确认（文献管理/代码环境）", "prep-checklist.md"),
            ("领域地图初建（3-5篇综述）", "domain-map.md"),
            ("精读2篇代表作并填卡片", "domain-map.md"),
            ("和导师对齐过方向", "prep-checklist.md"),
            ("3个月研究计划写完", "plan.md"),
        ],
    },
    {
        "id": "P1",
        "name": "选题调研",
        "color": "🟣",
        "checks": [
            ("主问题+子问题确定", "scope.json"),
            ("候选方向评估完成", "topic-evaluation.json"),
            ("体裁判断（原创/综述）", "scope.json"),
            ("范围检索完成", "search-log.json"),
            ("术语表建立", "glossary.md"),
            ("claim ledger骨架", "evidence.json"),
            ("目标期刊候选2-3个", "scope.json"),
        ],
    },
    {
        "id": "P2",
        "name": "文献综述",
        "color": "🟢",
        "checks": [
            ("检索方案（纳入/排除标准）", "search-log.json"),
            ("多源检索完成", "search-log.json"),
            ("文献身份核验", "evidence.json"),
            ("主张支持关系核验", "evidence.json"),
            ("全文证据矩阵", "evidence.json"),
            ("研究缺口提炼（每个≥3条证据）", "gaps.json"),
            ("主题框架完成", "review-outline.md"),
            ("参考文献库", "references.bib"),
        ],
    },
    {
        "id": "P3",
        "name": "实验设计",
        "color": "🟠",
        "checks": [
            ("数据审计完成", "data-audit.md"),
            ("可判定假设", "design.json"),
            ("匹配规则明确", "design.json"),
            ("全部参数填值或标null", "design.json"),
            ("混淆因素清单", "confounds.json"),
            ("3组以上稳健性检查设计", "design.json"),
            ("失败模式与边界", "design.json"),
            ("不确定性口径明确", "design.json"),
        ],
    },
    {
        "id": "P4",
        "name": "计算结果",
        "color": "🔴",
        "checks": [
            ("环境与版本记录", "analysis/env.json"),
            ("按设计执行", "analysis/run-log.json"),
            ("运行日志（含失败）", "analysis/run-log.json"),
            ("选择性报告风险记录", "analysis/run-log.json"),
            ("稳健性检查跑完", "robustness.json"),
            ("数值卫生检查", "analysis/run-log.json"),
            ("结果文件未手工修改", "analysis/results/"),
        ],
    },
    {
        "id": "P5",
        "name": "图表写作",
        "color": "🩷",
        "checks": [
            ("论点-证据-图表对应表", "claim-map.json"),
            ("科研线路图", "figures/manifest.json"),
            ("原理示意图", "figures/manifest.json"),
            ("数据图（源数据+代码）", "figures/manifest.json"),
            ("Methods写完", "manuscript/"),
            ("Results写完", "manuscript/"),
            ("Discussion写完", "manuscript/"),
            ("Introduction写完", "manuscript/"),
            ("Abstract写完", "manuscript/"),
            ("五道关卡全部通过", "review/gates.json"),
        ],
    },
    {
        "id": "P6",
        "name": "投稿返修",
        "color": "⚪",
        "checks": [
            ("Conclusion写完（含未回答问题）", "manuscript/conclusion.md"),
            ("科学审查完成", "audit/review.md"),
            ("引用终检完成", "audit/citation-final.json"),
            ("投稿前自查（对照作者指南）", "submission-checklist.md"),
            ("审稿人面板预演", "review/panel.json"),
            ("封面信写完", "audit/"),
            ("返修回应信（如需要）", "audit/response-letter.md"),
        ],
    },
]


def check_file_exists(workspace: Path, relative_path: str) -> bool:
    """检查文件是否存在，目录也算存在"""
    full_path = workspace / relative_path
    if full_path.exists():
        return True
    # 也检查analysis/和figures/等子目录
    return False


def get_phase_progress(workspace: Path, phase: dict) -> tuple[int, int, list[tuple[str, bool]]]:
    """计算一个阶段的完成度"""
    results = []
    for check_name, file_path in phase["checks"]:
        exists = check_file_exists(workspace, file_path)
        results.append((check_name, exists))
    done = sum(1 for _, exists in results if exists)
    total = len(results)
    return done, total, results


def main():
    if len(sys.argv) < 2:
        print("用法：python scripts/progress.py <workspace目录>")
        print("示例：python scripts/progress.py runs/my-study")
        sys.exit(1)

    workspace = Path(sys.argv[1])
    if not workspace.exists():
        print(f"错误：目录 {workspace} 不存在")
        print("先运行 python scripts/research.py init <workspace> 创建项目")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("📊 你的科研进度")
    print("=" * 60)

    total_done = 0
    total_checks = 0
    current_phase = None

    for phase in PHASES:
        done, total, results = get_phase_progress(workspace, phase)
        total_done += done
        total_checks += total
        percentage = int(done / total * 100)

        if done == total:
            status = "✅ 完成"
        elif done > 0:
            status = f"🔄 进行中 {percentage}%"
            if current_phase is None:
                current_phase = phase
        else:
            status = "⬜ 未开始"
            if current_phase is None:
                current_phase = phase

        print(f"\n{phase['color']} {phase['id']} {phase['name']} —— {status}")

        # 进行中的阶段显示具体检查项
        if 0 < done < total:
            for check_name, exists in results:
                mark = "  ✅" if exists else "  ❌"
                print(f"{mark} {check_name}")

    # 总进度
    total_percentage = int(total_done / total_checks * 100)
    print("\n" + "-" * 60)
    print(f"📈 总进度：{total_done}/{total_checks} 项完成（{total_percentage}%）")

    if current_phase and 0 < sum(1 for _, e in get_phase_progress(workspace, current_phase)[2] if e) < len(current_phase["checks"]):
        print(f"\n👉 你现在在【{current_phase['id']} {current_phase['name']}】阶段")
        print("   下一步先把上面打❌的项做完，再进入下一阶段。")
    elif total_done == 0:
        print("\n👉 你还没开始，先从 P0 入门准备开始。")
        print("   说一句「我是新手，从零开始」，我带你走第一步。")
    elif total_done == total_checks:
        print("\n🎉 所有检查项都完成了！可以投稿了。")
        print("   投稿前最后跑一遍审稿人面板模拟评审。")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
