"""
AI复盘分析模块
回测结束后让AI分析策略优缺点、亏损原因、改进建议
"""
import json
import config


def _call_deepseek(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=3000,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI调用失败: {str(e)}"


def analyze_backtest_result(metrics: dict, strategy_name: str,
                            trade_summary: dict = None,
                            broker_summary: dict = None) -> str:
    """
    AI复盘回测结果
    
    Args:
        metrics: 回测绩效指标
        strategy_name: 策略名称
        trade_summary: 交易统计
        broker_summary: 券商摘要
    
    Returns:
        AI分析文本
    """
    system_prompt = """你是一位资深量化策略研究员，负责复盘策略回测结果。
请基于提供的绩效指标，给出专业、具体、有建设性的分析：

1. 策略整体表现评价（用一句话概括好还是不好）
2. 主要优点（2-3条，基于数据）
3. 核心问题（2-3条，基于数据）
4. 亏损原因分析（如果有亏损交易）
5. 具体改进建议（3-5条，可操作的）
6. 风险提示

要求：直接给出分析，不要说"以下是分析"之类的套话。分析必须引用具体数据。"""

    data = {
        '策略名称': strategy_name,
        '总收益率': f"{metrics.get('total_return', 0):.2%}",
        '年化收益率': f"{metrics.get('annual_return', 0):.2%}",
        '最大回撤': f"{metrics.get('max_drawdown', 0):.2%}",
        '夏普比率': f"{metrics.get('sharpe_ratio', 0):.3f}",
        'Calmar比率': f"{metrics.get('calmar_ratio', 0):.3f}",
        '年化波动率': f"{metrics.get('annual_volatility', 0):.2%}",
        '最佳单日': f"{metrics.get('best_day', 0):.2%}",
        '最差单日': f"{metrics.get('worst_day', 0):.2%}",
        '交易天数': metrics.get('trading_days', 0),
    }
    
    if trade_summary:
        data.update({
            '总交易次数': trade_summary.get('total_trades', 0),
            '胜率': f"{trade_summary.get('win_rate', 0):.1%}",
            '盈亏比': f"{trade_summary.get('profit_factor', 0):.2f}",
            '平均持仓天数': f"{trade_summary.get('avg_hold_days', 0):.1f}",
            '最大连续亏损': trade_summary.get('max_consecutive_losses', 0),
            '期望收益': f"{trade_summary.get('expectancy', 0):.2%}",
        })
    
    if broker_summary:
        data.update({
            '总佣金': f"¥{broker_summary.get('total_commissions', 0):,.0f}",
            '总印花税': f"¥{broker_summary.get('total_stamp_tax', 0):,.0f}",
        })
    
    # 基准对比
    benchmark = metrics.get('benchmark')
    if benchmark:
        data.update({
            'Alpha': f"{benchmark.get('alpha', 0):.2%}",
            'Beta': f"{benchmark.get('beta', 0):.3f}",
            '超额收益': f"{benchmark.get('excess_return', 0):.2%}",
        })
    
    user_prompt = f"请复盘以下策略回测结果：\n\n{json.dumps(data, ensure_ascii=False, indent=2)}"
    
    return _call_deepseek(system_prompt, user_prompt)


def analyze_losing_trades(losing_trades: list) -> str:
    """分析亏损交易的共同特征"""
    if not losing_trades:
        return "无亏损交易"
    
    system_prompt = """你是量化分析师，分析一批亏损交易的共同特征和规律。
找出：1. 亏损集中在什么时间段？ 2. 平均持仓多久？ 3. 止损是否有效？ 4. 有什么可优化的？"""
    
    # 取前20笔最大亏损
    sorted_trades = sorted(losing_trades, key=lambda x: x.get('pnl_pct', 0))[:20]
    
    data = []
    for t in sorted_trades:
        data.append({
            'code': t.get('code', ''),
            'pnl%': f"{t.get('pnl_pct', 0):.2%}",
            'hold_days': t.get('hold_days', 0),
            'stop_type': t.get('stop_type', '策略卖出'),
        })
    
    user_prompt = f"分析以下亏损交易：\n{json.dumps(data, ensure_ascii=False, indent=2)}"
    return _call_deepseek(system_prompt, user_prompt)
