# 同类 Skill 对比与融合记录

[返回首页](../README.md) · [改动说明](CHANGELOG_v0.2.0.md)

本文件记录 v0.2.0 优化前实际检索到的同类科研 / 学术写作 Skill，逐项列出它们做得好的地方、做得不足的地方，以及本项目吸收了什么、为什么吸收、写进了哪个文件。

## 检索与判定方法

- 检索对象：GitHub 上以科研全流程、学术写作、降 AI 痕迹、科研绘图为主体的可复用 Skill 仓库。
- 判定依据：实际读取仓库的 `SKILL.md` 与关键参考文件，记录**可复述的具体机制**（编号规则、阈值、状态名、清单项），不采信 README 的宣传语与星数。
- 许可政策：MIT 等宽松许可的机制被**改写并泛化后重新实现**，不整段搬运；GPL 或许可不明的仓库只用于识别思路，不复制文本。
- 星数为检索当时数据，仅用于说明影响面，不构成质量判断。

## 对比表

| 仓库 | 星数 / 许可 | 主要可复用能力 | 优点 | 不足 | 本项目的处置 |
|---|---|---|---|---|---|
| [ShaishavMaisuria/research-paper-lifecycle-skills](https://github.com/ShaishavMaisuria/research-paper-lifecycle-skills) | 45★ / MIT | 引文四态判定 `VERIFIED / MISMATCH / UNRESOLVED / RETRACTED`；`CANONICAL_INSTANCE`；配色 `okabe-ito` 等无障碍色板；deltaE 可辨性阈值；三线表机械转换九步 | 工程化程度最高，规则可执行、可写成断言；明确区分"解析成功"与"支持当前句子" | 面向 LaTeX 单一路径，缺少中文场景与全流程阶段划分；未处理"数字与单位是否被篡改" | 引文判定与色板规则被吸收进 `modules/evidence-integrity.md` 与 `modules/figures.md`；三线表规则并入图表检查项 |
| [lishix520/academic-paper-skills](https://github.com/lishix520/academic-paper-skills) | 1309★ / MIT | 阶段闸门 + 数值阈值（样本 ≥8、相关性 ≥8/10、独立作者 ≥5；综述 ≥20 篇、缺口 ≥3；审稿人 7 维 ≥28/35 等） | 把"做完了"变成可打分的门槛，团队协作时争议最小 | 阈值来源未公开，硬搬会给人虚假安全感；七维清单未区分科学内容与形式 | 吸收"阶段必须过闸"的结构，阈值降级为**可配置默认值**并显式标注"工程下限，非统计保证"，写入 `modules/workflow.md` 与 `docs/PHASE_GATES.md` |
| [AIScientists-Dev/academic-humanizer](https://github.com/AIScientists-Dev/academic-humanizer) | 1597★ / MIT | 三层降 AI：反过度纠正层（保护证据绑定的 hedging、被动语态、"we"、术语）；区间优先于单点均值；与最强竞争者对比先行 | 唯一显式警告"为降 AI 而把 suggest 改成 prove 等于制造过度声称"的仓库，观点正确且少见 | 只处理语言，不碰证据链；对句式节奏的解释停留在建议层 | 反过度纠正层被完整吸收为 `modules/deai-writing.md` 的第一红线；该模块放在润色流程之前强制读取 |
| [matsuikentaro1/humanizer_academic](https://github.com/matsuikentaro1/humanizer_academic) | 180★ / 见仓库 | 句式节奏重构是单项收益最大干预（约 90%）；人类段落句长 12–55 词、SD 10–15，AI 常 SD <5；**仅删副词而不重构会反而提高 AI 分数（logit +0.72 恶化）** | 给出了可测量指标和反直觉结论，避免了"删词式降 AI"的常见错误 | 指标基于英文语料，直接套到中文会失真 | 指标吸收为"节奏诊断"，中文部分另设以逗号/句号节律与段落长度的等价判断；写入 `modules/deai-writing.md` |
| [redbaronyyyyy-eng/humanizer-zh-academic](https://github.com/redbaronyyyyy-eng/humanizer-zh-academic) | 292★ / 见仓库 | 中文硬约束：每段 AI 高频词 ≤2、段末总结套话全文 ≤1、三元排比每段 ≤1、加粗全文 ≤5、模糊结尾 0、无出处含糊归因（"专家认为/研究表明"）0；噪声预算——每千字保留 2–3 处轻度 AI 特征以免过度同质 | 中文场景下少见的量化禁令；噪声预算避免了"越改越假" | 只列禁词，不解释改写后的替代结构 | 禁令表收入 `modules/deai-writing.md` 与 `assets/deai-checklist.md`；与用户既有 `human-writing` 技能的禁词表做并集去重 |
| [zLanqing/codex-claude-academic-skills](https://github.com/zLanqing/codex-claude-academic-skills) | 3997★ / MIT | 示意图七原型分类（架构/流程/组件/概念/对比/分类/部署）；五条批评检查；矢量与灰度硬规格；跨图一致性五规则（锁色语义、节点形状词汇、统一字体线宽、组件命名一致、同抽象层复杂度相近）；Tufte 数据墨水比 | 是目前对"原理示意图"讲得最系统的来源；提出"不允许抽象色块，每个形状必须代表一个具名事物" | 只讲图，不讲图与论证的对应；未覆盖数据图的配色无障碍 | 七原型、跨图一致性、数据墨水比写入 `modules/figures.md`；"每个形状代表具名事物"变为路线图的硬检查项 |
| [yisyeasy-crypto/academic-writing-dna-skill](https://github.com/yisyeasy-crypto/academic-writing-dna-skill) | 53★ / 见仓库 | 按作者组划分训练/留出、模式 ID 必须保留页段定位、风格档案以"观察到的倾向"而非"期刊规定"表达 | 与既有 `journal-distillation` 方向一致，验证了本项目既有设计 | 未解决留出评测通过后的状态管理 | 既有 `modules/journal-distillation.md` 基本覆盖，仅补"同一 pattern ID 跨篇定义必须调和"的执行细节 |
| [kgraph57/paper-writer-skill](https://github.com/kgraph57/paper-writer-skill) | 57★ / 见仓库 | 超长单文件 Skill（79.5 KB）覆盖大量写作模板 | 覆盖面广，适合当模板库检索 | 单文件难以维护；规则之间冲突时无优先级裁决 | 不整文件吸收；只取"规则冲突需要优先级"这一点，写入 `modules/deai-writing.md` 的规则优先级段 |
| [binary-husky/gpt_academic](https://github.com/binary-husky/gpt_academic) | 71201★ / GPL-3.0 | 插件化解构论文、批量润色、PDF 翻译的工程组织方式 | 生态成熟，工具链完整 | GPL，且是应用而非 Skill 规范；直接搬运有许可与体量问题 | 仅用于确认"检索—解构—润色"的功能边界，不复制任何文本或代码 |

## 融合后的关键判断

### 1. 没有现成仓库同时满足四条

把"引用真实存在"（编码身份核验）、"引用确实支持这句话"（语义支持核验）、"数字与单位不可被语言修改"（数值守卫）、"部分通过不等于通过"（判定语义）四条同时做全的仓库，本次检索中没有找到。

最接近的是 `ShaishavMaisuria/...`（身份核验与判定语义强）与用户既有的 `math-modeling-to-sci`（支持核验与高风险错配清单强）。因此 v0.2.0 的 `modules/evidence-integrity.md` 采用**两者融合**：四态身份判定来自前者，六类支持状态与高风险错配清单来自后者。

### 2. 阈值只能当工程下限

`lishix520` 的阶段阈值好用在"逼人停下来"，风险在于把取样下限当成科学充分性。本项目所有阈值统一标注为可配置工程下限，并禁止用"降到阈值以下再跑一次"的方式把试运行标成正式验证。

### 3. 降 AI 必须防止改坏科学

`academic-humanizer` 的反过度纠正警告是本轮最有价值的单条结论。降 AI 模块的第一条不是"怎么改得像人"，而是"什么不许动"：数字、单位、样本量、符号、置信口径、仪器名、引用、证据强度。

### 4. 示意图与数据图是两类规则

`zLanqing` 回答的是"怎么把机制讲清楚"，`Maisuria` 回答的是"怎么让数据可安全辨认"。两者不能合并成一句"图要画好"，因此在 `modules/figures.md` 内部分为两节，并各自给出独立的检查清单。

## 上游文本的来源与许可

上表所有仓库均为公开仓库，本项目**未收录其原始文件**。`modules/evidence-integrity.md`、`modules/figures.md`、`modules/deai-writing.md` 中的规则均为改写与泛化后的重新表述，行文与原仓库不同，阈值与清单项可逐条追溯到上表来源。`config/upstream.lock.json` 登记的是另五个只做源码隔离下载的项目，与本次同类对比无关，未做改动。

## 后续可继续观察的方向

- 中文期刊（如《地球物理学报》《空间科学学报》）的格式与表达规范目前没有找到成体系的公开 Skill，需要自行积累语料。
- 数学符号与量纲一致性检查（`SI` 单位、量纲齐次、有效位数传播）在本次检索到的仓库中均为空白，若后续需求明确可单列模块。
- 图件可访问性目前只有色板与 deltaE 规则，缺少对色盲模拟渲染的自动化验证，暂由人工视觉审查承担。
