"""
动量策略
基于价格动量和成交量确认的趋势跟随策略
"""
import pandas as pd
import numpy as np
from strategies.base_strategy import BaseStrategy


class MomentumStrategy(BaseStrategy):
    """
    动量策略
    
    买入条件：
    1. 过去N日收益率排名前M
    2. 收盘价突破N日新高
    3. 成交量放大确认
    4. MA5 > MA20（趋势向上）
    
    卖出条件：
    1. 收盘价跌破MA20
    2. 动量反转（过去5日连续下跌）
    3. 风控止损
    """
    
    def __init__(self, params: dict = None):
        default_params = {
            'momentum_period': 20,       # 动量计算周期
            'breakout_period': 60,       # 突破周期
            'hold_period': 10,           # 最短持仓周期
            'rebalance_period': 5,       # 调仓周期
            'top_n': 3,                  # 选股数量
        }
        if params:
            default_params.update(params)
        super().__init__(name="动量策略", params=default_params)
        self.last_rebalance = -999
    
    def on_init(self):
        self.last_rebalance = -999
    
    def on_bar(self, context: dict):
        date = context['date']
        bars = context['bars']
        idx = context['date_index']
        
        if context['is_halted']:
            return
        
        # 检查卖出
        self._check_exits(context)
        
        # 调仓检查
        if idx - self.last_rebalance < self.params['rebalance_period']:
            return
        self.last_rebalance = idx
        
        # 计算动量排名
        momentum_scores = {}
        for code, bar in bars.items():
            if code not in self.data:
                continue
            df = self.data[code]
            date_ts = pd.Timestamp(date)
            if date_ts not in df.index:
                continue
            loc = df.index.get_loc(date_ts)
            
            mp = self.params['momentum_period']
            bp = self.params['breakout_period']
            
            if loc < max(mp, bp):
                continue
            
            row = df.iloc[loc]
            
            # 动量值
            momentum = row.get('close', 0) / df.iloc[loc - mp]['close'] - 1
            
            # 突破新高
            period_high = df.iloc[loc - bp:loc]['high'].max()
            is_breakout = row['close'] >= period_high * 0.98
            
            # 趋势确认
            trend_ok = row.get('ma5', 0) > row.get('ma20', 0)
            
            # 量价配合
            vol_ok = row.get('vol_ratio', 1) > 1.0
            
            if is_breakout and trend_ok and momentum > 0:
                score = momentum * 100
                if vol_ok:
                    score *= 1.2
                momentum_scores[code] = score
        
        # 选Top N
        ranked = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        targets = ranked[:self.params['top_n']]
        
        # 买入
        for code, score in targets:
            if self.has_position(code):
                continue
            
            can_open = self.risk_manager.can_open_position(
                self.broker.positions_compat, context['equity'], cash=context['cash']
            )
            if not can_open['allowed']:
                break
            
            bar = bars[code]
            price = bar['close']
            shares = self.calc_buy_shares(
                code, price, context,
                atr=bar.get('atr', price * 0.02)
            )
            
            if shares >= 100:
                self.buy(code, shares, price, date,
                         bar_data=self._make_bar_data(bar))
    
    def _check_exits(self, context: dict):
        """检查卖出条件"""
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
            
            # 卖出条件1：跌破MA20
            if row['close'] < row.get('ma20', row['close']):
                self.sell(code, pos['shares'], bar['close'], date,
                          bar_data=self._make_bar_data(bar))
                continue
            
            # 卖出条件2：连续5日下跌
            loc = df.index.get_loc(date_ts)
            if loc >= 5:
                recent = df.iloc[loc - 4:loc + 1]['close']
                if all(recent.diff().dropna() < 0):
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
