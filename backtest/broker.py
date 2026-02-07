"""
模拟券商模块 v2
- 分笔T+1跟踪（加仓当天新增份额不可卖出）
- 真实涨跌停判定（收盘=涨停价且最高=涨停价→封板）
- 科创板/创业板20%涨跌停
- FIFO卖出
- 完整交易日志导出
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import config
import csv
import os


@dataclass
class Order:
    code: str
    direction: str
    price: float
    shares: int
    date: str
    order_type: str = 'market'
    status: str = 'pending'
    filled_price: float = 0
    commission: float = 0
    stamp_tax: float = 0
    slippage_cost: float = 0
    total_cost: float = 0
    reject_reason: str = ''


@dataclass
class TradeRecord:
    code: str
    direction: str
    price: float
    shares: int
    date: str
    commission: float
    stamp_tax: float
    total_cost: float
    pnl: float = 0
    pnl_pct: float = 0
    hold_days: int = 0
    stop_type: str = ''


@dataclass
class PositionLot:
    """持仓分笔（精确T+1）"""
    shares: int
    buy_price: float
    buy_date: str

    def sellable_on(self, date: str) -> int:
        return 0 if date == self.buy_date else self.shares


class SimBroker:
    def __init__(self, initial_capital: float = None):
        self.initial_capital = initial_capital or config.INITIAL_CAPITAL
        self.cash = self.initial_capital
        self.positions: Dict[str, dict] = {}  # {code: {lots: [PositionLot], highest_price}}
        self.trades: List[TradeRecord] = []
        self.orders: List[Order] = []
        self.equity_history: Dict[str, float] = {}

        self.commission_rate = config.COMMISSION_RATE
        self.commission_min = config.COMMISSION_MIN
        self.stamp_tax_rate = config.STAMP_TAX_RATE
        self.slippage_rate = config.SLIPPAGE_RATE

    # ── 兼容旧接口 ──────────────────────────────────────────
    def get_position_dict(self, code: str) -> Optional[dict]:
        pos = self.positions.get(code)
        if not pos or not pos['lots']:
            return None
        lots = pos['lots']
        total_shares = sum(l.shares for l in lots)
        if total_shares == 0:
            return None
        avg_price = sum(l.shares * l.buy_price for l in lots) / total_shares
        entry_date = min(l.buy_date for l in lots)
        return {
            'shares': total_shares,
            'avg_price': avg_price,
            'entry_date': entry_date,
            'highest_price': pos.get('highest_price', avg_price),
        }

    @property
    def positions_compat(self) -> Dict[str, dict]:
        result = {}
        for code in list(self.positions.keys()):
            d = self.get_position_dict(code)
            if d:
                result[code] = d
        return result

    # ── 下单 ────────────────────────────────────────────────
    def submit_order(self, code: str, direction: str, shares: int,
                     price: float, date: str, bar_data: dict = None,
                     stop_type: str = '') -> Order:
        order = Order(code=code, direction=direction, price=price,
                      shares=shares, date=date)

        if shares % 100 != 0 or shares <= 0:
            return self._reject(order, f'股数须100整数倍，当前{shares}')

        # 卖出校验
        if direction == 'sell':
            sellable = self._sellable_shares(code, date)
            if sellable <= 0:
                return self._reject(order, '无可卖持仓（T+1限制或无仓）')
            if shares > sellable:
                shares = (sellable // 100) * 100
                if shares <= 0:
                    return self._reject(order, f'可卖{sellable}股不足100股')
                order.shares = shares

        # 涨跌停
        limit_msg = self._check_limit(code, direction, bar_data)
        if limit_msg:
            return self._reject(order, limit_msg)

        # 成交
        filled_price = self._fill_price(price, direction, bar_data)
        trade_amount = filled_price * shares
        commission = max(trade_amount * self.commission_rate, self.commission_min)
        stamp_tax = trade_amount * self.stamp_tax_rate if direction == 'sell' else 0
        slippage_cost = trade_amount * self.slippage_rate
        total_cost = commission + stamp_tax + slippage_cost

        if direction == 'buy' and trade_amount + total_cost > self.cash:
            return self._reject(order,
                f'资金不足：需{trade_amount+total_cost:,.0f}，可用{self.cash:,.0f}')

        order.status = 'filled'
        order.filled_price = filled_price
        order.commission = commission
        order.stamp_tax = stamp_tax
        order.slippage_cost = slippage_cost
        order.total_cost = total_cost

        if direction == 'buy':
            self._exec_buy(code, shares, filled_price, date, total_cost)
            self.trades.append(TradeRecord(
                code=code, direction='buy', price=filled_price,
                shares=shares, date=date, commission=commission,
                stamp_tax=0, total_cost=total_cost))
        else:
            pnl, pnl_pct, hold_days = self._exec_sell(
                code, shares, filled_price, date, total_cost)
            self.trades.append(TradeRecord(
                code=code, direction='sell', price=filled_price,
                shares=shares, date=date, commission=commission,
                stamp_tax=stamp_tax, total_cost=total_cost,
                pnl=pnl, pnl_pct=pnl_pct, hold_days=hold_days,
                stop_type=stop_type))

        self.orders.append(order)
        return order

    def _reject(self, order, reason):
        order.status = 'rejected'
        order.reject_reason = reason
        self.orders.append(order)
        return order

    # ── 执行 ────────────────────────────────────────────────
    def _exec_buy(self, code, shares, price, date, cost):
        self.cash -= (price * shares + cost)
        if code not in self.positions:
            self.positions[code] = {'lots': [], 'highest_price': price}
        self.positions[code]['lots'].append(
            PositionLot(shares=shares, buy_price=price, buy_date=date))
        self.positions[code]['highest_price'] = max(
            self.positions[code]['highest_price'], price)

    def _exec_sell(self, code, shares, price, date, cost):
        pos = self.positions[code]
        remaining = shares
        total_cost_basis = 0
        earliest_buy = date

        # FIFO
        new_lots = []
        for lot in pos['lots']:
            if remaining <= 0:
                new_lots.append(lot)
                continue
            sellable = lot.sellable_on(date)
            sell_qty = min(sellable, remaining)
            if sell_qty > 0:
                total_cost_basis += sell_qty * lot.buy_price
                earliest_buy = min(earliest_buy, lot.buy_date)
                remaining -= sell_qty
                lot.shares -= sell_qty
            if lot.shares > 0:
                new_lots.append(lot)

        pos['lots'] = new_lots
        self.cash += (price * shares - cost)

        if not pos['lots'] or sum(l.shares for l in pos['lots']) == 0:
            del self.positions[code]

        pnl = price * shares - total_cost_basis - cost
        pnl_pct = pnl / total_cost_basis if total_cost_basis > 0 else 0
        hold_days = (pd.Timestamp(date) - pd.Timestamp(earliest_buy)).days
        return pnl, pnl_pct, hold_days

    def _sellable_shares(self, code, date):
        pos = self.positions.get(code)
        if not pos:
            return 0
        return sum(lot.sellable_on(date) for lot in pos['lots'])

    # ── 涨跌停 ──────────────────────────────────────────────
    def _check_limit(self, code, direction, bar_data):
        if not bar_data or 'prev_close' not in bar_data:
            return ''
        prev_close = bar_data['prev_close']
        if not prev_close or prev_close <= 0:
            return ''

        close = bar_data.get('close', 0)
        high = bar_data.get('high', close)
        low = bar_data.get('low', close)
        is_st = bar_data.get('is_st', False)

        is_20pct = str(code).startswith(('688', '300'))
        limit_pct = 0.05 if is_st else (0.20 if is_20pct else 0.10)

        limit_up = round(prev_close * (1 + limit_pct), 2)
        limit_down = round(prev_close * (1 - limit_pct), 2)

        if direction == 'buy':
            if close >= limit_up * 0.998 and high <= limit_up * 1.002:
                return f'涨停封板({close:.2f}≈{limit_up:.2f})'
        elif direction == 'sell':
            if close <= limit_down * 1.002 and low >= limit_down * 0.998:
                return f'跌停封板({close:.2f}≈{limit_down:.2f})'
        return ''

    # ── 成交价 ──────────────────────────────────────────────
    def _fill_price(self, order_price, direction, bar_data=None):
        if bar_data:
            base = bar_data.get('open', order_price)
            if direction == 'buy':
                fill = base * (1 + self.slippage_rate)
                fill = min(fill, bar_data.get('high', fill))
            else:
                fill = base * (1 - self.slippage_rate)
                fill = max(fill, bar_data.get('low', fill))
            return round(fill, 2)
        slip = self.slippage_rate if direction == 'buy' else -self.slippage_rate
        return round(order_price * (1 + slip), 2)

    # ── 查询 ────────────────────────────────────────────────
    def get_equity(self, prices: Dict[str, float]) -> float:
        pos_val = 0
        for code, pos in self.positions.items():
            total_shares = sum(l.shares for l in pos['lots'])
            p = prices.get(code, pos['lots'][0].buy_price if pos['lots'] else 0)
            pos_val += total_shares * p
        return self.cash + pos_val

    def update_highest_prices(self, prices: Dict[str, float]):
        for code, pos in self.positions.items():
            if code in prices:
                pos['highest_price'] = max(pos.get('highest_price', 0), prices[code])

    def get_closed_trades(self) -> list:
        return [{'pnl': t.pnl, 'pnl_pct': t.pnl_pct,
                 'hold_days': t.hold_days, 'stop_type': t.stop_type}
                for t in self.trades if t.direction == 'sell']

    def get_summary(self) -> dict:
        return {
            'initial_capital': self.initial_capital,
            'cash': self.cash,
            'positions': self.positions_compat,
            'total_trades': len(self.trades),
            'total_commissions': sum(t.commission for t in self.trades),
            'total_stamp_tax': sum(t.stamp_tax for t in self.trades),
        }

    # ── 导出 ────────────────────────────────────────────────
    def export_trades_csv(self, filepath: str):
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['日期', '代码', '方向', '成交价', '股数',
                        '佣金', '印花税', '总费用', '盈亏', '盈亏%',
                        '持仓天数', '止损类型'])
            for t in self.trades:
                is_sell = t.direction == 'sell'
                w.writerow([
                    t.date, t.code,
                    '买入' if t.direction == 'buy' else '卖出',
                    f'{t.price:.2f}', t.shares,
                    f'{t.commission:.2f}', f'{t.stamp_tax:.2f}',
                    f'{t.total_cost:.2f}',
                    f'{t.pnl:.2f}' if is_sell else '',
                    f'{t.pnl_pct:.2%}' if is_sell else '',
                    t.hold_days if is_sell else '',
                    t.stop_type,
                ])

    def get_trades_df(self) -> pd.DataFrame:
        """返回交易记录DataFrame"""
        records = []
        for t in self.trades:
            records.append({
                '日期': t.date, '代码': t.code,
                '方向': '买入' if t.direction == 'buy' else '卖出',
                '成交价': t.price, '股数': t.shares,
                '佣金': t.commission, '印花税': t.stamp_tax,
                '盈亏': t.pnl if t.direction == 'sell' else None,
                '盈亏%': t.pnl_pct if t.direction == 'sell' else None,
                '持仓天数': t.hold_days if t.direction == 'sell' else None,
                '止损类型': t.stop_type,
            })
        return pd.DataFrame(records) if records else pd.DataFrame()
