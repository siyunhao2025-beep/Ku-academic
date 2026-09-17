# v0.4.0 改动说明

[返回首页](../README.md) · [v0.3.0 改动](CHANGELOG_v0.3.0.md) · [PPT 缺失依赖](../skills/ppt/MISSING_DEPENDENCIES.md)

**一句话总结：** v0.4.0 集成第三方 PPT 技能、新增审稿人评审、讲解版 Word、海报制作三块能力，并把版本统一到 0.4.0。**其中 PPT 技能有一个必须说清楚的缺口 —— 你给的合并文档只含 markdown，7 个被引用的非 markdown 文件不在里面。**

---

## 一、PPT 技能集成：完整拿到了什么、缺了什么

### 1.1 集成方式

你提供的 `ppt-skill-complete.md`（389,068 字节、5,509 行）是一份**文件合并文档**：每个文件前有 `# 📄 源文件：<路径>` 标记。我按标记切分，**逐字**还原出 31 个 markdown 文件，放入 `skills/ppt/`：

| 目录 | 数量 | 内容 |
|---|---|---|
| `SKILL.md` | 1 | 总入口与流程主线（8 步：理解需求 → 定设计系统 → 收集素材 → 大纲 → 准备 → 图片处理 → 逐页完成 → 验收交付） |
| `references/style/` | 10 | 设计系统总纲、版式分类、六大风格家族（学术研究 / 品牌创意 / 商业提案 / 管理报告 / 教育培训 / 策略分析）+ 兜底风格 |
| `references/xml/` | 3 | XML 元素属性速查、字体、IconPark 图标 |
| `references/cli/` | 13 | `lark-cli slides` 全部子命令（create / add-slide / replace / update / delete / media-upload / screenshot / history / xml-get / xml-slide-get / xml-slide-replace） |
| `references/workflow/` | 7 | 编辑流程、模板改写、错误处理、XML 校验、视觉校验、Windows 兼容、本地兼容 |
| **合计** | **31** | 5,249 行正文，383,545 字节 |

（原始文档 5,510 行；差额是 31 行标记 + 分隔线与注释，属正常。）

**唯一改动：3 处链接笔误。** `references/workflow/` 下三个互为兄弟的文件之间，链接写成了从技能根算起的路径（`references/workflow/slides-editing.md`），实际应是同目录文件名（`slides-editing.md`）。除这 3 处外**未改动任何原文件内容**。

### 1.2 缺失的 7 个文件（重要）

合并文档开头写明：

> 本文档由 ppt skill 目录下**所有 markdown 文件**按逻辑顺序合并而成。

**所以只合并了 `.md`。** 原技能里被引用的 7 个非 markdown 文件不在其中：

| 文件 | 作用 | 影响 |
|---|---|---|
| `references/xml/slides_xml_schema_definition.xml` | 被称"唯一权威 XML 协议" | 无法核对精确定义。部分缓解：`xml-schema-quick-ref.md` 自称是其摘要并声明"冲突时以 quick-ref 为准" |
| `references/xml/slides_chart_demo.xml` | 画图表前**照抄**的范例 | 图表语法失去可抄样例 |
| `scripts/xml_lint.py` | 11 类静态检查（well-formed、schema、ID 重复、文本重叠、遮挡、越界、溢出、表格尺寸、icon 填充、布局密度） | **最严重。** SKILL.md 要求"Step 7 每页提交前必跑，Step 8 对回读全文再跑一次"——**这道强制质量门禁跑不了** |
| `scripts/xml_inspect.py` | 回读 XML 导航器 | 只能自行解析回读结果 |
| `scripts/iconpark_tool.py` | IconPark 图标检索 | **图标基本不可用。** 技能禁止盲猜 `iconType`，规定必须先检索；同时禁止用 emoji 顶替 |
| `scripts/color_contrast_check.py` | 靠色回归检查 | 失去独立回归手段 |
| `scripts/gen_svg_charts.py` | SVG 专业图生成器（`make_<slug>` / `chart_help`） | 图表只能手写 SVG |

**为什么没有补齐：** 这些文件的真实内容我不知道。**编造一份 `xml_lint.py` 或一份 XSD 出来，比缺文件更糟**——它会让技能看起来能跑，实际产出的校验结论全是假的。所以选择**如实声明缺失**，写进 `skills/ppt/MISSING_DEPENDENCIES.md`，并由 `tests/test_vendor_ppt.py` 断言：
- 这 7 个文件**必须**在清单里被声明；
- 这 7 个文件**必须不存在**（防止将来有人"顺手补"一个假的）；
- 31 个 markdown 文件**必须**齐全。

### 1.3 另外两个运行前提

| 前提 | 说明 |
|---|---|
| `lark-cli` | 技能 frontmatter 声明 `metadata.requires.bins: ["lark-cli"]`。本仓库不提供也不安装它 |
| 飞书 / Lark 环境与授权 | `cli/` 与 `workflow/` 大量基于在线 Slides 与 `file_token`。**当前环境没有** |

### 1.4 仓库自己的校验器相应放宽了一处（有意为之）

`scripts/check_repository.py` 原先校验所有 markdown 的相对链接。但 `skills/` 是**第三方逐字保留的树**，它的链接不是我们该去改的；缺失的目标必须在文档里声明，而不是把链接偷偷改掉。

处理：新增 `VENDOR_PREFIXES = ("skills/",)`，跳过该前缀下的链接校验，并在代码注释里写明理由；同时把 `skills/ppt/SKILL.md` 与 `skills/ppt/MISSING_DEPENDENCIES.md` 加入**必需文件**集合。这样"放宽"是有边界、有说明、有对应检查的，不是打开一个洞。

---

## 二、新能力三：审稿人评审（3–5 位）

**你提的需求：** 文章写完后，以 3–5 位专业审稿人视角衡量水平并给出评审意见。

**新文件：** `modules/reviewer-panel.md` + `scripts/review.py` + `tests/test_review.py`

### 各功能的目标、输入、输出

| 功能 | 目标 | 输入 | 输出 |
|---|---|---|---|
| 建评审表单 | 给出 N 位互不重复的审稿人视角 | 稿件路径、人数（3–5） | `panel.json`：角色、关注点、七维空分数、规则 |
| 独立打分 | 每位审稿人独立评七个维度 | 审稿人 ID + 七个 0–5 的数 | 该审稿人总分（35 制）与达标判定 |
| 登记意见 | 记录具体问题 | 严重度、类型、精确位置、意见正文 | 稳定 ID（`审稿人ID.序号`）的意见条目 |
| 出结论 | 判定整组 | 全部分数与意见 | 六种结论之一 + 分歧统计 + 人读报告 |

### 五位候选审稿人

`handling-editor`（处理编辑）、`domain-expert`（领域专家）、`methods-reviewer`（方法统计）、`skeptical-reviewer`（怀疑论者）、`reproducibility-reviewer`（可复现性）。默认启用前四位，脚本**拒绝 2 人与 6 人**。

### 三个"不许"写进了代码

| 不许 | 实现方式 |
|---|---|
| **不许把分数平均** | 根本没有平均函数。分数分散 > 7 时结论直接判为 `PANEL_DISAGREEMENT`，把分歧交回作者 |
| **不许放过"没提科学问题"的评审** | 科学类意见 < 3 条 → `INSUFFICIENT_SCIENTIFIC_COVERAGE`，判为不通过 |
| **不许给录用概率** | `summary.acceptance_probability` 固定写 `not_estimated`，报告里没有任何概率数字 |

结论判定顺序（先命中先出）：`INCOMPLETE` → `BLOCKED` → `INSUFFICIENT_SCIENTIFIC_COVERAGE` → `PANEL_DISAGREEMENT` → `READY_FOR_HUMAN_SUBMISSION_CHECK` → `REVISION_REQUIRED`。

评分与 [阶段闸门](PHASE_GATES.md) Gate 5 用同一把尺子（七维、满分 35、通过线 28），不另立标准。

---

## 三、新能力四：讲解版 Word

**你提的需求：** 文章写完后要有一份专业 Word，给用户讲懂。

**新文件：** `modules/explainer-docx.md` + `scripts/ooxml.py` + `tests/test_ooxml.py`

### 目标 / 输入 / 输出

| 项 | 内容 |
|---|---|
| 目标 | 把论文**翻译**成非专家能懂的一份 Word；只换说法，不换事实 |
| 输入 | 一个 `spec.json`：标题 + 块列表（标题/段落/要点/引用/提示框/表格/键值） |
| 输出 | 真实 `.docx`，加一份校验报告 `{"parts": N, "problems": [], "ok": true}` |

### 七节固定结构

一句话结论（**必须同时写"没有回答什么"**）→ 为什么要做 → 你怎么做的 → 得到了什么 → 这些说明什么 → 有什么限制 → 术语表。另附"与论文的对应关系"表，便于逐项核对。

### 为什么没有引入 python-docx

**因为不需要。** `.docx` 本质是装着 XML 的 zip。要做的事只有"把文字放进段落 + 一张表"，用标准库 `zipfile` 直接写 5 个部件就能覆盖，约 300 行，**且自带 XML 良构校验**。为一个这样的需求引入依赖，违反精简模式自己的阶梯第 5 条。

**代价是明确写出来的：** 不支持页眉页脚、脚注、公式、目录、自动编号、图片。需要这些时再引入依赖或改用专门的文档工具。**这是知情选择，不是遗漏。**

另外两条有意的行为：输出用固定时间戳（同输入→同字节，便于校验）；**已存在的同名文件不会被覆盖**，直接报错。

---

## 四、新能力五：海报制作

**你提的需求：** 流程与 PPT 类似，但**先让用户选**海报尺寸、语言（中/英）、输出形式（直接出图片 / 出 PPT），选定后再开始。

**新文件：** `modules/poster.md` + `scripts/poster.py` + `tests/test_poster.py`

### 三个必答问题与"不许默认"

```bash
python scripts/poster.py choices   # 打印规范选项，供你问用户，而不是自己编
python scripts/poster.py plan --size a0 --lang zh --output image --out spec.json
python scripts/poster.py render spec.json --out poster.svg      # 或 poster.pptx
```

`plan` 在三个选择任一缺失时**报错退出 2 并且不写任何文件**，错误信息逐条列出还缺哪几项，并提示"不要替用户默认"。只给尺寸、只给语言、一项都不给，行为一致：拒绝执行。

| 问题 | 选项 |
|---|---|
| 尺寸 | `a0` `a1` `a2` `a3` `a4` `conf-90x120`（900×1200 竖） `conf-120x90`（1200×900 横） `screen-16x9` |
| 语言 | `zh` / `en` |
| 输出 | `image`（SVG，1 单位 = 1 mm，可直接送印）/ `ppt`（单页 .pptx，尺寸一致） |

**方向默认 `auto`**——按尺寸名自身的横竖来，不会静默旋转（这点是测试盯着的：`conf-120x90` 必须得到 1200×900）。

### 版式引擎

按面积缩放字号（以 A0 为基准，夹在 0.35–1.2）→ 按宽高比自动定 2 栏或 3 栏 → 每块放进当前最短的栏（块高按中英混排估算行数）→ 页眉页脚通栏 → 回写指标（栏数、边距、字号、内容底部、**填充率**、**重叠检测**、**残留占位符**）。

### 两个自我保护

| 检查 | 行为 |
|---|---|
| 重叠检测 | 任意两块重叠 → 打印并**退出 2**，不许当成功交付 |
| 占位符检测 | 骨架里还留着 `⟨在此填写⟩` → WARNING 说明"这是版式骨架，不是成品海报"；`--strict` 时退出 2 |

### 诚实的边界（写在模块文档里，不藏）

不做 PNG 光栅化（那需要渲染器或字体引擎，属依赖）；不做图片嵌入（"图 1" 是位置块）；行高与断行是**估算**（SVG 无自动换行，本模块自己按字符算断行），所以给重叠检测兜底；字体依赖系统，**送印前必须在目标机器预览一次**确认中文没变成方框；不做出血与裁切线。

---

## 五、验证结果（实测）

| 检查 | 命令 | 结果 |
|---|---|---|
| 单元测试 | `python -m unittest discover -s tests -v` | **Ran 175 tests — OK (skipped=1)** |
| 仓库校验 | `python scripts/check_repository.py` | **Repository checks: PASS** |
| OOXML 自校验 | `ooxml.py verify` | docx 5 部件 / pptx 11 部件，**problems 全为空** |
| 审稿人评审 | `review.py panel → score → finding → verdict` | 退出码 0，结论随分数与意见正确变化 |
| 海报 | `poster.py choices → plan（缺项拒绝）→ render（SVG / PPTX）` | 缺项退出 2；两种输出均成功；重叠为 none |
| 打包 | `python scripts/build_distribution.py --out dist` | 退出码 0，`Cool-Academic-v0.4.0-skill.zip`，98 个文件，407,631 字节 |

测试从 v0.3.0 的 101 项增至 **175 项**（新增：vendor 9 项 + ooxml 17 项 + poster 22 项 + review 20 项 + 既有调整）。

**那条 skip：** `test_symlink_escape`，因本机无 Windows 符号链接权限（原因见 [v0.2.0 改动说明](CHANGELOG_v0.2.0.md#26-顺带修掉的真实缺陷windows-符号链接)）。

---

## 六、需要你补的东西

**请把原 PPT 技能目录的完整导出发给我**（要包含非 markdown 文件），这 7 个：

```text
skills/ppt/scripts/xml_lint.py
skills/ppt/scripts/xml_inspect.py
skills/ppt/scripts/iconpark_tool.py
skills/ppt/scripts/color_contrast_check.py
skills/ppt/scripts/gen_svg_charts.py
skills/ppt/references/xml/slides_chart_demo.xml
skills/ppt/references/xml/slides_xml_schema_definition.xml
```

拿到后放进对应路径即可。`tests/test_vendor_ppt.py` 会提醒你更新 `MISSING_DEPENDENCIES.md`（其中两条断言会因此失败，这是有意的信号）。

**另外：** 要让 PPT 技能真正可用，还需要装 `lark-cli` 并具备可用的飞书/Lark 环境与授权。这两项本仓库不提供。
