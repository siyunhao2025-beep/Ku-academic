# 文件接口与可执行示例

下列值均为结构示例，不是真实论文或观测。把自己的 PDF 与 manifest 放在私有工作目录中；不要将它们提交到公开仓库。

## PDF 编目
manifest.json 是数组。path 可为绝对路径，或相对 manifest 目录的路径；Windows JSON 反斜杠需写成双反斜杠，也可以使用正斜杠。
```json
[{"id":"paper-A","doi":"","path":"paper-A.pdf","journal":"TARGET JOURNAL","article_type":"research-article","author_group":"team-A","split":"train"}]
```
```bash
python scripts/corpus.py ingest private/manifest.json private/extracted-v1
```
输出 corpus.json 和逐页 JSON。full_text_read/visual_checked/metadata_verified 都默认 false，必须完成真实检查后才能在阅读卡中设置 true。

## 授权 PDF 下载
```json
[{"id":"paper-A","url":"https://AUTHORIZED-HOST/paper.pdf","authorization":"open_access_verified","access_basis":"记录已核验的开放获取来源和日期"}]
```
```bash
python scripts/corpus.py download private/downloads.json private/download-v1 --allow-host AUTHORIZED-HOST
```
重定向目的主机也必须明确允许。脚本拒绝私网地址、非 HTTPS、伪 PDF、超大文件；不会绕过登录、验证码或付费墙。access_basis 是用户/代理核验记录，不是程序自动获得的版权许可。

## 期刊阅读卡
```json
[{"id":"paper-A","journal":"TARGET JOURNAL","article_type":"research-article","author_group":"team-A","split":"train","source":"授权全文来源","sha256":"真实文件哈希","metadata_verified":true,"full_text_read":true,"visual_checked":true,"patterns":[{"id":"quantified-result-first","description":"在对应结果段先量化现象，再讨论解释","locator":"p.4, Results, paragraph 2"}]}]
```
必须有足够训练卡、至少三个独立作者组和一个完全留出的作者组。默认 minimum=20 可配置，只是取样下限，不保证风格估计充分。训练/留出作者组不能交叉。编译后仍需语义与留出评测，不能直接声称 validated。

## 补稿与证据
changes.json 和 evidence.json 都是数组。
```json
[{"id":"C1","location":"Discussion paragraph 2","before":"原句","after":"有证据支持的新句","contribution":"comparison","reason":"明确与可比条件下前人结果的异同","evidence_ids":["E1"],"claim_level":"inference","decision":"accept","semantic_review":"passed"}]
```
```json
[{"id":"E1","source":"已核验文献或本项目结果路径","locator":"p.5, Fig.3 或 run ID","evidence_level":"full_text"}]
```
semantic_review=passed 必须对应真实核查记录，不应由脚本自动填上。meta-only 支持文献身份，不支持物理结果或机制句子。

## 断点与失效
```bash
python scripts/research.py checkpoint runs/my-study analysis --inputs inputs/data.csv domain.json --outputs analysis/result.csv
python scripts/research.py check runs/my-study
```
原始文件、参数或结果发生变化会标 stale，并传播到消费这些输出的后续阶段。检查的是已登记依赖；未登记依赖不能被自动发现，科学逻辑是否正确仍需审查。
