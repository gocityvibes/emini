from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Tuple, Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

class PresetType(str, Enum):
    TREND_HUNTER = "trend_hunter"
    CHOP_MASTER = "chop_master"
    NEWS_SPIKE = "news_spike"
    CUSTOM = "custom"

class SessionType(str, Enum):
    AM = "AM"
    PM = "PM"
    BOTH = "BOTH"

class Preset(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    # Identification
    name: str = Field(..., description="Preset name")
    preset_type: PresetType = Field(PresetType.CUSTOM, description="Preset category")
    description: str = Field("", description="Preset description")
    
    # AI Configuration
    confidence_threshold: float = Field(0.85, ge=0.0, le=1.0, description="Minimum confidence for trades")
    min_scalp_range_points: float = Field(1.0, gt=0, description="Minimum range for scalp setups")
    cooldown_seconds: int = Field(120, ge=0, description="Cooldown between trades")
    max_trades_per_session: int = Field(3, ge=1, description="Maximum trades per session")
    
    # A/B Testing
    weight: float = Field(0.5, ge=0.0, le=1.0, description="Weight for A/B testing")
    
    # Session Configuration
    target_session: SessionType = Field(SessionType.BOTH, description="Target trading session")
    
    # Risk Management
    max_risk_per_trade: float = Field(0.02, ge=0.001, le=0.1, description="Maximum risk per trade")
    max_daily_drawdown: float = Field(0.05, ge=0.01, le=0.2, description="Maximum daily drawdown")
    
    # Market Conditions
    preferred_volatility: str = Field("medium", description="Preferred volatility level")
    avoid_news_times: bool = Field(True, description="Avoid trading during news")
    
    # Performance Tracking
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used: Optional[datetime] = Field(None, description="Last time preset was used")
    total_trades: int = Field(0, ge=0, description="Total trades with this preset")
    win_rate: float = Field(0.0, ge=0.0, le=1.0, description="Historical win rate")
    
    @field_validator('confidence_threshold')
    @classmethod
    def validate_confidence(cls, v):
        if not 0.5 <= v <= 1.0:
            raise ValueError("Confidence threshold must be between 0.5 and 1.0")
        return v

    def update_performance(self, trade_result: str, pnl: float):
        """Update preset performance metrics"""
        self.total_trades += 1
        if trade_result == "win":
            # Update win rate using running average
            self.win_rate = ((self.win_rate * (self.total_trades - 1)) + 1) / self.total_trades
        else:
            self.win_rate = (self.win_rate * (self.total_trades - 1)) / self.total_trades
        
        self.last_used = datetime.utcnow()

class ABTestConfiguration(BaseModel):
    """Configuration for A/B testing between presets"""
    model_config = ConfigDict(use_enum_values=True)
    
    # Test Configuration
    test_name: str = Field(..., description="A/B test name")
    description: str = Field("", description="Test description")
    
    # Presets
    preset_a: Preset = Field(..., description="Preset A for testing")
    preset_b: Preset = Field(..., description="Preset B for testing")
    
    # Test Parameters
    traffic_split: float = Field(0.5, ge=0.0, le=1.0, description="Traffic split for A vs B")
    min_trades_per_preset: int = Field(50, ge=10, description="Minimum trades per preset")
    max_test_duration_days: int = Field(30, ge=1, description="Maximum test duration")
    
    # Statistical Significance
    significance_level: float = Field(0.05, ge=0.01, le=0.1, description="Statistical significance level")
    min_effect_size: float = Field(0.02, ge=0.01, description="Minimum detectable effect size")
    
    # Status
    is_active: bool = Field(True, description="Whether test is currently active")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = Field(None, description="Test end time")
    
    # Results
    trades_a: int = Field(0, ge=0, description="Number of trades for preset A")
    trades_b: int = Field(0, ge=0, description="Number of trades for preset B")
    win_rate_a: float = Field(0.0, ge=0.0, le=1.0, description="Win rate for preset A")
    win_rate_b: float = Field(0.0, ge=0.0, le=1.0, description="Win rate for preset B")
    pnl_a: float = Field(0.0, description="Total PnL for preset A")
    pnl_b: float = Field(0.0, description="Total PnL for preset B")

    def choose_preset(self) -> Tuple[str, Preset]:
        """Choose preset based on traffic split"""
        import random
        if random.random() < self.traffic_split:
            return "A", self.preset_a
        return "B", self.preset_b
    
    def update_results(self, preset_variant: str, trade_result: str, pnl: float):
        """Update A/B test results"""
        if preset_variant == "A":
            self.trades_a += 1
            if trade_result == "win":
                self.win_rate_a = ((self.win_rate_a * (self.trades_a - 1)) + 1) / self.trades_a
            else:
                self.win_rate_a = (self.win_rate_a * (self.trades_a - 1)) / self.trades_a
            self.pnl_a += pnl
        else:  # preset_variant == "B"
            self.trades_b += 1
            if trade_result == "win":
                self.win_rate_b = ((self.win_rate_b * (self.trades_b - 1)) + 1) / self.trades_b
            else:
                self.win_rate_b = (self.win_rate_b * (self.trades_b - 1)) / self.trades_b
            self.pnl_b += pnl
    
    def is_statistically_significant(self) -> bool:
        """Check if results are statistically significant"""
        # Simplified statistical significance check
        min_trades = min(self.trades_a, self.trades_b)
        if min_trades < self.min_trades_per_preset:
            return False
        
        # Basic effect size check
        effect_size = abs(self.win_rate_a - self.win_rate_b)
        return effect_size >= self.min_effect_size
    
    def get_winner(self) -> Optional[str]:
        """Get winning preset if test is complete and significant"""
        if not self.is_statistically_significant():
            return None
        
        if self.win_rate_a > self.win_rate_b:
            return "A"
        elif self.win_rate_b > self.win_rate_a:
            return "B"
        else:
            return None  # Tie

# Predefined preset configurations
PRESET_CONFIGURATIONS = {
    "trend_hunter": Preset(
        name="Trend Hunter",
        preset_type=PresetType.TREND_HUNTER,
        description="Aggressive trend-following preset for strong directional moves",
        confidence_threshold=0.85,
        min_scalp_range_points=1.0,
        cooldown_seconds=120,
        max_trades_per_session=3,
        target_session=SessionType.AM,
        preferred_volatility="medium",
        avoid_news_times=True
    ),
    
    "chop_master": Preset(
        name="Chop Master", 
        preset_type=PresetType.CHOP_MASTER,
        description="Conservative preset for choppy, range-bound markets",
        confidence_threshold=0.88,
        min_scalp_range_points=1.2,
        cooldown_seconds=180,
        max_trades_per_session=2,
        target_session=SessionType.PM,
        preferred_volatility="low",
        avoid_news_times=True
    ),
    
    "news_spike": Preset(
        name="News Spike",
        preset_type=PresetType.NEWS_SPIKE,
        description="High-frequency preset for news-driven volatility",
        confidence_threshold=0.90,
        min_scalp_range_points=0.5,
        cooldown_seconds=60,
        max_trades_per_session=5,
        target_session=SessionType.BOTH,
        preferred_volatility="high",
        avoid_news_times=False
    )
}
