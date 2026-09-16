# 从下载到第一次任务

[返回首页](../README.md) · [场景提示词](USE_CASES.md) · [常见问题](FAQ.md)

## 1. 先选使用方式

| 方式 | 需要准备 | 能做什么 |
|---|---|---|
| ChatGPT + GitHub | 在当前会话授权 GitHub 读取本仓库 | 实际读取 Skill 后，按上传资料完成任务；无需先安装本地环境 |
| ChatGPT 原生 Skills | 账号有 Skills 上传入口和权限 | 上传轻量 ZIP，经扫描并安装后调用 |
| 对话上传 ZIP | 当前会话支持上传、解压与读取文件 | 会话内读取入口和模块；不等于永久安装 |
| 本地 Python + AI 助手 | Python 3.10+，AI 助手按需读取本地文件 | 执行检索、PDF 编目、依赖检查；模型负责阅读、分析和写作 |

## 2. 下载哪个文件？

打开 [Releases](https://github.com/siyunhao2025-beep/Ku-academic/releases/latest)，在 Assets 中下载 **Ku-academic-v0.1.0-skill.zip**。同时提供 SHA256SUMS.txt，供核验下载文件。此 ZIP 内应只有一个 research-mother 顶层目录，包含 SKILL.md、modules、domains、scripts 和 docs。

GitHub 的 Code → Download ZIP 或 Release 中的 Source code 是完整仓库源码，更适合开发者。它与可上传的 Skill 包不是同一文件，校验值也不同。

## 3. ChatGPT 安装或会话调用

具备入口时：Plugins → Skills → Create → Upload from your computer → 选择 ZIP → 阅读扫描结果 → 完成安装。不要只上传 SKILL.md，配套模块也必须可读。

官方文档目前说明 Skills 面向符合条件的 Business、Enterprise、Healthcare 和 Edu 用户，并受工作区设置和产品可用性影响。不要假设所有个人账号都有上传入口。没有入口就使用 GitHub 读取或会话上传方式，而不是寻找不存在的按钮。说明核验于 2026-09-16：[OpenAI 官方文档](https://help.openai.com/en/articles/20001066-skills-in-chatgpt)。

GitHub 方式可复制：

```text
@GitHub 读取 siyunhao2025-beep/Ku-academic 根目录 SKILL.md，
再读取 modules/workflow.md。根据我的任务加载相关模块，不要一次加载全部上游仓库。
使用 research-mother，加载 space-weather-mlt。
本次任务：根据附件整理研究问题、证据矩阵和论文框架。
先报告实际读到的文件和缺失材料，再执行能够完成的步骤。
```

会话上传方式可复制：

```text
解压我上传的 Ku-academic Skill ZIP，读取 research-mother/SKILL.md、
modules/workflow.md 和当前任务需要的模块，按里面的流程处理我的研究资料。
这是会话内读取，不要报告为已永久安装。不要执行上游安装脚本。
```

## 4. 第一次准备哪些研究材料？

准备研究目标、已取得的文献全文、已有稿件、实际代码和结果。没有完成实验时，也可以先做检索、研究设计或框架，但不能写出不存在的 Results。

原始数据和未发表内容应上传到你认可的私有会话或保存在本地私有项目中，**不要上传到这个公开仓库**。检查平台的数据使用设置和单位的资料政策。

首次可先要求“只完成证据矩阵和框架”。确认资料和论证对应后，再推进后续阶段；不必一次处理几十篇 PDF 和完整稿件。

## 5. Windows 本地工具

安装 Python 3.10 或更高版本，打开仓库所在文件夹。不会用 Git 时，可从 Code → Download ZIP 下载并解压源码。确保当前目录能看到 requirements.txt 和 scripts。

双击 START_WINDOWS.bat，会创建 .venv、安装本项目依赖、运行 doctor 和首次离线示例；不会安装五个上游项目，不会上传论文。也可以在 PowerShell 手动执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/research.py doctor
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/quickstart.py runs/first-demo
```

python 不存在但 py 可用时，第一行换成 py -3 -m venv .venv。后续均直接调用虚拟环境 Python，不需要修改 PowerShell 的执行策略。

macOS / Linux 把 .\.venv\Scripts\python.exe 换成 .venv/bin/python，创建环境一般使用 python3 -m venv .venv。

离线示例成功时会出现 INSTALLATION_DEMO.md、project.json 和项目子目录，状态中包含 demonstration_only。示例只验证目录与依赖记录，不产生观测数据或论文结论。重复指定已有目录会拒绝覆盖；换一个目录即可。

## 6. 真正建立项目

以下命令的 python 指你已准备好的虚拟环境 Python：

```bash
python scripts/research.py init runs/my-study --kind original
python scripts/research.py init runs/my-review --kind review
```

两个目录互相独立。填写各项目 domain.json 的仪器版本、事件窗口、基线、分箱、地方时和不确定度设置，再交给模型读取 inputs 中的材料。项目默认 needs_inputs 是正常状态，不表示初始化失败。

联网检索示例（日期需改为实际窗口）：

```bash
python scripts/research.py search --query "geomagnetic storm SABER temperature" --since 2026-08-17 --until 2026-09-16 --pages 2 --rows 50 --out runs/search-20260916
```

同一窗口的延迟收录补捞可使用 --mode indexed 并换新输出目录。search.json 中的 records 是待筛选元数据，不是已经读完、确定相关的新论文。status=error 要看错误日志；truncated=true 表示只返回了受限候选。

PDF 下载、导入和阅读卡格式见 [文件接口](CONTRACTS.md)。全文阅读与期刊风格归纳需要模型实际执行，不能仅跑提取脚本。

## 7. 更新和维护

源码方式可在保存自己修改后 git pull。已安装或上传到会话的副本不会因 GitHub 更新自动替换，应重新下载并按宿主界面更新，保留旧版项目数据。

开发者验证与构建：

```bash
python -m unittest discover -s tests -v
python scripts/check_repository.py
python scripts/build_distribution.py --out dist
```

打包输出不能覆盖已有发行文件；需要重新构建时换输出目录。分发包只包含 config/distribution-files.json 列出的源码和文档，不包括用户研究目录、上游 ZIP 或 PDF。
