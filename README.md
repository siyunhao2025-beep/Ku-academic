<div align="center">

# Ku-academic
### 通用科研母 Skill × 可替换领域包

**从文献到证据，从代码到方法，从结果到论文。**

把检索、综述、论文框架、方法描述、绘图、补稿和润色接成可复用的研究工作流。  
首个领域包：**空间天气与中间层—低热层（MLT）温度响应**。

[开始使用](docs/GETTING_STARTED.md) · [下载 Skill 安装包](https://github.com/siyunhao2025-beep/Ku-academic/releases/latest) · [复制场景提示词](docs/USE_CASES.md) · [查看测试](https://github.com/siyunhao2025-beep/Ku-academic/actions)

</div>

---

## 它帮你解决什么？

不是再收藏一堆互不相通的提示词，而是让下一步接住上一步的证据和产物。

| 你正在做的事 | Ku-academic 的工作方式 | 应当留下的产物 |
|---|---|---|
| 开始一项研究 | 先读材料，分流原创研究或综述，梳理论点与证据 | 研究问题、项目状态、论点—图表—章节对应表 |
| 整理自己领域的经验 | 提炼文献与代码中的方法、适用条件、反例 | 有出处的知识卡、方法卡和测试用例 |
| 找新论文、写综述 | 按日期发现候选，再筛选、读全文、比较条件与结论 | 检索日志、证据矩阵、主题综合 |
| 描述实验或分析过程 | 根据实际代码、配置和日志写 Methods | 方法—代码对应记录、可复现的描述 |
| 做科研图 | 从真实数据与计算结果出图，保留处理和不确定度定义 | 源数据、绘图代码、图件和图注 |
| 给已有文章补内容 | 只补有贡献的比较、方法依据、机制约束或纠错 | 有证据的修改方案与前后对照 |
| 学习目标期刊、润色英文 | 从同刊同体裁全文提炼论证和表达习惯，再检验应用效果 | 逐篇阅读卡、期刊风格档案、修订稿 |

**科学内容由承载 Skill 的模型基于真实材料处理；Python 脚本负责检索、编目、检查与打包。** 脚本不会凭空完成实验、自动造图造结果，也没有接入一个隐藏的付费模型服务。

## 第一次使用：选一条路线

### A. 已经在 ChatGPT 连接 GitHub：直接开始

把下面这段发给 AI，无需先在电脑安装 Python：

```text
@GitHub 请读取 siyunhao2025-beep/Ku-academic 的根目录 SKILL.md，
再读取 modules/workflow.md 与当前任务需要的模块。
使用 research-mother，加载 space-weather-mlt 领域包。
根据我上传的文献、稿件、代码和结果，先建立项目状态和证据矩阵，再推进研究。
有实质证据才补稿，不堆防御性文字；缺少材料时继续能完成的步骤，不编造结果。
本次目标：[写原创论文 / 写综述 / 学习目标期刊 / 补稿 / 润色 / 描述方法 / 绘图]。
```

AI 必须实际读到仓库文件，而不是只看到仓库名称。这是**会话内按文件调用**，不等于已永久安装进账号；工具权限由当前平台决定。

### B. 想安装为 Skill：下载轻量包

进入 **[Releases 下载页](https://github.com/siyunhao2025-beep/Ku-academic/releases/latest)**，下载 `Ku-academic-v0.1.0-skill.zip`。它包含 `research-mother/SKILL.md` 及配套模块；不要把 GitHub 自动生成的 `Source code (zip)` 当成同一个安装包。

具有 Skills 上传权限的 ChatGPT 工作区：**Plugins → Skills → Create → Upload from your computer**，上传 ZIP，完成扫描并确认安装后，再说“使用 research-mother……”。没有该入口时，使用路线 A，或在支持文件与代码执行的对话中上传 ZIP、要求解压读取。以实际账号界面为准；GitHub 更新不会自动替换已上传副本。[官方安装说明](https://help.openai.com/en/articles/20001066-skills-in-chatgpt)

### C. 想在电脑处理文件：运行本地工具

```bash
git clone https://github.com/siyunhao2025-beep/Ku-academic.git
cd Ku-academic
python -m venv .venv
```

Windows（无需激活环境，不必修改 PowerShell 执行策略）：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/research.py doctor
.\.venv\Scripts\python.exe scripts/quickstart.py runs/first-demo
```

macOS / Linux：

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/research.py doctor
.venv/bin/python scripts/quickstart.py runs/first-demo
```

示例只创建项目骨架、说明与文件依赖记录，**不是生成一篇论文**。Windows 用户也可双击根目录 `START_WINDOWS.bat` 完成环境检查和首次示例。详细步骤见 [新手教程](docs/GETTING_STARTED.md)。

## 按什么顺序工作？

**原创研究**  
问题与文献 → 设计与数据审计 → 实际计算与稳健性检查 → 图表 → 方法与结果 → 讨论与引言 → 摘要与结论 → 审查和润色。

**综述**  
范围与检索方案 → 检索和筛选 → 全文证据矩阵 → 比较结论与适用条件 → 主题框架 → 分节综合 → 引用核验和修订。

期刊风格学习可以提前做；不能让目标文风反过来改变研究结果。基线、参数或样本变化后，重新检查依赖它们的图件与段落。已登记文件依赖可由脚本检测失效，语义依赖仍需研究者或模型审查。

## 两个特别的写作原则

**补稿是补论证，不是加免责声明。** 明确观测到的结果直接说清楚；机制证据不足时，只限定对应的机制句子。保留真正影响解释或复现的限制，不机械扩写泛泛的 limitations，不为增加引用数量而塞文献。

**学习期刊是学习表达组织，不是模仿作者或复制原句。** 从真实全文中提炼段落功能、量化方式、比较结构与图注职责；按期刊、体裁和作者组组织样本。没有读完语料，就没有完成风格学习；不以 AI 检测分数或投稿承诺作为验收标准。

## 换个研究领域也能用

母 Skill 不绑定个人简历、具体磁暴、基线日期或某个固定结论。复制领域配置并在项目中替换，保持检索词、术语、检查项与已学知识卡相互分离。见 [领域包与架构](docs/ARCHITECTURE.md)。

目前 `space-weather-mlt` 是**起步接口和检查流程**，不是已经读完所有空间天气文献的知识库。目标期刊档案也需要你的真实语料来建立。

## 文档导航

| 文档 | 内容 |
|---|---|
| [新手教程](docs/GETTING_STARTED.md) | 下载哪个文件、账号安装、GitHub 调用、Windows 与本地运行 |
| [场景提示词](docs/USE_CASES.md) | 原创研究、综述、近 30 天论文、期刊学习、补稿、润色、方法与绘图 |
| [文件接口](docs/CONTRACTS.md) | PDF 清单、期刊阅读卡、补稿证据、断点记录格式 |
| [架构与扩展](docs/ARCHITECTURE.md) | 新增领域包、区分期刊风格与项目结果、阶段依赖 |
| [常见问题](docs/FAQ.md) | 没有 Skills 入口、是否自动写论文、费用、PDF 和隐私 |
| [上游来源](docs/UPSTREAM.md) | 五个参考项目的版本、适配规则与独立许可 |
| [迁移记录](docs/MIGRATION.md) | 旧项目来源、迁入范围与历史验收的区别 |
| [验收范围](docs/ACCEPTANCE.md) | 自动化能检查什么，还需要哪些真实任务验证 |

## 维护、隐私与许可

源自 Research Mother v0.1.0，现以 **Ku-academic 独立仓库**维护，调用名保持 `research-mother`。五个上游项目通过 [版本清单](config/upstream.lock.json) 按需取用；登记或下载源码不代表全部原生安装与调用验收完成。没有默认开启后台文献订阅或自动投稿。

论文全文、未发表稿件、科研数据和密钥留在私有工作目录。不要提交到这个公开仓库；忽略规则和打包清单也不能替代发布前核查。本项目原创代码与文档遵循 [MIT](LICENSE)，第三方技能、论文及素材保留各自许可。
