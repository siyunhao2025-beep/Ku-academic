# 最新论文发现、筛选和证据更新

自动检索分为“执行一次刷新”和“已配置的定时刷新”。前者不意味着后台任务已创建。用户明确请求订阅时使用宿主任务能力或经授权的调度器，保存查询、时间窗口、来源和去重状态。

优先用可用的学术连接器、出版社页面及多源检索。Crossref 脚本作为无需账号的元数据后端；它不是全网检索器。OpenAlex、Semantic Scholar、ADS、Scite、Scholar Gateway 等只有实际可用时调用，认证与覆盖按当前官方文档核验，不假称已接入。

检索：同义词组/主题组分开运行；记录完整查询、检索日期、来源、分页数量、截断及失败。按 DOI 规范化合并，题名/作者/年份近似匹配仅标候选，不静默合并。预印本与正式版保留版本关系；复查更正、撤稿和记录更新。

日期：区分 first online、print、indexed、retrieved；年/月精度不补造具体日期。发现新近出版与补捞新近收录是两次不同查询。用最近一段重叠窗口刷新并去重，避免漏掉延迟收录的旧出版记录。元数据排序不代替出版社状态核验。

每条记录分 metadata_only / abstract_only / full_text / project_result。摘要只能支持摘要明确说出的内容；机制、方法细节和争议必须读相应全文。DOI 解析成功不代表引文支持当前句子。

输出：候选列表、纳入/排除理由、证据矩阵、与现稿的关系。只有确有贡献的论文进入 supplementation；其余写“无需修改正文”即可。检索失败与零命中分开报告。

## 跨轮检索的收益账本与停止规则

需要多轮扩展检索时，不能凭“感觉差不多了”停止，也不能用原始命中数制造进展。每轮在 JSON
账本中记录：完整查询、去重后的新记录数、实际纳入证据矩阵的来源数、真正新增或改变矩阵
单元格/争议/缺口的来源数，以及项目范围内仍必须覆盖的缺口。示例：

```json
{
  "rounds": [
    {
      "round": 0,
      "queries": ["topic AND method", "topic AND limitation"],
      "new_deduped_records": 18,
      "admitted_sources": 6,
      "matrix_changing_sources": 5,
      "open_required_gaps": ["target population"]
    }
  ]
}
```

`matrix_changing_sources` 只计入确实改变支持、反驳、限定条件或缺口判断的来源；重复命中、只补
元数据和未读全文的机制性主张不能计入。`open_required_gaps` 只放项目问题范围内的必要覆盖项，
不能为了迫使流程继续而无限扩张范围。

运行前由项目明确三个工程控制量：最大轮数 `budget`、允许连续低收益轮数 `patience`、每轮最低
矩阵变化来源数 `min_new`。它们不是科学充分性阈值，因此工具不提供伪装成通用标准的默认值：

```bash
python scripts/research.py search-progress --ledger audit/search-rounds.json \
  --budget 6 --patience 2 --min-new 2 --out audit/search-progress.json
```

判定语义：

- `CONTINUE`：尚未触发预算或连续低收益停止；
- `CONTINUE_FOR_COVERAGE`：收益已低，但仍有必需覆盖缺口；
- `STOP_SATURATED`：连续低收益达到项目设定值且没有必需缺口；
- `STOP_BUDGET`：达到预算且没有必需缺口；
- `AUTHOR_ACTION_REQUIRED`：达到预算但仍有必需缺口，需缩小问题、增加资源或接受覆盖限制。

任何停止结果都必须报告每轮 `matrix_changing_sources` 轨迹和薄弱区域，并明确“达到工程停止条件”
不等于“穷尽文献”。该工具只控制检索成本，不替代全文阅读、引用身份/支持双检或 Gate 2。
