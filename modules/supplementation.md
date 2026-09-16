# 证据贡献驱动的补稿，而非防御性写作

先读取当前完整稿件、结果与引用，找出真正影响论点的位置。不要见到新文献就加一句引用，更不要把审稿清单批量贴成 limitations。

只接受五类贡献：comparison（有条件可比的定量/定性对照）；method_basis（实际采用方法的依据）；mechanism_constraint（区分或约束机制）；context（确实改变问题定位）；correction（纠正事实/引用/解释）。每条说明“不补它会缺少哪一步论证”，并可得出不补稿的结论。

修订记录包括 id、location、before、after、contribution、reason、evidence_ids、claim_level、decision、semantic_review。接受前逐条核对源文页段与主张是否对应，比较范围/坐标/时间/采样是否匹配，以及是否悄悄加强了因果。

非防御性不等于删掉真实限制。优先顺序：修复分析或增加真正有用的对照；精准约束那一个受影响的主张；必要的实质限制只在最相关位置说明一次。不要连续堆 however、cannot rule out、further studies are needed 等通用句。

例如只有温度与地磁指数：温度升降按真实数值直述；机制解释根据文献与现有证据限定为 consistent with / suggests。不要把所有观测都改成 may，不要声称风场已被测量，不要用“不能证明任何东西”否定明确观察。

输出可审查的修订建议与差异，不自动覆盖原稿。经授权应用修订时保留原版，重验数字、单位、图号、引用和摘要。程序 contract_pass 只说明字段和证据状态符合约定，不代替语义核验。
