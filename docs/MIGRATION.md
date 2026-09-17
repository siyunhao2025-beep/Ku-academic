# Cool-Academic 独立仓库迁移记录

日期：2026-09-16。

来源：siyunhao2025-beep/math-modeling-to-sci-skill 中的 research-mother/。
固定源提交：3d044caf26d602ba08eddc93397b3923397b82bc。
原始安装包：research-mother-v0.1.0.zip，23 个文件，39,598 字节。
原始包 SHA-256：006db6744ac0a608ee1cb6bb5145bb368822a1cccacce7baf170ff11c23415cc。

## 迁入范围

母 Skill、七个模块、领域包接口、上游版本清单、三个辅助脚本、48 项原始测试、许可与接口文档迁到新仓库根目录。调用名保留 research-mother，原建模仓库不删除、不修改，也不复制与本项目无关的旧建模流水线。

本仓库新增公开首页、安装教程、场景提示词、架构与 FAQ、离线示例、Windows 启动器、确定性分发打包器和文档/分发测试。原始 README 被新首页替代，忽略规则补充虚拟环境及常见科研数据。五个上游的完整源码仍按需独立获取，不重新打进轻量包。

## 怎样核查来源？

config/migration-source.json 保存原始 23 文件中的 21 个逐文件 SHA-256。一次性导入器验证固定提交里的对应文件，再只创建缺失文件；明确允许首页和忽略规则由新仓库维护，不覆盖已经修改过的代码。执行记录生成在 docs/MIGRATION_IMPORT.json。

**少了哪两个，为什么。** 旧包里有一个绑定具体研究领域的领域包（两个文件）。本仓库不继承它，改为提供中性模板 `domains/example-domain`，使项目不绑定任何单一研究方向。因此这两个文件**从哈希表里移除**，而不是改个路径继续挂着它们从未有过的哈希。该决定记录在 migration-source.json 的 `not_carried_forward` 字段里，说明理由而不复述旧领域内容。

docs/LEGACY_VERIFICATION.md 是旧仓库验收记录，仅用于追溯，不充当新仓库的测试结论。当前测试以 Cool-Academic Actions 为准，发行包校验值以 Release 附件 SHA256SUMS.txt 为准。新包增加文档和工具，校验值不应与旧包相同。

## 本次并未宣称新增的成果

没有因搬迁而完成 GPT 账号安装、真实期刊语料学习、领域文献召回评估或用户科学数据分析。旧版证据边界保持不变。来源导入工作流是一次性搬迁工具；常规安装和使用不需要重新运行它。
