"""
数据获取模块
支持AKShare和yfinance数据源，带本地缓存
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import json
import config


def fetch_stock_history(code: str, start_date: str, end_date: str,
                        source: str = None) -> pd.DataFrame:
    """
    获取股票历史行情数据
    
    Args:
        code: 股票代码（纯数字，如 '600519'）
        start_date: 开始日期 'YYYY-MM-DD'
        end_date: 结束日期 'YYYY-MM-DD'
        source: 数据源 'akshare' 或 'yfinance'
    
    Returns:
        DataFrame with columns: date, open, high, low, close, volume, amount, turnover
    """
    source = source or config.DATA_SOURCE
    
    # 尝试从缓存读取
    cache_file = _get_cache_path(code, start_date, end_date, source)
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file, parse_dates=['date'])
        if len(df) > 0:
            return df
    
    if source == "akshare":
        df = _fetch_akshare(code, start_date, end_date)
    elif source == "yfinance":
        df = _fetch_yfinance(code, start_date, end_date)
    else:
        raise ValueError(f"不支持的数据源: {source}")
    
    # 缓存
    if len(df) > 0:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        df.to_csv(cache_file, index=False)
    
    return df


def _fetch_akshare(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """通过AKShare获取A股日线数据"""
    try:
        import akshare as ak
        
        # AKShare的日线接口
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date.replace('-', ''),
            end_date=end_date.replace('-', ''),
            adjust="qfq"  # 前复权
        )
        
        if df.empty:
            return pd.DataFrame()
        
        # 统一列名
        df = df.rename(columns={
            '日期': 'date',
            '开盘': 'open',
            '最高': 'high',
            '最低': 'low',
            '收盘': 'close',
            '成交量': 'volume',
            '成交额': 'amount',
            '换手率': 'turnover',
            '涨跌幅': 'pct_change',
        })
        
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        
        # 确保必要列存在
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col not in df.columns:
                return pd.DataFrame()
        
        if 'amount' not in df.columns:
            df['amount'] = df['close'] * df['volume']
        if 'turnover' not in df.columns:
            df['turnover'] = 0
        if 'pct_change' not in df.columns:
            df['pct_change'] = df['close'].pct_change() * 100
        
        return df
    
    except Exception as e:
        print(f"AKShare获取{code}数据失败: {e}")
        return pd.DataFrame()


def _fetch_yfinance(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """通过yfinance获取数据（备用）"""
    try:
        import yfinance as yf
        
        # A股代码转换为yfinance格式
        if code.startswith('6'):
            symbol = f"{code}.SS"
        else:
            symbol = f"{code}.SZ"
        
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date)
        
        if df.empty:
            return pd.DataFrame()
        
        df = df.reset_index()
        df = df.rename(columns={
            'Date': 'date',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume',
        })
        
        df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
        df['amount'] = df['close'] * df['volume']
        df['turnover'] = 0
        df['pct_change'] = df['close'].pct_change() * 100
        
        return df[['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'turnover', 'pct_change']]
    
    except Exception as e:
        print(f"yfinance获取{code}数据失败: {e}")
        return pd.DataFrame()


def fetch_stock_info(code: str) -> dict:
    """获取股票基本信息"""
    try:
        import akshare as ak
        info = ak.stock_individual_info_em(symbol=code)
        result = {}
        for _, row in info.iterrows():
            result[row['item']] = row['value']
        return result
    except Exception:
        return {'股票代码': code, '股票简称': code}


def fetch_financial_data(code: str) -> pd.DataFrame:
    """获取财务数据"""
    try:
        import akshare as ak
        
        # 获取主要财务指标
        df = ak.stock_financial_abstract_ths(symbol=code, indicator="按年度")
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    
    return pd.DataFrame()


def fetch_index_history(index_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取指数历史数据（用于基准对比）"""
    try:
        import akshare as ak
        
        df = ak.stock_zh_index_daily(symbol=index_code)
        if df.empty:
            return pd.DataFrame()
        
        df['date'] = pd.to_datetime(df['date'])
        df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
        df = df.sort_values('date').reset_index(drop=True)
        df['pct_change'] = df['close'].pct_change() * 100
        
        return df
    
    except Exception as e:
        print(f"获取指数{index_code}数据失败: {e}")
        return pd.DataFrame()


def fetch_stock_list() -> pd.DataFrame:
    """获取A股股票列表"""
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        df = df.rename(columns={
            '代码': 'code',
            '名称': 'name',
            '最新价': 'price',
            '总市值': 'market_cap',
            '流通市值': 'float_cap',
            '市盈率-动态': 'pe',
            '市净率': 'pb',
        })
        return df
    except Exception:
        return pd.DataFrame()


def _get_cache_path(code, start, end, source):
    """生成缓存文件路径"""
    cache_dir = getattr(config, 'CACHE_DIR', './data_cache')
    return os.path.join(cache_dir, f"{source}_{code}_{start}_{end}.csv")
