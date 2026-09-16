# 母 Skill、领域包与项目目录

[返回首页](../README.md)

## 四层分离

1. 通用流程：SKILL.md 和 modules，负责阶段与任务选择。
2. 领域包：domains，负责范围、检索词、术语、方法条件与检查项。
3. 期刊档案：放在自己的私有项目中，按期刊、体裁、语料版本隔离；保留出处和评测状态。
4. 项目状态：project.json、domain.json、证据、实际结果与审计，不能混入通用规则。

领域包是可替换的配置与资料，不是模型权重。更新文件也不等于训练模型或永久修改账号记忆。

## 新增领域

复制 domains/space-weather-mlt 到自己的工作目录，修改 domain.json 的 id、scope、search_queries、project_parameters、checks 和 journal_candidates，清空不适用的 learned_capability_cards。同步改写领域 SKILL.md，避免遗留 MLT 指标与假设。

```bash
python scripts/research.py init runs/new-field --domain private/my-domain/domain.json --kind original
```

当前初始化器复制 domain.json；不会自动复制同目录的 SKILL.md、知识卡及全文资源。应在私有工作区另行保存这些资料，并明确告诉模型读取它们。元数据字段能被解析不代表新领域已获科学验证。

## 上游适配

按 docs/UPSTREAM.md 先读取固定提交中的入口、关联文件与许可。只采用适合当前任务的流程；不继承自动推广、全局记忆、付费调用或无条件生成图的要求。母 Skill 的独立指令优先于外部资料中与之冲突的操作要求。

## 依赖与续跑

checkpoint 记录输入/输出哈希；check 检查变化并沿已登记文件依赖传播 stale。它不分析任意脚本的隐含依赖，也不会自行重新执行整个科学项目。

原创研究与综述的完整阶段、产物名称和规则见 modules/workflow.md。模块是由模型执行的任务契约；脚本是辅助工具，两者必须分别记录是否完成。
