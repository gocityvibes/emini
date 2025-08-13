# trading_bot/models/__init__.py - Complete Model Exports with AI Integration

from .trade import (
    Trade,
    TradeSetup,
    TradeDirection,
    TradeStatus,
    TradeOutcome,
    AIDecision,
    MarketCondition as TradeMarketCondition,
)

from .market import (
    MarketData,
    Candle,
    MarketCondition,
    TrendDirection,
    TimeFrame,
    MarketScenario,
)

from .simulation import (
    Simulation,
    SimulationMetrics,
    SimulationStatus,
)

from .preset_config import (
    Preset,
    ABTestConfiguration,
    PresetType,
    SessionType,
    PRESET_CONFIGURATIONS,
)

__all__ = [
    # Trade Models
    "Trade",
    "TradeSetup", 
    "TradeDirection",
    "TradeStatus",
    "TradeOutcome",
    "AIDecision",
    "TradeMarketCondition",
    
    # Market Models
    "MarketData",
    "Candle",
    "MarketCondition",
    "TrendDirection", 
    "TimeFrame",
    "MarketScenario",
    
    # Simulation Models
    "Simulation",
    "SimulationMetrics",
    "SimulationStatus",
    
    # Preset and A/B Testing Models
    "Preset",
    "ABTestConfiguration",
    "PresetType",
    "SessionType",
    "PRESET_CONFIGURATIONS",
]
