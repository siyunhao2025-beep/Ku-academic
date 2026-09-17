# 目标期刊范文获取：先用自动，再走人工兜底

[返回首页](../README.md) · [期刊语料学习](journal-distillation.md) · [文献真实性](evidence-integrity.md) · [阶段总控](phases.md)

**这一模块解决一个具体问题：** 想按目标期刊的写法写，就得先读到该刊在**你这个方向**上的最新论文。但论文能不能拿到，不由你决定。

所以这里设计成两条路：**能自动拿的自动拿，拿不到的用清单交给用户自己下。** 两条路都必须留下记录。

先打个比方。

**像去图书馆借书。** 开架区你自己就能拿（开放获取）。闭架区要馆员批准（授权访问）。有人就是没上架（付费墙）。**图书馆的规定不是你能绕的，但你可以先查清楚哪几本在开架区，剩下的写张单子请人帮忙。**

---

## 一、各功能的目标、输入与输出

| 功能 | 目标 | 输入 | 输出 |
|---|---|---|---|
| **F1 定向检索** | 找到该刊该方向的最新论文元数据 | 目标期刊名、研究方向关键词、时间窗口、目标篇数 | `search.json`（含 DOI、标题、期刊、年份、链接） |
| **F2 生成获取计划** | 把候选转成可执行、可追踪的获取清单 | `search.json` + 期刊名 + 方向 + 起始年 + 上限 | `sourcing-plan.json` + `sourcing-checklist.md` |
| **F3 自动获取** | 对**开放获取或已授权**的副本执行下载 | `downloads.json`（含 `authorization` 与 `access_basis`）、允许的主机 | 本地 PDF |
| **F4 提取与编目** | 把 PDF 变成可检索文本并登记 | PDF 目录、`manifest.json` | `corpus.json` + 逐页 JSON |
| **F5 人工兜底** | 自动获取失败时，让用户能一次性补齐 | `sourcing-checklist.md` 的建议文件名与落盘位置 | 用户放入的 PDF 集合 |
| **F6 状态回填** | 记录每篇的真实结果，区分"没拿到"和"不需要" | 条目 ID + 实际状态 | 更新后的 `sourcing-plan.json` |
| **F7 风格提炼** | 从已读全文提炼表达习惯并做留出评测 | 已读卡片、train/heldout 划分 | 期刊风格档案 |

F7 的完整规则在 [期刊语料学习](journal-distillation.md)，本模块负责把材料备齐。

---

## 二、路径 A：自动获取（先试这条）

```bash
# F1 定向检索（Crossref 是元数据后端，不是全网检索器）
python scripts/research.py search --query "your key construct your method" \
  --since 2025-01-01 --until 2026-09-17 --pages 2 --rows 50 \
  --out runs/sourcing-search

# F2 生成计划与清单
python scripts/sourcing.py plan runs/sourcing-search/search.json \
  --journal "Target Journal Name" --direction "your direction" \
  --since-year 2024 --top 30 --type journal-article \
  --out runs/sourcing/sourcing-plan.json

# F3 只对开放获取或已授权副本下载
python scripts/corpus.py download private/downloads.json private/download-v1 \
  --allow-host AUTHORIZED-HOST

# F4 提取与编目
python scripts/corpus.py ingest private/manifest.json private/extracted-v1
```

### 自动获取能做什么、不能做什么

| 能做 | 不能做 |
|---|---|
| 检索元数据（标题、DOI、期刊、年份、链接） | 绕过付费墙、登录、验证码 |
| 下载开放获取全文 | 下载未授权的版权内容 |
| 下载用户已明确授权的副本 | 访问私网地址或非 HTTPS 来源 |
| 提取文本、编目、登记哈希 | 把提取成功当成"读过" |

**这些限制不是建议，是脚本硬编码的。** `scripts/corpus.py` 会拒绝非 HTTPS、带凭据的 URL、非允许主机、重定向到未允许主机、私网 IP、超过 40 MB 的文件，以及文件头不是 `%PDF-` 的伪 PDF。它**不会**替你登录或付费。

---

## 三、路径 B：人工兜底（自动拿不到时走这条）

这是本模块的重点。**当自动获取失败，不要把条目删掉，也不要假装读过——把它变成一张用户能直接执行的清单。**

`sourcing.py plan` 生成的 `sourcing-checklist.md` 已经包含人工下载所需的全部信息：

| 清单列 | 作用 |
|---|---|
| ID | 回填状态时用的稳定标识，如 `P003` |
| 状态 | `pending` / `manual_download_required` / `not_accessible` / `failed` |
| 建议文件名 | 用户按此命名，后续脚本能自动对应到条目，不用手工配对 |
| 标题 / 期刊 / 年 | 用于在数据库中检索确认是同一篇 |
| DOI 链接 | 一键跳到出版社页面 |

### 用户要做的三步

1. 打开 `sourcing-checklist.md`，按 DOI 链接找到论文页面。
2. 用你自己的机构权限下载 PDF（这一步只有你能做，因为只有你有账号）。
3. 按「建议文件名」命名，放进 `private-corpus/inbox/`。

然后回到对话里说一句「我已经放好了」，接着跑 F4 导入。**清单里的文件名是刻意设计的**——它让导入环节可以自动把你下的 PDF 对应回计划条目，不需要你逐篇说明哪个是哪个。

### 状态回填

每篇都要有真实结论，四选一：

```bash
python scripts/sourcing.py record runs/sourcing/sourcing-plan.json P003 \
  --status manual_download_required --note "机构订阅，需本人登录下载"
```

| 状态 | 含义 | 后续动作 |
|---|---|---|
| `fetched` | 已拿到 | 进入 F4 提取与 F7 提炼 |
| `manual_download_required` | 需用户人工下载 | 留在清单里等用户 |
| `not_accessible` | 无法合法获取 | **明确记录**，不进入语料，不用它支撑任何论断 |
| `failed` | 尝试失败（网络、格式、损坏） | 记录失败原因，可重试 |

查看还没处理完的：

```bash
python scripts/sourcing.py list runs/sourcing/sourcing-plan.json
```

---

## 四、样本量与划分

拿到 PDF 不等于学会风格。按 [期刊语料学习](journal-distillation.md) 的规则：

- 同刊**同体裁**：期刊名不同子刊要分开（例如同一刊的综述与原创论文不能混）。
- 起步规模 20–50 篇，是**可配置的工程取样下限**，不是该刊规定，也不是充分性证明。
- 按**作者组**划分 train / heldout，避免同团队或同文不同版本泄漏。
- 至少留一个完全未参与提炼的作者组做评测。
- 覆盖不同年份与主题，不要只取最近三个月。

**自动检索的天然偏差要写下来：** 开放获取的论文与付费论文在期刊、作者、主题分布上可能不同。你拿到的这批不是该刊的无偏样本。这条限制要写进方法或限制说明，不能省。

---

## 五、绝对不许做的事

- **不许绕过付费墙、登录或验证码。** 没有例外，用户要求也不做。
- **不许假装读过没拿到的论文。** 拿不到就标 `not_accessible`。
- **不许把摘要当全文。** `metadata_only` 只能支持书目信息，不能支持物理结果或机制句子。
- **不许把"无法获取"写成"无需处理"。** 两者完全不同。
- **不许用完提取就标 `full_text_read=true`。** 必须真正读完正文与相关图表，且视觉核验过。
- **不许把自动检索结果说成该刊无偏样本。**
- **不许因为样本少就降低阈值凑数。** 样本少就说样本少，写清覆盖情况。

---

## 六、检查清单

- [ ] 候选来自定向检索，检索日志含查询语句、日期、来源、命中数与截断情况。
- [ ] 每条候选都有稳定 ID，且状态已回填，没有留在 `pending`。
- [ ] 每条 `fetched` 的条目都有对应的 `access_basis` 记录（开放获取或用户授权）。
- [ ] `not_accessible` 的条目已明确记录，且**没有**被用作论断证据。
- [ ] PDF 放入后已跑 `corpus.py ingest`，卡片中 `full_text_read` / `visual_checked` 与实际一致。
- [ ] train / heldout 按作者组划分，无泄漏。
- [ ] 已写下"开放获取样本可能有偏"这条限制。
- [ ] 风格档案状态为 `draft_needs_heldout_evaluation`，且**未**声称已完成泛化验证。

## 七、与其他模块的关系

- 引用身份与支持核验：`modules/evidence-integrity.md`（拿到全文后必做）
- 风格提炼与留出评测：`modules/journal-distillation.md`
- 下载与提取的安全实现：`scripts/corpus.py`（本模块不重复实现）
- 精简模式：`modules/lean-mode.md`——**省 token 不能省"实际读过"这一点**，没读就是没读。
