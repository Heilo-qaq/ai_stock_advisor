"""
绩效分析模块
计算各类投资绩效指标并生成报告
"""
import pandas as pd
import numpy as np
from utils.helpers import (calc_sharpe_ratio, calc_sortino_ratio, calc_max_drawdown,
                           calc_calmar_ratio, calc_annual_return, calc_win_rate)


class PerformanceAnalyzer:
    """绩效分析器"""
    
    def __init__(self, risk_free_rate: float = 0.03):
        self.risk_free_rate = risk_free_rate
    
    def analyze(self, equity_curve: pd.Series, trades: list = None,
                benchmark_curve: pd.Series = None) -> dict:
        """
        全面绩效分析
        
        Args:
            equity_curve: 每日权益曲线 (index=date, values=equity)
            trades: 交易记录列表
            benchmark_curve: 基准权益曲线
        
        Returns:
            完整的绩效指标字典
        """
        if len(equity_curve) < 2:
            return {}
        
        daily_returns = equity_curve.pct_change().dropna()
        
        # --- 基础收益指标 ---
        total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1
        trading_days = len(equity_curve)
        annual_return = calc_annual_return(total_return, trading_days)
        
        # --- 风险指标 ---
        volatility = daily_returns.std() * np.sqrt(252)
        max_dd, dd_start, dd_end, dd_duration = calc_max_drawdown(equity_curve)
        
        # --- 风险调整收益 ---
        sharpe = calc_sharpe_ratio(daily_returns, self.risk_free_rate)
        sortino = calc_sortino_ratio(daily_returns, self.risk_free_rate)
        calmar = calc_calmar_ratio(annual_return, max_dd)
        
        result = {
            # 收益指标
            'total_return': total_return,
            'annual_return': annual_return,
            'trading_days': trading_days,
            'final_equity': equity_curve.iloc[-1],
            
            # 风险指标
            'annual_volatility': volatility,
            'max_drawdown': max_dd,
            'max_drawdown_start': dd_start,
            'max_drawdown_end': dd_end,
            'max_drawdown_duration': dd_duration,
            
            # 风险调整收益
            'sharpe_ratio': sharpe,
            'sortino_ratio': sortino,
            'calmar_ratio': calmar,
            
            # 收益分布
            'skewness': daily_returns.skew(),
            'kurtosis': daily_returns.kurtosis(),
            'best_day': daily_returns.max(),
            'worst_day': daily_returns.min(),
            'positive_days_pct': (daily_returns > 0).mean(),
        }
        
        # --- 月度/年度收益 ---
        result['monthly_returns'] = self._monthly_returns(equity_curve)
        result['yearly_returns'] = self._yearly_returns(equity_curve)
        
        # --- 交易统计 ---
        if trades:
            result['trade_stats'] = calc_win_rate(trades)
        
        # --- 基准对比 ---
        if benchmark_curve is not None and len(benchmark_curve) > 1:
            result['benchmark'] = self._benchmark_comparison(
                daily_returns, equity_curve, benchmark_curve
            )
        
        return result
    
    def _monthly_returns(self, equity_curve: pd.Series) -> pd.DataFrame:
        """月度收益统计"""
        equity = equity_curve.copy()
        equity.index = pd.to_datetime(equity.index)
        
        monthly = equity.resample('M').last()
        monthly_ret = monthly.pct_change().dropna()
        
        # 创建年月矩阵
        df = pd.DataFrame({
            'year': monthly_ret.index.year,
            'month': monthly_ret.index.month,
            'return': monthly_ret.values
        })
        
        pivot = df.pivot_table(index='year', columns='month', values='return', aggfunc='sum')
        pivot.columns = [f'{m}月' for m in pivot.columns]
        
        return pivot
    
    def _yearly_returns(self, equity_curve: pd.Series) -> pd.Series:
        """年度收益统计"""
        equity = equity_curve.copy()
        equity.index = pd.to_datetime(equity.index)
        
        yearly = equity.resample('Y').last()
        return yearly.pct_change().dropna()
    
    def _benchmark_comparison(self, daily_returns: pd.Series,
                               equity_curve: pd.Series,
                               benchmark_curve: pd.Series) -> dict:
        """与基准对比分析"""
        bench_returns = benchmark_curve.pct_change().dropna()
        
        # 对齐日期
        common_idx = daily_returns.index.intersection(bench_returns.index)
        if len(common_idx) < 10:
            return {}
        
        strat_ret = daily_returns.loc[common_idx]
        bench_ret = bench_returns.loc[common_idx]
        
        # Alpha & Beta
        cov = np.cov(strat_ret, bench_ret)
        beta = cov[0, 1] / cov[1, 1] if cov[1, 1] != 0 else 0
        alpha = (strat_ret.mean() - beta * bench_ret.mean()) * 252
        
        # 超额收益
        excess = strat_ret - bench_ret
        
        # 信息比率
        tracking_error = excess.std() * np.sqrt(252)
        info_ratio = excess.mean() * 252 / tracking_error if tracking_error > 0 else 0
        
        # 基准总收益
        bench_total = (benchmark_curve.iloc[-1] / benchmark_curve.iloc[0]) - 1
        strat_total = (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1
        
        return {
            'alpha': alpha,
            'beta': beta,
            'information_ratio': info_ratio,
            'tracking_error': tracking_error,
            'benchmark_return': bench_total,
            'excess_return': strat_total - bench_total,
        }
    
    def format_report(self, metrics: dict) -> str:
        """格式化绩效报告为文本"""
        lines = []
        lines.append("=" * 60)
        lines.append("            策略回测绩效报告")
        lines.append("=" * 60)
        
        lines.append(f"\n📈 收益指标")
        lines.append(f"  总收益率:     {metrics.get('total_return', 0):.2%}")
        lines.append(f"  年化收益率:   {metrics.get('annual_return', 0):.2%}")
        lines.append(f"  最终净值:     {metrics.get('final_equity', 0):,.0f}")
        lines.append(f"  交易天数:     {metrics.get('trading_days', 0)}")
        
        lines.append(f"\n📉 风险指标")
        lines.append(f"  年化波动率:   {metrics.get('annual_volatility', 0):.2%}")
        lines.append(f"  最大回撤:     {metrics.get('max_drawdown', 0):.2%}")
        lines.append(f"  回撤持续:     {metrics.get('max_drawdown_duration', 0)}天")
        lines.append(f"  最佳单日:     {metrics.get('best_day', 0):.2%}")
        lines.append(f"  最差单日:     {metrics.get('worst_day', 0):.2%}")
        
        lines.append(f"\n⚖️ 风险调整收益")
        lines.append(f"  夏普比率:     {metrics.get('sharpe_ratio', 0):.3f}")
        lines.append(f"  索提诺比率:   {metrics.get('sortino_ratio', 0):.3f}")
        lines.append(f"  Calmar比率:   {metrics.get('calmar_ratio', 0):.3f}")
        
        if 'trade_stats' in metrics:
            ts = metrics['trade_stats']
            lines.append(f"\n🎯 交易统计")
            lines.append(f"  总交易次数:   {ts.get('total_trades', 0)}")
            lines.append(f"  胜率:         {ts.get('win_rate', 0):.1%}")
            lines.append(f"  平均盈利:     {ts.get('avg_win', 0):.2%}")
            lines.append(f"  平均亏损:     {ts.get('avg_loss', 0):.2%}")
            lines.append(f"  盈亏比:       {ts.get('profit_factor', 0):.2f}")
            lines.append(f"  期望收益:     {ts.get('expectancy', 0):.2%}")
            lines.append(f"  平均持仓:     {ts.get('avg_hold_days', 0):.1f}天")
            lines.append(f"  最大连胜:     {ts.get('max_consecutive_wins', 0)}次")
            lines.append(f"  最大连亏:     {ts.get('max_consecutive_losses', 0)}次")
        
        if 'benchmark' in metrics:
            bm = metrics['benchmark']
            lines.append(f"\n📊 基准对比 (沪深300)")
            lines.append(f"  Alpha:        {bm.get('alpha', 0):.2%}")
            lines.append(f"  Beta:         {bm.get('beta', 0):.3f}")
            lines.append(f"  信息比率:     {bm.get('information_ratio', 0):.3f}")
            lines.append(f"  超额收益:     {bm.get('excess_return', 0):.2%}")
        
        lines.append("\n" + "=" * 60)
        return "\n".join(lines)
