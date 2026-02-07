# ============================================================
# AI智能选股顾问系统 - 配置文件
# 支持环境变量覆盖（方便云端部署）
# ============================================================
import os

# --- DeepSeek API 配置 ---
# 优先级: 环境变量 > Streamlit Secrets > 默认值
def _get_secret(key, default=""):
    """从环境变量或Streamlit secrets获取配置"""
    val = os.getenv(key)
    if val:
        return val
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return default

DEEPSEEK_API_KEY = _get_secret("DEEPSEEK_API_KEY", "xxx")
DEEPSEEK_BASE_URL = _get_secret("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = _get_secret("DEEPSEEK_MODEL", "deepseek-chat")

# --- 交易成本配置（A股真实成本）---
COMMISSION_RATE = 0.00025       # 佣金费率 万2.5
COMMISSION_MIN = 5.0            # 最低佣金 5元
STAMP_TAX_RATE = 0.001          # 印花税 千分之一（仅卖出）
TRANSFER_FEE_RATE = 0.00001    # 过户费 万分之0.1
SLIPPAGE_RATE = 0.001           # 滑点 千分之一

# --- 风控参数 ---
MAX_DRAWDOWN_LIMIT = 0.15       # 账户最大回撤红线 15%
SINGLE_STOCK_MAX_LOSS = 0.08    # 个股最大止损 8%
TRAILING_STOP_RATIO = 0.10      # 跟踪止损回撤比例 10%
TIME_STOP_DAYS = 20             # 时间止损天数（持仓超过N天未盈利则止损）
MAX_SINGLE_POSITION = 0.25      # 单只股票最大仓位 25%
MAX_SECTOR_EXPOSURE = 0.40      # 单一行业最大敞口 40%
MAX_POSITIONS = 8               # 最大持仓数量

# --- 仓位管理 ---
POSITION_METHOD = "atr"         # 仓位方法: "kelly", "atr", "equal", "risk_parity"
ATR_RISK_PER_TRADE = 0.02       # ATR仓位法每笔交易风险比例
KELLY_FRACTION = 0.25           # Kelly公式使用比例（1/4 Kelly）

# --- 回测参数 ---
INITIAL_CAPITAL = 1000000       # 初始资金 100万
BENCHMARK = "sh000300"          # 基准指数：沪深300

# --- 数据源配置 ---
DATA_SOURCE = "akshare"         # "akshare" 或 "yfinance"
CACHE_DIR = "./data_cache"
