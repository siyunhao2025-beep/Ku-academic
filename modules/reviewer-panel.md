# 审稿人评审：3–5 位专业视角，各自独立打分

[返回首页](../README.md) · [阶段闸门](../docs/PHASE_GATES.md) · [阶段总控](phases.md) · [返修与投稿](phases.md)

**文章写完之后跑这一关。** 目的不是给自己发一张通过证，而是在投稿前把**别人会怎么挑你的毛病**先摆到桌面上。

先打个比方。

**像正式答辩前的预演。** 你请四位不同脾气的人来挑刺：管事的、懂行的、抠方法的、专门唱反调的。他们各说各的，**没有人替他们算平均分**——因为分歧本身就是最有价值的信息。有人说好有人说差，说明你的稿子在某个地方**只对一部分读者立得住**，这比一个漂亮的均分有用得多。

---

## 一、三个不许

这个模块的设计是先定死边界，再谈功能。

| 不许 | 为什么 |
|---|---|
| **不允许把审稿人分数平均成一个数** | 平均会抹掉分歧。分数散得开，说明稿件在争议点上不稳；平均之后这个信号就消失了 |
| **不允许放过"没提科学问题"的评审** | 一组只挑格式错的审稿人，不是干净通过，是**覆盖不足**。系统会把这种情况判为不通过 |
| **不允许输出录用概率或录用保证** | 本模块能给的最强结论只有「可进入人工投稿复核」 |

还有一条贯穿全文的：**不为满足审稿人而编造新结果、新样本量、新显著性检验或新伦理审批。** 审稿人提出需要新数据才能回答的问题时，正确做法是把它标为 `requires_author_data`，而不是造一个数出来。

---

## 二、审稿人从哪来

五位候选视角，默认启用前四位：

| ID | 角色 | 关注什么 | 要回答的问题 |
|---|---|---|---|
| `handling-editor` | 处理编辑 | 范围与目标期刊是否契合、贡献是否够、篇幅结构是否成比例 | 这把稿件如果送到我手上，我会不会直接送审？不送的话缺哪一块？ |
| `domain-expert` | 领域专家 | 论证链是否成立、文献是否覆盖了真正的竞争性解释、结论是否超前于证据 | 你最关键的论断，被最强的反面证据检验过吗？ |
| `methods-reviewer` | 方法与统计审稿人 | 设计、匹配、基线、不确定度口径、样本与重采样单位、多重比较、稳健性 | 把方法按原样重做一遍，结论还站得住吗？ |
| `skeptical-reviewer` | 怀疑论者 | 反例、替代解释、过度声称、把关联写成因果、把计划写成已完成 | 如果结论是错的，最可能错在哪一步？你排除它了吗？ |
| `reproducibility-reviewer` | 可复现性审稿人 | 数据与代码可得性、运行记录、版本与环境、图件能否由源数据重建 | 另一个人拿到这些材料，能复现出同一个数吗？ |

**人数限制是 3–5 人**，脚本会拒绝 2 人或 6 人。少于 3 人不足以形成视角差；多于 5 人只是重复劳动。

---

## 三、评分：七个维度，满分 35

与 [阶段闸门](../docs/PHASE_GATES.md) 的全文评分表一致，每个维度 0–5 分：

| 维度 | ID |
|---|---|
| 论证清晰度 | `argument_clarity` |
| 完整性 | `completeness` |
| 文献支持 | `literature_support` |
| 方法清晰度 | `method_clarity` |
| 原创性表达 | `originality_expression` |
| 组织与衔接 | `organization` |
| 与目标期刊契合度 | `platform_fit` |

**通过线 28/35。** 每位审稿人独立打分，**七项全打完**才产生总分；缺一项就是 `not_scored`，整组结论为 `INCOMPLETE`。

---

## 四、怎么用

```bash
# 1) 建评审表单（默认 4 位审稿人）
python scripts/review.py panel manuscript/draft.md \
  --out review/panel.json --report review/review.md

# 也可指定 3 位或 5 位
python scripts/review.py panel manuscript/draft.md \
  --reviewers handling-editor,domain-expert,methods-reviewer,skeptical-reviewer,reproducibility-reviewer \
  --out review/panel5.json

# 2) 每位审稿人独立打分（七个数按维度顺序）
python scripts/review.py score review/panel.json handling-editor \
  --scores 4,4,5,3,4,4,4 --note "范围合适，但贡献表述偏保守"

# 3) 记一条意见
python scripts/review.py finding review/panel.json methods-reviewer \
  --severity blocker --kind science --location "Methods, paragraph 3" \
  --comment "基线定义未说明窗口长度，改变窗口可能翻转结论方向" \
  --requires-author-data

# 4) 出结论 + 报告
python scripts/review.py verdict review/panel.json --report review/review.md
```

严重度：`blocker` / `major` / `minor` / `positive`。
类型：`science`（科学内容，计入覆盖率）或 `format`（格式，不计入）。
状态：`open` / `resolved` / `author_decision`。

---

## 五、结论怎么算（判定顺序不能颠倒）

脚本按下面的顺序判，**先命中先出**：

| 顺序 | 条件 | 结论 |
|---|---|---|
| 1 | 还有人没打分 | `INCOMPLETE` |
| 2 | 存在未解决的 `blocker` | `BLOCKED` |
| 3 | 科学类意见少于 3 条 | `INSUFFICIENT_SCIENTIFIC_COVERAGE` |
| 4 | 最高分与最低分之差 > 7 | `PANEL_DISAGREEMENT` |
| 5 | 所有人都 ≥ 28 | `READY_FOR_HUMAN_SUBMISSION_CHECK` |
| 6 | 其他 | `REVISION_REQUIRED` |

**第 3 条的用意：** 审稿人提不出科学问题，不能被当成"没毛病"。一组只挑错别字和排版的意见，说明这次评审没有真正触及科学内容，所以判为**覆盖不足**，需要重做或补充审稿人。

**第 4 条的用意：** 差距大于 7 分时不取平均，而是标为**存在分歧，由作者决定**。你要处理的是"为什么有人觉得行、有人觉得不行"，这比一个 30.5 更值得看。

---

## 六、结论怎么读

| 结论 | 含义 | 下一步 |
|---|---|---|
| `INCOMPLETE` | 有人没打分 | 补齐七项分数 |
| `BLOCKED` | 有未解决的阻断问题 | 先解决 blocker，再重跑 |
| `INSUFFICIENT_SCIENTIFIC_COVERAGE` | 意见多为格式类 | 请审稿人针对科学内容再评，或换更懂行的视角 |
| `PANEL_DISAGREEMENT` | 分歧过大 | **作者决定**：接受某一方的判断，或补证据让分歧消解 |
| `READY_FOR_HUMAN_SUBMISSION_CHECK` | 全体达标 | **仍不是录用保证**，只是可以进入人工投稿复核 |
| `REVISION_REQUIRED` | 有人低于 28 | 按低于标准的那几项返工 |

**无论哪种结论，都必须把它当作"模拟意见"。** 报告文件末尾固定写着三条禁止事项，不要把它当成真实同行评审记录来引用。

---

## 七、交付物

| 文件 | 内容 |
|---|---|
| `review/panel.json` | 审稿人、七维分数、逐条意见、结论与统计摘要 |
| `review/review.md` | 人读版：结论、各审稿人视角与打分、逐条意见表、禁止事项 |

`panel.json` 的 `summary` 里有 `acceptance_probability: "not_estimated"` 这个字段。**它是有意留着的**——时刻提醒读者，这份表里没有、也不会有录用概率。

---

## 八、与既有阶段的关系

- 它在 **P6 结论与投稿返修** 里跑，位置是「写完结论、做完引用终检、投稿之前」。
- 它的七维评分与 [阶段闸门](../docs/PHASE_GATES.md) Gate 5 是同一套尺子，不要另立标准。
- 审稿人提出的补充检索要求，回到 **P2**；要求补实验或补稳健性检查，回到 **P3/P4**。**不要用文字回应硬凑。**
- 返修阶段把审稿意见编号（`R1.1`、`AC.1`）时，可以直接沿用这里的 `审稿人ID.序号` 作为 ID 来源。

## 九、检查清单

- [ ] 审稿人数量在 3–5 之间，且各有明确角色，不是同一视角的复制。
- [ ] 每位审稿人七项都打了分，没有留在 `not_scored`。
- [ ] 科学类意见不少于 3 条。
- [ ] 存在阻断问题的情况下，**没有**跳过它去谈加分项。
- [ ] 分数分散时，输出的是分歧说明而不是平均值。
- [ ] 需要作者补数据的意见已标 `requires_author_data`，且**没有**被编造的数据"解决"。
- [ ] 报告里没有录用概率，也没有把模拟意见说成真实审稿意见。
