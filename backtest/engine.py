"""
回测引擎模块
事件驱动回测 + Walk-Forward滚动回测 + 蒙特卡洛模拟
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
from backtest.broker import SimBroker
from core.indicators import add_all_indicators
from core.risk_manager import RiskManager, Position
from core.performance import PerformanceAnalyzer
import config


class BacktestEngine:
    """
    事件驱动回测引擎
    严格模拟A股T+1、涨跌停、真实交易成本
    """
    
    def __init__(self, strategy, initial_capital: float = None):
        """
        Args:
            strategy: 策略实例（需实现 on_bar 方法）
            initial_capital: 初始资金
        """
        self.strategy = strategy
        self.initial_capital = initial_capital or config.INITIAL_CAPITAL
        self.broker = None
        self.risk_manager = None
        self.performance = PerformanceAnalyzer()
        
        # 回测数据
        self.data: Dict[str, pd.DataFrame] = {}  # {code: df}
        self.benchmark_data: pd.DataFrame = None  # 基准指数数据
        self.dates: List[str] = []
        self.equity_curve = {}
        self.trade_log = []
    
    def add_data(self, code: str, df: pd.DataFrame):
        """添加股票数据"""
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').sort_index()
        
        # 添加技术指标
        df_reset = df.reset_index()
        df_reset = add_all_indicators(df_reset)
        df = df_reset.set_index('date')
        
        # 添加前收盘价
        df['prev_close'] = df['close'].shift(1)
        
        self.data[code] = df
    
    def run(self, start_date: str = None, end_date: str = None) -> dict:
        """
        运行回测
        
        Returns:
            绩效指标字典
        """
        if not self.data:
            raise ValueError("请先添加数据 (add_data)")
        
        # 初始化
        self.broker = SimBroker(self.initial_capital)
        self.risk_manager = RiskManager()
        self.risk_manager.account_peak = self.initial_capital
        self.equity_curve = {}
        
        # 确定回测日期范围
        all_dates = set()
        for code, df in self.data.items():
            all_dates.update(df.index)
        self.dates = sorted(all_dates)
        
        if start_date:
            self.dates = [d for d in self.dates if d >= pd.Timestamp(start_date)]
        if end_date:
            self.dates = [d for d in self.dates if d <= pd.Timestamp(end_date)]
        
        # 传递引用给策略
        self.strategy.broker = self.broker
        self.strategy.risk_manager = self.risk_manager
        self.strategy.data = self.data
        
        if hasattr(self.strategy, 'on_init'):
            self.strategy.on_init()
        
        # --- 逐日回测 ---
        for i, date in enumerate(self.dates):
            date_str = date.strftime('%Y-%m-%d')
            
            # 收集当日行情
            current_bars = {}
            for code, df in self.data.items():
                if date in df.index:
                    row = df.loc[date]
                    current_bars[code] = row.to_dict()
                    current_bars[code]['code'] = code
            
            if not current_bars:
                continue
            
            # 更新持仓最高价
            prices = {code: bar['close'] for code, bar in current_bars.items()}
            self.broker.update_highest_prices(prices)
            
            # 检查止损
            self._check_stop_losses(current_bars, date_str)
            
            # 检查账户回撤
            equity = self.broker.get_equity(prices)
            dd_check = self.risk_manager.check_account_drawdown(equity)
            
            # 调用策略
            context = {
                'date': date_str,
                'date_index': i,
                'bars': current_bars,
                'equity': equity,
                'cash': self.broker.cash,
                'positions': self.broker.positions_compat,
                'drawdown': dd_check['drawdown'],
                'is_halted': self.risk_manager.is_trading_halted,
            }
            
            self.strategy.on_bar(context)
            
            # 记录权益
            self.equity_curve[date_str] = equity
        
        # --- 生成绩效报告 ---
        equity_series = pd.Series(self.equity_curve)
        equity_series.index = pd.to_datetime(equity_series.index)
        
        closed_trades = self.broker.get_closed_trades()
        
        # 基准曲线
        benchmark_curve = None
        if self.benchmark_data is not None and len(self.benchmark_data) > 0:
            bench = self.benchmark_data.copy()
            if not isinstance(bench.index, pd.DatetimeIndex):
                bench.index = pd.to_datetime(bench.index)
            # 对齐到回测日期
            common = equity_series.index.intersection(bench.index)
            if len(common) > 10:
                bench_aligned = bench.loc[common, 'close']
                # 归一化为同起始资金
                benchmark_curve = bench_aligned / bench_aligned.iloc[0] * self.initial_capital
        
        metrics = self.performance.analyze(
            equity_curve=equity_series,
            trades=closed_trades,
            benchmark_curve=benchmark_curve,
        )
        
        metrics['broker_summary'] = self.broker.get_summary()
        metrics['equity_curve'] = equity_series
        metrics['benchmark_curve'] = benchmark_curve
        
        return metrics
    
    def _check_stop_losses(self, current_bars: dict, date_str: str):
        """检查所有持仓的止损条件"""
        codes_to_sell = []
        
        for code, pos_info in list(self.broker.positions_compat.items()):
            if code not in current_bars:
                continue
            
            bar = current_bars[code]
            
            position = Position(
                code=code,
                name=code,
                entry_price=pos_info['avg_price'],
                entry_date=pos_info['entry_date'],
                shares=pos_info['shares'],
                current_price=bar['close'],
                highest_price=pos_info.get('highest_price', bar['close']),
                atr_at_entry=bar.get('atr', 0),
                current_date=date_str,
            )
            
            # T+1: 当天买入不可卖
            if pos_info['entry_date'] == date_str:
                continue
            
            stop_result = self.risk_manager.check_stop_loss(position)
            
            if stop_result['should_stop']:
                codes_to_sell.append((code, stop_result['type'], bar, pos_info['shares']))
        
        for code, stop_type, bar, shares in codes_to_sell:
            self.broker.submit_order(
                code=code,
                direction='sell',
                shares=shares,
                price=bar['close'],
                date=date_str,
                bar_data={
                    'open': bar['open'],
                    'high': bar['high'],
                    'low': bar['low'],
                    'close': bar['close'],
                    'volume': bar.get('volume', 0),
                    'prev_close': bar.get('prev_close', bar['close']),
                },
                stop_type=stop_type,
            )
    
    def run_walk_forward(self, train_window: int = 252, test_window: int = 63,
                          step: int = 63) -> dict:
        """
        Walk-Forward滚动回测
        
        Args:
            train_window: 训练窗口（交易日）
            test_window: 测试窗口（交易日）
            step: 滚动步长
        
        Returns:
            各期测试结果的汇总
        """
        # 计算全量日期（不被 run() 覆盖）
        all_dates = set()
        for code, df in self.data.items():
            all_dates.update(df.index)
        full_dates = sorted(all_dates)
        
        results = []
        total_dates = len(full_dates)
        
        i = 0
        while i + train_window + test_window <= total_dates:
            train_start = full_dates[i]
            train_end = full_dates[i + train_window - 1]
            test_start = full_dates[i + train_window]
            test_end = full_dates[min(i + train_window + test_window - 1, total_dates - 1)]
            
            # 训练期：策略可以用此期间数据优化参数
            if hasattr(self.strategy, 'optimize'):
                train_data = {
                    code: df.loc[train_start:train_end]
                    for code, df in self.data.items()
                }
                self.strategy.optimize(train_data)
            
            # 测试期：用优化后的参数回测
            test_metrics = self.run(
                start_date=test_start.strftime('%Y-%m-%d'),
                end_date=test_end.strftime('%Y-%m-%d')
            )
            
            results.append({
                'train_start': train_start.strftime('%Y-%m-%d'),
                'train_end': train_end.strftime('%Y-%m-%d'),
                'test_start': test_start.strftime('%Y-%m-%d'),
                'test_end': test_end.strftime('%Y-%m-%d'),
                'return': test_metrics.get('total_return', 0),
                'sharpe': test_metrics.get('sharpe_ratio', 0),
                'max_dd': test_metrics.get('max_drawdown', 0),
            })
            
            i += step
        
        # 汇总
        if results:
            returns = [r['return'] for r in results]
            sharpes = [r['sharpe'] for r in results]
            summary = {
                'periods': len(results),
                'avg_return': np.mean(returns),
                'std_return': np.std(returns),
                'positive_periods': sum(1 for r in returns if r > 0),
                'avg_sharpe': np.mean(sharpes),
                'details': results,
            }
        else:
            summary = {'periods': 0, 'details': []}
        
        return summary
    
    def run_monte_carlo(self, n_simulations: int = 1000, 
                         base_metrics: dict = None) -> dict:
        """
        蒙特卡洛模拟
        基于历史交易记录随机重采样，评估策略稳健性
        
        Args:
            n_simulations: 模拟次数
            base_metrics: 基础回测结果
        
        Returns:
            模拟统计结果
        """
        closed_trades = self.broker.get_closed_trades() if self.broker else []
        
        if not closed_trades:
            return {'error': '无交易记录，无法进行蒙特卡洛模拟'}
        
        trade_returns = [t['pnl_pct'] for t in closed_trades]
        n_trades = len(trade_returns)
        
        final_returns = []
        max_drawdowns = []
        
        for _ in range(n_simulations):
            # 随机重采样交易序列
            sampled = np.random.choice(trade_returns, size=n_trades, replace=True)
            
            # 构建模拟权益曲线
            equity = [1.0]
            for r in sampled:
                equity.append(equity[-1] * (1 + r))
            
            equity = np.array(equity)
            final_returns.append(equity[-1] / equity[0] - 1)
            
            # 计算回撤
            peak = np.maximum.accumulate(equity)
            dd = (peak - equity) / peak
            max_drawdowns.append(dd.max())
        
        final_returns = np.array(final_returns)
        max_drawdowns = np.array(max_drawdowns)
        
        return {
            'n_simulations': n_simulations,
            'n_trades': n_trades,
            # 收益分布
            'return_mean': final_returns.mean(),
            'return_median': np.median(final_returns),
            'return_std': final_returns.std(),
            'return_5th': np.percentile(final_returns, 5),
            'return_25th': np.percentile(final_returns, 25),
            'return_75th': np.percentile(final_returns, 75),
            'return_95th': np.percentile(final_returns, 95),
            'prob_positive': (final_returns > 0).mean(),
            # 回撤分布
            'dd_mean': max_drawdowns.mean(),
            'dd_median': np.median(max_drawdowns),
            'dd_95th': np.percentile(max_drawdowns, 95),
            # 原始数据（用于绘图）
            'return_distribution': final_returns,
            'dd_distribution': max_drawdowns,
        }
