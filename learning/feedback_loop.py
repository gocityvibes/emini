"""
Feedback Loop System
Records and processes trade outcomes for learning and adaptation.
"""

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum


class TradeOutcome(Enum):
    """Trade result categories."""
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"
    TIMEOUT = "timeout"


@dataclass
class TradeRecord:
    """Complete trade record for learning system."""
    # Trade identification
    trade_id: str
    timestamp: datetime
    
    # Trade outcome
    result: str  # win/loss/breakeven/timeout
    pnl_pts: float
    pnl_dollars: float
    
    # Setup information
    prefilter_score: float
    gpt_confidence: int
    setup_type: str
    session: str
    
    # Execution details
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    direction: str
    exit_reason: str
    
    # Performance metrics
    time_to_target_sec: Optional[int]
    time_to_be_sec: Optional[int]
    mae: float  # Maximum Adverse Excursion
    mfe: float  # Maximum Favorable Excursion
    
    # Market context
    volume_multiple: float
    atr_5m: float
    ema_alignment: str
    vwap_distance: float
    
    # Quality metrics
    wickiness: float  # Wick vs body ratio
    slippage_pts: float
    commission_paid: float
    
    # Learning features
    confluence_factors: List[str]
    risk_factors: List[str]
    market_regime: str  # trending/ranging/volatile
    
    # Additional context
    metadata: Dict[str, Any]


class FeedbackLoop:
    """
    Trade feedback processing system for continuous learning.
    
    Features:
    - Complete trade record creation
    - Performance metric calculation  
    - Learning signal generation
    - Integration with calibrator and pattern memory
    - Market regime detection
    - Quality assessment
    """
    
    def __init__(self, config: Dict):
        """
        Initialize feedback loop system.
        
        Args:
            config: System configuration
        """
        self.config = config
        self.trade_records = []
        self.learning_signals = []
        
        # Components for integration
        self.confidence_calibrator = None
        self.hard_negatives = None
        self.pattern_memory = None
        
    def set_learning_components(self, calibrator, hard_negatives, pattern_memory):
        """Set references to other learning components."""
        self.confidence_calibrator = calibrator
        self.hard_negatives = hard_negatives
        self.pattern_memory = pattern_memory
    
    def record_trade_completion(self,
                              trade_result,
                              candidate_info: Dict,
                              gpt_decision: Dict,
                              market_context: Dict) -> TradeRecord:
        """
        Record completed trade and trigger learning updates.
        
        Args:
            trade_result: TradeResult from simulator
            candidate_info: Original candidate data
            gpt_decision: GPT decision details
            market_context: Additional market information
            
        Returns:
            Complete TradeRecord for storage
        """
        # Generate trade ID
        trade_id = f"trade_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        # Determine outcome category
        outcome = self._categorize_outcome(trade_result)
        
        # Calculate quality metrics
        quality_metrics = self._calculate_quality_metrics(trade_result, candidate_info)
        
        # Detect market regime
        market_regime = self._detect_market_regime(market_context)
        
        # Create complete trade record
        trade_record = TradeRecord(
            trade_id=trade_id,
            timestamp=trade_result.exit_time,
            
            # Outcome
            result=outcome.value,
            pnl_pts=trade_result.pnl_points,
            pnl_dollars=trade_result.pnl_dollars,
            
            # Setup
            prefilter_score=candidate_info['candidate'].prefilter_score,
            gpt_confidence=gpt_decision['confidence'],
            setup_type=candidate_info['candidate'].setup_type,
            session=candidate_info['candidate'].session_label,
            
            # Execution
            entry_price=trade_result.entry_price,
            exit_price=trade_result.exit_price,
            entry_time=trade_result.entry_time,
            exit_time=trade_result.exit_time,
            direction=trade_result.direction.value,
            exit_reason=trade_result.exit_reason.value,
            
            # Performance
            time_to_target_sec=trade_result.time_to_target_seconds,
            time_to_be_sec=trade_result.time_to_be_seconds,
            mae=trade_result.mae,
            mfe=trade_result.mfe,
            
            # Market context
            volume_multiple=candidate_info['candidate'].volume_multiple,
            atr_5m=candidate_info['candidate'].atr_5m,
            ema_alignment=candidate_info['candidate'].ema_alignment,
            vwap_distance=candidate_info['candidate'].vwap_distance,
            
            # Quality
            wickiness=quality_metrics['wickiness'],
            slippage_pts=trade_result.slippage_points,
            commission_paid=trade_result.commission_paid,
            
            # Learning
            confluence_factors=candidate_info['candidate'].confidence_factors,
            risk_factors=candidate_info['candidate'].risk_factors,
            market_regime=market_regime,
            
            # Metadata
            metadata={
                'gpt_processing_time_ms': gpt_decision.get('processing_time_ms', 0),
                'gpt_rationale': gpt_decision.get('rationale', ''),
                'prefilter_subscores': market_context.get('prefilter_subscores', {}),
                'bars_to_target': quality_metrics.get('bars_to_target', 0)
            }
        )
        
        # Store record
        self.trade_records.append(trade_record)
        
        # Trigger learning updates
        self._trigger_learning_updates(trade_record)
        
        # Generate learning signals
        learning_signal = self._generate_learning_signal(trade_record)
        self.learning_signals.append(learning_signal)
        
        return trade_record
    
    def _categorize_outcome(self, trade_result) -> TradeOutcome:
        """Categorize trade outcome."""
        if trade_result.exit_reason.value == 'timeout':
            return TradeOutcome.TIMEOUT
        elif trade_result.pnl_points > 0.1:  # Small buffer for breakeven
            return TradeOutcome.WIN
        elif trade_result.pnl_points < -0.1:
            return TradeOutcome.LOSS
        else:
            return TradeOutcome.BREAKEVEN
    
    def _calculate_quality_metrics(self, trade_result, candidate_info: Dict) -> Dict:
        """Calculate additional quality metrics."""
        metrics = {}
        
        # Wickiness - measure of choppy vs clean price action
        # This would ideally use bar data, for now use MAE/MFE ratio
        if trade_result.mfe > 0:
            metrics['wickiness'] = trade_result.mae / trade_result.mfe
        else:
            metrics['wickiness'] = 1.0  # Neutral if no favorable movement
        
        # Time-based metrics
        if trade_result.time_to_target_seconds:
            metrics['bars_to_target'] = trade_result.time_to_target_seconds // 60  # Rough 1min bars
        else:
            metrics['bars_to_target'] = 0
        
        return metrics
    
    def _detect_market_regime(self, market_context: Dict) -> str:
        """Detect current market regime for context."""
        # Simplified regime detection based on ATR and trend alignment
        atr = market_context.get('atr_5m', 1.0)
        trend_score = market_context.get('trend_score', 50)
        
        if atr > 1.8:
            return 'volatile'
        elif trend_score > 75:
            return 'trending'
        elif trend_score < 40:
            return 'ranging'
        else:
            return 'mixed'
    
    def _trigger_learning_updates(self, trade_record: TradeRecord):
        """Trigger updates to learning components."""
        
        # Update confidence calibrator
        if self.confidence_calibrator:
            try:
                calibration_event = self.confidence_calibrator.record_trade_result(
                    trade_record, 
                    trade_record.gpt_confidence,
                    trade_record.timestamp
                )
                if calibration_event:
                    trade_record.metadata['calibration_event'] = asdict(calibration_event)
            except Exception as e:
                print(f"Calibrator update error: {e}")
        
        # Update hard negatives
        if self.hard_negatives and trade_record.result == 'loss':
            try:
                self.hard_negatives.process_loss(trade_record)
            except Exception as e:
                print(f"Hard negatives update error: {e}")
        
        # Update pattern memory
        if self.pattern_memory:
            try:
                self.pattern_memory.update_pattern_stats(trade_record)
            except Exception as e:
                print(f"Pattern memory update error: {e}")
    
    def _generate_learning_signal(self, trade_record: TradeRecord) -> Dict:
        """Generate learning signals for system improvement."""
        
        signal = {
            'trade_id': trade_record.trade_id,
            'timestamp': trade_record.timestamp.isoformat(),
            'signal_type': [],
            'recommendations': [],
            'severity': 'info'
        }
        
        # High confidence loss signal
        if trade_record.result == 'loss' and trade_record.gpt_confidence >= 90:
            signal['signal_type'].append('high_confidence_loss')
            signal['recommendations'].append('Review setup criteria for false positives')
            signal['severity'] = 'warning'
        
        # Poor execution signal
        if trade_record.mae > 1.0:  # Large adverse move
            signal['signal_type'].append('poor_execution')
            signal['recommendations'].append('Review entry timing and market conditions')
        
        # Timeout pattern signal
        if trade_record.result == 'timeout':
            signal['signal_type'].append('timeout_pattern')
            signal['recommendations'].append('Analyze setup momentum requirements')
        
        # Quality degradation signal
        if trade_record.wickiness > 2.0:  # Very choppy
            signal['signal_type'].append('choppy_conditions')
            signal['recommendations'].append('Consider stricter body cleanliness requirements')
        
        return signal
    
    def get_performance_summary(self, lookback_trades: int = 50) -> Dict:
        """
        Get performance summary for recent trades.
        
        Args:
            lookback_trades: Number of recent trades to analyze
            
        Returns:
            Dict with performance metrics
        """
        if not self.trade_records:
            return {'status': 'no_trades'}
        
        recent_trades = self.trade_records[-lookback_trades:]
        
        # Basic metrics
        total_trades = len(recent_trades)
        wins = sum(1 for t in recent_trades if t.result == 'win')
        losses = sum(1 for t in recent_trades if t.result == 'loss')
        timeouts = sum(1 for t in recent_trades if t.result == 'timeout')
        
        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
        
        # P&L metrics
        total_pnl = sum(t.pnl_pts for t in recent_trades)
        avg_win = sum(t.pnl_pts for t in recent_trades if t.pnl_pts > 0) / max(1, wins)
        avg_loss = sum(t.pnl_pts for t in recent_trades if t.pnl_pts < 0) / max(1, losses)
        
        # Time metrics
        target_times = [t.time_to_target_sec for t in recent_trades if t.time_to_target_sec]
        avg_time_to_target = sum(target_times) / len(target_times) if target_times else 0
        
        # Setup breakdown
        setup_stats = {}
        for trade in recent_trades:
            setup = trade.setup_type
            if setup not in setup_stats:
                setup_stats[setup] = {'trades': 0, 'wins': 0, 'pnl': 0}
            setup_stats[setup]['trades'] += 1
            if trade.result == 'win':
                setup_stats[setup]['wins'] += 1
            setup_stats[setup]['pnl'] += trade.pnl_pts
        
        # Calculate win rates by setup
        for setup, stats in setup_stats.items():
            stats['win_rate'] = (stats['wins'] / stats['trades']) * 100 if stats['trades'] > 0 else 0
        
        return {
            'status': 'summary_ready',
            'lookback_trades': total_trades,
            'overall': {
                'win_rate': win_rate,
                'total_pnl_pts': total_pnl,
                'avg_win_pts': avg_win,
                'avg_loss_pts': avg_loss,
                'profit_factor': abs(avg_win * wins / (avg_loss * losses)) if losses > 0 else float('inf'),
                'avg_time_to_target_sec': avg_time_to_target
            },
            'breakdown': {
                'wins': wins,
                'losses': losses,
                'timeouts': timeouts,
                'breakevens': total_trades - wins - losses - timeouts
            },
            'by_setup': setup_stats,
            'recent_signals': self.learning_signals[-10:] if self.learning_signals else []
        }
    
    def get_trade_history(self, 
                         date_filter: Optional[str] = None,
                         setup_filter: Optional[str] = None,
                         limit: int = 100) -> List[Dict]:
        """
        Get filtered trade history.
        
        Args:
            date_filter: Date string (YYYY-MM-DD) to filter by
            setup_filter: Setup type to filter by
            limit: Maximum number of trades to return
            
        Returns:
            List of trade record dicts
        """
        filtered_trades = self.trade_records
        
        # Apply date filter
        if date_filter:
            try:
                filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
                filtered_trades = [t for t in filtered_trades if t.timestamp.date() == filter_date]
            except ValueError:
                pass  # Invalid date format, skip filter
        
        # Apply setup filter
        if setup_filter:
            filtered_trades = [t for t in filtered_trades if t.setup_type == setup_filter]
        
        # Apply limit and convert to dicts
        recent_trades = filtered_trades[-limit:] if filtered_trades else []
        
        return [asdict(trade) for trade in recent_trades]
    
    def export_learning_data(self) -> Dict:
        """Export learning data for analysis."""
        return {
            'trade_records': [asdict(record) for record in self.trade_records],
            'learning_signals': self.learning_signals,
            'export_timestamp': datetime.now(timezone.utc).isoformat(),
            'total_trades': len(self.trade_records)
        }


# Trade record structure and learning integration:
"""
Complete TradeRecord fields:
- Trade ID and timestamps
- Outcome: win/loss/breakeven/timeout
- P&L in points and dollars
- Setup information (type, session, scores)
- Execution details (prices, times, direction)
- Performance metrics (MAE, MFE, time to target)
- Market context (volume, ATR, alignment)
- Quality metrics (wickiness, slippage)
- Learning features (confluences, risk factors)
- Market regime classification
- Metadata for additional context

Learning Integration:
1. Trade completed → record_trade_completion()
2. Update confidence calibrator
3. Update hard negatives (if loss)
4. Update pattern memory
5. Generate learning signals
6. Store complete record

Learning Signals Generated:
- high_confidence_loss: GPT confidence ≥90 but loss
- poor_execution: Large adverse moves (MAE > 1.0)
- timeout_pattern: Frequent timeouts in setup
- choppy_conditions: High wickiness ratio

Performance Summary Example:
{
    'overall': {
        'win_rate': 78.5,
        'total_pnl_pts': 12.75,
        'avg_win_pts': 1.15,
        'avg_loss_pts': -0.68,
        'profit_factor': 2.1,
        'avg_time_to_target_sec': 42
    },
    'by_setup': {
        'ORB_retest_go': {
            'trades': 15,
            'wins': 12,
            'win_rate': 80.0,
            'pnl': 8.25
        }
    }
}

Trade History API:
- Filter by date: /metrics/trades?date=2025-01-20
- Filter by setup: /metrics/trades?setup=ORB_retest_go
- Paginated results with limit parameter
- Complete trade records with all context
"""