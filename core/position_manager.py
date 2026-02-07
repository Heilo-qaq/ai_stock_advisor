"""
仓位管理模块
支持多种仓位计算方法：Kelly, ATR, 等权, 风险平价
"""
import numpy as np
import pandas as pd
import config


class PositionManager:
    """仓位管理器"""
    
    def __init__(self, method: str = None):
        self.method = method or config.POSITION_METHOD
        self.atr_risk = config.ATR_RISK_PER_TRADE
        self.kelly_fraction = config.KELLY_FRACTION
        self.max_position = config.MAX_SINGLE_POSITION
    
    def calculate_position_size(self, total_equity: float, price: float,
                                 atr: float = None, win_rate: float = None,
                                 avg_win: float = None, avg_loss: float = None,
                                 volatility: float = None) -> dict:
        """
        计算建议仓位大小
        
        Args:
            total_equity: 总权益
            price: 当前股价
            atr: ATR值
            win_rate: 历史胜率
            avg_win: 平均盈利比例
            avg_loss: 平均亏损比例
            volatility: 年化波动率
        
        Returns:
            {
                'method': str,
                'position_ratio': float,   # 建议仓位比例
                'position_value': float,    # 建议仓位金额
                'shares': int,              # 建议股数（100的整数倍）
                'risk_amount': float,       # 该仓位的风险金额
            }
        """
        if self.method == "kelly":
            ratio = self._kelly_sizing(win_rate, avg_win, avg_loss)
        elif self.method == "atr":
            ratio = self._atr_sizing(total_equity, price, atr)
        elif self.method == "risk_parity":
            ratio = self._risk_parity_sizing(volatility)
        else:  # equal
            ratio = self._equal_sizing()
        
        # 限制最大仓位
        ratio = min(ratio, self.max_position)
        ratio = max(ratio, 0)
        
        position_value = total_equity * ratio
        shares = int(position_value / price / 100) * 100  # A股100股整数倍
        actual_value = shares * price
        
        # 风险金额估算
        risk_amount = actual_value * (config.SINGLE_STOCK_MAX_LOSS if not atr else
                                       min(config.SINGLE_STOCK_MAX_LOSS, 2 * atr / price))
        
        return {
            'method': self.method,
            'position_ratio': ratio,
            'position_value': actual_value,
            'shares': shares,
            'risk_amount': risk_amount,
            'risk_pct_of_equity': risk_amount / total_equity if total_equity > 0 else 0
        }
    
    def _kelly_sizing(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """
        Kelly公式仓位计算
        f* = (p * b - q) / b
        其中 p=胜率, q=1-p, b=盈亏比
        使用 1/4 Kelly 降低风险
        """
        if not all([win_rate, avg_win, avg_loss]) or avg_loss == 0:
            return 0.1  # 默认10%
        
        p = win_rate
        q = 1 - p
        b = avg_win / avg_loss  # 盈亏比
        
        kelly = (p * b - q) / b
        
        # 负值说明策略不值得下注
        if kelly <= 0:
            return 0
        
        # 使用 fraction Kelly
        return kelly * self.kelly_fraction
    
    def _atr_sizing(self, total_equity: float, price: float, atr: float) -> float:
        """
        ATR仓位法
        每笔交易风险 = 总权益 * 风险比例
        仓位 = 风险金额 / (ATR * 倍数) / 价格
        """
        if not atr or atr == 0 or price == 0:
            return 0.1
        
        risk_amount = total_equity * self.atr_risk
        # 2倍ATR作为止损幅度
        stop_distance = 2 * atr
        shares_value = risk_amount / stop_distance * price
        
        return shares_value / total_equity
    
    def _risk_parity_sizing(self, volatility: float) -> float:
        """
        风险平价法
        仓位与波动率成反比，高波动低仓位
        """
        if not volatility or volatility == 0:
            return 0.1
        
        # 目标组合波动率20%，分配到单只股票
        target_vol = 0.20
        max_stocks = config.MAX_POSITIONS
        target_stock_vol = target_vol / np.sqrt(max_stocks)
        
        ratio = target_stock_vol / volatility
        return ratio
    
    def _equal_sizing(self) -> float:
        """等权分配"""
        return 1.0 / config.MAX_POSITIONS
    
    def adjust_for_drawdown(self, base_ratio: float, current_drawdown: float) -> float:
        """
        根据账户回撤动态调整仓位（赢冲输缩）
        回撤越大，仓位越小
        """
        if current_drawdown <= 0.05:
            # 回撤5%以内，正常仓位
            multiplier = 1.0
        elif current_drawdown <= 0.10:
            # 回撤5-10%，减半仓位
            multiplier = 0.5
        elif current_drawdown <= 0.15:
            # 回撤10-15%，四分之一仓位
            multiplier = 0.25
        else:
            # 超过15%，停止开仓
            multiplier = 0
        
        return base_ratio * multiplier
    
    def suggest_scale_in_plan(self, total_position: float, price: float,
                               atr: float) -> list:
        """
        分批建仓计划
        将总仓位分3批建立，降低择时风险
        """
        if atr is None or atr == 0:
            atr = price * 0.02  # 默认2%
        
        batches = [
            {
                'batch': 1,
                'ratio': 0.4,  # 第一批40%
                'trigger': '立即',
                'price_range': f"{price:.2f}",
            },
            {
                'batch': 2,
                'ratio': 0.3,  # 第二批30%
                'trigger': '确认支撑后加仓',
                'price_range': f"{price - atr:.2f} ~ {price:.2f}",
            },
            {
                'batch': 3,
                'ratio': 0.3,  # 第三批30%
                'trigger': '突破关键位加仓',
                'price_range': f"{price:.2f} ~ {price + atr:.2f}",
            }
        ]
        
        return batches
