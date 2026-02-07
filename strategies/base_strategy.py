"""
策略基类
所有策略必须继承此类并实现 on_bar 方法
"""
from abc import ABC, abstractmethod
from typing import Dict
from core.position_manager import PositionManager


class BaseStrategy(ABC):
    """策略基类"""
    
    def __init__(self, name: str = "BaseStrategy", params: dict = None):
        self.name = name
        self.params = params or {}
        self.broker = None              # 由引擎注入
        self.risk_manager = None        # 由引擎注入
        self.data = None                # 由引擎注入
        self.position_manager = PositionManager()
    
    def on_init(self):
        """策略初始化（可选重写）"""
        pass
    
    @abstractmethod
    def on_bar(self, context: dict):
        """
        每个交易日调用一次
        
        context:
            date: str               当前日期
            date_index: int         日期索引
            bars: dict              当日所有股票行情 {code: {open,high,low,close,...}}
            equity: float           当前总权益
            cash: float             可用资金
            positions: dict         当前持仓
            drawdown: float         当前回撤
            is_halted: bool         是否停止交易
        """
        pass
    
    def optimize(self, train_data: dict):
        """Walk-Forward优化回调（可选重写）"""
        pass
    
    def buy(self, code: str, shares: int, price: float, date: str, bar_data: dict = None):
        """买入"""
        return self.broker.submit_order(
            code=code, direction='buy', shares=shares,
            price=price, date=date, bar_data=bar_data
        )
    
    def sell(self, code: str, shares: int, price: float, date: str,
             bar_data: dict = None, stop_type: str = ''):
        """卖出"""
        return self.broker.submit_order(
            code=code, direction='sell', shares=shares,
            price=price, date=date, bar_data=bar_data, stop_type=stop_type
        )
    
    def get_position(self, code: str) -> dict:
        """获取指定股票持仓"""
        return self.broker.positions_compat.get(code)
    
    def has_position(self, code: str) -> bool:
        """是否持有某只股票"""
        return code in self.broker.positions_compat
    
    def calc_buy_shares(self, code: str, price: float, context: dict, **kwargs) -> int:
        """根据仓位管理器计算建议买入股数"""
        result = self.position_manager.calculate_position_size(
            total_equity=context['equity'],
            price=price,
            **kwargs
        )
        
        # 根据回撤调整
        ratio = self.position_manager.adjust_for_drawdown(
            result['position_ratio'], context['drawdown']
        )
        
        shares = int(context['equity'] * ratio / price / 100) * 100
        
        # 确保不超过可用资金
        max_affordable = int(context['cash'] * 0.98 / price / 100) * 100
        shares = min(shares, max_affordable)
        
        return max(shares, 0)
