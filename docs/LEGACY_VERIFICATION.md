> 历史记录：以下内容对应旧仓库及原始 23 文件安装包，不是 Cool-Academic 当前构建的测试或校验值。新构建以本仓库 Actions 和 Release 的 SHA256SUMS.txt 为准。

# Research Mother v0.1.0 — 交付与验收记录

日期：2026-09-16。

## GitHub 交付
仓库：https://github.com/siyunhao2025-beep/math-modeling-to-sci-skill
项目目录：https://github.com/siyunhao2025-beep/math-modeling-to-sci-skill/tree/master/research-mother
PR（已合并）：https://github.com/siyunhao2025-beep/math-modeling-to-sci-skill/pull/6
合并提交：3d044caf26d602ba08eddc93397b3923397b82bc

原有建模代码、SKILL.md 和科研配置未改；新增独立 research-mother 子包、三个根目录 CLI 入口，并使原 CI 安装新包 PDF 依赖和编译新脚本。未关闭原测试与审计。

## 交付包
research-mother-v0.1.0.zip，23 个文件，39,598 字节。
SHA-256：006db6744ac0a608ee1cb6bb5145bb368822a1cccacce7baf170ff11c23415cc

文件与 GitHub Actions 构建 ZIP 一致。包内无论文 PDF、字体文件、用户科研数据、凭据或上游大体积源码。README.md 为中文使用说明。

## 实测结果
- 本地母 Skill 回归：48 项通过。测试使用合成夹具，不是科研观测结果。
- 原仓库 CI 通过：https://github.com/siyunhao2025-beep/math-modeling-to-sci-skill/actions/runs/35079227388
- 母 Skill CI 通过：https://github.com/siyunhao2025-beep/math-modeling-to-sci-skill/actions/runs/35079227362
- Skill 校验通过：https://github.com/siyunhao2025-beep/math-modeling-to-sci-skill/actions/runs/35079227422
- 联网检索、五个上游源码获取、构建联合测试通过：https://github.com/siyunhao2025-beep/math-modeling-to-sci-skill/actions/runs/35078970766

修复了 Crossref 游标分页不支持按出版日期排序的 HTTP 400、上游源码包大小上限、子包路径兼容，以及原 CI 缺少 PDF 依赖的问题。

## 五个上游项目
Cangjie、Claude Scholar、Supervisor-Skills、K-Dense scientific-agent-skills、Skill Seekers 已锁定提交并在 GitHub Actions 隔离取回源码；许可和入口见 config/upstream.lock.json 与 docs/UPSTREAM.md。

源码保持隔离，未运行第三方安装器、hooks 或修改全局记忆。Supervisor-Skills 保留其独立 CC BY-NC-SA 4.0 标识；母 Skill 原创文件的 MIT 不覆盖第三方资源。

## 功能与边界
母 Skill 的七个模块负责总控、领域提炼、文献、期刊学习、证据补稿、分析/方法/绘图、写作审查。语义任务由承载 Skill 的模型执行。脚本负责检索、编目、已读卡片编译、契约检查、哈希依赖检查和打包，不自动替代科学研究。

1. GPT 账号原生安装尚未完成，也没有逐项验证五个上游的原生调用。源码下载成功不等于安装成功。
2. Crossref 测试只证明联网响应、解析和记录流程可执行。5 条截断候选在该小样本中没有可用的领域相关论文；不代表找到 5 篇领域新文献。实际使用必须多源检索、相关性筛选和全文核验；领域召回率未验证。
3. 没有接收并读完真实目标期刊的几十篇全文；期刊风格学习和留出验证尚未完成。期刊卡编译器不能把提取到的文本自动标为已读。
4. 领域包是可替换接口、检索词和审查清单，不是已从用户资料完成蒸馏的领域知识库。没有执行用户科学数据分析、生成科研图或实际补写稿件。
5. 不防御性写作：只补比较、方法依据、机制约束、研究定位或纠错；保留真实的重要边界，但不堆通用免责声明，不删掉必要限制。
6. 没有创建定时订阅、后台监控或自动投稿。文风改善、领域知识正确性与发表前景均未由单元测试证明。

## 安装与启动
具有 Skills 入口及权限的账号，可在 Plugins → Skills → Create → Upload from your computer 上传本 ZIP，并以宿主扫描和安装结果为准。官方说明：https://help.openai.com/en/articles/20001066-skills-in-chatgpt

没有 Skills 上传入口时，可以在支持文件与代码的对话中上传 ZIP，要求解压并读取 SKILL.md；这是会话内使用，不等于永久账号安装。

启动语句：
使用 research-mother，加载 example-domain 领域包。读取我上传的资料，先建立证据矩阵和项目状态，再按原创研究或综述路线推进。补稿只增加有实质贡献的证据；不堆防御性文字，不编造结果。期刊风格依据真实全文和留出验证，而不是套通用模板。
