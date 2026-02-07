"""
技术指标计算模块
所有指标均基于pandas计算，无需TA-Lib依赖
"""
import pandas as pd
import numpy as np


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """为DataFrame添加所有技术指标"""
    df = df.copy()
    df = add_ma(df)
    df = add_ema(df)
    df = add_macd(df)
    df = add_rsi(df)
    df = add_kdj(df)
    df = add_bollinger(df)
    df = add_atr(df)
    df = add_obv(df)
    df = add_vwap(df)
    df = add_momentum(df)
    return df


def add_ma(df: pd.DataFrame, periods: list = None) -> pd.DataFrame:
    """移动平均线"""
    periods = periods or [5, 10, 20, 60, 120, 250]
    for p in periods:
        df[f'ma{p}'] = df['close'].rolling(window=p, min_periods=1).mean()
    return df


def add_ema(df: pd.DataFrame, periods: list = None) -> pd.DataFrame:
    """指数移动平均线"""
    periods = periods or [12, 26, 50]
    for p in periods:
        df[f'ema{p}'] = df['close'].ewm(span=p, adjust=False).mean()
    return df


def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD指标"""
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    df['macd_dif'] = ema_fast - ema_slow
    df['macd_dea'] = df['macd_dif'].ewm(span=signal, adjust=False).mean()
    df['macd_hist'] = 2 * (df['macd_dif'] - df['macd_dea'])
    return df


def add_rsi(df: pd.DataFrame, periods: list = None) -> pd.DataFrame:
    """RSI指标"""
    periods = periods or [6, 12, 24]
    delta = df['close'].diff()
    
    for p in periods:
        gain = delta.where(delta > 0, 0).rolling(window=p, min_periods=1).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=p, min_periods=1).mean()
        rs = gain / loss.replace(0, np.inf)
        df[f'rsi{p}'] = 100 - (100 / (1 + rs))
    return df


def add_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """KDJ指标"""
    low_n = df['low'].rolling(window=n, min_periods=1).min()
    high_n = df['high'].rolling(window=n, min_periods=1).max()
    
    rsv = (df['close'] - low_n) / (high_n - low_n).replace(0, np.inf) * 100
    
    df['kdj_k'] = rsv.ewm(alpha=1/m1, adjust=False).mean()
    df['kdj_d'] = df['kdj_k'].ewm(alpha=1/m2, adjust=False).mean()
    df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']
    return df


def add_bollinger(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
    """布林带"""
    df['boll_mid'] = df['close'].rolling(window=period, min_periods=1).mean()
    rolling_std = df['close'].rolling(window=period, min_periods=1).std()
    df['boll_upper'] = df['boll_mid'] + std_dev * rolling_std
    df['boll_lower'] = df['boll_mid'] - std_dev * rolling_std
    df['boll_width'] = (df['boll_upper'] - df['boll_lower']) / df['boll_mid']
    return df


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """ATR (Average True Range) 平均真实波幅"""
    high = df['high']
    low = df['low']
    close_prev = df['close'].shift(1)
    
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    
    df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(window=period, min_periods=1).mean()
    df['atr_pct'] = df['atr'] / df['close']  # ATR占价格百分比
    return df


def add_obv(df: pd.DataFrame) -> pd.DataFrame:
    """OBV 能量潮指标"""
    direction = np.sign(df['close'].diff())
    df['obv'] = (direction * df['volume']).cumsum()
    df['obv_ma20'] = df['obv'].rolling(window=20, min_periods=1).mean()
    return df


def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """VWAP 成交量加权平均价"""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    cum_vol = df['volume'].cumsum()
    cum_tp_vol = (typical_price * df['volume']).cumsum()
    df['vwap'] = cum_tp_vol / cum_vol.replace(0, np.inf)
    return df


def add_momentum(df: pd.DataFrame) -> pd.DataFrame:
    """动量指标"""
    df['momentum_5'] = df['close'].pct_change(5)
    df['momentum_10'] = df['close'].pct_change(10)
    df['momentum_20'] = df['close'].pct_change(20)
    df['momentum_60'] = df['close'].pct_change(60)
    
    # 成交量变化
    df['vol_ratio'] = df['volume'] / df['volume'].rolling(window=20, min_periods=1).mean()
    
    # 波动率
    df['volatility_20'] = df['close'].pct_change().rolling(window=20, min_periods=1).std() * np.sqrt(252)
    
    return df


def detect_signals(df: pd.DataFrame) -> dict:
    """
    检测技术信号
    返回当前最新的技术信号汇总
    """
    if len(df) < 60:
        return {'signals': [], 'score': 0}
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    signals = []
    score = 0
    
    # --- 均线信号 ---
    if latest['ma5'] > latest['ma20'] and prev['ma5'] <= prev['ma20']:
        signals.append(('金叉', 'MA5上穿MA20', 'bullish', 2))
        score += 2
    elif latest['ma5'] < latest['ma20'] and prev['ma5'] >= prev['ma20']:
        signals.append(('死叉', 'MA5下穿MA20', 'bearish', -2))
        score -= 2
    
    if latest['close'] > latest['ma60']:
        signals.append(('多头', '股价在60日均线上方', 'bullish', 1))
        score += 1
    else:
        signals.append(('空头', '股价在60日均线下方', 'bearish', -1))
        score -= 1
    
    # --- MACD信号 ---
    if latest['macd_dif'] > latest['macd_dea'] and prev['macd_dif'] <= prev['macd_dea']:
        signals.append(('MACD金叉', 'DIF上穿DEA', 'bullish', 2))
        score += 2
    elif latest['macd_dif'] < latest['macd_dea'] and prev['macd_dif'] >= prev['macd_dea']:
        signals.append(('MACD死叉', 'DIF下穿DEA', 'bearish', -2))
        score -= 2
    
    if latest['macd_hist'] > 0 and latest['macd_hist'] > prev['macd_hist']:
        signals.append(('MACD增强', '红柱增长', 'bullish', 1))
        score += 1
    
    # --- RSI信号 ---
    if latest['rsi6'] < 20:
        signals.append(('RSI超卖', f"RSI6={latest['rsi6']:.1f}", 'bullish', 2))
        score += 2
    elif latest['rsi6'] > 80:
        signals.append(('RSI超买', f"RSI6={latest['rsi6']:.1f}", 'bearish', -2))
        score -= 2
    
    # --- KDJ信号 ---
    if latest['kdj_j'] < 0:
        signals.append(('KDJ超卖', f"J值={latest['kdj_j']:.1f}", 'bullish', 1))
        score += 1
    elif latest['kdj_j'] > 100:
        signals.append(('KDJ超买', f"J值={latest['kdj_j']:.1f}", 'bearish', -1))
        score -= 1
    
    # --- 布林带信号 ---
    if latest['close'] < latest['boll_lower']:
        signals.append(('触及下轨', '价格跌破布林带下轨', 'bullish', 1))
        score += 1
    elif latest['close'] > latest['boll_upper']:
        signals.append(('触及上轨', '价格突破布林带上轨', 'bearish', -1))
        score -= 1
    
    # --- 成交量信号 ---
    if latest['vol_ratio'] > 2:
        signals.append(('放量', f"量比={latest['vol_ratio']:.1f}", 'neutral', 0))
    
    return {
        'signals': signals,
        'score': score,
        'rating': _score_to_rating(score)
    }


def _score_to_rating(score: int) -> str:
    """信号分数转评级"""
    if score >= 5:
        return "强烈看多"
    elif score >= 2:
        return "看多"
    elif score >= -1:
        return "中性"
    elif score >= -4:
        return "看空"
    else:
        return "强烈看空"
