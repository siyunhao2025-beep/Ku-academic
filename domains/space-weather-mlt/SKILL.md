---
name: space-weather-mlt
description: Apply the Research Mother workflow to geomagnetic-storm responses of mesospheric and lower-thermospheric temperature; audit SABER sampling, geographic/magnetic coordinates, local time, baselines, temporal dependence and causal interpretation without fixing any event-specific values.
license: MIT
metadata:
  version: "0.1.0"
---
# 空间天气与 MLT 温度响应领域包

读取同目录 domain.json。这里提供接口、检索词和任务审查项；尚非从用户期刊全文完成提炼的领域知识库。

将 MLT（mesosphere and lower thermosphere）与磁地方时 magnetic local time 的变量命名分开；LST、UT、AACGM 纬度分别标记。记录坐标转换库、模型版本、高度、日期、返回状态与无效区，不将失效值零填充或当真实低纬观测。

SABER：核实真实产品版本、仪器质量标记、沿轨采样、升降轨标签含义、地方时漂移、纬度/高度覆盖及检索误差适用范围。不要从旧项目继承固定精度上限、tpAD 含义或静日值；先核验该产品资料与代码。

ΔT：公式、基线、窗口、分箱、平滑与节点分离须来自当前项目。记录基线误差与样本依赖；样本 SD 不是磁暴归因的充分依据。识别采样/潮汐/季节与背景变化可能带来的混淆，用匹配采样和实际对照约束，而非机械添加限制句。

机制：温度数据可支持明确观测描述。绝热升降温、平流、焦耳加热、粒子沉降、辐射和波耦合等解释分别检查可获得证据；缺风场/电导率时不得直接宣称测得相应动力/加热项。列出可区分机制的观测或分析，不预设唯一原因。

Dst 极小、主相边界、冲击时刻和指数时间分辨率分别核验；不把 Dst 最小当所有高度温度最大时刻。延迟分析定义零时刻、搜索窗口、多重比较、平滑影响和不确定度。

实际出图/计算由项目数据决定，本包不包含预置磁暴结果。候选 JGR/GRL/Space Weather 仅是研究相关的期刊名称，不包含未核验的格式规则。
