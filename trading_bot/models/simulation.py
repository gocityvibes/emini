# trading_bot/models/simulation.py - Complete Simulation Model with AI Integration

from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum

from .trade import Trade, TradeOutcome
from .market import MarketCondition

class SimulationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class SimulationMetrics(BaseModel):
    """Enhanced metrics for MES scalping performance tracking"""
    model_config = ConfigDict(use_enum_values=True)

    # Basic trade counts
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0

    # PnL metrics
    total_pnl: float = 0.0
    total_pnl_usd: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0

    # Trade size metrics
    largest_win: float = 0.0
    largest_loss: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0

    # Performance ratios
    win_rate: float = 0.0
    scalp_hit_rate: float = 0.0  # Percentage hitting TP vs SL
    profit_factor: float = 0.0
    risk_reward_ratio: float = 0.0
    max_drawdown: float = 0.0

    # Scalping-specific metrics
    avg_time_to_target_sec: float = 0.0
    avg_mae_points: float = 0.0  # Average Maximum Adverse Excursion
    avg_mfe_points: float = 0.0  # Average Maximum Favorable Excursion
    fastest_winner_sec: Optional[float] = None
    slowest_winner_sec: Optional[float] = None

    # Session breakdown
    am_trades: int = 0
    pm_trades: int = 0
    am_win_rate: float = 0.0
    pm_win_rate: float = 0.0

    # Scenario performance
    scenario_performance: Dict[str, Dict[str, float]] = Field(default_factory=dict)

    def calculate_metrics(self, trades: List[Trade]) -> None:
        """Calculate comprehensive scalping metrics from trade list"""
        if not trades:
            # Reset to defaults
            self.__init__()
            return

        self.total_trades = len(trades)

        # Categorize trades
        wins = [t for t in trades if t.outcome == TradeOutcome.WIN]
        losses = [t for t in trades if t.outcome == TradeOutcome.LOSS]
        breakevens = [t for t in trades if t.outcome == TradeOutcome.BREAKEVEN]

        self.winning_trades = len(wins)
        self.losing_trades = len(losses)
        self.breakeven_trades = len(breakevens)

        # PnL calculations
        win_pnls = [t.pnl for t in wins if t.pnl is not None and t.pnl >= 0]
        loss_pnls = [abs(t.pnl) for t in losses if t.pnl is not None]
        all_pnls = [t.pnl for t in trades if t.pnl is not None]

        self.gross_profit = float(sum(win_pnls)) if win_pnls else 0.0
        self.gross_loss = float(sum(loss_pnls)) if loss_pnls else 0.0
        self.total_pnl = float(sum(all_pnls)) if all_pnls else 0.0

        # USD conversion (MES: $5 per point)
        self.total_pnl_usd = self.total_pnl * 5.0

        # Win/Loss statistics
        if win_pnls:
            self.largest_win = max(win_pnls)
            self.average_win = self.gross_profit / len(win_pnls)
        else:
            self.largest_win = 0.0
            self.average_win = 0.0

        if loss_pnls:
            self.largest_loss = max(loss_pnls)
            self.average_loss = self.gross_loss / len(loss_pnls)
        else:
            self.largest_loss = 0.0
            self.average_loss = 0.0

        # Performance ratios
        self.win_rate = (self.winning_trades / self.total_trades) if self.total_trades > 0 else 0.0
        # For fixed TP/SL scalping, hit rate aligns with win rate
        self.scalp_hit_rate = self.win_rate
        self.profit_factor = (self.gross_profit / self.gross_loss) if self.gross_loss > 0 else 0.0
        self.risk_reward_ratio = (self.average_win / self.average_loss) if self.average_loss > 0 else 0.0

class Simulation(BaseModel):
    """Enhanced simulation model for MES scalping strategy with AI integration"""
    model_config = ConfigDict(
        use_enum_values=True,
        json_encoders={datetime: lambda v: v.isoformat()}
    )

    # Identification
    simulation_id: str = Field(..., description="Unique simulation identifier")
    batch_id: Optional[str] = Field(None, description="Batch this simulation belongs to")

    # Configuration
    market_condition: MarketCondition
    symbols: List[str] = Field(default_factory=lambda: ["MES"])
    target_trades: int = Field(450, description="Target number of scalping trades")
    
    # AI Configuration - NEW FIELDS
    contract_qty_default: int = Field(default=1, description="Default contract quantity")
    allowed_directions: List[str] = Field(default_factory=lambda: ["long", "short"], description="Allowed trade directions")
    prompt_profile_id: str = Field(default="default", description="AI prompt profile ID")

    # Session and scenario tracking
    session_focus: Optional[str] = Field(None, description="AM, PM, or None for both")
    active_scenario: Optional[str] = Field(None, description="Current scenario preset")

    # Status and Timing
    status: SimulationStatus = SimulationStatus.PENDING
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: Optional[int] = None

    # Trading Data
    trades: List[Trade] = Field(default_factory=list)
    current_position: Optional[str] = Field(None, description="Current active position ID")

    # Performance
    metrics: SimulationMetrics = Field(default_factory=SimulationMetrics)

    # GPT-5 Performance Tracking - NEW FIELDS
    gpt5_decisions: int = 0
    gpt5_executions: int = 0
    gpt5_rejections_confidence: int = 0
    gpt5_rejections_schema: int = 0
    gpt5_api_failures: int = 0

    # Hybrid Mode Tracking - NEW FIELDS
    prefilter_calls: int = 0
    prefilter_passes: int = 0
    prefilter_failures: int = 0
    avg_prefilter_score: float = 0.0

    # Session tracking
    session_trade_counts: Dict[str, int] = Field(default_factory=lambda: {"AM": 0, "PM": 0})

    # Guardrail tracking
    soft_gate_blocks: int = 0
    cooldown_blocks: int = 0
    session_limit_blocks: int = 0

    # AI Learning Metrics - NEW FIELDS
    learning_updates_triggered: int = 0
    avg_ai_confidence: float = 0.0
    confidence_distribution: Dict[str, int] = Field(default_factory=lambda: {"high": 0, "medium": 0, "low": 0})

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None

    def update_ai_metrics(self, confidence: float, decision_result: str):
        """Update AI performance metrics"""
        self.gpt5_decisions += 1
        
        # Update confidence tracking
        if confidence >= 0.8:
            self.confidence_distribution["high"] += 1
        elif confidence >= 0.6:
            self.confidence_distribution["medium"] += 1
        else:
            self.confidence_distribution["low"] += 1
        
        # Update average confidence
        total_decisions = sum(self.confidence_distribution.values())
        if total_decisions > 0:
            self.avg_ai_confidence = (self.avg_ai_confidence * (total_decisions - 1) + confidence) / total_decisions
        
        # Track decision results
        if decision_result == "executed":
            self.gpt5_executions += 1
        elif decision_result == "rejected_confidence":
            self.gpt5_rejections_confidence += 1
        elif decision_result == "rejected_schema":
            self.gpt5_rejections_schema += 1
        elif decision_result == "api_failure":
            self.gpt5_api_failures += 1

    def update_prefilter_metrics(self, score: float, passed: bool):
        """Update hybrid mode prefilter metrics"""
        self.prefilter_calls += 1
        
        if passed:
            self.prefilter_passes += 1
        else:
            self.prefilter_failures += 1
        
        # Update average score
        self.avg_prefilter_score = (self.avg_prefilter_score * (self.prefilter_calls - 1) + score) / self.prefilter_calls

    def get_ai_performance_summary(self) -> Dict[str, Any]:
        """Get AI performance summary"""
        total_decisions = self.gpt5_decisions
        
        if total_decisions == 0:
            return {
                "total_decisions": 0,
                "execution_rate": 0.0,
                "avg_confidence": 0.0,
                "api_success_rate": 0.0,
                "prefilter_pass_rate": 0.0
            }
        
        execution_rate = self.gpt5_executions / total_decisions
        api_success_rate = (total_decisions - self.gpt5_api_failures) / total_decisions
        prefilter_pass_rate = self.prefilter_passes / self.prefilter_calls if self.prefilter_calls > 0 else 0.0
        
        return {
            "total_decisions": total_decisions,
            "executions": self.gpt5_executions,
            "execution_rate": round(execution_rate, 3),
            "avg_confidence": round(self.avg_ai_confidence, 3),
            "confidence_distribution": self.confidence_distribution,
            "api_success_rate": round(api_success_rate, 3),
            "prefilter_calls": self.prefilter_calls,
            "prefilter_pass_rate": round(prefilter_pass_rate, 3),
            "avg_prefilter_score": round(self.avg_prefilter_score, 1),
            "learning_updates": self.learning_updates_triggered,
            "rejections": {
                "confidence": self.gpt5_rejections_confidence,
                "schema": self.gpt5_rejections_schema,
                "api_failures": self.gpt5_api_failures
            }
        }
