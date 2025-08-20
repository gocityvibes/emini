"""
Realistic Trade Simulator
Simulates MES scalping trades with advanced bracket orders and realistic fills.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum


class ExitReason(Enum):
    """Trade exit reasons."""
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    BREAKEVEN = "breakeven"
    TRAILING_STOP = "trailing_stop"
    TIMEOUT = "timeout"
    MANUAL = "manual"


class TradeDirection(Enum):
    """Trade direction."""
    LONG = "long"
    SHORT = "short"


@dataclass
class TradeResult:
    """Complete trade result with all metrics.

    Notes:
      - pnl_dollars is NET (after commission)
      - net_pnl_points is NET (commission converted to points)
      - slippage_points is total entry+exit slippage in points
    """
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    direction: TradeDirection
    exit_reason: ExitReason
    pnl_points: float
    pnl_dollars: float
    mae: float  # Maximum Adverse Excursion
    mfe: float  # Maximum Favorable Excursion
    time_to_target_seconds: Optional[int]
    time_to_be_seconds: Optional[int]
    commission_paid: float
    slippage_points: float
    gross_pnl_points: float
    net_pnl_points: float


class RealisticSimulator:
    """
    Advanced trade simulator for MES scalping with realistic execution.

    Features:
    - Bracket orders (TP/SL/BE/Trail)
    - Slippage modeling based on volume/spread
    - Commission calculation
    - Partial fill simulation (future extension)
    - MAE/MFE tracking
    - Timeout handling
    - Intrabar price simulation
    """

    def __init__(self, config: Dict):
        """
        Initialize simulator with risk management configuration.

        Args:
            config: Configuration dict containing risk and market settings
        """
        self.config = config
        self.risk_config = config['risk']
        self.market_config = config['market']

        # Risk parameters from config
        self.tp_points = self.risk_config['tp']
        self.sl_points = self.risk_config['sl']
        self.be_threshold = self.risk_config['move_to_be_at']
        self.trail_start = self.risk_config['trail_after']
        self.trail_distance = self.risk_config['trail_distance']
        self.timeout_minutes = self.risk_config['timeout_minutes']

        # Market parameters
        self.tick_size = self.market_config['tick_size']
        self.contract_size = self.market_config['contract_size']

        # Execution costs (configurable)
        self.commission_per_trade = 0.62  # Round trip commission (USD)
        self.base_slippage_ticks = 0.5    # Base slippage in ticks

    def simulate_trade(self,
                       entry_price: float,
                       entry_time: datetime,
                       direction: TradeDirection,
                       bar_data: pd.DataFrame) -> TradeResult:
        """
        Simulate a complete trade with bracket orders.

        Args:
            entry_price: Intended entry price
            entry_time: Trade entry timestamp (UTC preferred)
            direction: LONG or SHORT
            bar_data: OHLCV data starting from entry time

        Returns:
            TradeResult with complete trade metrics
        """
        # Normalize entry_time to aware UTC if naive
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)

        # Apply entry slippage first to get actual fill
        slipped_entry = self._apply_entry_slippage(entry_price, direction, bar_data.iloc[0] if not bar_data.empty else None)

        # Calculate brackets from the ACTUAL filled price (fix)
        brackets = self._calculate_brackets(slipped_entry, direction)

        # Track trade state
        trade_state = {
            'entry_price': slipped_entry,
            'current_sl': brackets['initial_sl'],
            'current_tp': brackets['tp'],
            'be_moved': False,
            'trail_active': False,
            'mae': 0.0,
            'mfe': 0.0,
            'time_to_be': None,
            'time_to_target': None,
            'entry_time': entry_time,  # store for result assembly (fix)
        }

        # Iterate bars
        for i, (timestamp, bar) in enumerate(bar_data.iterrows()):
            # Ensure timestamp is aware UTC for math
            if isinstance(timestamp, datetime) and timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)

            # Check timeout BEFORE processing the bar
            if self._is_timeout(entry_time, timestamp):
                # Exit at current bar's CLOSE (fix: not at original entry)
                exit_px = float(bar['Close']) if 'Close' in bar else trade_state['entry_price']
                return self._create_trade_result(
                    trade_state, entry_time, timestamp, exit_px, ExitReason.TIMEOUT, direction
                )

            # Process the bar
            exit_result = self._process_bar(bar, trade_state, direction, timestamp, entry_time)
            if exit_result:
                return exit_result

        # Force close at last known close if still open
        last_bar = bar_data.iloc[-1]
        last_ts = bar_data.index[-1]
        if isinstance(last_ts, datetime) and last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        last_price = float(last_bar['Close'])

        return self._create_trade_result(
            trade_state, entry_time, last_ts, last_price, ExitReason.MANUAL, direction
        )

    def _calculate_brackets(self, fill_price: float, direction: TradeDirection) -> Dict[str, float]:
        """Calculate initial bracket order levels from the actual fill price."""
        if direction == TradeDirection.LONG:
            tp = fill_price + self.tp_points
            initial_sl = fill_price - self.sl_points
        else:
            tp = fill_price - self.tp_points
            initial_sl = fill_price + self.sl_points

        return {
            'tp': tp,
            'initial_sl': initial_sl,
            'be_level': fill_price + (self.be_threshold if direction == TradeDirection.LONG else -self.be_threshold),
            'trail_start_level': fill_price + (self.trail_start if direction == TradeDirection.LONG else -self.trail_start)
        }

    def _apply_entry_slippage(self, entry_price: float, direction: TradeDirection, first_bar: Optional[pd.Series]) -> float:
        """Apply realistic entry slippage based on market conditions."""
        base_slippage = self.base_slippage_ticks * self.tick_size

        # Increase slippage based on spread
        if first_bar is not None:
            spread = float(first_bar['High']) - float(first_bar['Low'])
            if spread > 2.0:  # wide spread
                base_slippage *= 1.5

        # Apply in unfavorable direction
        if direction == TradeDirection.LONG:
            return entry_price + base_slippage
        else:
            return entry_price - base_slippage

    def _process_bar(self, bar: pd.Series, trade_state: Dict, direction: TradeDirection,
                     timestamp: datetime, entry_time: datetime) -> Optional[TradeResult]:
        """Process a single bar for trade management."""
        # Update MAE/MFE
        self._update_mae_mfe(bar, trade_state, direction)

        # Check for breakeven move
        if not trade_state['be_moved']:
            be_hit = self._check_breakeven(bar, trade_state, direction)
            if be_hit:
                trade_state['time_to_be'] = int((timestamp - entry_time).total_seconds())

        # Check for trailing activation
        if not trade_state['trail_active'] and trade_state['be_moved']:
            self._check_trailing_activation(bar, trade_state, direction)

        # Update trailing stop if active
        if trade_state['trail_active']:
            self._update_trailing_stop(bar, trade_state, direction)

        # Simulate intrabar execution using OHLC
        return self._simulate_intrabar_execution(bar, trade_state, direction, timestamp, entry_time)

    def _update_mae_mfe(self, bar: pd.Series, trade_state: Dict, direction: TradeDirection):
        """Update Maximum Adverse/Favorable Excursion."""
        entry_price = trade_state['entry_price']
        high = float(bar['High'])
        low = float(bar['Low'])

        if direction == TradeDirection.LONG:
            current_mfe = high - entry_price
            current_mae = entry_price - low
        else:
            current_mfe = entry_price - low
            current_mae = high - entry_price

        trade_state['mfe'] = max(trade_state['mfe'], current_mfe)
        trade_state['mae'] = max(trade_state['mae'], current_mae)

    def _check_breakeven(self, bar: pd.Series, trade_state: Dict, direction: TradeDirection) -> bool:
        """Check if breakeven threshold is hit and move stop."""
        entry_price = trade_state['entry_price']
        high = float(bar['High'])
        low = float(bar['Low'])

        if direction == TradeDirection.LONG:
            if high >= entry_price + self.be_threshold:
                trade_state['current_sl'] = entry_price
                trade_state['be_moved'] = True
                return True
        else:
            if low <= entry_price - self.be_threshold:
                trade_state['current_sl'] = entry_price
                trade_state['be_moved'] = True
                return True

        return False

    def _check_trailing_activation(self, bar: pd.Series, trade_state: Dict, direction: TradeDirection):
        """Check if trailing stop should be activated."""
        entry_price = trade_state['entry_price']
        high = float(bar['High'])
        low = float(bar['Low'])

        if direction == TradeDirection.LONG:
            if high >= entry_price + self.trail_start:
                trade_state['trail_active'] = True
        else:
            if low <= entry_price - self.trail_start:
                trade_state['trail_active'] = True

    def _update_trailing_stop(self, bar: pd.Series, trade_state: Dict, direction: TradeDirection):
        """Update trailing stop level."""
        high = float(bar['High'])
        low = float(bar['Low'])
        if direction == TradeDirection.LONG:
            new_stop = high - self.trail_distance
            trade_state['current_sl'] = max(trade_state['current_sl'], new_stop)
        else:
            new_stop = low + self.trail_distance
            trade_state['current_sl'] = min(trade_state['current_sl'], new_stop)

    def _simulate_intrabar_execution(self, bar: pd.Series, trade_state: Dict, direction: TradeDirection,
                                     timestamp: datetime, entry_time: datetime) -> Optional[TradeResult]:
        """Simulate realistic order execution within the bar."""
        o = float(bar['Open'])
        h = float(bar['High'])
        l = float(bar['Low'])
        c = float(bar['Close'])

        # Order of price action simulation: Open -> High/Low -> Close
        prices = [o]
        if h != o and l != o:
            prices.extend([l, h] if c > o else [h, l])
        elif h != o:
            prices.append(h)
        elif l != o:
            prices.append(l)
        prices.append(c)

        for price in prices:
            # Stop loss / BE / trailing
            if self._is_stop_hit(price, trade_state['current_sl'], direction):
                exit_reason = ExitReason.TRAILING_STOP if trade_state['trail_active'] else (
                    ExitReason.BREAKEVEN if trade_state['be_moved'] else ExitReason.STOP_LOSS
                )
                return self._create_trade_result(
                    trade_state, entry_time, timestamp, trade_state['current_sl'], exit_reason, direction
                )

            # Take profit
            if self._is_target_hit(price, trade_state['current_tp'], direction):
                if trade_state['time_to_target'] is None:
                    trade_state['time_to_target'] = int((timestamp - entry_time).total_seconds())
                return self._create_trade_result(
                    trade_state, entry_time, timestamp, trade_state['current_tp'], ExitReason.TAKE_PROFIT, direction
                )

        return None

    def _is_stop_hit(self, current_price: float, stop_price: float, direction: TradeDirection) -> bool:
        """Check if stop loss is hit."""
        if direction == TradeDirection.LONG:
            return current_price <= stop_price
        else:
            return current_price >= stop_price

    def _is_target_hit(self, current_price: float, target_price: float, direction: TradeDirection) -> bool:
        """Check if take profit is hit."""
        if direction == TradeDirection.LONG:
            return current_price >= target_price
        else:
            return current_price <= target_price

    def _is_timeout(self, entry_time: datetime, current_time: datetime) -> bool:
        """Check if trade has timed out."""
        time_elapsed = (current_time - entry_time).total_seconds() / 60
        return time_elapsed >= self.timeout_minutes

    def _create_trade_result(self, trade_state: Dict, entry_time: datetime, exit_time: datetime,
                             exit_price: float, exit_reason: ExitReason, direction: TradeDirection) -> TradeResult:
        """Create final trade result with all metrics."""
        entry_price = trade_state['entry_price']

        # Gross P&L (slippage applied below)
        if direction == TradeDirection.LONG:
            gross_pnl_points = exit_price - entry_price
        else:
            gross_pnl_points = entry_price - exit_price

        # Exit slippage for market orders (stops/timeout)
        exit_slippage = 0.0
        if exit_reason in {ExitReason.STOP_LOSS, ExitReason.BREAKEVEN, ExitReason.TRAILING_STOP, ExitReason.TIMEOUT}:
            exit_slippage = self.base_slippage_ticks * self.tick_size
            if direction == TradeDirection.LONG:
                exit_price -= exit_slippage
            else:
                exit_price += exit_slippage
            # Recompute gross with exit slippage
            if direction == TradeDirection.LONG:
                gross_pnl_points = exit_price - entry_price
            else:
                gross_pnl_points = entry_price - exit_price

        # Total slippage (entry + exit)
        total_slippage = self.base_slippage_ticks * self.tick_size + exit_slippage

        # Dollars (gross & net)
        gross_pnl_dollars = gross_pnl_points * self.contract_size
        net_pnl_dollars = gross_pnl_dollars - self.commission_per_trade

        # Points net (subtract commission converted to points)
        commission_points = self.commission_per_trade / self.contract_size
        net_pnl_points = gross_pnl_points - commission_points

        return TradeResult(
            entry_price=entry_price,
            exit_price=exit_price,
            entry_time=entry_time,
            exit_time=exit_time,
            direction=direction,
            exit_reason=exit_reason,
            pnl_points=gross_pnl_points,          # gross points
            pnl_dollars=net_pnl_dollars,          # NET dollars (kept for backward compat)
            mae=trade_state['mae'],
            mfe=trade_state['mfe'],
            time_to_target_seconds=trade_state.get('time_to_target'),
            time_to_be_seconds=trade_state.get('time_to_be'),
            commission_paid=self.commission_per_trade,
            slippage_points=total_slippage,
            gross_pnl_points=gross_pnl_points,
            net_pnl_points=net_pnl_points
        )
