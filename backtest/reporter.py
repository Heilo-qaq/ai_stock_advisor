"""
回测报告生成模块
生成可视化图表和文本报告
"""
import pandas as pd
import numpy as np


def generate_plotly_equity_chart(equity_curve: pd.Series, 
                                  benchmark: pd.Series = None,
                                  title: str = "策略净值曲线"):
    """生成权益曲线图（Plotly）"""
    import plotly.graph_objects as go
    
    fig = go.Figure()
    
    # 归一化
    norm_equity = equity_curve / equity_curve.iloc[0]
    
    fig.add_trace(go.Scatter(
        x=norm_equity.index, y=norm_equity.values,
        name='策略', line=dict(color='#2196F3', width=2)
    ))
    
    if benchmark is not None and len(benchmark) > 0:
        norm_bench = benchmark / benchmark.iloc[0]
        fig.add_trace(go.Scatter(
            x=norm_bench.index, y=norm_bench.values,
            name='基准(沪深300)', line=dict(color='#FF9800', width=1.5, dash='dot')
        ))
    
    fig.update_layout(
        title=title,
        xaxis_title='日期', yaxis_title='净值',
        template='plotly_white',
        height=400,
    )
    
    return fig


def generate_drawdown_chart(equity_curve: pd.Series):
    """生成回撤图"""
    import plotly.graph_objects as go
    
    peak = equity_curve.expanding(min_periods=1).max()
    drawdown = (equity_curve - peak) / peak
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=drawdown.index, y=drawdown.values,
        fill='tozeroy',
        name='回撤',
        line=dict(color='#F44336', width=1),
        fillcolor='rgba(244,67,54,0.3)'
    ))
    
    fig.update_layout(
        title='策略回撤',
        xaxis_title='日期', yaxis_title='回撤比例',
        template='plotly_white',
        height=300,
    )
    
    return fig


def generate_monthly_heatmap(monthly_returns: pd.DataFrame):
    """生成月度收益热力图"""
    import plotly.graph_objects as go
    
    if monthly_returns.empty:
        return None
    
    fig = go.Figure(data=go.Heatmap(
        z=monthly_returns.values * 100,
        x=monthly_returns.columns,
        y=monthly_returns.index.astype(str),
        colorscale='RdYlGn',
        zmid=0,
        text=[[f"{v:.1f}%" for v in row] for row in monthly_returns.values * 100],
        texttemplate="%{text}",
        hovertemplate="年份: %{y}<br>月份: %{x}<br>收益: %{text}<extra></extra>",
    ))
    
    fig.update_layout(
        title='月度收益热力图',
        template='plotly_white',
        height=300,
    )
    
    return fig


def generate_trade_distribution(trades: list):
    """生成交易收益分布图"""
    import plotly.graph_objects as go
    
    if not trades:
        return None
    
    pnl_pcts = [t['pnl_pct'] * 100 for t in trades]
    
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=pnl_pcts,
        nbinsx=30,
        marker_color=['#4CAF50' if x >= 0 else '#F44336' for x in pnl_pcts],
        name='交易收益分布'
    ))
    
    fig.add_vline(x=0, line_dash="dash", line_color="black")
    fig.add_vline(x=np.mean(pnl_pcts), line_dash="dot", line_color="blue",
                  annotation_text=f"均值: {np.mean(pnl_pcts):.1f}%")
    
    fig.update_layout(
        title='单笔交易收益分布',
        xaxis_title='收益率(%)', yaxis_title='次数',
        template='plotly_white',
        height=300,
    )
    
    return fig


def generate_monte_carlo_chart(mc_result: dict):
    """生成蒙特卡洛模拟分布图"""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    
    fig = make_subplots(rows=1, cols=2, subplot_titles=('收益率分布', '最大回撤分布'))
    
    # 收益分布
    returns = mc_result['return_distribution'] * 100
    fig.add_trace(go.Histogram(
        x=returns, nbinsx=50, name='模拟收益',
        marker_color='rgba(33,150,243,0.6)',
    ), row=1, col=1)
    
    fig.add_vline(x=mc_result['return_mean'] * 100, line_dash="dash",
                  line_color="red", row=1, col=1)
    
    # 回撤分布
    dds = mc_result['dd_distribution'] * 100
    fig.add_trace(go.Histogram(
        x=dds, nbinsx=50, name='模拟回撤',
        marker_color='rgba(244,67,54,0.6)',
    ), row=1, col=2)
    
    fig.update_layout(
        title=f'蒙特卡洛模拟 ({mc_result["n_simulations"]}次)',
        template='plotly_white',
        height=350,
        showlegend=False,
    )
    
    return fig
