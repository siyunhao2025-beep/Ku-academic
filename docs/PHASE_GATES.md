# 阶段闸门、阈值与产物接口

[返回首页](../README.md) · [阶段总控](../modules/phases.md) · [同类对比来源](PEER_COMPARISON.md)

本文件定义七阶段之间的**通过条件**、**数值阈值**和**产物的数据结构**。

**先说清楚阈值的性质：** 下面所有数字都是**可配置的工程下限**，用来逼人停下来检查，**不是统计充分性保证，也不是任何期刊的规定**。不要用调低阈值的方式把一次试运行标成正式验证。

**闸门由脚本硬执行，不靠模型自觉：** 每个闸门都对应 `scripts/progress.py gate <workspace> <下一阶段>` 的非零退出。未通过时脚本逐条列出缺失项，流程停在当前阶段；不允许凭记忆宣布通过、不允许删改检查项强行通过。

---

## 一、闸门总览

| 闸门 | 位置 | 核心问题 | 不过怎么办 |
|---|---|---|---|
| Gate 0 | P0 → P1 | 入门准备做扎实了吗？ | 补精读卡片、领域地图或和导师对齐，不要带着空白进选题 |
| Gate 1 | P1 → P2 | 问题立得住吗？ | 回 P1 重写问题，不带着模糊问题做检索 |
| Gate 2 | P2 → P3 | 证据够不够支撑设计？ | 补检索或补全文；不是"差不多就行" |
| Gate 3 | P3 → P4 | 设计能执行吗？ | 缩范围或换数据，不要缩标准 |
| Gate 4 | P4 → P5 | 结果站得住吗？ | 补稳健性检查；不要直接开始写 |
| Gate 5 | P5 → P6 | 稿子能投吗？ | 按未过项返工，不要带病投稿 |

---

## 一·五、Gate 0：入门准备的完整性

| 指标 | 默认下限 | 含义 |
|---|---|---|
| 准备清单 `prep-checklist.md` | 全部勾选 | 工具/环境/数据访问/账号逐项落实，不是写了就算 |
| 领域地图 `domain-map.md` | 实质内容（≥200 字） | 基于 3–5 篇综述梳理，不是空标题 |
| 精读卡片 | ≥ 2 篇且字段完整 | 用 `reading.py check` 校验；没填卡片只算"下载过" |
| 研究计划 `plan.md` | 含时间里程碑 | 3 个月计划，能说出第一个小结果什么时候出 |

**Gate 0 不考知识量，只考"有没有带着地图和问题上路"。** 卡片可由 `reading.py card` 生成、`check` 校验、`sync` 同步进 evidence.json。

---

## 二、Gate 1：范围检索的充分性

| 指标 | 默认下限 | 含义 |
|---|---|---|
| 每个子问题的候选文献数 | ≥ 8 | 说明这个坑有人踩过 |
| 相关性评分 | ≥ 8/10 | 平均分，低于说明问题或检索词有问题 |
| 不同作者团队数 | ≥ 5 | 防止只看到一个组的工作 |
| 术语表条目 | ≥ 主问题涉及的关键量 × 2 种叫法 | 或明确记录"本领域只有一种叫法" |

配置位置：`domain.json` 的 `gate1`（可选，缺省用上表）。

**不过的典型原因**：问题太宽（"某个因素有什么影响"）；检索词只有一种叫法；候选全是综述没有原始研究。

---

## 三、Gate 2：证据基础的充分性

| 指标 | 默认下限 | 含义 |
|---|---|---|
| 纳入文献总数 | ≥ 20 | 综述类任务的取样下限 |
| 独立研究缺口 | ≥ 3 | 每个都要有 ≥3 条支撑证据 |
| 完整条件矩阵覆盖率 | 100% | 每条纳入文献都要填全条件列 |
| `citation_verdict == VERIFIED` 比例 | 100% | 未核验的不计入 |
| 硬阻断项（`CONTRADICTS`/`DOES_NOT_SUPPORT`） | 0 | 未处理的阻断项不算通过 |

**注意**：文献总数 20 是工程取样下限，**不是"读完 20 篇就够了"**。如果领域本身只有 8 篇相关工作，就写 8 篇并说明覆盖情况，不要为了凑数把不相关的也塞进来。**覆盖是否充分要看条件矩阵有没有漏洞，不是看数量。**

---

## 四、Gate 3：设计的可执行性

| 指标 | 要求 |
|---|---|
| 假设可判定性 | 每个假设都能被数据支持或反对，不能出现"大概率支持"这种结果 |
| 参数字段完整率 | 100% —— 每个字段要么有具体值，要么是 `null`，不允许"约""典型值" |
| 匹配规则 | 比较类设计必须写明配对条件，不匹配处必须写明 |
| 替代设置数量 | ≥ 3 组，且在跑之前定好 |
| 混淆因素处置率 | 100% —— 每条都要有约束策略或写明"确实约束不了" |
| 不确定性口径 | 明确写出用的是 SD/SE/CI 中的哪一个，及样本单位 |
| 数据审计结论 | 必须明确给出"可进入 P4"或"不可进入" |

**"不可进入"是正常结论。** 数据审计发现关键变量缺失时，正确做法是改设计或换数据，不是硬跑。

---

## 五、Gate 4：结果的可靠性

| 维度 | 满分 | 通过线 |
|---|---|---|
| 运行可追溯（日志、哈希、版本、种子） | 5 | |
| 失败与重试留档 | 5 | |
| 替代设置已跑并有差异记录 | 5 | |
| 数值卫生（单位、坐标、时区、缺测） | 5 | |
| 样本与统计口径自洽 | 5 | |
| **合计** | **25** | **≥ 20** |

任一项为 0 分则整体不通过，即使总分够。

**扣分典型**：结果文件被手工改过数字（-5）；缺测被零填充（-5）；只报了最好的一组参数（-5）。

---

## 六、Gate 5：稿件质量（两套评分）

### 6.1 分章评分（每章单独评，满分 20）

| 维度 | 满分 | 说明 |
|---|---|---|
| 论证清晰度 | 4 | 这一章要回答的问题说清楚了吗 |
| 完整性 | 4 | 该有的要素齐了吗 |
| 证据支持 | 4 | 每个论断都有出处吗 |
| 方法透明度 | 4 | 别人能照着做吗 |
| 组织与衔接 | 4 | 段落之间接得上吗 |
| **合计** | **20** | **每章 ≥ 16** |

### 6.2 全文评分（满分 35）

| 维度 | 满分 |
|---|---|
| 论证清晰度 | 5 |
| 完整性 | 5 |
| 文献支持 | 5 |
| 方法清晰度 | 5 |
| 原创性表达 | 5 |
| 组织 | 5 |
| 与目标平台/期刊的适配 | 5 |
| **合计** | **35**，**通过线 ≥ 28** |

### 6.3 补充硬条件

除评分外，以下必须同时满足：

- [ ] `citation_verdict` 中 `UNRESOLVED` 数量为 0
- [ ] 高风险错配数量为 0
- [ ] 线路图与示意图已产出（或已说明为何该任务不需要示意图）
- [ ] 数据图全部经人工视觉审查
- [ ] 降 AI 自查第一层全过（见 `assets/deai-checklist.md`）
- [ ] AI 辅助披露已按期刊要求处理

**评分不替代硬条件。** 评分满分但有一项硬条件未过，仍然不通过。

---

## 七、审稿人模拟：多个persona 不取平均

投稿前可做一轮模拟审稿。规则：

- 用**多个不同视角**（主编视角 / 领域专家视角 / 方法统计视角 / 怀疑论者视角）分别评审。
- **不要取平均。** 分歧本身就是信息，平均会把它抹掉。
- 每条意见给：稳定 ID（`RS-1`、`RS-2`…）、视角、严重度、精确位置、用审稿人语言写的反对意见、依据、什么能满足它、是否需要作者补数据、安全的修改方案、回应草稿、状态。
- 状态 ∈ `OPEN / RESOLVED / AUTHOR_DECISION`。
- 至少 3 条必须涉及**科学内容**，不能全是格式问题。
- **绝不为了满足模拟审稿而编造新结果、新样本量、新显著性检验、新稳健性测试或新的伦理审批。**
- 修改循环最多 3 轮。
- **模拟意见永远不能表述为真实同行评审意见，也不能给录用概率。**

---

## 八、产物的数据结构

### `project.json`

```json
{
  "id": "my-study",
  "kind": "original",
  "domain": "example-domain",
  "status": "needs_inputs",
  "stage": "P0",
  "created": "2026-09-17T00:00:00Z",
  "gates": {
    "gate0": {"status": "not_run"},
    "gate1": {"status": "not_run"},
    "gate2": {"status": "not_run"},
    "gate3": {"status": "not_run"},
    "gate4": {"status": "not_run"},
    "gate5": {"status": "not_run"}
  }
}
```

`status` 取值顺序：`needs_inputs → prepped → scoped → reviewed → designed → computed → drafted → submitted`（`prepped` 为 P0 完成、通过 Gate 0 后的状态）。

### `scope.json`（P1）

```json
{
  "main_question": "...",
  "sub_questions": ["..."],
  "genre": "original-research",
  "time_range": "...",
  "data_sources": ["..."],
  "known_limits": ["... (具体限制，不要泛泛而谈)"],
  "target_journals": [{"name": "...", "reason": "..."}],
  "domain": "example-domain"
}
```

### `topic-evaluation.json`（P0→P1，由 `scripts/topic_score.py` 生成/计算）

```json
{
  "candidates": [
    {
      "name": "方向A",
      "objective_inputs": {
        "total_hits_10y": 230,
        "recent3_ratio": 0.42,
        "high_cited_reviews_mentioning_gap": 4,
        "high_cited_count": 6,
        "applications_or_projects": 3,
        "data_available": "ready",
        "method_mature": "mature",
        "first_result_months": 3
      },
      "subjective_scores": {
        "risk": {"score": 4, "reason": "失败也有观测事实可写"},
        "resource": {"score": 5, "reason": "课题组强项，有人带"}
      },
      "scores": {"feasibility": 5.0, "innovation": 3.0, "value": 5.0,
                 "risk": 4, "resource": 5},
      "total_score": 4.35
    }
  ],
  "ranked": ["方向A", "方向B"],
  "recommendation": "..."
}
```

客观三维（可行性/创新性/价值）由检索数据计算；风险、资源两维必须本人与导师确认并写理由，缺任一数据脚本拒绝排名。总分 < 3.0 淘汰；多个 ≥ 3.5 时选可行性最高者。创新性打满分还要求 ≥3 篇高被引综述明确提到该缺口，否则按"死路保护"封顶 3 分。

### `evidence.json`（P2，每条记录）

```json
{
  "id": "E1",
  "source": "文件路径或 DOI",
  "locator": "p.5, Fig.3 或 run ID",
  "evidence_level": "full_text",
  "citation_verdict": "VERIFIED",
  "support_status": "SUPPORTS",
  "conditions": {
    "instrument": "...", "altitude": "...", "latitude_coordinate": "...",
    "local_time": "...", "event_phase": "...", "baseline": "..."
  },
  "claim": "该文献支持的主张",
  "claim_level": "observation"
}
```

`evidence_level` ∈ `{metadata_only, abstract_only, full_text, project_result}`
`claim_level` ∈ `{observation, association, inference, bibliographic}`

**约束**：`metadata_only` 只能支持 `bibliographic` 层的句子。用 `metadata_only` 支持 `inference` 属于不通过。

**精读卡片联动**：三遍法精读的核心文献由 `scripts/reading.py sync` 写入，带 `is_core_reading: true`、`reading_card`（卡片路径）、`evidence_level: full_text`、`relation_to_my_work`（`SUPPORTS / CONTRADICTS_MY_HYPOTHESIS / CONDITION_MISMATCH / METHOD_REFERENCE`），`claim_level` 由卡片勾选的结论强度（观测事实/统计关联/机制假设）映射。**精读不等于核验**：同步后 `citation_verdict` 仍为 `UNRESOLVED`、`support_status` 为空，必须再跑身份与支持两道核验才能计入 Gate 2。

### `design.json`（P3）

```json
{
  "hypotheses": [{"id": "H1", "statement": "...", "decision_rule": "..."}],
  "parameters": {"instrument_version": null, "...": null},
  "matching_rules": "...",
  "alternative_settings": [{"id": "A1", "change": "...", "reason": "..."}],
  "confounds": [{"id": "C1", "factor": "...", "control": "..."}],
  "uncertainty": {"definition": "SD", "sampling_unit": "per orbit"},
  "failure_modes": ["..."],
  "data_audit_verdict": "can_proceed"
}
```

### `analysis/run-log.json`（P4，每条运行）

```json
{
  "run_id": "run-001",
  "command": "...",
  "inputs_hash": "...", "code_hash": "...",
  "env": {"python": "...", "libs": {}},
  "seed": 42,
  "started": "...", "ended": "...",
  "outputs": ["analysis/results/..."],
  "status": "success",
  "notes": "失败重试第 2 次成功，第一次因 ... 失败"
}
```

**失败的运行也要在这里。** 没有失败记录等于隐藏了选择性报告。

### `claim-map.json`（P5）

```json
{
  "claims": [
    {
      "claim_id": "CL1",
      "statement": "...",
      "evidence_ids": ["E1"],
      "result_files": ["analysis/results/..."],
      "figures": ["figures/fig2"],
      "sections": ["Results 3.1", "Abstract"],
      "claim_level": "observation",
      "strength": "suggests"
    }
  ]
}
```

### `figures/manifest.json`（P5）

```json
{
  "figures": [
    {
      "id": "fig1",
      "type": "roadmap",
      "source_data": ["..."],
      "script": "figures/plot_fig1.py",
      "params": {},
      "axes": {"x": "...", "y": "..."},
      "colorbar": null,
      "masks": "...",
      "colors": {"palette": "okabe-ito", "redundant_encoding": "marker shape"},
      "uncertainty": {"type": "SD", "sampling_unit": "per orbit"},
      "caption": "...",
      "outputs": ["figures/fig1.pdf", "figures/fig1.png"],
      "visual_review": "passed",
      "notes": "概念示意，非观测结果"
    }
  ]
}
```

`visual_review` 必须由人眼确认，不能凭文件存在填 `passed`。

---

## 九、阈值在哪里改

| 阈值 | 位置 |
|---|---|
| Gate 1–5 的默认值 | 本文件；项目级覆盖写在 `domain.json` |
| 期刊风格语料最小篇数 | `scripts/research.py journal --minimum` |
| 相关性评分标准 | 项目自己的 `design.json` 或领域包 checks |

改阈值必须在 `audit/review.md` 里记一笔：改了哪个、为什么。**尤其不能用"降低阈值重跑一遍"的方式让 Gate 通过。**

---

## 十、最强结论的措辞

无论闸门全过还是部分过，**输出的最强结论只能是**：

```text
READY_FOR_HUMAN_SUBMISSION_CHECK
（可进入人工投稿复核）
```

不允许输出：

- 录用概率
- "保证录用""确保通过"
- "已通过同行评审模拟"
- "AI 检测已通过"

这些说法要么无法保证，要么把工程检查包装成科学结论。
