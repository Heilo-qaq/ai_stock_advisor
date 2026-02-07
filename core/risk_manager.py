"""
风控系统模块
多层次风险管理：个股级、组合级、账户级
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import config


@dataclass
class StopLossConfig:
    """止损配置"""
    hard_stop: float = 0.08          # 硬止损比例
    trailing_stop: float = 0.10       # 跟踪止损回撤比例
    time_stop_days: int = 20          # 时间止损天数
    volatility_multiplier: float = 2  # 波动率止损倍数（ATR）


@dataclass
class Position:
    """持仓信息"""
    code: str
    name: str
    entry_price: float
    entry_date: str
    shares: int
    current_price: float = 0
    highest_price: float = 0        # 持仓期间最高价
    sector: str = ""
    atr_at_entry: float = 0
    current_date: str = ""          # 当前日期（回测时传入）
    
    @property
    def market_value(self):
        return self.shares * self.current_price
    
    @property
    def cost_value(self):
        return self.shares * self.entry_price
    
    @property
    def pnl(self):
        return self.market_value - self.cost_value
    
    @property
    def pnl_pct(self):
        if self.cost_value == 0:
            return 0
        return self.pnl / self.cost_value
    
    @property
    def hold_days(self):
        entry = pd.Timestamp(self.entry_date)
        if self.current_date:
            now = pd.Timestamp(self.current_date)
        else:
            now = pd.Timestamp(datetime.now().strftime('%Y-%m-%d'))
        return (now - entry).days


class RiskManager:
    """
    风控管理器
    实现多层止损、账户级风控、A股特殊机制处理
    """
    
    def __init__(self, stop_config: StopLossConfig = None):
        self.stop_config = stop_config or StopLossConfig(
            hard_stop=config.SINGLE_STOCK_MAX_LOSS,
            trailing_stop=config.TRAILING_STOP_RATIO,
            time_stop_days=config.TIME_STOP_DAYS,
        )
        self.max_drawdown_limit = config.MAX_DRAWDOWN_LIMIT
        self.max_single_position = config.MAX_SINGLE_POSITION
        self.max_sector_exposure = config.MAX_SECTOR_EXPOSURE
        self.max_positions = config.MAX_POSITIONS
        self.account_peak = 0
        self.is_trading_halted = False  # 触发账户红线后停止交易
    
    # ============================================================
    # 个股级风控
    # ============================================================
    
    def check_stop_loss(self, position: Position) -> dict:
        """
        检查个股是否触发止损
        返回: {'should_stop': bool, 'reason': str, 'type': str}
        """
        results = []
        
        # 1. 硬止损
        if position.pnl_pct <= -self.stop_config.hard_stop:
            results.append({
                'should_stop': True,
                'reason': f"触发硬止损: 亏损{position.pnl_pct:.1%} >= {self.stop_config.hard_stop:.0%}",
                'type': 'hard_stop',
                'priority': 1
            })
        
        # 2. 跟踪止损（从最高点回撤）
        if position.highest_price > 0 and position.current_price > 0:
            drawdown_from_peak = (position.highest_price - position.current_price) / position.highest_price
            if drawdown_from_peak >= self.stop_config.trailing_stop and position.pnl_pct > 0:
                results.append({
                    'should_stop': True,
                    'reason': f"触发跟踪止损: 从最高{position.highest_price:.2f}回撤{drawdown_from_peak:.1%}",
                    'type': 'trailing_stop',
                    'priority': 2
                })
        
        # 3. 时间止损
        if position.hold_days >= self.stop_config.time_stop_days and position.pnl_pct <= 0:
            results.append({
                'should_stop': True,
                'reason': f"触发时间止损: 持仓{position.hold_days}天未盈利",
                'type': 'time_stop',
                'priority': 3
            })
        
        # 4. 波动率止损（基于ATR）
        if position.atr_at_entry > 0:
            atr_stop_price = position.entry_price - self.stop_config.volatility_multiplier * position.atr_at_entry
            if position.current_price <= atr_stop_price:
                results.append({
                    'should_stop': True,
                    'reason': f"触发波动率止损: 价格低于ATR止损线{atr_stop_price:.2f}",
                    'type': 'volatility_stop',
                    'priority': 2
                })
        
        if results:
            # 返回最高优先级的止损信号
            return sorted(results, key=lambda x: x['priority'])[0]
        
        return {'should_stop': False, 'reason': '', 'type': ''}
    
    # ============================================================
    # 组合级风控
    # ============================================================
    
    def check_portfolio_risk(self, positions, total_equity: float,
                              current_prices: dict = None) -> dict:
        """
        检查组合级风险
        positions: List[Position] 或 dict {code: {shares, avg_price, ...}} 或 list of dicts
        返回风险警告列表
        """
        warnings = []
        
        if not positions or total_equity <= 0:
            return {'warnings': warnings, 'risk_level': 'low'}
        
        # 统一转换为可处理的列表
        pos_list = self._normalize_positions(positions, current_prices)
        
        # 1. 单只股票仓位过重
        for pos in pos_list:
            weight = pos['market_value'] / total_equity
            if weight > self.max_single_position:
                warnings.append({
                    'level': 'high',
                    'type': 'concentration',
                    'message': f"{pos['name']}({pos['code']}) 仓位{weight:.1%}，超过上限{self.max_single_position:.0%}"
                })
        
        # 2. 行业集中度
        sector_exposure = {}
        for pos in pos_list:
            sector = pos.get('sector') or "未知"
            sector_exposure[sector] = sector_exposure.get(sector, 0) + pos['market_value'] / total_equity
        
        for sector, exposure in sector_exposure.items():
            if exposure > self.max_sector_exposure:
                warnings.append({
                    'level': 'high',
                    'type': 'sector_concentration',
                    'message': f"行业{sector}敞口{exposure:.1%}，超过上限{self.max_sector_exposure:.0%}"
                })
        
        # 3. 持仓数量
        if len(pos_list) > self.max_positions:
            warnings.append({
                'level': 'medium',
                'type': 'too_many_positions',
                'message': f"持仓{len(pos_list)}只，超过上限{self.max_positions}只"
            })
        
        # 4. 持仓相关性（简化：同一行业视为高相关）
        sectors = [pos.get('sector') or "未知" for pos in pos_list]
        from collections import Counter
        sector_counts = Counter(sectors)
        for sector, count in sector_counts.items():
            if count >= 3:
                warnings.append({
                    'level': 'medium',
                    'type': 'high_correlation',
                    'message': f"{sector}板块持有{count}只股票，存在高相关性风险"
                })
        
        # 风险等级
        high_count = sum(1 for w in warnings if w['level'] == 'high')
        if high_count >= 2:
            risk_level = 'critical'
        elif high_count >= 1:
            risk_level = 'high'
        elif warnings:
            risk_level = 'medium'
        else:
            risk_level = 'low'
        
        return {'warnings': warnings, 'risk_level': risk_level}
    
    def _normalize_positions(self, positions, current_prices=None) -> list:
        """将各种格式的持仓统一转为 list of dict"""
        result = []
        if isinstance(positions, dict):
            for code, pos in positions.items():
                price = (current_prices or {}).get(code, pos.get('avg_price', 0))
                shares = pos.get('shares', 0)
                result.append({
                    'code': code,
                    'name': pos.get('name', code),
                    'shares': shares,
                    'market_value': shares * price,
                    'sector': pos.get('sector', ''),
                })
        elif isinstance(positions, list):
            for p in positions:
                if isinstance(p, dict):
                    code = p.get('code', '')
                    price = p.get('current_price', p.get('avg_price', 0))
                    shares = p.get('shares', 0)
                    result.append({
                        'code': code,
                        'name': p.get('name', code),
                        'shares': shares,
                        'market_value': shares * price,
                        'sector': p.get('sector', ''),
                    })
                elif hasattr(p, 'market_value'):
                    # Position对象
                    result.append({
                        'code': p.code,
                        'name': p.name,
                        'shares': p.shares,
                        'market_value': p.market_value,
                        'sector': getattr(p, 'sector', ''),
                    })
        return result
    
    # ============================================================
    # 账户级风控
    # ============================================================
    
    def check_account_drawdown(self, current_equity: float) -> dict:
        """
        检查账户级最大回撤
        """
        self.account_peak = max(self.account_peak, current_equity)
        
        if self.account_peak == 0:
            return {'drawdown': 0, 'exceeded': False}
        
        drawdown = (self.account_peak - current_equity) / self.account_peak
        exceeded = drawdown >= self.max_drawdown_limit
        
        if exceeded:
            self.is_trading_halted = True
        
        return {
            'drawdown': drawdown,
            'peak': self.account_peak,
            'exceeded': exceeded,
            'message': f"当前回撤{drawdown:.1%}" + (
                f" ⚠️ 已触发{self.max_drawdown_limit:.0%}红线，停止开新仓！" if exceeded else ""
            )
        }
    
    def can_open_position(self, positions, total_equity: float,
                          cash: float = None, current_prices: dict = None) -> dict:
        """
        判断是否允许开新仓
        positions 可以是 List[Position] 或 broker 的 dict 格式 {code: {shares, avg_price, ...}}
                  也可以是 list of dict（broker.positions.values()）
        """
        if self.is_trading_halted:
            return {
                'allowed': False,
                'reason': '账户回撤触发红线，已停止交易'
            }
        
        # 兼容不同格式：计算持仓数量
        if isinstance(positions, dict):
            n_positions = len(positions)
        else:
            n_positions = len(positions)
        
        if n_positions >= self.max_positions:
            return {
                'allowed': False,
                'reason': f'已达最大持仓数{self.max_positions}只'
            }
        
        # 计算剩余可用仓位
        if cash is not None and total_equity > 0:
            # 直接用 cash/equity 计算
            used_ratio = 1 - (cash / total_equity)
        else:
            # 尝试从positions计算
            used_ratio = self._calc_used_ratio(positions, total_equity, current_prices)
        
        available = 1 - used_ratio
        
        if available < 0.1:
            return {
                'allowed': False,
                'reason': f'可用仓位不足（剩余{available:.1%}）'
            }
        
        return {
            'allowed': True,
            'max_position_size': min(available, self.max_single_position),
            'reason': f'允许开仓，最大仓位{min(available, self.max_single_position):.1%}'
        }
    
    def _calc_used_ratio(self, positions, total_equity, current_prices=None):
        """计算已用仓位比例，兼容 Position 对象和 dict"""
        if total_equity <= 0:
            return 0
        total_mv = 0
        if isinstance(positions, dict):
            # broker.positions 格式: {code: {shares, avg_price, ...}}
            for code, pos in positions.items():
                price = (current_prices or {}).get(code, pos.get('avg_price', 0))
                total_mv += pos.get('shares', 0) * price
        elif isinstance(positions, list):
            for p in positions:
                if isinstance(p, dict):
                    price = p.get('current_price', p.get('avg_price', 0))
                    total_mv += p.get('shares', 0) * price
                elif hasattr(p, 'market_value'):
                    total_mv += p.market_value
        return total_mv / total_equity
    
    # ============================================================
    # A股特殊机制
    # ============================================================
    
    @staticmethod
    def check_limit_up(price: float, prev_close: float, is_st: bool = False) -> bool:
        """检查是否涨停"""
        limit = 0.05 if is_st else 0.10
        return price >= prev_close * (1 + limit - 0.001)
    
    @staticmethod
    def check_limit_down(price: float, prev_close: float, is_st: bool = False) -> bool:
        """检查是否跌停"""
        limit = 0.05 if is_st else 0.10
        return price <= prev_close * (1 - limit + 0.001)
    
    @staticmethod
    def check_t1_sellable(entry_date: str, current_date: str) -> bool:
        """检查T+1规则：买入当天不可卖出"""
        return pd.Timestamp(current_date) > pd.Timestamp(entry_date)
    
    def assess_overnight_risk(self, position: Position, df: pd.DataFrame) -> dict:
        """
        评估隔夜风险
        基于历史跳空数据估算隔夜Gap风险
        """
        if len(df) < 60:
            return {'risk': 'unknown', 'avg_gap': 0}
        
        # 计算历史跳空幅度
        gaps = (df['open'].shift(-1) - df['close']) / df['close']
        gaps = gaps.dropna()
        
        neg_gaps = gaps[gaps < 0]
        avg_neg_gap = neg_gaps.mean() if len(neg_gaps) > 0 else 0
        max_neg_gap = neg_gaps.min() if len(neg_gaps) > 0 else 0
        gap_95 = neg_gaps.quantile(0.05) if len(neg_gaps) > 0 else 0  # 5%分位（极端跳空）
        
        risk_level = 'low'
        if abs(avg_neg_gap) > 0.01:
            risk_level = 'medium'
        if abs(max_neg_gap) > 0.05:
            risk_level = 'high'
        
        return {
            'risk': risk_level,
            'avg_neg_gap': avg_neg_gap,
            'max_neg_gap': max_neg_gap,
            'gap_95_percentile': gap_95,
            'estimated_overnight_var': abs(gap_95) * position.market_value
        }
