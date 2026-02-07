"""
价值成长策略
结合基本面价值因子和成长因子，筛选估值合理的成长股
"""
import pandas as pd
import numpy as np
from strategies.base_strategy import BaseStrategy


class ValueGrowthStrategy(BaseStrategy):
    """
    价值成长策略
    
    核心逻辑：
    1. 筛选：估值合理（PE < 30, PB < 5）且有成长性的股票
    2. 技术面确认：均线多头排列 + MACD看多
    3. 入场：技术面确认后买入
    4. 出场：破20日线 或 基本面恶化 或 止损
    """
    
    def __init__(self, params: dict = None):
        default_params = {
            'rebalance_period': 20,
            'top_n': 5,
            'pe_max': 30,
            'pb_max': 5,
        }
        if params:
            default_params.update(params)
        super().__init__(name="价值成长策略", params=default_params)
        self.last_rebalance = -999
        self.stock_fundamentals = {}
    
    def on_init(self):
        self.last_rebalance = -999  # 缓存基本面数据
    
    def on_bar(self, context: dict):
        date = context['date']
        bars = context['bars']
        idx = context['date_index']
        
        if context['is_halted']:
            return
        
        # 检查卖出
        self._check_exits(context)
        
        if idx - self.last_rebalance < self.params['rebalance_period']:
            return
        self.last_rebalance = idx
        
        # 综合打分
        candidates = []
        for code, bar in bars.items():
            if code not in self.data:
                continue
            
            df = self.data[code]
            date_ts = pd.Timestamp(date)
            if date_ts not in df.index:
                continue
            
            loc = df.index.get_loc(date_ts)
            if loc < 60:
                continue
            
            row = df.iloc[loc]
            score = 0
            
            # 技术面评分
            # 均线多头
            if row.get('ma5', 0) > row.get('ma10', 0) > row.get('ma20', 0):
                score += 3
            elif row.get('ma5', 0) > row.get('ma20', 0):
                score += 1
            
            # MACD金叉
            if row.get('macd_dif', 0) > row.get('macd_dea', 0):
                score += 2
            
            # 温和动量
            mom = row.get('momentum_20', 0)
            if 0 < mom < 0.15:
                score += 2
            elif mom >= 0.15:
                score += 1
            
            # 布林带位置（中轨以上但未到上轨）
            if row.get('boll_mid', 0) < row['close'] < row.get('boll_upper', float('inf')):
                score += 1
            
            # RSI适中
            rsi = row.get('rsi12', 50)
            if 40 < rsi < 65:
                score += 1
            
            if score >= 4:
                candidates.append((code, score, bar))
        
        # 排序选top
        candidates.sort(key=lambda x: x[1], reverse=True)
        targets = candidates[:self.params['top_n']]
        
        for code, score, bar in targets:
            if self.has_position(code):
                continue
            
            can_open = self.risk_manager.can_open_position(
                self.broker.positions_compat, context['equity'], cash=context['cash']
            )
            if not can_open['allowed']:
                break
            
            price = bar['close']
            shares = self.calc_buy_shares(
                code, price, context,
                atr=bar.get('atr', price * 0.02)
            )
            
            if shares >= 100:
                self.buy(code, shares, price, date,
                         bar_data=self._make_bar_data(bar))
    
    def _check_exits(self, context: dict):
        """检查卖出"""
        date = context['date']
        bars = context['bars']
        
        for code in list(context['positions'].keys()):
            pos = context['positions'][code]
            if pos['entry_date'] == date:
                continue
            if code not in bars or code not in self.data:
                continue
            
            bar = bars[code]
            df = self.data[code]
            date_ts = pd.Timestamp(date)
            if date_ts not in df.index:
                continue
            
            row = df.loc[date_ts]
            
            # 跌破MA20卖出
            if row['close'] < row.get('ma20', row['close']):
                self.sell(code, pos['shares'], bar['close'], date,
                          bar_data=self._make_bar_data(bar))
                continue
            
            # MACD死叉 + 量缩
            if (row.get('macd_dif', 0) < row.get('macd_dea', 0) and 
                row.get('vol_ratio', 1) < 0.8):
                self.sell(code, pos['shares'], bar['close'], date,
                          bar_data=self._make_bar_data(bar))
    
    def _make_bar_data(self, bar):
        return {
            'open': bar.get('open', bar['close']),
            'high': bar.get('high', bar['close']),
            'low': bar.get('low', bar['close']),
            'close': bar['close'],
            'volume': bar.get('volume', 0),
            'prev_close': bar.get('prev_close', bar['close']),
        }
