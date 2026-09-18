# v0.5.0 改动说明

[返回首页](../README.md) · [v0.4.0 改动](CHANGELOG_v0.4.0.md) · [论文写作总调度](../modules/paper-orchestrator.md)

**一句话总结：** v0.5.0 加了一整套论文写作总调度——四阶段、五道关卡、四箱事实锁、Token 刹车。核心不是"提示词写得更好"，而是**把护栏做成脚本能拦的东西**：数字被改动、定义被压掉、正文出现 AI 自言自语、结论没有引文，全部由代码判定并驳回。

版本统一到 **0.5.0**。

---

## 一、新增的四个阶段

```text
阶段0  导师引言风格蒸馏（可选）→ 引言定稿入库（A 箱）
阶段1  其余章节写作 + 五道关卡流水线 → 通过后入箱
阶段2  Token 监控 → 80% 预警 / 90% 刹车 → 四箱事实锁压缩（只生成副本）
阶段3  导出完整全文（只读四箱原始存档）
```

入口文档：[modules/paper-orchestrator.md](../modules/paper-orchestrator.md)

---

## 二、五道关卡（顺序固定，不可跳）

| # | 关卡 | 新文件 | 拦什么 |
|---|---|---|---|
| 1 | 论文内容校验过滤器 | `modules/content-filter.md` | AI 自言自语、元叙述 |
| 2 | 主题锚定自检 | `modules/topic-anchoring.md` | 脱离全文核心主旨的句子 |
| 3 | 写作靶心校验 | `modules/bullseye-check.md` | 射不中靶心、图文不匹配、数据平淡堆砌 |
| 4 | 去 AI 味专业润色 | 复用 `modules/deai-writing.md` | 模板句；**且校验红锁没被改动** |
| 5 | 参考文献校验与引用布控 | `modules/citation-placement.md` | 引文不匹配、未定义 key、结论段引文不足 |

### 三个"宁可更严"的设计决定

**1. 脚本不提供 `--only` / `--skip` 开关。** 规范要求严格时序；保证一条规则最省事的办法就是**不提供绕过它的入口**。有测试断言这三个 flag 都会被 argparse 拒绝。

**2. 第 4 关不交润色结果就不算通过。** 红锁校验需要"改前 / 改后"两份文本。不交 `text_after` 就返回 `flag`，提示"补交（内容相同也算）"。**没跑过的关卡不能通过**，这是全流程一贯的原则。

**3. 前序驳回 → 后续关卡不执行，并明确写进报告。** 报告里 `gates_not_run` 列出未执行的关卡，不允许假装跑过。

### 第 1 关的核心难点：区分"研究的模型"与"写作的 AI"

规则明确要求**不可误删论文中描述研究算法、研究模型的句子**。所以实现里做了两组标记的判别：

| 命中情况 | 判定 |
|---|---|
| 黑名单 + **AI 自指**（我无法处理 / 本次对话 / 我的算力…） | ❌ 驳回 |
| 黑名单 + **研究自指**（本研究 / 我们 / 算法 / 训练…），无 AI 自指 | ✅ 通过，标为 `pass_as_study_description` |
| 黑名单，两者都无 | ⚠️ 待语义复核，**复核前不得删除** |

### 第 3 关的诚实边界

图文一致性**只在用户提供了图件数值时比对**。没提供就报 `cannot_check` —— 规范明确禁止臆测图表内容，所以这一关宁可不判，也不猜。

---

## 三、四箱与三级事实锁

| 箱 | 名称 | 密度 | 上限 |
|---|---|---|---|
| A | 引言箱 | 最低 | 6× |
| B | 数据箱 | 中 | 3× |
| C | 结果箱 | 最高 | **1×（禁止压缩）** |
| D | 结论箱 | 次高 | 2× |

新文件：`modules/four-box-compression.md`

### 红锁识别

数字 + 单位、`n = N`、不等号阈值、日期时间、以及你在 `domain_keywords` 里声明的仪器名与参数名。**识别是模式匹配，不认识的写法会漏**——所以配置要填全，这一点在文档里写明了。

### 红锁升级：防止"数字还在、定义没了"

这是整套机制里最值钱的一条。红锁事实常依赖某个定义（"12.5 K，是安静基线的 3.1 倍"）。定义句被压掉，数字就失去参照。

实现：任何**定义了红锁事实所涉及术语**的句子自动升级为临时红锁。而且 `verify()` **强制执行**——定义句消失而术语仍在被使用时，校验失败并报 `red_escalated_lost`。

```
改前：… baseline level. The quiet baseline is defined as the 10-day median… n = 48 orbits.
改后：… baseline level. n = 48 orbits.
判定：ok = False，red_escalated_lost = ["baseline"]
```

### 二分搜索最大可行倍率

在上限内二分，可行 = **红锁召回 100%**（从实际保留的文本重算，不假设）且不超过箱子上限。每次探测的 `ratio` 与 `feasible` 都记入报告。

实测：

| 箱 | 上限 | 实测最大倍率 |
|---|---|---|
| A | 6.0× | 5.99× |
| B | 3.0× | 2.66× |
| C | 1.0× | 1.00×（禁止压缩） |
| D | 2.0× | 1.99× |

### 原始存档不可变 + 导出只读原稿

- 每箱原始文本带 SHA-256。**在工具之外**的修改会被检测到，之后的 `add` / `compress` 直接报错。
- 压缩**从不写原始存档**，写在独立副本文件里；有测试断言"压缩前后原始存档逐字节相同"。
- `export` 只读 `archive_path`；有测试断言该函数源码里**不出现** `compressed_path`。
- 导出拒绝覆盖已存在的文件。

**所以"压缩损坏稿件"在结构上不可能发生：压缩产物根本不是导出源。**

---

## 四、Token 刹车与一个必须说清的限制

80% 预警、90% 刹车。四个输入 `window` / `history` / `query` / `reserve` **必须由调用方声明**。

**本工具读不到对话的 token 计量。** 已实际排查本机会话记录位置（详见 [Token 统计口径](TOKEN_ACCOUNTING.md)），没有一处包含当前对话用量。缺任何一个数就返回：

```json
{"status": "unknown", "unknown_inputs": ["history"],
 "action": "cannot decide; supply the missing figures from the platform's usage view rather than estimating them"}
```

**为什么不猜：用编出来的数字触发的刹车，比没有刹车更危险** —— 它会让你以为自己在安全区里。

**能精确测量的是压缩收益**：四箱文本量、压缩倍率、红锁召回率全部实测。所以"该压多少"可执行，只有"现在用了多少"需要你从平台用量页拿。

---

## 五、新增文件清单

| 类型 | 文件 |
|---|---|
| 模块（7） | `paper-orchestrator.md`、`intro-distillation.md`、`content-filter.md`、`topic-anchoring.md`、`bullseye-check.md`、`citation-placement.md`、`four-box-compression.md` |
| 脚本（3） | `locks.py`（事实锁与红锁校验）、`gates.py`（五道关卡）、`boxes.py`（四箱 / 压缩 / 刹车 / 导出） |
| 测试（3） | `test_locks.py`、`test_gates.py`、`test_boxes.py` |
| 文档（1） | 本文件 |

### 一处刻意的字段设计

`manuscript.json` 的 `domain_keywords` 与 `citation_domain_keywords` 是**项目级配置**，仓库里保持通用，没有写死任何研究方向。

> 规范里曾举例提到某个具体研究方向的关键词。考虑到此前明确要求"**不暴露研究方向、保持从 0 的独立项目**"，这里改为项目级配置项：你填自己的方向，仓库本身不承载它。这既满足了两条要求，也让技能对任何领域都可用。

---

## 六、验证结果（实测）

| 检查 | 命令 | 结果 |
|---|---|---|
| 单元测试 | `python -m unittest discover -s tests -v` | **Ran 269 tests — OK (skipped=1)** |
| 仓库校验 | `python scripts/check_repository.py` | **Repository checks: PASS** |
| 五关流水线 | `gates.py run` 8 段测试稿 | 五关全部实际触发：内容过滤 1 段、锚定 1 段、靶心 1 段、润色 1 段、引文 1 段被驳回 |
| 关键拦截实测 | 润色把 `12.5 K` 改成 `21 K` | **reject**，报告写明 `changed=[{'kind':'quantity','was':'12.5'}]` |
| 定义丢失实测 | 删掉基线定义句 | **ok=False**，`red_escalated_lost=["baseline"]` |
| 四箱压缩 | `boxes.py search` | A 5.99× / B 2.66× / C 1.00× / D 1.99×，全部在上限内 |
| 结果箱保护 | `boxes.py compress C` | 退出码 2，拒绝压缩 |
| 存档保护 | 工具外改写原始存档 | 后续 `add` 退出码 2 |
| 导出溯源 | `boxes.py export` | 四箱 `source=original_archive`，含逐箱 SHA-256 |

测试从 v0.4.0 的 175 项增至 **269 项**（新增 locks 30、gates 34、boxes 30）。

**开发中修掉的两个真实缺陷（都被测试钉住）：**

1. **中文术语提取失效。** 第一版把"一整串连续汉字"当成一个术语，导致它与任何句子都不可能重合，锚定关卡把**所有段落**都判为跑题。改为输出 2 字与 3 字 n-gram 后才可比较。
2. **无红锁时召回率算成 0。** 这会让一个全是背景句的箱子永远无法通过压缩校验。正确语义是"没有红锁要保留 → 召回应为 1.0（空真）"。修改后 D 箱从 1.00× 变为 1.99×。

**诚实说明：** 锚定与靶心的判定是**启发式初筛**（报告里固定标注 `heuristic_term_overlap`），不替代语义判断。测试通过证明的是护栏按设计工作，**不证明**它能判断你的科学结论是否正确。

---

## 七、续：把剩下靠自觉的规则也脚本化（四模块成体系补齐）

v0.5.0 把"写稿/润色"环节的护栏做成了脚本。这一轮把同样的思路推到**图件、返工、取文献、换领域**四件此前仍靠模型自觉的事上，原则不变：**靠结构护栏，不靠模型自觉。**

| 模块 | 新脚本/文档 | 把什么从"提醒"变成"硬拦" |
|---|---|---|
| A 图件护栏 | `scripts/figures.py`、`modules/figures.md` 第八节 | 三类图齐全（示意图可写理由豁免）；数据图只用无障碍色板（jet/rainbow 直接拦）；多系列必须有颜色之外的冗余通道、>6 系列判拆图；至少一个矢量输出；`source_data→script→outputs` 文件真实存在；人眼审查必须带署名和时间。脚本只查文件链与审查证据，**不替人看图** |
| B 变更影响与回退 | `scripts/impact.py`、`modules/change-management.md` | 改了设计/结果/证据后，沿 26 节点七阶段依赖图正向传播，给出受影响产物（重跑/重画/重写/重核 + 最短传导链）、建议回退阶段、可安全保留产物，写 `audit/impact-report.json`；配套 L0–L4 变更分级、回退五步、阈值/纳入标准变更纪律与三条硬禁令 |
| C 引用分级与合法全文 | `scripts/access.py`、`modules/evidence-integrity.md` | 按句子强度（背景/方法/定量/机制）定最低访问深度；定量句、机制句**必须读到全文并定位页/图/表**，拿不到全文只精准卡死这两类句，不连坐背景句；合法全文走 Unpaywall 指向出版社/机构库/作者自存档，**绝无盗版来源**，无网/无邮箱如实标"待确认"，不伪造可访问性 |
| D 去领域化 + 示范包 | `domains/sample-space-physics/`、`domains/example-domain/` | 母流程规则型硬编码全部中性化（时间/空间分组、坐标口径、对照基线"以领域包为准"）；`example-domain` 是中性空模板，新增 `sample-space-physics` 作为**填好的教具**（数值仍全为 `null`，配 `parameter_guidance` 教每个参数去哪查），不是默认值 |

**闸门接线：** `scripts/progress.py` 的 P5 闸门直接复用 `figures.check_one` 与 `access.evaluate_citation`（规则单一事实源，不双写）；示意图豁免、visual_review 对象格式在闸门生效，旧的字符串 `"passed"` 不再被默默当作通过。引用分级在存在 `audit/citation-provenance.json` 时硬查，早期项目无此文件则跳过，保持向后兼容。

**分发包补遗：** `config/distribution-files.json` 除本轮 9 个新文件外，一并补上此前遗漏的 `progress.py / reading.py / topic_score.py / test_guardrails.py`、被路由引用但漏打包的四个引导模块（research-kickoff / topic-evaluation / paper-reading-guide / polishing-ladder），以及被引用的 `ga-reference-isometric.svg`、`hero-anime.png`，共 296 条逐条核验存在。

| 检查 | 结果 |
|---|---|
| 单元测试 | **Ran 358 tests — OK (skipped=1)**，本轮新增 figures 16、impact 18、access 13、P5 闸门 10 |
| 仓库校验 | `python scripts/check_repository.py` → **PASS** |
| 分发包 | 清单 296 条全部存在，`build_distribution` 可复现构建 |

**边界不变：** 这三个脚本同样只保证"流程没被跳过、证据链完整、来源合法"。图好不好看、改动是否动摇论证语义、文献里的科学结论对不对，仍由人判断；拿不到的全文一律标"待确认"，没有任何脚本会替你补一个数字或一个来源。
