# 数据、代码与复现声明

本模块用于 P6 投稿前检查。目标不是生成一段看似合规的套话，而是让每个可用性声明都能回答：材料在哪里、如何取得、受什么条件约束，以及谁在什么时间实际检查过入口。

## 四种合法路线

数据与代码分别选择一条路线，不能用数据的链接替代码过关，也不能把“仓库”两个字当成定位信息。

| route | 必须记录 | 不通过示例 |
|---|---|---|
| `public` | 具体 URL/DOI/accession、持久标识、许可或访问条件、未登录访问检查；公开代码另需 release/tag/commit/归档版本 | “已上传到公共仓库”但没有记录号或链接 |
| `restricted` | 不能公开的具体原因、可执行的委员会/申请页/联系人路径、审批或协议条件、路径检查记录 | 只有 “available upon reasonable request” |
| `in_manuscript` | 正文、Source Data、表、图或补充材料的精确位置 | 只写“见附件” |
| `not_applicable` | 与研究设计相符的具体理由 | `N/A`、`none`、`不适用` |

隐私、伦理、同意、法律和第三方许可可以构成合理限制；限制不会自动构成失败。失败的是没有解释限制，或没有给出真实可走的获取路径。不得上传没有再分发权的数据、全文或代码资产。

## 执行

先建立中性清单，再由作者或获授权人员填入真实信息：

```bash
python scripts/availability.py init runs/my-study/availability-manifest.json
python scripts/availability.py check runs/my-study/availability-manifest.json \
  --out runs/my-study/audit/availability.json
```

公开定位和受限申请入口应在未登录状态下实际检查；`planned`、`not_checked` 或“我记得能打开”都不算证据。检查记录包含带时区的时间和执行者。双盲评审使用私有 reviewer link 时，也要按目标期刊规则检查匿名性、权限和失效时间。

`audit/availability.json` 为 `PASS` 只表示所填合同完整并记录了检查；它不证明材料合法可分享、不证明文件完整，也不证明研究能复现。

## “完全可复现”的主张上限

材料有链接、脚本能运行、作者本人能重跑，分别都不能推出“完全可复现”。只有在非作者执行者从声明的入口取得材料、按说明完成独立复跑，并留下执行者、带时区时间和证据定位时，清单才允许 `claims_fully_reproducible: true`。否则改写为可核验的较窄事实，例如“数据和版本化代码已按上述位置提供”。

## 与 P6 的关系

- 当前目标期刊的官方作者指南决定哪些声明必须出现、放在哪里；本地合同不替代官方规则。
- 声明中的 DOI、accession、release 和许可仍需人工核验；脚本只验证已记录字段。
- P6 阶段门读取 `audit/availability.json`。缺失、`BLOCKED` 或仍有 blocker 时，不得输出 `READY_FOR_HUMAN_SUBMISSION_CHECK`。
- 数据、代码或复跑证据变化时，按 `modules/change-management.md` 向 Methods、结果、图表、补充材料和投稿清单传播。
