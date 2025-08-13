from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime
from typing import List, Dict, Optional, Annotated
from enum import Enum
import numpy as np
from pydantic import StringConstraints

# Type aliases for validation
SymbolStr = Annotated[str, StringConstraints(pattern=r"^[A-Z/]{1,10}$")]
VolatilityLevel = Annotated[str, StringConstraints(pattern=r"^(low|medium|high)$")]
VolumePattern = Annotated[str, StringConstraints(pattern=r"^(low|normal|high|increasing|decreasing)$")]

class TimeFrame(str, Enum):
    ONE_MINUTE = "1m"
    FIVE_MINUTE = "5m"
    FIFTEEN_MINUTE = "15m"
    ONE_HOUR = "1h"

class MarketCondition(str, Enum):
    TREND = "trend"
    CHOP = "chop"
    MIXED = "mixed"

class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"

class Candle(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    timestamp: datetime
    open: float = Field(..., gt=0)
    high: float = Field(..., gt=0)  
    low: float = Field(..., gt=0)
    close: float = Field(..., gt=0)
    volume: int = Field(..., ge=0)

    @field_validator('high', 'low', 'close')
    @classmethod
    def validate_ohlc(cls, v, info):
        # Basic validation - full OHLC validation would need all fields
        if v <= 0:
            raise ValueError("Price must be positive")
        return v

    @property
    def is_green(self) -> bool:
        return self.close > self.open

    @property
    def is_red(self) -> bool:
        return self.close < self.open

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def range(self) -> float:
        return self.high - self.low

class MarketData(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    symbol: SymbolStr
    timeframe: TimeFrame
    candles: List[Candle] = Field(default_factory=list)
    market_condition: MarketCondition
    trend_direction: TrendDirection = TrendDirection.SIDEWAYS
    volatility: float = Field(..., ge=0)

    # Technical Indicators
    sma_20: List[float] = Field(default_factory=list)
    sma_50: List[float] = Field(default_factory=list)
    rsi: List[float] = Field(default_factory=list)
    macd: Dict[str, List[float]] = Field(default_factory=dict)
    bollinger_bands: Dict[str, List[float]] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    def add_candle(self, candle: Candle):
        """Add a new candle and update indicators"""
        self.candles.append(candle)
        self._update_indicators()

    def get_latest_price(self) -> Optional[float]:
        """Get the most recent close price"""
        return self.candles[-1].close if self.candles else None

    def get_price_change_percentage(self, periods: int = 20) -> Optional[float]:
        """Calculate price change over specified periods"""
        if len(self.candles) < periods:
            return None

        start_price = self.candles[-periods].close
        current_price = self.candles[-1].close
        return ((current_price - start_price) / start_price) * 100

    def calculate_atr(self, periods: int = 14) -> Optional[float]:
        """Calculate Average True Range"""
        if len(self.candles) < periods + 1:
            return None

        true_ranges = []
        for i in range(len(self.candles) - periods, len(self.candles)):
            if i == 0:
                continue

            current = self.candles[i]
            previous = self.candles[i-1]

            tr = max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close)
            )
            true_ranges.append(tr)

        return sum(true_ranges) / len(true_ranges) if true_ranges else None

    def _update_indicators(self):
        """Update technical indicators when new candles are added"""
        if len(self.candles) < 2:
            return

        closes = [candle.close for candle in self.candles]

        # Simple Moving Averages
        if len(closes) >= 20:
            self.sma_20.append(sum(closes[-20:]) / 20)

        if len(closes) >= 50:
            self.sma_50.append(sum(closes[-50:]) / 50)

        # RSI
        if len(closes) >= 14:
            rsi_value = self._calculate_rsi(closes)
            self.rsi.append(rsi_value)

    def _calculate_rsi(self, prices: List[float], periods: int = 14) -> float:
        """Calculate RSI indicator"""
        if len(prices) < periods + 1:
            return 50.0  # Neutral RSI

        gains = []
        losses = []

        for i in range(len(prices) - periods, len(prices)):
            if i == 0:
                continue

            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / periods if gains else 0
        avg_loss = sum(losses) / periods if losses else 0.01  # Avoid division by zero

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

class MarketScenario(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    scenario_id: str
    condition: MarketCondition
    trend_direction: TrendDirection
    volatility_level: VolatilityLevel
    duration_candles: int = Field(..., gt=0)

    # Scenario parameters
    base_price: float = Field(..., gt=0)
    trend_strength: float = Field(0.0, ge=-1, le=1)  # -1 strong down, 1 strong up
    noise_level: float = Field(0.02, ge=0, le=0.1)  # Random noise percentage
    volume_pattern: VolumePattern = Field("normal")
