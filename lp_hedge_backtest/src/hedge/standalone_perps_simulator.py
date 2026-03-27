"""Standalone perps simulator for FURY bot (no LP position required).

Handles one position at a time on BTC or ETH with:
  - ATR-based hybrid stops (capped/floored per asset)
  - Dynamic leverage by signal gate score (3→3x … 6→12x)
  - Position sizing via (account × risk_pct) / stop_distance_usd
  - Commission + slippage on both sides
  - Circuit breaker: pause on 5% daily drawdown OR 3 consecutive losses
  - BTC golden rule: long-only enforced at open_position level
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

import logging

logger = logging.getLogger(__name__)

# ── ATR hybrid stop constants (per asset) ────────────────────────────────────
_ATR_FLOORS = {"BTC": 150.0, "ETH": 50.0}
_ATR_CEILINGS = {"BTC": 800.0, "ETH": 300.0}

# Gate score → leverage mapping
_GATE_LEVERAGE = {3: 3, 4: 5, 5: 8, 6: 12}

# Circuit breaker thresholds
_DAILY_DD_LIMIT = 0.05        # 5% daily drawdown
_CONSEC_LOSS_LIMIT = 3        # 3 consecutive losses


@dataclass
class Trade:
    """Immutable record of a completed trade."""
    symbol: str
    side: str                  # 'LONG' | 'SHORT'
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    size_usd: float
    leverage: int
    gate_score: int
    entry_ts: datetime
    exit_ts: datetime
    exit_reason: str           # 'STOP_LOSS' | 'TAKE_PROFIT' | 'CIRCUIT_BREAKER' | 'END_OF_DATA'
    gross_pnl: float           # before fees
    commission: float
    net_pnl: float             # after fees
    balance_before: float
    balance_after: float


@dataclass
class _OpenPosition:
    symbol: str
    side: str
    entry_price: float
    stop_loss: float
    take_profit: float
    size_usd: float
    leverage: int
    gate_score: int
    entry_ts: datetime
    entry_commission: float


class StandalonePerpsSimulator:
    """Backtest-grade perps simulator for the FURY RSI Trader strategy.

    Usage:
        sim = StandalonePerpsSimulator(initial_capital=1000, symbol='ETH')
        for each candle:
            if not sim.position and gates_pass:
                sim.open_position(side, entry_price, atr, gate_score)
            elif sim.position:
                closed = sim.check_sl_tp(candle_high, candle_low, candle_close, ts)
            if sim.circuit_breaker_triggered:
                sim.maybe_reset_circuit_breaker(today)
    """

    def __init__(
        self,
        initial_capital: float,
        symbol: str = "ETH",
        commission: float = 0.0005,    # 0.05% taker each side
        slippage: float = 0.00075,     # 0.075% each side
        atr_multiplier: float = 1.5,
    ):
        if symbol not in _ATR_FLOORS:
            raise ValueError(f"symbol must be one of {list(_ATR_FLOORS)}")

        self.symbol = symbol
        self.commission = commission
        self.slippage = slippage
        self.atr_multiplier = atr_multiplier

        self.capital = initial_capital
        self._initial_capital = initial_capital
        self._peak_capital = initial_capital

        self.position: Optional[_OpenPosition] = None
        self.trades: list[Trade] = []

        # Circuit breaker state
        self.circuit_breaker_triggered = False
        self._cb_reset_date: Optional[date] = None
        self._consecutive_losses = 0
        self._daily_start_capital: Optional[float] = None
        self._current_day: Optional[date] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def open_position(
        self,
        side: str,
        entry_price: float,
        atr: float,
        gate_score: int,
        ts: Optional[datetime] = None,
    ) -> bool:
        """Open a new position.

        Returns True if opened, False if blocked (circuit breaker, BTC short, etc.).
        """
        if self.position:
            logger.debug("open_position: already in a position, skipped")
            return False

        if self.circuit_breaker_triggered:
            logger.debug("open_position: circuit breaker active, skipped")
            return False

        # BTC golden rule — long only
        if self.symbol == "BTC" and side == "SHORT":
            logger.warning("BTC golden rule: SHORT blocked")
            return False

        ts = ts or datetime.now(timezone.utc)
        self._init_daily_tracking(ts)

        leverage = _GATE_LEVERAGE.get(gate_score, 3)
        stop_distance = self.atr_stop_distance(atr)
        stop_loss = (
            entry_price - stop_distance if side == "LONG"
            else entry_price + stop_distance
        )
        take_profit = (
            entry_price + stop_distance * 3 if side == "LONG"
            else entry_price - stop_distance * 3
        )

        # Position sizing: risk 2% of capital / stop_distance_pct
        risk_amount = self.capital * 0.02
        stop_pct = stop_distance / entry_price
        size_usd = min(risk_amount / stop_pct, self.capital * leverage)

        # Apply entry slippage
        filled_price = (
            entry_price * (1 + self.slippage) if side == "LONG"
            else entry_price * (1 - self.slippage)
        )

        entry_commission = size_usd * self.commission

        self.position = _OpenPosition(
            symbol=self.symbol,
            side=side,
            entry_price=filled_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            size_usd=size_usd,
            leverage=leverage,
            gate_score=gate_score,
            entry_ts=ts,
            entry_commission=entry_commission,
        )

        logger.debug(
            f"Opened {side} {self.symbol} @ {filled_price:.2f} | "
            f"SL {stop_loss:.2f} TP {take_profit:.2f} | "
            f"Size ${size_usd:.0f} | {leverage}x | Gates {gate_score}"
        )
        return True

    def check_sl_tp(
        self,
        candle_high: float,
        candle_low: float,
        candle_close: float,
        ts: Optional[datetime] = None,
    ) -> Optional[Trade]:
        """Check if SL or TP was hit on this candle.

        SL is checked before TP (conservative).
        Returns a Trade record if closed, None if still open.
        """
        if not self.position:
            return None

        ts = ts or datetime.now(timezone.utc)
        pos = self.position

        if pos.side == "LONG":
            sl_hit = candle_low <= pos.stop_loss
            tp_hit = candle_high >= pos.take_profit
        else:
            sl_hit = candle_high >= pos.stop_loss
            tp_hit = candle_low <= pos.take_profit

        if sl_hit:
            return self._close(pos.stop_loss, "STOP_LOSS", ts)
        if tp_hit:
            return self._close(pos.take_profit, "TAKE_PROFIT", ts)
        return None

    def force_close(self, price: float, reason: str = "END_OF_DATA",
                    ts: Optional[datetime] = None) -> Optional[Trade]:
        """Force-close the open position (end of backtest or circuit breaker)."""
        if not self.position:
            return None
        return self._close(price, reason, ts or datetime.now(timezone.utc))

    def maybe_reset_circuit_breaker(self, today: date):
        """Reset circuit breaker at the start of a new calendar day."""
        if self.circuit_breaker_triggered and today != self._cb_reset_date:
            self.circuit_breaker_triggered = False
            self._consecutive_losses = 0
            self._daily_start_capital = self.capital
            self._current_day = today
            logger.info(f"Circuit breaker reset for {today}")

    def atr_stop_distance(self, atr: float) -> float:
        """Return capped/floored ATR stop distance in price units."""
        raw = atr * self.atr_multiplier
        floor = _ATR_FLOORS[self.symbol]
        ceiling = _ATR_CEILINGS[self.symbol]
        return max(floor, min(raw, ceiling))

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        wins = sum(1 for t in self.trades if t.net_pnl > 0)
        return wins / len(self.trades) if self.trades else 0.0

    @property
    def total_fees(self) -> float:
        return sum(t.commission for t in self.trades)

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _close(self, exit_price: float, reason: str, ts: datetime) -> Trade:
        pos = self.position
        self.position = None

        # Apply exit slippage
        if pos.side == "LONG":
            filled_exit = exit_price * (1 - self.slippage)
            gross_pnl = (filled_exit - pos.entry_price) / pos.entry_price * pos.size_usd
        else:
            filled_exit = exit_price * (1 + self.slippage)
            gross_pnl = (pos.entry_price - filled_exit) / pos.entry_price * pos.size_usd

        exit_commission = pos.size_usd * self.commission
        total_commission = pos.entry_commission + exit_commission
        net_pnl = gross_pnl - total_commission

        balance_before = self.capital
        self.capital += net_pnl
        if self.capital > self._peak_capital:
            self._peak_capital = self.capital

        trade = Trade(
            symbol=pos.symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=filled_exit,
            stop_loss=pos.stop_loss,
            take_profit=pos.take_profit,
            size_usd=pos.size_usd,
            leverage=pos.leverage,
            gate_score=pos.gate_score,
            entry_ts=pos.entry_ts,
            exit_ts=ts,
            exit_reason=reason,
            gross_pnl=gross_pnl,
            commission=total_commission,
            net_pnl=net_pnl,
            balance_before=balance_before,
            balance_after=self.capital,
        )
        self.trades.append(trade)

        emoji = "✅" if net_pnl > 0 else "❌"
        logger.debug(
            f"{emoji} Closed {pos.side} {pos.symbol} @ {filled_exit:.2f} "
            f"({reason}) | Net PnL ${net_pnl:+.2f} | Balance ${self.capital:.2f}"
        )

        self._update_circuit_breaker(trade, ts)
        return trade

    def _update_circuit_breaker(self, trade: Trade, ts: datetime):
        today = ts.date() if hasattr(ts, "date") else date.today()
        self._init_daily_tracking(ts)

        if trade.net_pnl <= 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

        daily_dd = (self._daily_start_capital - self.capital) / self._daily_start_capital

        if self._consecutive_losses >= _CONSEC_LOSS_LIMIT:
            logger.warning(
                f"Circuit breaker: {_CONSEC_LOSS_LIMIT} consecutive losses"
            )
            self._trigger_circuit_breaker(today)
        elif daily_dd >= _DAILY_DD_LIMIT:
            logger.warning(
                f"Circuit breaker: daily drawdown {daily_dd:.1%} >= {_DAILY_DD_LIMIT:.0%}"
            )
            self._trigger_circuit_breaker(today)

    def _trigger_circuit_breaker(self, today: date):
        self.circuit_breaker_triggered = True
        self._cb_reset_date = today  # resets next calendar day

    def _init_daily_tracking(self, ts):
        today = ts.date() if hasattr(ts, "date") else date.today()
        if self._current_day != today:
            self._current_day = today
            self._daily_start_capital = self.capital
