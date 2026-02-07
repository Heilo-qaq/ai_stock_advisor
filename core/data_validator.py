"""
数据质量验证模块
检查缺失值、异常值、复权跳变等
"""
import pandas as pd
import numpy as np


def validate_stock_data(df: pd.DataFrame, code: str = '') -> dict:
    """
    验证股票数据质量
    
    Returns:
        {
            'valid': bool,
            'issues': list of str,
            'stats': dict,
        }
    """
    issues = []
    
    if df.empty:
        return {'valid': False, 'issues': ['数据为空'], 'stats': {}}
    
    required = ['date', 'open', 'high', 'low', 'close', 'volume']
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        return {'valid': False, 'issues': [f'缺少列: {missing_cols}'], 'stats': {}}
    
    n_rows = len(df)
    
    # 缺失值检查
    for col in ['open', 'high', 'low', 'close', 'volume']:
        na_count = df[col].isna().sum()
        if na_count > 0:
            pct = na_count / n_rows
            if pct > 0.05:
                issues.append(f'{col}列缺失{na_count}行({pct:.1%})，超过5%')
            else:
                issues.append(f'{col}列缺失{na_count}行({pct:.1%})，已自动填充')
    
    # 异常值检查
    if (df['close'] <= 0).any():
        issues.append(f'存在{(df["close"]<=0).sum()}行收盘价<=0')
    
    if (df['high'] < df['low']).any():
        issues.append(f'存在{(df["high"]<df["low"]).sum()}行最高价<最低价')
    
    if (df['volume'] < 0).any():
        issues.append(f'存在负成交量')
    
    # 复权跳变检查
    pct = df['close'].pct_change().abs()
    big_jumps = pct[pct > 0.20]  # 日涨跌超20%（排除科创板首日）
    if len(big_jumps) > 3:
        issues.append(f'存在{len(big_jumps)}个>20%日涨跌，可能复权异常')
    
    # 日期连续性检查
    if 'date' in df.columns:
        dates = pd.to_datetime(df['date'])
        gaps = dates.diff().dt.days
        long_gaps = gaps[gaps > 10]  # 超过10天空白
        if len(long_gaps) > 0:
            issues.append(f'存在{len(long_gaps)}个>10天的数据空白期')
    
    # 零成交量天数
    zero_vol = (df['volume'] == 0).sum()
    if zero_vol > n_rows * 0.1:
        issues.append(f'{zero_vol}天零成交量({zero_vol/n_rows:.0%})，可能停牌')
    
    stats = {
        'rows': n_rows,
        'date_range': f"{df['date'].iloc[0]} ~ {df['date'].iloc[-1]}" if 'date' in df.columns else 'N/A',
        'zero_volume_days': int(zero_vol),
        'na_total': int(df[['open','high','low','close','volume']].isna().sum().sum()),
        'issues_count': len(issues),
    }
    
    severe = [i for i in issues if '缺失' in i and '超过5%' in i or '<=0' in i or '复权' in i]
    
    return {
        'valid': len(severe) == 0,
        'issues': issues,
        'stats': stats,
    }


def clean_stock_data(df: pd.DataFrame) -> pd.DataFrame:
    """清洗股票数据"""
    df = df.copy()
    
    # 前向填充缺失价格
    for col in ['open', 'high', 'low', 'close']:
        if col in df.columns:
            df[col] = df[col].fillna(method='ffill').fillna(method='bfill')
    
    # 零成交量填0（不填充）
    if 'volume' in df.columns:
        df['volume'] = df['volume'].fillna(0)
    
    # 去除收盘价<=0的行
    if 'close' in df.columns:
        df = df[df['close'] > 0]
    
    return df.reset_index(drop=True)
