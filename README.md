# 🧠 AI智能选股顾问系统 v2

## 系统概述

基于多AI智能体协作的A股智能选股系统，融合专业量化交易的风控体系、仓位管理、组合优化，
并具备完整的历史回测验证能力。

## v2 新增功能

| 功能 | 说明 |
|------|------|
| ✅ 分笔T+1跟踪 | 加仓当天新增份额不可卖出（FIFO） |
| ✅ 科创板/创业板20%涨跌停 | 自动识别300/688代码 |
| ✅ 沪深300基准对比 | Alpha/Beta/超额收益 |
| ✅ 多策略对比 | 一键对比三策略+叠加净值曲线 |
| ✅ 大盘择时过滤器 | 牛/熊/震荡判定，动态调节仓位系数 |
| ✅ 数据质量验证 | 缺失/异常/复权跳变自动检查 |
| ✅ 交易明细导出 | CSV下载+界面内展示 |
| ✅ AI复盘分析 | 回测后AI分析优缺点和改进建议 |
| ✅ 配置持久化 | session_state保持参数不丢失 |
| ✅ 止损类型标记 | 记录每笔卖出的止损触发原因 |

## 核心特性

### 1. AI智能体团队
- 技术面分析师 / 量价分析师 / 风控官 / 首席策略师
- 每个建议附带0-100%置信度
- AI回测复盘分析

### 2. 多因子量化选股
- 趋势因子 / 动量因子 / MACD因子 / RSI因子 / 成交量因子
- 三套策略: 多因子 / 动量 / 价值成长

### 3. 专业风控体系
- 4层止损: 硬止损 / 跟踪止损 / 时间止损 / 波动率止损
- 账户级最大回撤红线（自动停止交易）
- 大盘择时过滤（牛市满仓/震荡半仓/熊市空仓）

### 4. 完整回测引擎
- 分笔T+1（加仓当天份额不可卖）
- 科创板/创业板20%涨跌停
- 佣金(万2.5) + 印花税(千1) + 滑点
- 蒙特卡洛模拟 + Walk-Forward

### 5. 组合优化
- Markowitz均值-方差 / 最小方差 / 风险平价
- 相关性矩阵 + 高相关警告

### 6. 绩效分析
- 夏普/Sortino/Calmar/Alpha/Beta
- 月度收益热力图
- 交易收益分布图
- 沪深300基准对比

## 快速开始

```bash
pip install -r requirements.txt
# 编辑 config.py 填入 DeepSeek API Key
streamlit run app.py
```

## 项目结构

```
ai_stock_advisor/           4420 lines
├── app.py                  主界面 (698行)
├── config.py               配置
├── core/
│   ├── data_fetcher.py     数据获取
│   ├── data_validator.py   数据质量验证 [NEW]
│   ├── indicators.py       技术指标
│   ├── market_filter.py    大盘择时 [NEW]
│   ├── risk_manager.py     风控系统
│   ├── position_manager.py 仓位管理
│   ├── portfolio_optimizer.py 组合优化
│   └── performance.py      绩效指标
├── backtest/
│   ├── broker.py           模拟券商v2 (分笔T+1)
│   ├── engine.py           回测引擎 (基准对比)
│   └── reporter.py         图表生成
├── strategies/
│   ├── base_strategy.py    策略基类
│   ├── multi_factor.py     多因子策略
│   ├── momentum.py         动量策略
│   └── value_growth.py     价值成长策略
└── agents/
    ├── ai_advisor.py       AI分析引擎
    └── post_analysis.py    AI复盘 [NEW]
```

## ⚠️ 风险提示

本系统仅供学习研究使用，AI建议需经回测验证后方可参考。投资有风险，入市需谨慎。
