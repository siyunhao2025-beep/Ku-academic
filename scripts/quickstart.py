#!/usr/bin/env python3
"""Create a labelled offline installation demo, never scientific results."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import research


def create_demo(target: Path) -> dict:
    target = Path(target)
    if target.exists():
        raise FileExistsError("Demo destination exists; choose a new directory")
    research.init_project(target, research.ROOT / "domains/space-weather-mlt/domain.json", "original")
    (target / "inputs/installation-note.txt").write_text(
        "INSTALLATION DEMO ONLY. No observations, papers or research results are supplied.\n", encoding="utf-8")
    (target / "analysis/installation-plan.txt").write_text(
        "Next: supply real materials, define a question and build an evidence matrix.\n", encoding="utf-8")
    research.checkpoint(target, "installation-demo", ["inputs/installation-note.txt", "domain.json"],
                        ["analysis/installation-plan.txt"])
    (target / "INSTALLATION_DEMO.md").write_text(
        "# Installation demo / 安装示例\n\n此目录只验证初始化与文件依赖记录，没有科研结果。\n"
        "接下来请另建真实项目，加入文献、数据说明与代码，再让模型读取 SKILL.md。\n",
        encoding="utf-8")
    state = research.read(target / "project.json")
    state["status"] = "demonstration_only"
    research.write(target / "project.json", state)
    return {"status": "demonstration_only", "workspace": str(target.resolve()),
            "dependency_check": research.check_project(target),
            "scientific_results_generated": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(create_demo(args.target), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
