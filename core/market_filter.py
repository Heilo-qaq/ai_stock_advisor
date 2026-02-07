"""
大盘择时过滤器
根据沪深300/上证指数状态判断市场环境，动态调整策略行为
"""
import pandas as pd
import numpy as np


class MarketFilter:
    """
    市场环境过滤器
    
    判定逻辑：
    - 牛市：指数 > MA60 且 MA20 > MA60
    - 震荡：指数 > MA60 但 MA20 < MA60（或反之）
    - 熊市：指数 < MA60 且 MA20 < MA60
    
    对策略的影响：
    - 牛市：正常交易，满仓
    - 震荡：半仓，只买强势股
    - 熊市：空仓或极低仓位，不开新仓
    """
    
    BULL = 'bull'
    BEAR = 'bear'
    NEUTRAL = 'neutral'
    
    def __init__(self, index_data: pd.DataFrame = None):
        """
        Args:
            index_data: 指数DataFrame (index=date, columns含 close)
        """
        self.index_data = index_data
        self._cache = {}
    
    def set_index_data(self, df: pd.DataFrame):
        """设置指数数据"""
        df = df.copy()
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
        df['ma20'] = df['close'].rolling(20, min_periods=1).mean()
        df['ma60'] = df['close'].rolling(60, min_periods=1).mean()
        df['ma120'] = df['close'].rolling(120, min_periods=1).mean()
        df['rsi14'] = self._calc_rsi(df['close'], 14)
        self.index_data = df
        self._cache = {}
    
    def get_regime(self, date: str) -> str:
        """获取指定日期的市场状态"""
        if self.index_data is None or len(self.index_data) == 0:
            return self.NEUTRAL
        
        if date in self._cache:
            return self._cache[date]
        
        ts = pd.Timestamp(date)
        
        # 找到最近的有数据的日期
        valid = self.index_data.index[self.index_data.index <= ts]
        if len(valid) == 0:
            return self.NEUTRAL
        
        row = self.index_data.loc[valid[-1]]
        close = row['close']
        ma20 = row.get('ma20', close)
        ma60 = row.get('ma60', close)
        
        if close > ma60 and ma20 > ma60:
            regime = self.BULL
        elif close < ma60 and ma20 < ma60:
            regime = self.BEAR
        else:
            regime = self.NEUTRAL
        
        self._cache[date] = regime
        return regime
    
    def get_position_multiplier(self, date: str) -> float:
        """
        获取仓位调节系数
        牛市=1.0, 震荡=0.5, 熊市=0.1
        """
        regime = self.get_regime(date)
        if regime == self.BULL:
            return 1.0
        elif regime == self.NEUTRAL:
            return 0.5
        else:
            return 0.1
    
    def should_open_position(self, date: str) -> bool:
        """是否允许开新仓"""
        return self.get_regime(date) != self.BEAR
    
    def get_regime_detail(self, date: str) -> dict:
        """获取详细的市场状态信息"""
        if self.index_data is None:
            return {'regime': self.NEUTRAL, 'detail': '无指数数据'}
        
        ts = pd.Timestamp(date)
        valid = self.index_data.index[self.index_data.index <= ts]
        if len(valid) == 0:
            return {'regime': self.NEUTRAL, 'detail': '无数据'}
        
        row = self.index_data.loc[valid[-1]]
        close = row['close']
        ma20 = row.get('ma20', close)
        ma60 = row.get('ma60', close)
        ma120 = row.get('ma120', close)
        rsi = row.get('rsi14', 50)
        regime = self.get_regime(date)
        
        labels = {self.BULL: '🟢 牛市', self.NEUTRAL: '🟡 震荡', self.BEAR: '🔴 熊市'}
        
        return {
            'regime': regime,
            'label': labels.get(regime, '未知'),
            'index_close': close,
            'ma20': ma20,
            'ma60': ma60,
            'ma120': ma120,
            'rsi14': rsi,
            'position_multiplier': self.get_position_multiplier(date),
            'detail': (
                f"指数{close:.0f} vs MA60({ma60:.0f}) "
                f"{'↑' if close > ma60 else '↓'} | "
                f"MA20({ma20:.0f}) vs MA60({ma60:.0f}) "
                f"{'↑' if ma20 > ma60 else '↓'} | "
                f"RSI={rsi:.0f}"
            ),
        }
    
    @staticmethod
    def _calc_rsi(series, period=14):
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(period, min_periods=1).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period, min_periods=1).mean()
        rs = gain / loss.replace(0, np.inf)
        return 100 - (100 / (1 + rs))
