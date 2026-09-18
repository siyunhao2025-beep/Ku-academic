# v0.3.0 改动说明

[返回首页](../README.md) · [v0.2.0 改动](CHANGELOG_v0.2.0.md) · [同类对比](PEER_COMPARISON.md)

**一句话总结：** v0.3.0 做四件事——**改名**（Ku-academic → Cool-Academic）、**去领域化**（移除绑定具体研究方向的领域包，换成中性模板）、**加能力**（目标期刊范文获取 + token 可视化看板）、**加纪律**（精简模式省 token，但明列不许省的东西）。

版本号统一到 **0.3.0**（此前 `scripts/research.py` 的 `VERSION` 与打包 `ASSET` 停在 0.1.0，是遗留的不一致，本次一并修掉）。调用名 `research-mother` **不变**。

---

## 一、项目改名

| 项目 | 旧 | 新 |
|---|---|---|
| 项目名 | Ku-academic | **Cool-Academic** |
| 发行包 | `Ku-academic-v0.1.0-skill.zip` | `Cool-Academic-v0.3.0-skill.zip` |
| Skill 调用名 | `research-mother` | `research-mother`（**不变**） |
| 安装包顶层目录 | `research-mother/` | `research-mother/`（**不变**） |

**为什么调用名不动：** `scripts/check_repository.py` 会断言 `SKILL.md` 含 `name: research-mother`，这是兼容性硬约束。改项目名不改调用名，已安装的用户不会因为改名而失效。

**代码里的改动方式：** `scripts/build_distribution.py` 不再硬编码资产名，改为 `ASSET = "Cool-Academic-v%s-skill.zip" % VERSION`，版本只在一处定义。`scripts/research.py` 的 `VERSION` 同步为 `0.3.0`。

**⚠️ 需要你手动做的一步：** GitHub 仓库本身的改名只能在 **Settings → Repository name** 里操作，本次用的连接器**没有**改名接口。仓库内所有引用（含 README 链接、克隆命令、文档中的 URL）已经改成 `Cool-Academic`。**在你完成仓库改名之前，这些链接会 404。** 改名后 GitHub 会自动把旧的 `Ku-academic` 链接重定向到新名字，所以不会有链接永久失效。

> **2026-09-18 更正：上面那句"在你完成仓库改名之前，这些链接会 404"是一句过早的自我安慰。** 实际后果是：仓库内 **9 处链接真的 404 了**（`releases/latest`、`actions`、`git clone`、`@GitHub 读取`），用户点开就是 404 页面。离线链接校验器抓不到它——它按设计会跳过绝对 http(s) 链接。
>
> **处置：** 所有内部 URL 改回**当前真实存在的** `Ku-academic`。理由是重定向方向只有旧→新，所以**旧名在改名前后都可用**，新名只在改名后可用——旧名严格更稳。
>
> **防复发：** 新增 `config/repository.json` 作为 slug 的唯一事实来源，并加 `tests/test_repository_identity.py` 断言所有内部 URL 与 `@GitHub 读取` 提示都使用该 slug。仓库真正改名时，只改这一处配置，跑一遍这个测试就会列出所有需要同步的文件。同时该测试禁止用户可见文档写死构建产物版本号（会随每次发布过期）。


## 二、去领域化：不再绑定任何研究方向

原仓库带一个绑定具体研究领域的领域包（含该领域的检索词、仪器、坐标系与检查项），README 首页也把那句话写在标题下面。

**v0.3.0 移除了它**，改为中性模板 `domains/example-domain/`：

| 项 | 处理 |
|---|---|
| 领域包目录 | 删除旧包，新建 `domains/example-domain/` |
| `project_parameters` 键名 | 改为通用名（`data_source_version`、`study_window`、`baseline_definition`、`primary_axis_bins`、`coordinate_system`、`time_reference`、`subsample_definition`、`uncertainty_definition`、`independent_sampling_unit` 等），去掉了指向特定观测方式与坐标体系的措辞 |
| 所有参数值 | 保持 `null`（`test_domain_not_event_hardcoded` 断言不放宽） |
| `learned_capability_cards` | 保持 `[]` |
| `checks` | 改为通用完整性检查，不再提具体仪器或指数 |
| `journal_candidates` | 改为占位符 `<target journal>` / `<alternative journal>` |
| 代码与测试中的路径 | `scripts/research.py`、`scripts/quickstart.py`、`tests/test_research.py` 全部指向新路径 |
| 文档示例 | README、ARCHITECTURE、GETTING_STARTED、USE_CASES、PHASE_GATES、LEGACY_VERIFICATION、MIGRATION、CHANGELOG、`modules/*` 中的领域示例全部改为通用措辞 |

**保留的东西（这些是通用能力，不是领域内容）：** 变量定义与坐标系要写清、数据源版本与质量标记要核实、观测/关联/机制三层要分开、基线不确定度要写明、不硬编码事件与阈值。这些条款对任何领域都成立，所以留着。

### 溯源记录的处理（重要）

`config/migration-source.json` 原先记录旧包两个文件的 SHA-256。改名脚本会把它变成"新路径挂着旧哈希"——**那等于伪造溯源记录**。

处理方式：把这两个条目**从哈希表中移除**（23 → 21），并新增 `not_carried_forward` 字段说明原因，**不复述旧领域内容**。`docs/MIGRATION.md` 同步说明少了哪两个、为什么。

**没有做的事：** 没有改路径后继续挂着旧哈希，也没有悄悄删掉不提。

## 三、新能力一：目标期刊范文获取

**你提的需求：** 根据目标期刊自动读取该刊在相关方向的最新论文 PDF 作为写作参考；调不到时支持用户自行下载后上传。

**新文件：** `modules/journal-sourcing.md` + `scripts/sourcing.py` + `tests/test_sourcing.py`（21 项测试）

### 各功能的目标、输入、输出

| 功能 | 目标 | 输入 | 输出 |
|---|---|---|---|
| F1 定向检索 | 找到该刊该方向最新论文元数据 | 期刊名、方向关键词、时间窗口、篇数 | `search.json` |
| F2 生成计划 | 转成可执行可追踪的清单 | `search.json` + 期刊 + 方向 + 起始年 + 上限 | `sourcing-plan.json` + `sourcing-checklist.md` |
| F3 自动获取 | 对开放获取或已授权副本下载 | `downloads.json`（含 `authorization` 与 `access_basis`）、允许主机 | 本地 PDF |
| F4 提取编目 | PDF → 可检索文本并登记 | PDF 目录、`manifest.json` | `corpus.json` + 逐页 JSON |
| F5 人工兜底 | 自动失败时让用户一次补齐 | 清单的建议文件名与落盘位置 | 用户放入的 PDF |
| F6 状态回填 | 区分"没拿到"和"不需要" | 条目 ID + 实际状态 | 更新的 `sourcing-plan.json` |
| F7 风格提炼 | 提炼表达习惯并留出评测 | 已读卡片、train/heldout 划分 | 期刊风格档案 |

### 两条路径

**路径 A（自动）** 复用已有的 `scripts/corpus.py`，**不重新实现下载**。这是有意的：corpus.py 已经硬编码了安全约束（仅 HTTPS、显式主机白名单、不跟随重定向、私网地址拒绝、40 MB 上限、`%PDF-` 魔数校验、必须声明授权依据），重写一遍只会把安全关键部分稀释掉。

**路径 B（人工兜底）** 是本模块的重点。自动拿不到时不删条目、不假装读过，而是生成一份用户可直接执行的清单：

| 清单列 | 作用 |
|---|---|
| ID（`P003`） | 回填状态用的稳定标识 |
| 建议文件名 | 用户照此命名，导入时能自动对应回条目，不用手工配对 |
| 标题 / 期刊 / 年 | 在数据库中检索确认是同一篇 |
| DOI 链接 | 一键跳到出版社页面 |

用户三步：按 DOI 下载 → 按建议文件名命名 → 放进 `private-corpus/inbox/`，然后回来说一句"放好了"，接着跑 `corpus.py ingest`。

### 状态与硬限制

四态：`fetched` / `manual_download_required` / `not_accessible` / `failed`。

```bash
python scripts/sourcing.py plan runs/sourcing-search/search.json \
  --journal "Target Journal" --direction "your direction" \
  --since-year 2024 --top 30 --type journal-article \
  --out runs/sourcing/sourcing-plan.json

python scripts/sourcing.py record runs/sourcing/sourcing-plan.json P003 \
  --status manual_download_required --note "机构订阅，需本人登录下载"

python scripts/sourcing.py list runs/sourcing/sourcing-plan.json
```

**写进测试的硬限制：**

- `expected_access` 初始只能是 `unverified_pending_check`——**未核实前不许声称知道能不能拿到**（`test_access_is_not_claimed_before_checking`）。
- 计划里必须带 `access_rule` 文本：只处理开放获取或用户授权副本，绝不绕过付费墙/登录/验证码。
- 清单里必须保留 `not_accessible` 条目可见（`test_checklist_keeps_not_accessible_visible`）。
- 清单必须写明"提取成功不等于读过"。
- 非法状态值、未知条目 ID 一律报错，返回码 2。

**没有做的事：** 没有自动绕过任何付费墙；没有把摘要当全文；没有把"无法获取"写成"无需处理"。

## 四、新能力二：token 可视化看板

**你提的需求：** 让用户直观地看到 token 使用量。

在已有 `scripts/lean.py` 上加一个 `--html`，输出**单文件、无 JS、无外部资源、离线可用**的看板：

```bash
python scripts/lean.py report <workspace> --html <workspace>/audit/token-dashboard.html
```

看板包含四张汇总卡（累计 / 步数 / 单步最大 / 对话状态）、纯 CSS 横向条形图（每步占比）、明细表，以及一条**不可省略的橙色提示**：这个数不是账单，只统计产出物文件，对话本身的用量本机读不到。

**为什么用纯 CSS 而不是图表库：** 引一个图表库只为了画几根柱子，违反精简模式自己的阶梯第 5 条。CSS 的 `width: X%` 已经够了。

## 五、新纪律：精简模式

**新文件：** `modules/lean-mode.md`、`docs/TOKEN_ACCOUNTING.md`、`assets/deai-checklist.md` 已在 v0.2.0 落地，精简模式与 token 口径属 v0.3.0。

### 触发方式

| 方式 | 怎么写 |
|---|---|
| 全程 | 对话开头 `@skill:ponytail` |
| 触发词 | `精简模式` / `省点 token` / `别过度设计` / `最短路径` / `lazy mode` / `YAGNI` |
| 档位 | `/ponytail lite`、`/ponytail full`（默认）、`/ponytail ultra` |
| 关闭 | `stop ponytail` / `normal mode` |

### 生效范围

**管：** 产出物数量、模块加载、重复读取、回复长度、工具调用次数、依赖引入。

**绝不管（红线）：** 数字、单位、有效位数、符号、证据强度、引用的两道核验、`待确认` 标记、失败运行记录、数据审计结论、图件人工视觉审查、隐私与授权、用户明确要求的东西。

判据：**省掉它会让结论更不可验证吗？会就不能省。**

### 统计口径与展示形式

两个口径，**不能无条件相减**（统计的是不同文件集合）：

| 口径 | 定义 | 用途 |
|---|---|---|
| **A 写入量**（默认） | 记录步骤里实际写入的文件 token 之和，改写重计 | 衡量成本 |
| **B 快照** | 目录当前全部文本文件之和，去重 | 衡量交付物体积 |

**能测：** 产出物文件的 token（有 `tiktoken` 时 `cl100k_base` 实测；无则用 `tokens ≈ CJK×1.05 + 非CJK÷3.8` 估算，`SKILL.md` 对照实测偏高约 25%，偏高是有意选的偏差方向）。

**不能测：** 对话输入输出、计费金额、模型推理。已实际排查 `~/.claude/projects/`（只有 1 个 2026-05-14 的无关会话）、WorkBuddy 日志目录（最新 2026-08-31，且不含用量）。**没有本机记录**，所以记为 `not_measurable_from_here`，不猜数字。

展示形式（每轮两行，**第二行不许删**）：

```text
📊 累计 token（口径 A 写入量 · tiktoken:cl100k_base）：12,345
   对话本身 token：无法从本地读取 · 见 docs/TOKEN_ACCOUNTING.md
```

**没有做的事：** 没有把估算标成实测；没有省略"对话 token 无法测量"那一行；没有暗示产出物数字等于账单。

## 六、验证结果（实测）

| 检查 | 命令 | 结果 |
|---|---|---|
| 单元测试 | `python -m unittest discover -s tests -v` | **Ran 101 tests — OK (skipped=1)** |
| 仓库校验 | `python scripts/check_repository.py` | **Repository checks: PASS** |
| 打包 | `python scripts/build_distribution.py --out dist` | 退出码 0 |
| 端到端·范文获取 | `sourcing.py plan` → `record` → `list` | 退出码 0，2 条候选，状态回填生效，清单 2,231 字节 |
| 端到端·token 看板 | `lean.py report --html` | 退出码 0，看板 3,955 字节 |

测试从 v0.2.0 的 57 项增至 **101 项**（新增 21 项 sourcing + 20 项 lean，其余为既有）。

**那条 skip：** `test_symlink_escape`，因本机无 Windows 符号链接权限。原因见 [v0.2.0 改动说明](CHANGELOG_v0.2.0.md#26-顺带修掉的真实缺陷windows-符号链接)。

**诚实说明：** 测试通过只证明结构、链接、打包契约与既有接口未被破坏，**不证明**新增规则在真实科研任务上有效。规则实效需要真实任务评估。

## 七、需要你做的事

1. **在 GitHub Settings 里把仓库改名为 `Cool-Academic`**（连接器无此接口）。
2. 如需重新发包，跑一次 `python scripts/build_distribution.py --out dist`，新资产名为 `Cool-Academic-v0.3.0-skill.zip`。
