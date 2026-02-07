"""
工具函数模块
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import json
import hashlib


def ensure_dir(path):
    """确保目录存在"""
    os.makedirs(path, exist_ok=True)
    return path


def format_pct(value, decimals=2):
    """格式化百分比"""
    if pd.isna(value):
        return "N/A"
    return f"{value * 100:.{decimals}f}%"


def format_money(value):
    """格式化金额"""
    if abs(value) >= 1e8:
        return f"{value / 1e8:.2f}亿"
    elif abs(value) >= 1e4:
        return f"{value / 1e4:.2f}万"
    return f"{value:.2f}"


def stock_code_to_symbol(code: str) -> str:
    """
    股票代码标准化：纯数字 -> 带前缀
    600xxx -> sh600xxx (上海)
    000xxx/001xxx/002xxx/003xxx -> sz000xxx (深圳)
    300xxx -> sz300xxx (创业板)
    688xxx -> sh688xxx (科创板)
    """
    code = str(code).strip().zfill(6)
    if code.startswith(('sh', 'sz', 'SH', 'SZ')):
        return code.lower()
    if code.startswith(('6', '9')):
        return f"sh{code}"
    return f"sz{code}"


def symbol_to_code(symbol: str) -> str:
    """带前缀代码 -> 纯数字"""
    return symbol.replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '')


def is_trading_day(date: datetime) -> bool:
    """简单判断是否为交易日（周末排除，节假日需额外处理）"""
    return date.weekday() < 5


def get_trading_days(start_date: str, end_date: str) -> list:
    """获取交易日列表（简化版，仅排除周末）"""
    dates = pd.date_range(start=start_date, end=end_date, freq='B')
    return [d.strftime('%Y-%m-%d') for d in dates]


def calc_annual_return(total_return: float, days: int) -> float:
    """计算年化收益率"""
    if days <= 0 or total_return <= -1:
        return 0
    return (1 + total_return) ** (252 / days) - 1


def calc_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.03) -> float:
    """计算夏普比率"""
    if returns.std() == 0 or len(returns) < 2:
        return 0
    daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1
    excess = returns - daily_rf
    return np.sqrt(252) * excess.mean() / excess.std()


def calc_sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.03) -> float:
    """计算索提诺比率（只考虑下行风险）"""
    daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1
    excess = returns - daily_rf
    downside = returns[returns < 0]
    if len(downside) < 2 or downside.std() == 0:
        return 0
    return np.sqrt(252) * excess.mean() / downside.std()


def calc_max_drawdown(equity_curve: pd.Series) -> tuple:
    """
    计算最大回撤
    返回: (最大回撤比例, 开始日期, 结束日期, 持续天数)
    """
    peak = equity_curve.expanding(min_periods=1).max()
    drawdown = (equity_curve - peak) / peak
    max_dd = drawdown.min()
    
    if max_dd == 0:
        return 0, None, None, 0
    
    end_idx = drawdown.idxmin()
    peak_idx = equity_curve[:end_idx].idxmax()
    duration = (pd.Timestamp(end_idx) - pd.Timestamp(peak_idx)).days
    
    return abs(max_dd), peak_idx, end_idx, duration


def calc_calmar_ratio(annual_return: float, max_drawdown: float) -> float:
    """计算Calmar比率"""
    if max_drawdown == 0:
        return 0
    return annual_return / max_drawdown


def calc_win_rate(trades: list) -> dict:
    """
    计算交易统计
    trades: [{'pnl': float, 'pnl_pct': float, 'hold_days': int}, ...]
    """
    if not trades:
        return {'win_rate': 0, 'avg_win': 0, 'avg_loss': 0, 'profit_factor': 0, 'expectancy': 0}
    
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    
    win_rate = len(wins) / len(trades) if trades else 0
    avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t['pnl_pct'] for t in losses])) if losses else 0
    
    total_win = sum(t['pnl'] for t in wins)
    total_loss = abs(sum(t['pnl'] for t in losses))
    profit_factor = total_win / total_loss if total_loss > 0 else float('inf')
    
    expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss
    
    avg_hold = np.mean([t['hold_days'] for t in trades]) if trades else 0
    
    return {
        'total_trades': len(trades),
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'expectancy': expectancy,
        'avg_hold_days': avg_hold,
        'max_consecutive_wins': _max_consecutive(trades, win=True),
        'max_consecutive_losses': _max_consecutive(trades, win=False),
    }


def _max_consecutive(trades, win=True):
    """计算最大连续盈/亏次数"""
    max_count = 0
    current = 0
    for t in trades:
        if (win and t['pnl'] > 0) or (not win and t['pnl'] <= 0):
            current += 1
            max_count = max(max_count, current)
        else:
            current = 0
    return max_count
