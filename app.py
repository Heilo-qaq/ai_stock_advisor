"""
AI智能选股顾问系统 v2 - 主界面
新增: 基准对比 · 大盘择时 · 策略对比 · 交易导出 · AI复盘
"""
import streamlit as st
import pandas as pd
import numpy as np
import json, io, os, sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from core.data_fetcher import fetch_stock_history, fetch_stock_info, fetch_index_history
from core.indicators import add_all_indicators, detect_signals
from core.risk_manager import RiskManager, Position, StopLossConfig
from core.position_manager import PositionManager
from core.portfolio_optimizer import PortfolioOptimizer
from core.performance import PerformanceAnalyzer
from core.market_filter import MarketFilter
from core.data_validator import validate_stock_data, clean_stock_data
from backtest.engine import BacktestEngine
from backtest.broker import SimBroker
from backtest.reporter import (
    generate_plotly_equity_chart, generate_drawdown_chart,
    generate_monthly_heatmap, generate_trade_distribution,
    generate_monte_carlo_chart,
)
from strategies.multi_factor import MultiFactorStrategy
from strategies.momentum import MomentumStrategy
from strategies.value_growth import ValueGrowthStrategy
from agents.ai_advisor import analyze_stock, multi_agent_analysis

# ============================================================
# session_state 配置持久化
# ============================================================
def _ss(key, default):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]

_ss('api_key', config.DEEPSEEK_API_KEY)
_ss('max_dd', int(config.MAX_DRAWDOWN_LIMIT * 100))
_ss('stop_loss', int(config.SINGLE_STOCK_MAX_LOSS * 100))
_ss('max_pos', int(config.MAX_SINGLE_POSITION * 100))
_ss('max_n', config.MAX_POSITIONS)
_ss('pos_method', config.POSITION_METHOD)
_ss('capital', config.INITIAL_CAPITAL)

def _sync_config():
    """同步session_state → config"""
    config.DEEPSEEK_API_KEY = st.session_state['api_key']
    config.MAX_DRAWDOWN_LIMIT = st.session_state['max_dd'] / 100
    config.SINGLE_STOCK_MAX_LOSS = st.session_state['stop_loss'] / 100
    config.MAX_SINGLE_POSITION = st.session_state['max_pos'] / 100
    config.MAX_POSITIONS = st.session_state['max_n']
    config.POSITION_METHOD = st.session_state['pos_method']
    config.INITIAL_CAPITAL = st.session_state['capital']

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(page_title="AI智能选股顾问", page_icon="🧠",
                   layout="wide", initial_sidebar_state="collapsed")

# ============================================================
# 移动端适配CSS
# ============================================================
st.markdown("""
<style>
/* 移动端全局适配 */
@media (max-width: 768px) {
    /* 主容器全宽 */
    .main .block-container {
        padding: 0.5rem 0.8rem !important;
        max-width: 100% !important;
    }
    /* 侧边栏在移动端默认收起 */
    [data-testid="stSidebar"] {
        min-width: 0px !important;
    }
    /* 指标卡片紧凑 */
    [data-testid="stMetric"] {
        padding: 0.3rem 0 !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.1rem !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.75rem !important;
    }
    /* 列布局移动端堆叠 */
    [data-testid="column"] {
        width: 100% !important;
        flex: 100% !important;
        min-width: 0 !important;
    }
    /* 表格横向滚动 */
    [data-testid="stDataFrame"] {
        overflow-x: auto !important;
    }
    /* Tab文字缩小 */
    .stTabs [data-baseweb="tab-list"] button {
        font-size: 0.8rem !important;
        padding: 0.3rem 0.5rem !important;
    }
    /* 输入框全宽 */
    .stTextInput, .stNumberInput, .stSelectbox {
        width: 100% !important;
    }
    /* 图表不溢出 */
    .js-plotly-plot, .plotly {
        width: 100% !important;
    }
    /* 按钮更大的点击区域 */
    .stButton button {
        width: 100% !important;
        padding: 0.6rem !important;
        font-size: 1rem !important;
    }
    /* 下载按钮 */
    .stDownloadButton button {
        width: 100% !important;
    }
}

/* 通用优化 */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.3rem;
    flex-wrap: wrap;
}
/* Plotly图表响应式 */
.js-plotly-plot .plotly .main-svg {
    width: 100% !important;
}
</style>
""", unsafe_allow_html=True)
st.title("🧠 AI智能选股顾问系统")
st.caption("融合多AI智能体 · 专业风控 · 量化回测验证 · 大盘择时")

# ============================================================
# 侧边栏
# ============================================================
with st.sidebar:
    st.header("⚙️ 系统设置")
    st.text_input("DeepSeek API Key", type="password", key="api_key")
    st.divider()

    st.subheader("🛡️ 风控参数")
    st.slider("账户最大回撤红线(%)", 5, 30, key="max_dd")
    st.slider("个股止损线(%)", 3, 15, key="stop_loss")
    st.slider("单股最大仓位(%)", 10, 40, step=5, key="max_pos")
    st.slider("最大持仓数量", 3, 15, key="max_n")
    st.divider()

    st.subheader("📊 仓位管理")
    st.selectbox("仓位方法", ["atr", "kelly", "risk_parity", "equal"], key="pos_method")
    st.divider()

    st.subheader("🔬 回测参数")
    st.number_input("初始资金", step=100000, format="%d", key="capital")

_sync_config()

# ============================================================
# 工具函数
# ============================================================
def _safe(val, default=0):
    try:
        v = float(val)
        return default if pd.isna(v) else v
    except (TypeError, ValueError):
        return default

def _make_bar_data(bar):
    return {
        'open': bar.get('open', bar['close']),
        'high': bar.get('high', bar['close']),
        'low': bar.get('low', bar['close']),
        'close': bar['close'],
        'volume': bar.get('volume', 0),
        'prev_close': bar.get('prev_close', bar['close']),
    }

def _load_stock_data(codes, start_str, end_str, progress_widget=None):
    """批量加载股票数据，带验证和清洗"""
    loaded = {}
    issues_log = []
    for i, code in enumerate(codes):
        if progress_widget:
            progress_widget.progress((i+1)/len(codes), text=f"加载 {code}...")
        df = fetch_stock_history(code, start_str, end_str)
        if df.empty:
            issues_log.append(f"❌ {code}: 无数据")
            continue
        # 验证
        check = validate_stock_data(df, code)
        if check['issues']:
            for iss in check['issues'][:2]:
                issues_log.append(f"⚠️ {code}: {iss}")
        if not check['valid']:
            issues_log.append(f"❌ {code}: 数据质量不合格，已跳过")
            continue
        df = clean_stock_data(df)
        if len(df) > 60:
            loaded[code] = df
        else:
            issues_log.append(f"⚠️ {code}: 数据不足60行")
    return loaded, issues_log

# ============================================================
# TABs
# ============================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 个股AI分析", "🎯 智能选股", "🔬 策略回测", "📈 组合优化", "📋 风控面板"
])

# ============================================================
# Tab 1: 个股AI分析
# ============================================================
with tab1:
    st.header("个股AI智能分析")

    col1, col2, col3 = st.columns([2, 2, 1])
    stock_code = col1.text_input("股票代码", value="600519", placeholder="输入6位代码")
    analysis_period = col2.selectbox("分析周期", ["近1年","近6个月","近3个月","近2年"])
    analysis_mode = col3.selectbox("分析模式", ["单AI分析","多智能体协作"])

    if st.button("🔍 开始分析", type="primary", key="analyze_btn"):
        days = {"近1年":365,"近6个月":180,"近3个月":90,"近2年":730}[analysis_period]
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        with st.spinner(f"获取 {stock_code} 数据..."):
            df = fetch_stock_history(stock_code, start_date, end_date)

        if df.empty:
            st.error(f"无法获取 {stock_code} 数据")
        else:
            df = clean_stock_data(df)
            df = add_all_indicators(df)
            signals = detect_signals(df)
            latest = df.iloc[-1]

            # 行情概览
            st.subheader("📈 行情概览")
            m1,m2,m3,m4,m5 = st.columns(5)
            m1.metric("最新价", f"¥{_safe(latest['close']):.2f}")
            pct = _safe(latest.get('pct_change',0))
            m2.metric("涨跌幅", f"{pct:.2f}%", delta=f"{pct:.2f}%")
            m3.metric("20日动量", f"{_safe(latest.get('momentum_20',0))*100:.1f}%")
            m4.metric("RSI(12)", f"{_safe(latest.get('rsi12',50)):.1f}")
            m5.metric("ATR%", f"{_safe(latest.get('atr_pct',0))*100:.2f}%")

            # K线图
            st.subheader("📊 K线走势")
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                                vertical_spacing=0.03, row_heights=[0.6,0.2,0.2])
            fig.add_trace(go.Candlestick(
                x=df['date'], open=df['open'], high=df['high'],
                low=df['low'], close=df['close'], name='K线'), row=1, col=1)
            for ma, color in [('ma5','#FF6B6B'),('ma20','#4ECDC4'),('ma60','#FFE66D')]:
                if ma in df.columns:
                    fig.add_trace(go.Scatter(x=df['date'],y=df[ma],name=ma.upper(),
                        line=dict(color=color,width=1)), row=1, col=1)
            colors = ['#F44336' if c>=o else '#4CAF50' for c,o in zip(df['close'],df['open'])]
            fig.add_trace(go.Bar(x=df['date'],y=df['volume'],name='成交量',
                marker_color=colors), row=2, col=1)
            fig.add_trace(go.Bar(x=df['date'],y=df['macd_hist'],name='MACD柱',
                marker_color=['#F44336' if v>=0 else '#4CAF50' for v in df['macd_hist']]),
                row=3, col=1)
            fig.add_trace(go.Scatter(x=df['date'],y=df['macd_dif'],name='DIF',
                line=dict(color='#2196F3',width=1)), row=3, col=1)
            fig.add_trace(go.Scatter(x=df['date'],y=df['macd_dea'],name='DEA',
                line=dict(color='#FF9800',width=1)), row=3, col=1)
            fig.update_layout(height=700,template='plotly_white',
                xaxis_rangeslider_visible=False, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

            # 信号
            st.subheader("🔔 技术信号")
            scols = st.columns(3)
            for i,(sn,sd,st2,ss) in enumerate(signals.get('signals',[])):
                emoji = "🟢" if st2=='bullish' else "🔴" if st2=='bearish' else "⚪"
                scols[i%3].markdown(f"{emoji} **{sn}**: {sd}")
            score = signals.get('score',0)
            st.info(f"📊 综合评分: **{score}** → **{signals.get('rating','中性')}**")

            # AI分析
            st.subheader("🤖 AI智能分析")
            indicator_data = {}
            for k in ['close','ma5','ma10','ma20','ma60','macd_dif','macd_dea','macd_hist',
                       'rsi6','rsi12','kdj_k','kdj_d','kdj_j','boll_upper','boll_mid','boll_lower',
                       'atr','vol_ratio','momentum_5','momentum_20','volatility_20']:
                indicator_data[k] = _safe(latest.get(k, 0))

            if config.DEEPSEEK_API_KEY == "your-api-key-here":
                st.warning("⚠️ 请在侧边栏设置 DeepSeek API Key")
            else:
                with st.spinner("AI分析中..."):
                    if analysis_mode == "单AI分析":
                        result = analyze_stock(stock_code, stock_code, indicator_data, signals)
                    else:
                        result = multi_agent_analysis(stock_code, stock_code, indicator_data, signals)

                rec = result.get('recommendation','观望')
                conf = result.get('confidence',0)
                colors_map = {'买入':'🟢','持有':'🔵','卖出':'🔴','观望':'⚪'}
                st.markdown(f"### {colors_map.get(rec,'⚪')} 建议: **{rec}** | 置信度: **{conf:.0%}**")
                st.markdown(f"**分析摘要:** {result.get('summary','N/A')}")
                for r in result.get('reasons',[]):
                    st.markdown(f"  - {r}")
                if result.get('risks'):
                    st.markdown("**风险提示:**")
                    for r in result['risks']:
                        st.markdown(f"  - ⚠️ {r}")
                if 'agent_reports' in result:
                    with st.expander("查看各智能体报告"):
                        for agent, report in result['agent_reports'].items():
                            st.markdown(f"**{agent}:**")
                            st.text(str(report)[:800])
                            st.divider()

# ============================================================
# Tab 2: 智能选股
# ============================================================
with tab2:
    st.header("🎯 AI智能选股")
    stock_input = st.text_area("候选股票代码（每行一个或逗号分隔）",
        value="600519\n000858\n601318\n000333\n300750\n002714\n600036\n000001", height=150)
    sel_col1, sel_col2 = st.columns(2)
    screening_criteria = sel_col1.text_input("筛选条件",
        value="选出趋势向上、技术面健康、近期有放量突破迹象的股票")
    top_n = sel_col2.slider("选股数量", 1, 10, 5)

    if st.button("🎯 开始选股", type="primary", key="screen_btn"):
        codes = [c.strip() for c in stock_input.replace(',','\n').replace('，','\n').split('\n') if c.strip()]
        if not codes:
            st.warning("请输入至少一个股票代码")
        else:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now()-timedelta(days=365)).strftime('%Y-%m-%d')
            results = []
            progress = st.progress(0, text="正在分析...")
            for i, code in enumerate(codes):
                progress.progress((i+1)/len(codes), text=f"分析 {code}...")
                df = fetch_stock_history(code, start_date, end_date)
                if df.empty: continue
                df = clean_stock_data(df)
                df = add_all_indicators(df)
                signals = detect_signals(df)
                latest = df.iloc[-1]
                results.append({
                    '代码': code,
                    '最新价': _safe(latest['close']),
                    '综合评分': signals['score'],
                    '评级': signals['rating'],
                    '20日动量': f"{_safe(latest.get('momentum_20',0))*100:.1f}%",
                    'RSI(12)': f"{_safe(latest.get('rsi12',50)):.1f}",
                    '量比': f"{_safe(latest.get('vol_ratio',1)):.1f}",
                    '波动率': f"{_safe(latest.get('volatility_20',0))*100:.1f}%",
                    'MACD': '多' if _safe(latest.get('macd_hist',0))>0 else '空',
                    '均线': '多' if _safe(latest.get('ma5',0))>_safe(latest.get('ma20',0)) else '空',
                })
            progress.empty()
            if results:
                results.sort(key=lambda x: x['综合评分'], reverse=True)
                st.subheader("📊 多因子评分结果")
                st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
                st.subheader(f"🏆 Top {top_n} 推荐")
                for r in results[:top_n]:
                    emoji = "🟢" if r['综合评分']>=3 else "🟡" if r['综合评分']>=0 else "🔴"
                    st.markdown(f"{emoji} **{r['代码']}** | 评分 {r['综合评分']} | {r['评级']} | 动量 {r['20日动量']}")

# ============================================================
# Tab 3: 策略回测 (大幅增强)
# ============================================================
with tab3:
    st.header("🔬 策略历史回测")

    bt_col1, bt_col2, bt_col3 = st.columns(3)
    strategy_choice = bt_col1.selectbox("选择策略",
        ["多因子选股策略","动量策略","价值成长策略","📊 多策略对比"])
    bt_start = bt_col2.date_input("回测开始", value=datetime(2023,1,1))
    bt_end = bt_col3.date_input("回测结束", value=datetime.now())

    bt_stocks = st.text_area("回测股票池（每行一个代码）",
        value="600519\n000858\n601318\n000333\n300750\n600036\n000001\n002475\n600887\n000568",
        height=120)

    bt_adv = st.expander("高级设置")
    with bt_adv:
        ac1,ac2,ac3,ac4 = st.columns(4)
        rebalance_period = ac1.number_input("调仓周期(天)", value=20, min_value=1, max_value=60)
        top_n_bt = ac2.number_input("选股数量", value=5, min_value=1, max_value=10)
        run_mc = ac3.checkbox("蒙特卡洛模拟", value=True)
        run_ai_review = ac4.checkbox("AI复盘", value=False)
        use_market_filter = st.checkbox("启用大盘择时过滤（沪深300）", value=False)

    if st.button("🚀 运行回测", type="primary", key="bt_btn"):
        codes = [c.strip() for c in bt_stocks.split('\n') if c.strip()]
        if not codes:
            st.warning("请输入回测股票池")
        else:
            start_str = bt_start.strftime('%Y-%m-%d')
            end_str = bt_end.strftime('%Y-%m-%d')
            params = {'rebalance_period': rebalance_period, 'top_n': top_n_bt}

            # --- 加载数据 ---
            progress = st.progress(0, text="加载数据中...")
            loaded, issues = _load_stock_data(codes, start_str, end_str, progress)

            if issues:
                with st.expander(f"📋 数据加载日志 ({len(issues)}条)"):
                    for iss in issues:
                        st.caption(iss)

            if not loaded:
                st.error("无法加载任何有效数据")
            else:
                progress.progress(1.0, text=f"已加载 {len(loaded)}/{len(codes)} 只，开始回测...")

                # --- 加载基准 ---
                bench_df = fetch_index_history('sh000300', start_str, end_str)

                # --- 运行策略 ---
                strategies_to_run = {}
                if strategy_choice == "📊 多策略对比":
                    strategies_to_run = {
                        "多因子": MultiFactorStrategy(params),
                        "动量": MomentumStrategy(params),
                        "价值成长": ValueGrowthStrategy(params),
                    }
                else:
                    name_map = {"多因子选股策略": MultiFactorStrategy,
                                "动量策略": MomentumStrategy,
                                "价值成长策略": ValueGrowthStrategy}
                    cls = name_map[strategy_choice]
                    strategies_to_run = {strategy_choice: cls(params)}

                all_results = {}
                for sname, strategy in strategies_to_run.items():
                    engine = BacktestEngine(strategy, config.INITIAL_CAPITAL)
                    for code, df in loaded.items():
                        engine.add_data(code, df)
                    if bench_df is not None and not bench_df.empty:
                        bdf = bench_df.copy()
                        bdf['date'] = pd.to_datetime(bdf['date'])
                        engine.benchmark_data = bdf.set_index('date')

                    with st.spinner(f"回测 [{sname}] ..."):
                        metrics = engine.run(start_str, end_str)

                    metrics['_engine'] = engine
                    all_results[sname] = metrics

                progress.empty()

                # ============================================================
                # 显示结果
                # ============================================================
                if len(all_results) > 1:
                    # --- 多策略对比 ---
                    st.subheader("📊 策略对比")
                    compare_rows = []
                    for sname, m in all_results.items():
                        ts = m.get('trade_stats', {})
                        compare_rows.append({
                            '策略': sname,
                            '总收益': f"{m.get('total_return',0):.2%}",
                            '年化收益': f"{m.get('annual_return',0):.2%}",
                            '夏普': f"{m.get('sharpe_ratio',0):.3f}",
                            '最大回撤': f"{m.get('max_drawdown',0):.2%}",
                            'Calmar': f"{m.get('calmar_ratio',0):.3f}",
                            '胜率': f"{ts.get('win_rate',0):.1%}",
                            '盈亏比': f"{ts.get('profit_factor',0):.2f}",
                            '交易数': ts.get('total_trades',0),
                        })
                    st.dataframe(pd.DataFrame(compare_rows), use_container_width=True, hide_index=True)

                    # 叠加净值曲线
                    import plotly.graph_objects as go2
                    fig_cmp = go2.Figure()
                    color_cycle = ['#2196F3','#FF5722','#4CAF50','#9C27B0']
                    for i,(sname,m) in enumerate(all_results.items()):
                        eq = m.get('equity_curve')
                        if eq is not None:
                            norm = eq / eq.iloc[0]
                            fig_cmp.add_trace(go2.Scatter(x=norm.index, y=norm.values,
                                name=sname, line=dict(color=color_cycle[i%4], width=2)))
                    # 基准
                    bench_curve = list(all_results.values())[0].get('benchmark_curve')
                    if bench_curve is not None:
                        norm_b = bench_curve / bench_curve.iloc[0]
                        fig_cmp.add_trace(go2.Scatter(x=norm_b.index, y=norm_b.values,
                            name='沪深300', line=dict(color='#999', width=1.5, dash='dot')))
                    fig_cmp.update_layout(title='策略净值对比', height=450,
                        template='plotly_white', yaxis_title='净值')
                    st.plotly_chart(fig_cmp, use_container_width=True)

                # --- 逐策略详细结果 ---
                for sname, metrics in all_results.items():
                    if len(all_results) > 1:
                        st.divider()
                        st.subheader(f"📋 {sname} 详情")

                    # 核心指标
                    c1,c2,c3,c4,c5,c6 = st.columns(6)
                    c1.metric("总收益率", f"{metrics.get('total_return',0):.2%}")
                    c2.metric("年化收益", f"{metrics.get('annual_return',0):.2%}")
                    c3.metric("夏普比率", f"{metrics.get('sharpe_ratio',0):.3f}")
                    c4.metric("最大回撤", f"{metrics.get('max_drawdown',0):.2%}")
                    c5.metric("Calmar", f"{metrics.get('calmar_ratio',0):.3f}")
                    c6.metric("Sortino", f"{metrics.get('sortino_ratio',0):.3f}")

                    # 交易统计
                    ts = metrics.get('trade_stats', {})
                    if ts:
                        t1,t2,t3,t4 = st.columns(4)
                        t1.metric("总交易", ts.get('total_trades',0))
                        t2.metric("胜率", f"{ts.get('win_rate',0):.1%}")
                        t3.metric("盈亏比", f"{ts.get('profit_factor',0):.2f}")
                        t4.metric("期望收益", f"{ts.get('expectancy',0):.2%}")

                    # Alpha/Beta
                    bm = metrics.get('benchmark')
                    if bm:
                        b1,b2,b3 = st.columns(3)
                        b1.metric("Alpha", f"{bm.get('alpha',0):.2%}")
                        b2.metric("Beta", f"{bm.get('beta',0):.3f}")
                        b3.metric("超额收益", f"{bm.get('excess_return',0):.2%}")

                    # 成本
                    bs = metrics.get('broker_summary',{})
                    co1,co2 = st.columns(2)
                    co1.metric("总佣金", f"¥{bs.get('total_commissions',0):,.0f}")
                    co2.metric("总印花税", f"¥{bs.get('total_stamp_tax',0):,.0f}")

                    # 净值曲线 + 基准
                    equity_curve = metrics.get('equity_curve')
                    bench_curve = metrics.get('benchmark_curve')
                    if equity_curve is not None:
                        fig_eq = generate_plotly_equity_chart(
                            equity_curve, bench_curve,
                            title=f"{sname} 净值曲线")
                        st.plotly_chart(fig_eq, use_container_width=True)
                        fig_dd = generate_drawdown_chart(equity_curve)
                        st.plotly_chart(fig_dd, use_container_width=True)

                    # 月度热力图
                    monthly = metrics.get('monthly_returns')
                    if monthly is not None and not monthly.empty:
                        fig_m = generate_monthly_heatmap(monthly)
                        if fig_m:
                            st.plotly_chart(fig_m, use_container_width=True)

                    # 交易分布
                    engine = metrics.get('_engine')
                    closed_trades = engine.broker.get_closed_trades() if engine else []
                    if closed_trades:
                        fig_td = generate_trade_distribution(closed_trades)
                        if fig_td:
                            st.plotly_chart(fig_td, use_container_width=True)

                    # 交易明细导出
                    if engine:
                        trades_df = engine.broker.get_trades_df()
                        if not trades_df.empty:
                            with st.expander("📋 交易明细"):
                                st.dataframe(trades_df, use_container_width=True, hide_index=True)
                                csv_buf = io.StringIO()
                                trades_df.to_csv(csv_buf, index=False, encoding='utf-8-sig')
                                st.download_button(
                                    f"⬇️ 导出CSV ({sname})",
                                    csv_buf.getvalue(),
                                    f"trades_{sname}.csv",
                                    "text/csv"
                                )

                    # 蒙特卡洛
                    if run_mc and closed_trades:
                        st.markdown("#### 🎲 蒙特卡洛模拟")
                        with st.spinner("模拟中..."):
                            mc = engine.run_monte_carlo(n_simulations=1000)
                        if 'error' not in mc:
                            mc1,mc2,mc3,mc4 = st.columns(4)
                            mc1.metric("盈利概率", f"{mc['prob_positive']:.1%}")
                            mc2.metric("收益中位数", f"{mc['return_median']:.2%}")
                            mc3.metric("5%分位", f"{mc['return_5th']:.2%}")
                            mc4.metric("95%分位回撤", f"{mc['dd_95th']:.2%}")
                            fig_mc = generate_monte_carlo_chart(mc)
                            if fig_mc:
                                st.plotly_chart(fig_mc, use_container_width=True)

                    # AI复盘
                    if run_ai_review and config.DEEPSEEK_API_KEY != "your-api-key-here":
                        st.markdown("#### 🤖 AI复盘分析")
                        with st.spinner("AI复盘中..."):
                            from agents.post_analysis import analyze_backtest_result
                            review = analyze_backtest_result(
                                metrics, sname, ts, bs)
                        st.markdown(review)

                    # 完整报告
                    with st.expander("📋 完整文本报告"):
                        analyzer = PerformanceAnalyzer()
                        report = analyzer.format_report(metrics)
                        st.code(report)

# ============================================================
# Tab 4: 组合优化
# ============================================================
with tab4:
    st.header("📈 投资组合优化")
    port_stocks = st.text_area("组合股票代码（每行一个）",
        value="600519\n000858\n601318\n000333\n300750", height=100, key="port_stocks")
    opt_col1, opt_col2 = st.columns(2)
    opt_method = opt_col1.selectbox("优化方法",
        ["最大夏普比率 (max_sharpe)","最小方差 (min_variance)","风险平价 (risk_parity)"])
    opt_period = opt_col2.selectbox("历史数据周期", ["近1年","近2年","近3年"])

    if st.button("🔧 优化组合", type="primary", key="opt_btn"):
        codes = [c.strip() for c in port_stocks.split('\n') if c.strip()]
        if len(codes) < 2:
            st.warning("至少需要2只股票")
        else:
            days = {"近1年":365,"近2年":730,"近3年":1095}[opt_period]
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now()-timedelta(days=days)).strftime('%Y-%m-%d')

            returns_data = {}
            with st.spinner("获取数据中..."):
                for code in codes:
                    df = fetch_stock_history(code, start_date, end_date)
                    if not df.empty:
                        df['date'] = pd.to_datetime(df['date'])
                        df = df.set_index('date')
                        returns_data[code] = df['close'].pct_change().dropna()

            if len(returns_data) < 2:
                st.error("数据不足")
            else:
                returns_df = pd.DataFrame(returns_data).dropna()
                optimizer = PortfolioOptimizer()
                method_map = {"最大夏普比率 (max_sharpe)":"max_sharpe",
                    "最小方差 (min_variance)":"min_variance",
                    "风险平价 (risk_parity)":"risk_parity"}
                result = optimizer.optimize(returns_df, method=method_map[opt_method])

                weights = result.get('weights',{})
                if weights:
                    st.subheader("📊 最优权重")
                    w_df = pd.DataFrame([
                        {'股票': k, '权重': f"{v:.1%}", '权重值': v}
                        for k,v in sorted(weights.items(), key=lambda x:x[1], reverse=True)
                    ])
                    import plotly.express as px
                    fig_pie = px.pie(w_df, values='权重值', names='股票', title='组合权重分布')
                    st.plotly_chart(fig_pie, use_container_width=True)
                    st.dataframe(w_df[['股票','权重']], hide_index=True)

                p1,p2,p3 = st.columns(3)
                p1.metric("预期年化收益", f"{result.get('expected_return',0):.2%}")
                p2.metric("预期年化波动", f"{result.get('expected_volatility',0):.2%}")
                p3.metric("夏普比率", f"{result.get('sharpe_ratio',0):.3f}")

                corr = result.get('correlation_matrix')
                if corr is not None:
                    st.subheader("🔗 相关性矩阵")
                    import plotly.figure_factory as ff
                    fig_corr = ff.create_annotated_heatmap(
                        z=corr.values, x=list(corr.columns), y=list(corr.index),
                        colorscale='RdYlGn', zmid=0,
                        annotation_text=[[f"{v:.2f}" for v in row] for row in corr.values])
                    fig_corr.update_layout(height=400)
                    st.plotly_chart(fig_corr, use_container_width=True)

                high_corr = optimizer.check_correlation(returns_df, threshold=0.7)
                if high_corr:
                    st.warning("⚠️ 高相关性股票对 (>0.7):")
                    for s1,s2,c in high_corr:
                        st.markdown(f"  - {s1} ↔ {s2}: **{c:.3f}**")

# ============================================================
# Tab 5: 风控面板
# ============================================================
with tab5:
    st.header("🛡️ 风控监控面板")

    st.subheader("当前风控参数")
    rc1,rc2,rc3,rc4 = st.columns(4)
    rc1.metric("最大回撤红线", f"{config.MAX_DRAWDOWN_LIMIT:.0%}")
    rc2.metric("个股止损线", f"{config.SINGLE_STOCK_MAX_LOSS:.0%}")
    rc3.metric("单股最大仓位", f"{config.MAX_SINGLE_POSITION:.0%}")
    rc4.metric("最大持仓数", f"{config.MAX_POSITIONS}")

    # 大盘状态
    st.divider()
    st.subheader("🌍 大盘状态 (沪深300)")
    mf = MarketFilter()
    bench_data = fetch_index_history('sh000300',
        (datetime.now()-timedelta(days=365)).strftime('%Y-%m-%d'),
        datetime.now().strftime('%Y-%m-%d'))
    if bench_data is not None and not bench_data.empty:
        mf.set_index_data(bench_data)
        detail = mf.get_regime_detail(datetime.now().strftime('%Y-%m-%d'))
        mr1,mr2,mr3 = st.columns(3)
        mr1.metric("市场状态", detail['label'])
        mr2.metric("仓位系数", f"{detail['position_multiplier']:.0%}")
        mr3.metric("指数", f"{detail['index_close']:.0f}")
        st.caption(detail['detail'])
    else:
        st.info("无法获取沪深300数据")

    st.divider()

    # 止损模拟器
    st.subheader("🔧 止损模拟器")
    sim_col1,sim_col2,sim_col3,sim_col4 = st.columns(4)
    sim_entry = sim_col1.number_input("买入价格", value=50.0, step=0.1)
    sim_current = sim_col2.number_input("当前价格", value=46.0, step=0.1)
    sim_highest = sim_col3.number_input("持仓最高价", value=55.0, step=0.1)
    sim_days = sim_col4.number_input("持仓天数", value=25, step=1)
    sim_atr = st.number_input("买入时ATR", value=1.5, step=0.1)

    if st.button("检查止损", key="sl_btn"):
        rm = RiskManager()
        pos = Position(
            code='TEST', name='测试', entry_price=sim_entry,
            entry_date=(datetime.now()-timedelta(days=sim_days)).strftime('%Y-%m-%d'),
            shares=1000, current_price=sim_current,
            highest_price=sim_highest, atr_at_entry=sim_atr)
        result = rm.check_stop_loss(pos)
        pnl_pct = (sim_current-sim_entry)/sim_entry
        trail_dd = (sim_highest-sim_current)/sim_highest if sim_highest>0 else 0

        st.markdown(f"**盈亏:** {pnl_pct:.2%} | **从最高回撤:** {trail_dd:.2%} | "
                    f"**ATR止损价:** {sim_entry-2*sim_atr:.2f}")
        if result['should_stop']:
            st.error(f"⚠️ 触发止损！ {result['reason']} ({result['type']})")
        else:
            st.success("✅ 未触发止损")

    st.divider()

    # 仓位计算器
    st.subheader("📊 仓位计算器")
    pm_col1,pm_col2,pm_col3 = st.columns(3)
    pm_equity = pm_col1.number_input("账户总权益", value=1000000, step=10000)
    pm_price = pm_col2.number_input("股票价格", value=50.0, step=0.1)
    pm_atr2 = pm_col3.number_input("ATR值", value=1.5, step=0.1, key="pm_atr2")
    pm_method = st.selectbox("仓位方法", ["atr","kelly","risk_parity","equal"], key="pm_m2")

    if st.button("计算仓位", key="pos_btn"):
        pm = PositionManager(method=pm_method)
        r = pm.calculate_position_size(total_equity=pm_equity, price=pm_price,
            atr=pm_atr2, volatility=0.3, win_rate=0.55, avg_win=0.08, avg_loss=0.05)
        st.markdown(
            f"**方法:** {r['method']} | **仓位:** {r['position_ratio']:.1%} | "
            f"**金额:** ¥{r['position_value']:,.0f} | **股数:** {r['shares']}股 | "
            f"**风险:** ¥{r['risk_amount']:,.0f} ({r['risk_pct_of_equity']:.2%})")
        batches = pm.suggest_scale_in_plan(r['position_ratio'], pm_price, pm_atr2)
        for b in batches:
            st.caption(f"第{b['batch']}批 ({b['ratio']:.0%}): {b['trigger']} | {b['price_range']}")

# ============================================================
st.divider()
st.caption("⚠️ 本系统仅供学习研究，AI建议需经回测验证，投资有风险，入市需谨慎。")
