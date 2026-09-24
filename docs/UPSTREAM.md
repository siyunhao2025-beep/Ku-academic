# 上游来源：保留出处、隔离安装、按需加载

## 来源与用途
| 源码项目 | 集成位置 | 适配原则 |
|---|---|---|
| kangarooking/cangjie-skill | 领域资料到能力卡 | 保留完整方法和条件；科研证据与案例区分；不强制假装可用并行 agent |
| Galaxy-Dawn/claude-scholar | 研究路线、paper-miner、编辑 | 不采用其默认全局写作记忆路径；期刊/体裁档案隔离，项目结果不混入通用规则 |
| HKUSTDial/Supervisor-Skills | 框架、润色、审查的可选外部参考 | CC BY-NC-SA 4.0 独立保留；不改许可，不把 AI 顶会模板直接强加给空间物理 |
| K-Dense-AI/scientific-agent-skills | 文献、分析和科学绘图候选模块 | 逐个核验技能许可和依赖；不强制 AI 示意图、营销、外部服务或与任务无关的医疗工具 |
| yusufkaraaslan/Skill_Seekers | 大语料导入/知识资产准备的可选工具 | 转换成功不等于理解成功；本版不执行它的环境安装或外部模型调用 |
| ChenLiu-1996/figures4papers | 独立 `skills/scientific-figure-making/` + 本地 `modules/figures4papers-profile.md` | 锁定提交与 CC BY-NC 4.0；安装真实主 Skill、五个 references、完整许可与来源记录，本地科研护栏优先；不复制 demo 脚本、数据、图片或 PDF |

原始入口由 config/upstream.lock.json 的仓库、提交和路径定位。该清单会分别标明“仅登记”“仓库内安装”和“宿主安装”，三者不能混称。当前母 Skill 的调度/契约是本项目原创；`skills/scientific-figure-making/` 是明确列出的例外，它以 CC BY-NC 4.0 独立分发，没有被根 MIT 重新授权，也不代表已经安装到用户的全局 Codex 账户。

## 调用纪律
先在锁定提交读取目标 SKILL/agent 文件、它引用的必要资源和许可证。识别宿主相关工具名称、全局路径、hooks、API Key、外部费用和数据上传行为。仅在实际工具可用、任务需要、许可允许时采用；记录改动与调用结果。只读参考可用，不等于原生安装。

若某上游要求改变全局记忆、自动安装依赖、上传论文、无条件绘制生成图或启用推广服务，不继承该要求；使用本项目独立模块，说明外部模块未直接执行。原始文档保留，不静默修改后冒称原版。

### figures4papers 的额外边界

锁定版本为 `3c181f85e82c6f24948fcaaf3be6696102b41d8d`，入口为 `scientific-figure-making/SKILL.md`，上游声明许可为 CC BY-NC 4.0。分发包包含两层：

1. 独立安装的真实 [`skills/scientific-figure-making/SKILL.md`](../skills/scientific-figure-making/SKILL.md)、五个 references、完整 [CC BY-NC 4.0 LICENSE](../skills/scientific-figure-making/LICENSE)、来源/改动记录与 Codex 界面元数据；
2. 本项目独立撰写的 [`modules/figures4papers-profile.md`](../modules/figures4papers-profile.md)，负责 adopt / adapt / reject / reference-only 决策。

真实 Skill 已记录本地适配：demo 链接锁到上述提交；截断柱图、隐藏标签、alpha-only、红绿单通道和机械超宽画布不得覆盖本地规则。真实数据、`source_data -> script -> outputs -> caption`、无障碍、柱图零基线、热图尺度披露、雷达/3D 替代及人工视觉审查始终优先。未收录上游 25 个绘图脚本、demo 数据、39 个 PNG、3 个 PDF 或论文资产。

独立 Skill 的署名、仓库 URL、锁定提交、许可链接和本地改动列在其 [SOURCE.md](../skills/scientific-figure-making/SOURCE.md)。继续复用其它上游材料时仍须逐件核实权利范围，仅限非商业用途并补全归属与改动说明。根目录 MIT 只覆盖本项目原创文件，明确不覆盖 `skills/scientific-figure-making/`；商业或权利不清的场景应从零实现通用方法或先取得单独授权。

## 源码获取
python scripts/upstream.py --out vendor-cache

按固定提交下载源码 ZIP，验证路径/解压大小，发现入口，写状态文件。ZIP 保持隔离、不自动解压执行。全部下载成功也只是 source_staged_quarantined；账号安装需由真实宿主完成并记录。除上节明确列出的 `scientific-figure-making` 独立 Skill 文件外，上游源码不加入母 Skill 的轻量 ZIP；需要时按 ID 取用，避免把大量无关工具塞满上下文。

## 许可
Cangjie、Claude Scholar、Skill Seekers 的项目说明列 MIT；K-Dense 项目级 MIT 但单个 Skill 可能不同，须逐项核查。Supervisor-Skills 明示 CC BY-NC-SA 4.0；figures4papers 明示 CC BY-NC 4.0。上述为来源标识，具体使用或分发仍须审查锁定提交中的完整许可。本项目原创文件的 MIT 不覆盖第三方材料、`skills/scientific-figure-making/` 或用户论文。
