"""
AI顾问引擎
调用DeepSeek API进行智能分析，附带置信度评估
"""
import json
from typing import Dict, List, Optional
import config


def _call_deepseek(system_prompt: str, user_prompt: str, 
                   temperature: float = 0.3) -> str:
    """调用DeepSeek API"""
    try:
        from openai import OpenAI
        
        client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
        )
        
        response = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=2000,
        )
        
        return response.choices[0].message.content
    
    except Exception as e:
        return f"AI调用失败: {str(e)}"


def analyze_stock(code: str, name: str, indicators: dict,
                  signals: dict, recent_data: dict = None) -> dict:
    """
    AI综合分析单只股票
    
    Args:
        code: 股票代码
        name: 股票名称
        indicators: 技术指标数据
        signals: 技术信号
        recent_data: 近期行情摘要
    
    Returns:
        {
            'summary': str,
            'recommendation': str,    # 买入/持有/卖出/观望
            'confidence': float,       # 置信度 0-1
            'reasons': list,
            'risks': list,
            'target_price': dict,      # {support, resistance}
            'position_advice': str,
        }
    """
    system_prompt = """你是一位专业的A股证券分析师。你需要基于提供的技术指标和信号数据，给出专业、客观的分析。

要求：
1. 必须给出明确的操作建议：买入/持有/卖出/观望
2. 必须给出置信度（0-100%），基于信号一致性和数据充分性
3. 必须指出主要风险点
4. 给出支撑位和压力位估算
5. 给出仓位建议

你的回复必须严格按照以下JSON格式，不要有其他内容：
{
    "recommendation": "买入/持有/卖出/观望",
    "confidence": 65,
    "summary": "简要分析总结",
    "reasons": ["理由1", "理由2"],
    "risks": ["风险1", "风险2"],
    "support_price": 0,
    "resistance_price": 0,
    "position_advice": "建议仓位说明"
}"""
    
    user_prompt = f"""请分析以下股票：

股票：{name}（{code}）

技术指标：
{json.dumps(indicators, ensure_ascii=False, indent=2, default=str)}

技术信号：
{json.dumps(signals, ensure_ascii=False, indent=2, default=str)}

{f"近期行情：{json.dumps(recent_data, ensure_ascii=False, default=str)}" if recent_data else ""}

请给出专业分析和操作建议。"""
    
    response = _call_deepseek(system_prompt, user_prompt)
    
    # 解析JSON
    try:
        # 尝试从回复中提取JSON
        if '```json' in response:
            json_str = response.split('```json')[1].split('```')[0]
        elif '{' in response:
            start = response.index('{')
            end = response.rindex('}') + 1
            json_str = response[start:end]
        else:
            json_str = response
        
        result = json.loads(json_str)
        result['confidence'] = result.get('confidence', 50) / 100  # 转为0-1
        result['raw_response'] = response
        return result
    
    except (json.JSONDecodeError, ValueError):
        return {
            'recommendation': '观望',
            'confidence': 0,
            'summary': response[:500],
            'reasons': ['AI分析解析失败'],
            'risks': ['数据不完整'],
            'raw_response': response,
        }


def multi_agent_analysis(code: str, name: str, indicators: dict,
                         signals: dict) -> dict:
    """
    多智能体协作分析
    4个角色独立分析，最后由首席策略师综合
    
    角色：
    1. 基本面分析师
    2. 技术面分析师
    3. 风控官
    4. 首席策略师（综合）
    """
    
    # --- Agent 1: 技术面分析师 ---
    tech_prompt = """你是技术面分析师，只关注价格走势和技术指标。
分析K线形态、均线系统、MACD、RSI、KDJ、布林带等，给出技术面评估。
用JSON回复：{"rating": "看多/中性/看空", "confidence": 0-100, "analysis": "分析", "key_levels": {"support": 0, "resistance": 0}}"""
    
    tech_result = _call_deepseek(tech_prompt, 
        f"股票{name}({code})技术指标：\n{json.dumps(indicators, ensure_ascii=False, default=str)}\n信号：{json.dumps(signals, ensure_ascii=False, default=str)}")
    
    # --- Agent 2: 量价分析师 ---
    vol_prompt = """你是量价分析师，专注成交量与价格的关系。
分析量价配合、资金流向信号、成交量异动等。
用JSON回复：{"rating": "看多/中性/看空", "confidence": 0-100, "analysis": "分析"}"""
    
    vol_data = {k: v for k, v in indicators.items() if any(w in k for w in ['vol', 'obv', 'amount', 'turnover'])}
    vol_data['close'] = indicators.get('close', 0)
    vol_result = _call_deepseek(vol_prompt,
        f"股票{name}({code})量价数据：\n{json.dumps(vol_data, ensure_ascii=False, default=str)}")
    
    # --- Agent 3: 风控官 ---
    risk_prompt = """你是风控官，专注识别风险。
评估波动率、回撤风险、技术面风险信号、是否处于超买区域等。
用JSON回复：{"risk_level": "低/中/高", "risks": ["风险1"], "max_position": "建议最大仓位百分比", "analysis": "分析"}"""
    
    risk_result = _call_deepseek(risk_prompt,
        f"股票{name}({code})数据：\n{json.dumps(indicators, ensure_ascii=False, default=str)}")
    
    # --- Agent 4: 首席策略师综合 ---
    chief_prompt = """你是首席策略师。基于技术面分析师、量价分析师和风控官的意见，给出最终综合建议。
注意：各分析师的观点可能有分歧，你需要权衡后给出结论。

必须严格用JSON回复：
{
    "recommendation": "买入/持有/卖出/观望",
    "confidence": 0-100,
    "summary": "综合分析摘要",
    "team_consensus": "一致/分歧",
    "dissenting_views": "不同意见说明",
    "action_plan": "具体操作计划",
    "position_size": "建议仓位比例",
    "stop_loss": "建议止损位",
    "take_profit": "建议止盈位"
}"""
    
    chief_input = f"""股票：{name}({code})

技术面分析师意见：
{tech_result}

量价分析师意见：
{vol_result}

风控官意见：
{risk_result}

请综合以上意见，给出最终建议。"""
    
    chief_result = _call_deepseek(chief_prompt, chief_input, temperature=0.2)
    
    # 解析最终结果
    try:
        if '{' in chief_result:
            start = chief_result.index('{')
            end = chief_result.rindex('}') + 1
            final = json.loads(chief_result[start:end])
        else:
            final = {'recommendation': '观望', 'confidence': 50, 'summary': chief_result}
    except (json.JSONDecodeError, ValueError):
        final = {'recommendation': '观望', 'confidence': 50, 'summary': chief_result[:500]}
    
    final['confidence'] = final.get('confidence', 50) / 100
    final['agent_reports'] = {
        'technical': tech_result,
        'volume_price': vol_result,
        'risk': risk_result,
    }
    
    return final


def batch_screening(stock_list: List[dict], criteria: str = None) -> str:
    """
    AI批量初筛
    让AI根据条件从股票列表中筛选候选
    
    Args:
        stock_list: [{'code': '600519', 'name': '贵州茅台', 'indicators': {...}}, ...]
        criteria: 筛选条件描述
    """
    if not criteria:
        criteria = "选出技术面健康、趋势向上、风险可控的股票"
    
    system_prompt = """你是选股助手。从候选股票列表中，根据技术指标筛选最优股票。
回复JSON格式：{"selected": [{"code": "代码", "reason": "入选理由"}], "excluded_reason": "排除说明"}"""
    
    # 只取核心指标减少token
    simplified = []
    for s in stock_list[:20]:  # 限制数量避免超token
        simplified.append({
            'code': s['code'],
            'name': s.get('name', ''),
            'close': s.get('indicators', {}).get('close', 0),
            'ma_trend': 'up' if s.get('indicators', {}).get('ma5', 0) > s.get('indicators', {}).get('ma20', 0) else 'down',
            'rsi': s.get('indicators', {}).get('rsi12', 50),
            'macd': 'positive' if s.get('indicators', {}).get('macd_hist', 0) > 0 else 'negative',
            'momentum_20': s.get('indicators', {}).get('momentum_20', 0),
        })
    
    user_prompt = f"""筛选条件：{criteria}

候选股票：
{json.dumps(simplified, ensure_ascii=False, indent=2)}

请筛选并说明理由。"""
    
    return _call_deepseek(system_prompt, user_prompt)
