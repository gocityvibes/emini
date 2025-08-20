"""
Confidence Calibrator
Adaptive confidence threshold adjustment based on win rate performance.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, NamedTuple
from dataclasses import dataclass
from collections import deque


@dataclass
class CalibrationEvent:
    """Single calibration adjustment event."""
    timestamp: datetime
    trigger_reason: str  # 'win_rate_low', 'win_rate_high'
    old_floor: int
    new_floor: int
    trailing_win_rate: float
    trade_count: int


class ConfidenceCalibrator:
    """
    Adaptive confidence threshold calibrator.
    
    Rules:
    - If trailing-20 win rate < 78% → raise floor by +2 (max 92)
    - If trailing-20 win rate ≥ 85% → lower floor by -2 (min 82)
    - Apply adjustment at end of each trade
    - Persist current floor for the day
    - Reset to base level each new trading day
    """
    
    def __init__(self, config: Dict):
        """
        Initialize calibrator with configuration.
        
        Args:
            config: System configuration with GPT settings
        """
        self.config = config
        self.gpt_config = config['gpt']
        
        # Calibration parameters
        self.base_confidence_min = self.gpt_config['confidence_min']  # 85
        self.floor_min = self.gpt_config['floor_min']  # 82
        self.floor_max = self.gpt_config['floor_max']  # 92
        self.adjustment_step = 2
        
        # Thresholds for adjustment
        self.low_win_rate_threshold = 78.0
        self.high_win_rate_threshold = 85.0
        
        # State tracking
        self.current_floor = self.base_confidence_min
        self.trade_history = deque(maxlen=50)  # Keep more history for analysis
        self.calibration_history = deque(maxlen=20)  # Track adjustments
        
        # Daily reset tracking
        self.last_reset_date = datetime.now(timezone.utc).date()
        
    def record_trade_result(self, trade_result, gpt_confidence: int, timestamp: datetime) -> Optional[CalibrationEvent]:
        """
        Record trade result and potentially adjust confidence floor.
        
        Args:
            trade_result: TradeResult object from simulator
            gpt_confidence: Original GPT confidence score
            timestamp: Trade completion timestamp
            
        Returns:
            CalibrationEvent if adjustment made, None otherwise
        """
        # Check for daily reset
        self._check_daily_reset(timestamp)
        
        # Record trade
        is_win = trade_result.pnl_points > 0
        trade_record = {
            'timestamp': timestamp,
            'result': 'win' if is_win else 'loss',
            'pnl_points': trade_result.pnl_points,
            'gpt_confidence': gpt_confidence,
            'exit_reason': trade_result.exit_reason.value
        }
        
        self.trade_history.append(trade_record)
        
        # Only calibrate if we have enough trades
        if len(self.trade_history) < 20:
            return None
        
        # Calculate trailing-20 win rate
        trailing_20 = list(self.trade_history)[-20:]
        wins = sum(1 for trade in trailing_20 if trade['result'] == 'win')
        win_rate = (wins / 20) * 100
        
        # Determine if adjustment needed
        adjustment_event = None
        
        if win_rate < self.low_win_rate_threshold and self.current_floor < self.floor_max:
            # Win rate too low - raise floor (be more selective)
            old_floor = self.current_floor
            self.current_floor = min(self.floor_max, self.current_floor + self.adjustment_step)
            
            adjustment_event = CalibrationEvent(
                timestamp=timestamp,
                trigger_reason='win_rate_low',
                old_floor=old_floor,
                new_floor=self.current_floor,
                trailing_win_rate=win_rate,
                trade_count=len(self.trade_history)
            )
            
        elif win_rate >= self.high_win_rate_threshold and self.current_floor > self.floor_min:
            # Win rate high enough - lower floor (be less selective)
            old_floor = self.current_floor
            self.current_floor = max(self.floor_min, self.current_floor - self.adjustment_step)
            
            adjustment_event = CalibrationEvent(
                timestamp=timestamp,
                trigger_reason='win_rate_high',
                old_floor=old_floor,
                new_floor=self.current_floor,
                trailing_win_rate=win_rate,
                trade_count=len(self.trade_history)
            )
        
        # Record calibration event if adjustment made
        if adjustment_event:
            self.calibration_history.append(adjustment_event)
        
        return adjustment_event
    
    def get_current_confidence_threshold(self) -> int:
        """
        Get current adaptive confidence threshold.
        
        Returns:
            Current minimum confidence required for trades
        """
        return self.current_floor
    
    def _check_daily_reset(self, current_time: datetime):
        """Reset calibrator state for new trading day."""
        current_date = current_time.date()
        
        if current_date > self.last_reset_date:
            self.current_floor = self.base_confidence_min
            self.last_reset_date = current_date
            
            # Clear daily state but keep some history for analysis
            # Keep trade history across days for better long-term calibration
            # Only reset floor to base level
    
    def get_calibration_status(self) -> Dict:
        """
        Get current calibration status and statistics.
        
        Returns:
            Dict with calibration metrics
        """
        # Calculate recent win rates
        recent_stats = self._calculate_win_rate_stats()
        
        # Get recent calibration events
        recent_calibrations = [
            {
                'timestamp': event.timestamp.isoformat(),
                'reason': event.trigger_reason,
                'old_floor': event.old_floor,
                'new_floor': event.new_floor,
                'win_rate': event.trailing_win_rate
            }
            for event in list(self.calibration_history)[-5:]  # Last 5 adjustments
        ]
        
        return {
            'current_floor': self.current_floor,
            'base_threshold': self.base_confidence_min,
            'floor_range': [self.floor_min, self.floor_max],
            'total_trades': len(self.trade_history),
            'recent_stats': recent_stats,
            'total_calibrations': len(self.calibration_history),
            'recent_calibrations': recent_calibrations,
            'next_evaluation': self._get_next_evaluation_info()
        }
    
    def _calculate_win_rate_stats(self) -> Dict:
        """Calculate various win rate statistics."""
        if not self.trade_history:
            return {
                'trailing_5': None,
                'trailing_10': None,
                'trailing_20': None,
                'overall': None
            }
        
        stats = {}
        
        # Calculate different trailing windows
        for window in [5, 10, 20]:
            if len(self.trade_history) >= window:
                recent_trades = list(self.trade_history)[-window:]
                wins = sum(1 for trade in recent_trades if trade['result'] == 'win')
                stats[f'trailing_{window}'] = (wins / window) * 100
            else:
                stats[f'trailing_{window}'] = None
        
        # Overall win rate
        if self.trade_history:
            total_wins = sum(1 for trade in self.trade_history if trade['result'] == 'win')
            stats['overall'] = (total_wins / len(self.trade_history)) * 100
        else:
            stats['overall'] = None
        
        return stats
    
    def _get_next_evaluation_info(self) -> Dict:
        """Get information about next calibration evaluation."""
        trades_needed = max(0, 20 - len(self.trade_history))
        
        if trades_needed > 0:
            return {
                'trades_until_eligible': trades_needed,
                'status': 'building_history'
            }
        else:
            recent_stats = self._calculate_win_rate_stats()
            trailing_20 = recent_stats.get('trailing_20', 0)
            
            if trailing_20 < self.low_win_rate_threshold:
                direction = 'likely_increase'
                reason = f'Win rate {trailing_20:.1f}% < {self.low_win_rate_threshold}%'
            elif trailing_20 >= self.high_win_rate_threshold:
                direction = 'likely_decrease'
                reason = f'Win rate {trailing_20:.1f}% ≥ {self.high_win_rate_threshold}%'
            else:
                direction = 'no_change'
                reason = f'Win rate {trailing_20:.1f}% in acceptable range'
            
            return {
                'trades_until_eligible': 0,
                'status': 'ready_for_evaluation',
                'likely_direction': direction,
                'reason': reason,
                'current_win_rate': trailing_20
            }
    
    def force_adjustment(self, new_floor: int, reason: str = 'manual_override') -> bool:
        """
        Manually force confidence floor adjustment.
        
        Args:
            new_floor: New confidence floor value
            reason: Reason for manual adjustment
            
        Returns:
            True if adjustment successful
        """
        if not (self.floor_min <= new_floor <= self.floor_max):
            return False
        
        old_floor = self.current_floor
        self.current_floor = new_floor
        
        # Record manual adjustment
        adjustment_event = CalibrationEvent(
            timestamp=datetime.now(timezone.utc),
            trigger_reason=reason,
            old_floor=old_floor,
            new_floor=new_floor,
            trailing_win_rate=self._calculate_win_rate_stats().get('trailing_20', 0),
            trade_count=len(self.trade_history)
        )
        
        self.calibration_history.append(adjustment_event)
        
        return True
    
    def get_performance_analysis(self) -> Dict:
        """
        Get detailed performance analysis for calibration effectiveness.
        
        Returns:
            Dict with performance metrics
        """
        if len(self.trade_history) < 10:
            return {'status': 'insufficient_data'}
        
        # Analyze performance by confidence ranges
        confidence_ranges = {
            '82-85': [],
            '86-89': [],
            '90-94': [],
            '95-100': []
        }
        
        for trade in self.trade_history:
            confidence = trade['gpt_confidence']
            is_win = trade['result'] == 'win'
            
            if 82 <= confidence <= 85:
                confidence_ranges['82-85'].append(is_win)
            elif 86 <= confidence <= 89:
                confidence_ranges['86-89'].append(is_win)
            elif 90 <= confidence <= 94:
                confidence_ranges['90-94'].append(is_win)
            elif 95 <= confidence <= 100:
                confidence_ranges['95-100'].append(is_win)
        
        # Calculate win rates by range
        range_stats = {}
        for range_name, results in confidence_ranges.items():
            if results:
                win_rate = (sum(results) / len(results)) * 100
                range_stats[range_name] = {
                    'win_rate': win_rate,
                    'sample_size': len(results)
                }
            else:
                range_stats[range_name] = {
                    'win_rate': None,
                    'sample_size': 0
                }
        
        return {
            'status': 'analysis_ready',
            'total_calibrations': len(self.calibration_history),
            'performance_by_confidence': range_stats,
            'calibration_effectiveness': self._assess_calibration_effectiveness(),
            'recommendations': self._generate_recommendations()
        }
    
    def _assess_calibration_effectiveness(self) -> str:
        """Assess how well the calibration system is working."""
        if len(self.calibration_history) < 3:
            return 'insufficient_calibration_history'
        
        recent_stats = self._calculate_win_rate_stats()
        trailing_20 = recent_stats.get('trailing_20', 0)
        
        if trailing_20 >= 80:
            return 'effective'
        elif trailing_20 >= 75:
            return 'marginal'
        else:
            return 'ineffective'
    
    def _generate_recommendations(self) -> List[str]:
        """Generate calibration recommendations."""
        recommendations = []
        
        recent_stats = self._calculate_win_rate_stats()
        trailing_20 = recent_stats.get('trailing_20', 0)
        
        if trailing_20 and trailing_20 < 75:
            recommendations.append("Consider raising base confidence threshold")
        
        if len(self.calibration_history) > 10:
            recommendations.append("System has extensive calibration history - review for patterns")
        
        if self.current_floor >= self.floor_max:
            recommendations.append("At maximum floor - may need strategy review")
        
        return recommendations


# Calibration rules and examples:
"""
Adaptive Calibration Rules:

Trigger Conditions:
- Evaluate after each completed trade
- Require minimum 20 trades for calibration
- Check trailing-20 win rate vs thresholds

Adjustment Logic:
- Win rate < 78% → +2 confidence floor (max 92)
- Win rate ≥ 85% → -2 confidence floor (min 82)  
- No change if 78% ≤ win rate < 85%

Daily Reset:
- Floor resets to base (85) each new trading day
- Trade history persists for better long-term analysis
- Calibration events logged with timestamps

Example Calibration Sequence:
Day 1: Base floor 85, trades complete, win rate 72% → floor 87
Day 1: More trades, win rate 76% → floor 89  
Day 2: Reset to 85, new trades, win rate 88% → floor 83
Day 2: More trades, win rate 82% → floor 85 (no change)

CalibrationEvent Structure:
{
    timestamp: datetime(2025, 1, 20, 15, 30, 0),
    trigger_reason: 'win_rate_low',
    old_floor: 85,
    new_floor: 87,
    trailing_win_rate: 72.5,
    trade_count: 25
}

Status Output Example:
{
    current_floor: 87,
    base_threshold: 85,
    floor_range: [82, 92],
    total_trades: 25,
    recent_stats: {
        trailing_5: 80.0,
        trailing_10: 75.0,
        trailing_20: 72.5,
        overall: 74.2
    },
    total_calibrations: 3,
    next_evaluation: {
        trades_until_eligible: 0,
        status: 'ready_for_evaluation',
        likely_direction: 'likely_increase',
        current_win_rate: 72.5
    }
}

Performance Analysis:
- Tracks win rates by confidence ranges
- Assesses calibration effectiveness
- Provides recommendations for improvement
- Identifies patterns in confidence vs performance
"""