# 本技能的缺失依赖（重要，请先读这一页）

这一页由 Cool-Academic 维护，**不是** 原 PPT 技能的文件。

## 为什么会缺东西

本技能是从一份合并文档还原出来的，那份文档的开头写明：

> 本文档由 ppt skill 目录下**所有 markdown 文件**按逻辑顺序合并而成。

也就是说，**只合并了 `.md`。** 原技能目录里的 `.xml` 与 `.py` 文件没有被包含进来。

因此本目录下 **31 个 markdown 文件全部齐全且逐字保留**，但以下 7 个文件**从未被提供**，本仓库也不凭空编造它们。

## 缺失清单（7 个）

### XML（2 个）

| 文件 | 在技能里的作用 | 缺失的影响 |
|---|---|---|
| `references/xml/slides_xml_schema_definition.xml` | SKILL.md 称其为「**唯一权威 XML 协议**，需要精确定义时查」 | 无法核对精确的元素/属性定义。**部分缓解：** `xml-schema-quick-ref.md` 自称是它的精简摘要，并声明「两者不一致时以 quick-ref 为准（冲突处均经实测验证）」 |
| `references/xml/slides_chart_demo.xml` | 画图表前**照抄**的范例（柱状/条形/折线/面积/饼环/雷达/组合） | 图表语法失去可照抄的范例来源。`xml-schema-quick-ref.md` 仍描述语法，但不再有完整可抄样例 |

### Python 工具（5 个）

| 文件 | 在技能里的作用 | 缺失的影响 |
|---|---|---|
| `scripts/xml_lint.py` | XML 静态检查：well-formed、schema 合法性、元素 ID 重复、文本重叠、形状/图片/表格/图表遮挡文字、越界、文本溢出（宽高）、表格尺寸、icon 填充、布局密度 | **最严重的缺失。** SKILL.md 要求「Step 7 每页提交前必跑，Step 8 对回读全文再跑一次」。**现在这道强制校验跑不了**，等于质量门禁失效 |
| `scripts/xml_inspect.py` | 回读 XML 的导航器：摘要模式输出页数/页序/每页 `slide_id`/元素统计/正文预览，`--slide-id` 取单页完整 XML | 只能自行解析回读结果。技能明确要求用 XML 解析器、命名空间从根元素实际读取、不要硬编码或猜测 |
| `scripts/iconpark_tool.py` | IconPark 图标检索：`search --query`、`resolve --name`、`list-categories` | **图标基本不可用。** 技能**禁止**盲猜 `iconType`，规定必须先用此工具检索、再从候选里二次判断。工具缺失时只能不用图标（技能同时禁止用 emoji 顶替） |
| `scripts/color_contrast_check.py` | 独立的 XML 靠色回归入口（图片背景跳过）：`--xml <回读 XML>` | 靠色检查失去独立回归手段 |
| `scripts/gen_svg_charts.py` | 所有 SVG 专业图的生成器集合，暴露 `make_<slug>(...)` 与 `chart_help()` | 技能要求「多张专业图表一律走生成器」，现只能手写 SVG |

## 还有两个运行环境前提

| 前提 | 说明 |
|---|---|
| `lark-cli` | 技能的 frontmatter 声明 `metadata.requires.bins: ["lark-cli"]`，帮助入口是 `lark-cli slides --help`。**本仓库不提供也不安装它。** 没有它，云端 Slides 的创建/读取/替换/截图/历史等全部 `cli/` 流程都无法执行 |
| 飞书 / Lark 连接 | 技能的 `cli/` 与 `workflow/` 大量基于在线 Slides 与 `file_token`。需要一个可用的飞书/Lark 环境与相应授权。**当前 Cool-Academic 仓库的运行环境里没有它** |

## 因此，现在的可用范围

| 部分 | 状态 |
|---|---|
| 31 个 markdown 文件（设计系统、版式分类、风格家族、XML 速查、CLI 参考、编辑与校验流程、平台兼容说明） | ✅ 完整、逐字保留 |
| 设计/叙事/版式类规则（`style/` 全部） | ✅ 可直接用于指导版式与文案决策 |
| XML 语法本身 | ⚠️ 只有速查摘要，缺权威 XSD 与图表范例 |
| 强制静态校验（Step 7 / Step 8 的 lint） | ❌ 无法执行 |
| 图标检索、SVG 图表生成、靠色回归 | ❌ 无法执行 |
| 未安装 `lark-cli` 时的在线 Slides 操作 | ❌ 无法执行 |

**不要把上面标 ❌ 的能力报告为"已实现"或"已通过"。** 缺失就是缺失。

## 需要什么才能补齐

请提供原技能目录的**完整**导出（包含非 markdown 文件），即：

```text
skills/ppt/
├── SKILL.md
├── references/
│   ├── style/*.md              ← 已齐全（10 个）
│   ├── xml/*.md                ← 已齐全（3 个）
│   ├── xml/slides_chart_demo.xml              ← 缺
│   ├── xml/slides_xml_schema_definition.xml   ← 缺
│   ├── cli/*.md                ← 已齐全（13 个）
│   └── workflow/*.md           ← 已齐全（7 个，含 1 处链接笔误已修）
└── scripts/
    ├── xml_lint.py             ← 缺
    ├── xml_inspect.py          ← 缺
    ├── iconpark_tool.py        ← 缺
    ├── color_contrast_check.py ← 缺
    └── gen_svg_charts.py       ← 缺
```

拿到之后，把它们放进对应路径即可；本页的缺失清单随之作废，`tests/test_vendor_ppt.py` 里的对应断言会提醒你更新本文件。

## 本仓库对原文件做过的唯一改动

只修了 **3 处同类链接笔误**：`references/workflow/` 下三个互为兄弟的文件之间，链接写成了从技能根算起的路径（例如 `references/workflow/slides-editing.md`），实际应为同目录文件名（`slides-editing.md`）。除此之外**未改动任何原文件内容**。
