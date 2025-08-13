# trading_bot/models/trade.py - Complete Trade Model with AI Integration

from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime
from typing import Optional, Dict, Any, List, Annotated
from enum import Enum
import json
from pydantic import StringConstraints

# Constants for common futures point values
_POINT_VALUE_USD = {
    "MES": 5.0,  # Micro E-mini S&P 500
}

# Type aliases
SymbolStr = Annotated[str, StringConstraints(pattern=r"^[A-Z/]{1,10}$")]

class TradeDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class TradeStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"

class TradeOutcome(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    PENDING = "PENDING"

class MarketCondition(BaseModel):
    """Market condition assessment for trade context"""
    trend: str = Field(..., description="Overall trend direction")
    volatility: str = Field(..., description="Volatility level")
    momentum: str = Field(..., description="Momentum strength")
    range_points: Optional[float] = Field(None, description="Recent range in points")
    confidence: Optional[float] = Field(None, description="Condition confidence score")

class AIDecision(BaseModel):
    """GPT-5 trading decision with confidence scoring"""
    decision: str = Field(..., description="LONG, SHORT, or HOLD")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Decision confidence")
    reasoning: str = Field(..., description="Decision rationale")
    entry_price: Optional[float] = Field(None, description="Suggested entry price")
    stop_loss: Optional[float] = Field(None, description="Suggested stop loss")
    take_profit: Optional[float] = Field(None, description="Suggested take profit")
    market_assessment: Optional[MarketCondition] = Field(None, description="Market condition")
    model_used: str = Field(default="gpt-5", description="AI model identifier")
    tokens_used: Optional[int] = Field(None, description="Token consumption")
    response_time_ms: Optional[int] = Field(None, description="Model response latency")

class TradeSetup(BaseModel):
    """Trade setup parameters and entry conditions"""
    symbol: SymbolStr
    direction: TradeDirection = Field(..., description="Trade direction")
    entry_price: float = Field(..., description="Entry price")
    stop_loss: float = Field(..., description="Stop loss price")
    take_profit: float = Field(..., description="Take profit price")
    quantity: int = Field(default=1, description="Position size")
    timeframe: str = Field(default="1m", description="Analysis timeframe")
    ai_decision: Optional[AIDecision] = Field(None, description="AI decision context")
    setup_quality: Optional[float] = Field(None, ge=0.0, le=1.0, description="Setup quality score")

class Trade(BaseModel):
    """Enhanced trade model for MES scalping with comprehensive AI integration"""
    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat() if v else None}
    )

    # Core trade identification
    id: Optional[str] = Field(None, description="Trade unique identifier")
    symbol: SymbolStr = Field(..., description="Trading symbol")
    direction: TradeDirection = Field(..., description="Trade direction")

    # AI Decision Context - NEW FIELDS
    contract_qty: int = Field(default=1, description="Number of contracts traded")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="AI confidence score")
    reasoning: Optional[str] = Field(None, description="AI decision reasoning")

    # Trade execution data
    entry_price: float = Field(..., description="Actual entry price")
    exit_price: Optional[float] = Field(None, description="Actual exit price")
    stop_loss: float = Field(..., description="Stop loss price")
    take_profit: float = Field(..., description="Take profit price")
    quantity: int = Field(default=1, description="Position size")

    # Trade lifecycle timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Trade creation time")
    entry_time: Optional[datetime] = Field(None, description="Entry execution time")
    exit_time: Optional[datetime] = Field(None, description="Exit execution time")

    # Trade status and outcome
    status: TradeStatus = Field(default=TradeStatus.PENDING, description="Current trade status")
    outcome: Optional[TradeOutcome] = Field(None, description="Trade result")

    # Financial metrics (PnL in points and USD)
    pnl: Optional[float] = Field(None, description="Profit and loss in points")
    pnl_usd: Optional[float] = Field(None, description="P&L in USD")
    commission: Optional[float] = Field(None, description="Commission costs")

    # Enhanced scalping metrics
    time_to_target_sec: Optional[float] = Field(None, description="Seconds to hit target/stop")
    mae_points: Optional[float] = Field(None, description="Maximum Adverse Excursion in points")
    mfe_points: Optional[float] = Field(None, description="Maximum Favorable Excursion in points")
    session_label: Optional[str] = Field(None, description="Trading session: AM or PM")
    scenario_name: Optional[str] = Field(None, description="Market scenario preset name")

    # AI and setup context
    ai_decision: Optional[AIDecision] = Field(None, description="AI decision that triggered trade")
    setup: Optional[TradeSetup] = Field(None, description="Trade setup parameters")

    # Market context
    market_condition: Optional[MarketCondition] = Field(None, description="Market state at entry")
    entry_candle: Optional[Dict[str, Any]] = Field(None, description="Entry candle data")

    # Metadata and tags
    tags: List[str] = Field(default_factory=list, description="Trade classification tags")
    notes: Optional[str] = Field(None, description="Additional trade notes")

    @field_validator('pnl')
    @classmethod
    def calculate_pnl(cls, v, info):
        """Auto-calculate PnL in points if not provided."""
        if v is not None:
            return v

        values = info.data
        entry = values.get('entry_price')
        exit_price = values.get('exit_price')
        direction = values.get('direction')

        if entry is not None and exit_price is not None and direction is not None:
            if direction == TradeDirection.LONG:
                return exit_price - entry
            else:  # SHORT
                return entry - exit_price
        return None

    @field_validator('pnl_usd')
    @classmethod
    def calculate_pnl_usd(cls, v, info):
        """Compute PnL in USD using per-symbol point value if possible."""
        if v is not None:
            return v

        values = info.data
        pnl_pts = values.get('pnl')
        symbol = values.get('symbol') or "MES"

        if pnl_pts is not None:
            point_value = _POINT_VALUE_USD.get(symbol, None)
            if point_value is not None:
                qty = values.get('contract_qty') or values.get('quantity') or 1
                return pnl_pts * point_value * qty
        return None

    @field_validator('session_label')
    @classmethod
    def determine_session(cls, v, info):
        """Auto-determine session from entry time if not set."""
        if v is not None:
            return v

        values = info.data
        entry_time = values.get('entry_time')
        if entry_time:
            hour = entry_time.hour
            minute = entry_time.minute
            time_decimal = hour + minute / 60.0

            # AM session: 08:30-10:30 ET (inclusive)
            if 8.5 <= time_decimal <= 10.5:
                return "AM"
            # PM session: 13:00-15:00 ET (inclusive)
            if 13.0 <= time_decimal <= 15.0:
                return "PM"
        return None

    def finalize_scalp_metrics(self) -> None:
        """Finalize scalp-specific metrics and derive outcome if needed."""
        # Derive outcome from PnL if not set
        if self.outcome is None and self.pnl is not None:
            if self.pnl > 0:
                self.outcome = TradeOutcome.WIN
            elif self.pnl < 0:
                self.outcome = TradeOutcome.LOSS
            else:
                self.outcome = TradeOutcome.BREAKEVEN

        # Compute time to target if applicable
        if self.time_to_target_sec is None and self.entry_time and self.exit_time:
            delta = self.exit_time - self.entry_time
            self.time_to_target_sec = delta.total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with datetime serialization."""
        return json.loads(self.model_dump_json())

    def is_scalp_winner(self) -> bool:
        """Check if trade hit target (not stop loss)."""
        if self.exit_price is None or self.take_profit is None:
            return False

        tolerance = 0.01  # small tolerance for fill/slippage
        if self.direction == TradeDirection.LONG:
            return self.exit_price >= (self.take_profit - tolerance)
        else:  # SHORT
            return self.exit_price <= (self.take_profit + tolerance)

    def get_risk_reward_ratio(self) -> Optional[float]:
        """Calculate reward:risk ratio for the trade setup."""
        if self.entry_price is None or self.stop_loss is None or self.take_profit is None:
            return None

        if self.direction == TradeDirection.LONG:
            risk = self.entry_price - self.stop_loss
            reward = self.take_profit - self.entry_price
        else:  # SHORT
            risk = self.stop_loss - self.entry_price
            reward = self.entry_price - self.take_profit

        return (reward / risk) if (risk is not None and risk > 0) else None

    def get_ai_summary(self) -> Dict[str, Any]:
        """Get summary of AI decision and performance"""
        return {
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "model_used": self.ai_decision.model_used if self.ai_decision else "unknown",
            "direction": self.direction.value,
            "outcome": self.outcome.value if self.outcome else "pending",
            "pnl_points": self.pnl,
            "pnl_usd": self.pnl_usd,
            "session": self.session_label,
            "time_to_result": self.time_to_target_sec
        }
