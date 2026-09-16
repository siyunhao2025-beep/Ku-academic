# 五个上游：保留来源、隔离安装、按需加载

## 来源与用途
| 源码项目 | 集成位置 | 适配原则 |
|---|---|---|
| kangarooking/cangjie-skill | 领域资料到能力卡 | 保留完整方法和条件；科研证据与案例区分；不强制假装可用并行 agent |
| Galaxy-Dawn/claude-scholar | 研究路线、paper-miner、编辑 | 不采用其默认全局写作记忆路径；期刊/体裁档案隔离，项目结果不混入通用规则 |
| HKUSTDial/Supervisor-Skills | 框架、润色、审查的可选外部参考 | CC BY-NC-SA 4.0 独立保留；不改许可，不把 AI 顶会模板直接强加给空间物理 |
| K-Dense-AI/scientific-agent-skills | 文献、分析和科学绘图候选模块 | 逐个核验技能许可和依赖；不强制 AI 示意图、营销、外部服务或与任务无关的医疗工具 |
| yusufkaraaslan/Skill_Seekers | 大语料导入/知识资产准备的可选工具 | 转换成功不等于理解成功；本版不执行它的环境安装或外部模型调用 |

原始入口由 config/upstream.lock.json 的仓库、提交和路径定位。该清单是注册与版本锁定，不代表软件安装、全部文件审查或兼容性测试已完成。当前母 Skill 是基于本项目需求原创的调度/契约；没有复制五个仓库的源码并重新授权。

## 调用纪律
先在锁定提交读取目标 SKILL/agent 文件、它引用的必要资源和许可证。识别宿主相关工具名称、全局路径、hooks、API Key、外部费用和数据上传行为。仅在实际工具可用、任务需要、许可允许时采用；记录改动与调用结果。只读参考可用，不等于原生安装。

若某上游要求改变全局记忆、自动安装依赖、上传论文、无条件绘制生成图或启用推广服务，不继承该要求；使用本项目独立模块，说明外部模块未直接执行。原始文档保留，不静默修改后冒称原版。

## 源码获取
python scripts/upstream.py --out vendor-cache

按固定提交下载源码 ZIP，验证路径/解压大小，发现入口，写状态文件。ZIP 保持隔离、不自动解压执行。全部下载成功也只是 source_staged_quarantined；账号安装需由真实宿主完成并记录。五个上游源码不加入母 Skill 的轻量 ZIP；需要时按 ID 取用，避免把大量无关工具塞满上下文。

## 许可
Cangjie、Claude Scholar、Skill Seekers 的项目说明列 MIT；K-Dense 项目级 MIT 但单个 Skill 可能不同，须逐项核查。Supervisor-Skills 明示 CC BY-NC-SA 4.0。上述为来源标识，具体使用或分发仍须审查锁定提交中的完整许可。本项目原创文件的 MIT 不覆盖第三方材料或用户论文。
