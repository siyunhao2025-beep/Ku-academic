# PPT 技能状态（已补全工具链）

这一页由 Cool-Academic 维护。**2026-09 起，本技能的可执行工具链已补全**：原先只拿到 markdown 文档、缺脚本与模板的问题，通过接入上游完整实现 `YinsenWANG/feishu-ppt-skill`（MIT，Copyright 2026 Cherry Studio）解决。

## 现在有什么

| 部分 | 状态 |
|---|---|
| 31 个设计/版式/CLI/流程 markdown（`references/style\|xml\|cli\|workflow/`） | ✅ 完整、逐字保留 |
| 51 个原生 960×540 幻灯片模板（`templates/slide01.xml … slide51.xml` + `INDEX.md` + `fields.json`） | ✅ 已补入 |
| Python 工具链（`scripts/`） | ✅ 已补入，本地已跑通 |
| 主题令牌 `tokens.yaml`、依赖 `requirements.txt`、回归 `tests/`、图标资产 `assets/` | ✅ 已补入 |
| 在线创建/截图/写入飞书 Slides | ⚠️ 仍需 `lark-cli` 与飞书授权（见下） |

## 工具入口（替代旧文档里写的脚本名）

旧合并文档按预期引用过 `xml_lint.py` / `xml_inspect.py` / `iconpark_tool.py` / `color_contrast_check.py` / `gen_svg_charts.py` 这五个名字，**原作者未随 markdown 一起提供，本仓库不按这些名字伪造文件**。实际补入的上游工具用的是另一套命令名，功能对应关系如下：

| 旧文档里的意图 | 实际命令 |
|---|---|
| 环境自检 | `python scripts/preflight.py --json`（需要 CLI 时加 `--check-cli`） |
| XML 静态检查 / 布局审查 | `python scripts/validate.py --dir <目录> --json`（可加 `--schema xsd --require-schema`） |
| 单页独立诊断 | `python scripts/review_layout.py …` / `python scripts/review_design.py …` |
| 本地 SVG 近似预览（替代手写 SVG 图表） | `python scripts/xml2svg.py --dir <目录> --output-dir <预览目录>` |
| 图标 / 字段绑定 / 模板准备 | `python scripts/template_fields.py prepare --template slideNN …` |
| 回读三方对比（baseline/working/remote） | `python scripts/compare_slides.py …` |

新模板若改动过，先跑 `python scripts/template_fields.py index` 重建字段索引，否则 `prepare` 会报 `Stale fields index`。

## 运行前提

- Python **3.10+**，先 `pip install -r requirements.txt`（仅 `PyYAML`、`lxml`）。
- `lark-cli` 与飞书/Lark 授权：本仓库**不提供也不安装**它。没有它，模板准备、本地校验、SVG 预览都能跑；只有真正在线创建/截图/写回飞书 Slides 的步骤需要它。官方 schema 用 `lark-cli skills read lark-slides/references/xml/slides_xml_schema_definition.xml` 导出后再传给 `validate.py --schema`。

## 关于旧清单里那 7 个文件名

下列名字来自最初的缺失声明，**按名仍不提供**（上游用的是上表另一套命令名，不是这些文件）：

- `references/xml/slides_xml_schema_definition.xml`（在线 schema，由 `lark-cli skills read` 导出，不内置）
- `references/xml/slides_chart_demo.xml`（图表样例已由 `templates/` 内各图表页承担）
- `scripts/xml_lint.py` → 由 `scripts/validate.py` 承担
- `scripts/xml_inspect.py` → 由 `scripts/template_fields.py` / `compare_slides.py` 承担
- `scripts/iconpark_tool.py` → 图标改用 Lucide 资产（`assets/lucide-*.png`，ISC 许可见 `assets/Lucide-LICENSE`）
- `scripts/color_contrast_check.py` → 并入 `scripts/validate.py` / `review_design.py`
- `scripts/gen_svg_charts.py` → 由 `scripts/xml2svg.py` 的内置图表渲染承担

## 来源与许可

代码、模板、脚本：MIT，源自 https://github.com/YinsenWANG/feishu-ppt-skill 。`assets/cherry-logo.png` 为品牌示例图，**不在 MIT 范围**，正式使用请替换为你自己的品牌素材。
