"""
多因子选股策略
融合价值、成长、动量、质量因子
"""
import pandas as pd
import numpy as np
from strategies.base_strategy import BaseStrategy


class MultiFactorStrategy(BaseStrategy):
    """
    多因子策略
    
    因子体系：
    1. 价值因子：低PE + 低PB → 估值合理
    2. 成长因子：营收增速 + 净利增速 + ROE改善
    3. 动量因子：近期涨幅（排除过热）+ 趋势强度
    4. 技术因子：MA排列 + MACD + 成交量
    
    信号：多因子打分 → 排序 → 选Top-N → 仓位分配
    """
    
    def __init__(self, params: dict = None):
        default_params = {
            'rebalance_period': 20,     # 调仓周期（交易日）
            'top_n': 5,                 # 选股数量
            'momentum_window': 20,       # 动量窗口
            'min_score': 3,             # 最低入选分数
            'sell_score_threshold': -2,  # 卖出分数阈值
        }
        if params:
            default_params.update(params)
        
        super().__init__(name="多因子选股策略", params=default_params)
        self.last_rebalance = -999
    
    def on_init(self):
        """策略初始化/重置"""
        self.last_rebalance = -999
    
    def on_bar(self, context: dict):
        """每日执行"""
        date = context['date']
        bars = context['bars']
        idx = context['date_index']
        
        # 账户被冻结则不操作
        if context['is_halted']:
            return
        
        # --- 检查是否需要调仓 ---
        if idx - self.last_rebalance < self.params['rebalance_period']:
            # 非调仓日：检查持仓是否需要提前卖出
            self._check_sell_signals(context)
            return
        
        self.last_rebalance = idx
        
        # --- 对所有股票打分 ---
        scores = {}
        for code, bar in bars.items():
            if code not in self.data:
                continue
            
            df = self.data[code]
            date_ts = pd.Timestamp(date)
            
            if date_ts not in df.index:
                continue
            
            loc = df.index.get_loc(date_ts)
            if loc < 60:  # 需要足够历史数据
                continue
            
            score = self._score_stock(df, loc)
            scores[code] = score
        
        if not scores:
            return
        
        # --- 排序选股 ---
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_stocks = [(code, score) for code, score in ranked 
                      if score >= self.params['min_score']][:self.params['top_n']]
        
        selected_codes = set(c for c, _ in top_stocks)
        
        # --- 卖出不在选股列表中的持仓 ---
        for code in list(context['positions'].keys()):
            if code not in selected_codes:
                pos = context['positions'][code]
                if code in bars and pos['entry_date'] != date:
                    bar = bars[code]
                    self.sell(code, pos['shares'], bar['close'], date,
                              bar_data=self._make_bar_data(bar))
        
        # --- 买入新选股票 ---
        for code, score in top_stocks:
            if self.has_position(code):
                continue
            
            # 检查是否允许开仓
            can_open = self.risk_manager.can_open_position(
                self.broker.positions_compat, context['equity'], cash=context['cash']
            )
            if not can_open['allowed']:
                break
            
            if code not in bars:
                continue
            
            bar = bars[code]
            price = bar['close']
            atr = bar.get('atr', price * 0.02)
            
            # 计算仓位
            shares = self.calc_buy_shares(
                code, price, context,
                atr=atr,
                volatility=bar.get('volatility_20', 0.3)
            )
            
            if shares >= 100:
                self.buy(code, shares, price, date,
                         bar_data=self._make_bar_data(bar))
    
    def _score_stock(self, df: pd.DataFrame, loc: int) -> float:
        """
        多因子打分
        返回综合分数
        """
        row = df.iloc[loc]
        score = 0
        
        # --- 趋势因子（权重30%）---
        # MA排列：MA5 > MA10 > MA20 > MA60
        try:
            if row.get('ma5', 0) > row.get('ma10', 0) > row.get('ma20', 0):
                score += 3
            elif row.get('ma5', 0) > row.get('ma10', 0):
                score += 1
            elif row.get('ma5', 0) < row.get('ma10', 0) < row.get('ma20', 0):
                score -= 3
            
            # 价格在60日线上方
            if row['close'] > row.get('ma60', row['close']):
                score += 1
            else:
                score -= 1
        except (KeyError, TypeError):
            pass
        
        # --- 动量因子（权重25%）---
        try:
            momentum = row.get('momentum_20', 0)
            if 0 < momentum < 0.20:  # 温和上涨
                score += 2
            elif 0.20 <= momentum < 0.40:
                score += 1
            elif momentum >= 0.40:  # 涨幅过大，风险
                score -= 1
            elif momentum < -0.10:
                score -= 2
        except (KeyError, TypeError):
            pass
        
        # --- MACD因子（权重20%）---
        try:
            if row.get('macd_dif', 0) > row.get('macd_dea', 0):
                score += 1
            if row.get('macd_hist', 0) > 0:
                score += 1
                # MACD红柱增长
                if loc > 0 and row.get('macd_hist', 0) > df.iloc[loc - 1].get('macd_hist', 0):
                    score += 1
        except (KeyError, TypeError):
            pass
        
        # --- RSI因子（权重15%）---
        try:
            rsi = row.get('rsi12', 50)
            if 30 < rsi < 60:
                score += 1
            elif rsi <= 30:
                score += 2  # 超卖可能反弹
            elif rsi >= 70:
                score -= 2  # 超买风险
        except (KeyError, TypeError):
            pass
        
        # --- 成交量因子（权重10%）---
        try:
            vol_ratio = row.get('vol_ratio', 1)
            if 1.2 < vol_ratio < 3:
                score += 1  # 温和放量
            elif vol_ratio >= 3:
                score -= 1  # 异常放量
        except (KeyError, TypeError):
            pass
        
        return score
    
    def _check_sell_signals(self, context: dict):
        """非调仓日检查是否需要提前卖出"""
        date = context['date']
        bars = context['bars']
        
        for code in list(context['positions'].keys()):
            pos = context['positions'][code]
            
            if pos['entry_date'] == date:
                continue
            
            if code not in bars or code not in self.data:
                continue
            
            df = self.data[code]
            date_ts = pd.Timestamp(date)
            
            if date_ts not in df.index:
                continue
            
            loc = df.index.get_loc(date_ts)
            if loc < 10:
                continue
            
            score = self._score_stock(df, loc)
            
            # 分数过低则卖出
            if score <= self.params['sell_score_threshold']:
                bar = bars[code]
                self.sell(code, pos['shares'], bar['close'], date,
                          bar_data=self._make_bar_data(bar))
    
    def _make_bar_data(self, bar: dict) -> dict:
        """构造bar_data用于订单"""
        return {
            'open': bar.get('open', bar['close']),
            'high': bar.get('high', bar['close']),
            'low': bar.get('low', bar['close']),
            'close': bar['close'],
            'volume': bar.get('volume', 0),
            'prev_close': bar.get('prev_close', bar['close']),
        }
