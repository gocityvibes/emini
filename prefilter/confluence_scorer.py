"""
Confluence Scorer
Calculates prefilter scores using weighted confluence factors for MES scalping.
"""

import pandas as pd
import numpy as np
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple
from enum import Enum


class SetupType(Enum):
    """Recognized setup patterns."""
    ORB_RETEST_GO = "ORB_retest_go"
    EMA_PULLBACK = "20EMA_pullback"
    VWAP_REJECTION = "VWAP_rejection"
    NONE = "none"


class ConfluenceScorer:
    """
    Calculates confluence scores (0-100) using weighted factors.
    
    Scoring weights (must sum to 100):
    - Trend: 25 (multi-timeframe EMA alignment)
    - Volume: 20 (expansion vs MA20)
    - Structure: 20 (setup pattern recognition)
    - ATR Band: 10 (volatility in acceptable range)
    - Session: 10 (valid trading window)
    - Body Cleanliness: 5 (clean price action)
    - Liquidity: 5 (no air gaps)
    - News: 5 (news event proximity)
    """
    
    def __init__(self, config: Dict):
        """
        Initialize with configuration.
        
        Args:
            config: Configuration dict with prefilter settings
        """
        self.config = config
        self.weights = config['prefilter']['weights']
        self.thresholds = config['prefilter']['thresholds']
        
        # Validate weights sum to 100
        total_weight = sum(self.weights.values())
        if abs(total_weight - 100) > 0.1:
            raise ValueError(f"Weights must sum to 100, got {total_weight}")
    
    def calculate_score(self, 
                       indicators: Dict,
                       session_info: Dict,
                       recent_bars: Dict[str, pd.DataFrame],
                       news_status: Dict = None) -> Dict:
        """
        Calculate overall confluence score.
        
        Args:
            indicators: Multi-timeframe indicator values from TechnicalAnalyzer
            session_info: Session validation info from SessionValidator  
            recent_bars: Dict with '1m', '5m', '15m' recent bar data
            news_status: News event status (optional)
            
        Returns:
            Dict with total score and component subscores
        """
        subscores = {}
        
        # 1. Trend Score (25 points)
        subscores['trend'] = self._score_trend(indicators)
        
        # 2. Volume Score (20 points)  
        subscores['volume'] = self._score_volume(indicators, recent_bars.get('1m'))
        
        # 3. Structure Score (20 points)
        subscores['structure'] = self._score_structure(indicators, recent_bars)
        
        # 4. ATR Band Score (10 points)
        subscores['atr_band'] = self._score_atr_band(indicators)
        
        # 5. Session Score (10 points)
        subscores['session'] = self._score_session(session_info)
        
        # 6. Body Cleanliness Score (5 points)
        subscores['body_cleanliness'] = self._score_body_cleanliness(recent_bars.get('1m'))
        
        # 7. Liquidity Score (5 points)
        subscores['liquidity'] = self._score_liquidity(recent_bars.get('1m'))
        
        # 8. News Score (5 points)  
        subscores['news'] = self._score_news(news_status)
        
        # Calculate weighted total
        total_score = sum(
            subscores[factor] * self.weights[factor] / 100
            for factor in subscores.keys()
        )
        
        return {
            'total_score': round(total_score, 1),
            'subscores': subscores,
            'passing': total_score >= self.config['prefilter']['min_score']
        }
    
    def _score_trend(self, indicators: Dict) -> float:
        """
        Score trend alignment across timeframes (0-100).
        
        Perfect score: All EMAs aligned in same direction
        Good score: 1m+5m aligned, 15m neutral/aligned  
        Poor score: Mixed signals or choppy
        """
        if not all(key in indicators for key in ['1m_EMA_20', '5m_EMA_20', '15m_EMA_20', 'current_price']):
            return 0.0
        
        current_price = indicators['current_price']
        ema_1m = indicators['1m_EMA_20']
        ema_5m = indicators['5m_EMA_20'] 
        ema_15m = indicators['15m_EMA_20']
        
        # Determine price position relative to each EMA
        above_1m = current_price > ema_1m
        above_5m = current_price > ema_5m
        above_15m = current_price > ema_15m
        
        # Check EMA slope alignment (simplified)
        ema_1m_rising = ema_1m > indicators.get('1m_EMA_20_prev', ema_1m)
        ema_5m_rising = ema_5m > indicators.get('5m_EMA_20_prev', ema_5m)
        
        # Score based on alignment
        if above_1m == above_5m == above_15m:
            # Perfect alignment - all timeframes agree
            base_score = 100
        elif above_1m == above_5m:
            # 1m and 5m aligned, 15m different
            base_score = 75
        elif above_1m == above_15m:
            # 1m and 15m aligned, 5m different  
            base_score = 60
        else:
            # Mixed signals
            base_score = 25
        
        # Bonus for slope alignment
        if ema_1m_rising == above_1m and ema_5m_rising == above_5m:
            base_score = min(100, base_score + 15)
        
        return float(base_score)
    
    def _score_volume(self, indicators: Dict, bars_1m: Optional[pd.DataFrame]) -> float:
        """
        Score volume expansion vs MA20 (0-100).
        
        Excellent: 2.2x+ (especially for ORB)
        Good: 1.8x-2.2x
        Average: 1.5x-1.8x
        Poor: <1.5x
        """
        volume_multiple = indicators.get('1m_Volume_Multiple')
        if volume_multiple is None or pd.isna(volume_multiple):
            return 0.0
        
        if volume_multiple >= 2.2:
            return 100.0
        elif volume_multiple >= 1.8:
            return 80.0
        elif volume_multiple >= 1.5:
            return 60.0
        elif volume_multiple >= 1.2:
            return 40.0
        else:
            return 20.0
    
    def _score_structure(self, indicators: Dict, recent_bars: Dict[str, pd.DataFrame]) -> float:
        """
        Score setup structure recognition (0-100).
        
        Must identify one of three valid setups:
        - ORB retest-go
        - 20EMA pullback  
        - VWAP rejection
        """
        setup_type = self._identify_setup(indicators, recent_bars)
        
        if setup_type == SetupType.ORB_RETEST_GO:
            return 100.0
        elif setup_type == SetupType.EMA_PULLBACK:
            return 90.0
        elif setup_type == SetupType.VWAP_REJECTION:
            return 85.0
        else:
            return 0.0  # No valid setup identified
    
    def _identify_setup(self, indicators: Dict, recent_bars: Dict[str, pd.DataFrame]) -> SetupType:
        """
        Identify the current setup pattern.
        
        Returns:
            SetupType enum value
        """
        bars_1m = recent_bars.get('1m')
        if bars_1m is None or len(bars_1m) < 10:
            return SetupType.NONE
        
        current_price = indicators.get('current_price')
        ema_20 = indicators.get('1m_EMA_20')
        vwap = indicators.get('1m_VWAP')
        
        if not all([current_price, ema_20, vwap]):
            return SetupType.NONE
        
        # Get recent price action
        recent_highs = bars_1m['High'].tail(10)
        recent_lows = bars_1m['Low'].tail(10)
        recent_closes = bars_1m['Close'].tail(5)
        
        # ORB Retest-Go: Price broke opening range, pulled back, now retesting breakout
        if self._is_orb_retest_pattern(bars_1m, current_price):
            return SetupType.ORB_RETEST_GO
        
        # 20EMA Pullback: Price pulled back to EMA and bouncing
        elif self._is_ema_pullback_pattern(current_price, ema_20, recent_closes):
            return SetupType.EMA_PULLBACK
        
        # VWAP Rejection: Price tested VWAP and rejected
        elif self._is_vwap_rejection_pattern(current_price, vwap, recent_closes):
            return SetupType.VWAP_REJECTION
        
        return SetupType.NONE
    
    def _is_orb_retest_pattern(self, bars_1m: pd.DataFrame, current_price: float) -> bool:
        """Check for ORB retest-go pattern."""
        if len(bars_1m) < 20:
            return False
        
        # Define opening range (first 5-10 minutes)
        opening_bars = bars_1m.head(10)
        orb_high = opening_bars['High'].max()
        orb_low = opening_bars['Low'].min()
        
        # Check if we've had a breakout and retest
        recent_bars = bars_1m.tail(10)
        had_breakout = (recent_bars['High'].max() > orb_high + 0.5) or (recent_bars['Low'].min() < orb_low - 0.5)
        
        # Check if current price is near breakout level
        near_orb_high = abs(current_price - orb_high) < 1.0
        near_orb_low = abs(current_price - orb_low) < 1.0
        
        return had_breakout and (near_orb_high or near_orb_low)
    
    def _is_ema_pullback_pattern(self, current_price: float, ema_20: float, recent_closes: pd.Series) -> bool:
        """Check for 20EMA pullback pattern."""
        # Price should be near EMA
        distance_to_ema = abs(current_price - ema_20)
        near_ema = distance_to_ema < 1.0
        
        # Should have recent pullback to EMA
        touched_ema = any(abs(close - ema_20) < 0.5 for close in recent_closes)
        
        return near_ema and touched_ema
    
    def _is_vwap_rejection_pattern(self, current_price: float, vwap: float, recent_closes: pd.Series) -> bool:
        """Check for VWAP rejection pattern."""
        # Price should be moving away from VWAP after test
        distance_to_vwap = abs(current_price - vwap)
        
        # Should have recently tested VWAP
        tested_vwap = any(abs(close - vwap) < 0.5 for close in recent_closes)
        
        # Now moving away
        moving_away = distance_to_vwap > 0.5
        
        return tested_vwap and moving_away
    
    def _score_atr_band(self, indicators: Dict) -> float:
        """
        Score ATR within acceptable range (0-100).
        
        Optimal: 0.8-2.0 points
        Too low: <0.8 (insufficient movement)
        Too high: >2.0 (too volatile)
        """
        atr_5m = indicators.get('ATR_5m')
        if atr_5m is None or pd.isna(atr_5m):
            return 0.0
        
        min_atr = self.thresholds['atr_min']
        max_atr = self.thresholds['atr_max']
        
        if min_atr <= atr_5m <= max_atr:
            # Within optimal range - score based on position in range
            if 1.0 <= atr_5m <= 1.5:
                return 100.0  # Sweet spot
            else:
                return 80.0   # Good but not perfect
        elif atr_5m < min_atr:
            # Too low - scale from 0 to 60
            return max(0.0, (atr_5m / min_atr) * 60.0)
        else:
            # Too high - scale from 60 to 0
            excess = atr_5m - max_atr
            penalty = min(60.0, excess * 30.0)
            return max(0.0, 60.0 - penalty)
    
    def _score_session(self, session_info: Dict) -> float:
        """
        Score trading session validity (0-100).
        
        Perfect: In RTH A or RTH B
        Zero: Weekend, holiday, or lunch block
        """
        if not session_info.get('tradable_now', False):
            return 0.0
        
        current_session = session_info.get('current_session', '')
        
        if current_session == 'rth_a':
            return 100.0  # Morning session preferred
        elif current_session == 'rth_b':
            return 90.0   # Afternoon session good
        else:
            return 0.0    # Outside trading hours
    
    def _score_body_cleanliness(self, bars_1m: Optional[pd.DataFrame]) -> float:
        """
        Score price action cleanliness (0-100).
        
        Clean: Real bodies are ≥35% of total range
        Measures last 5 bars for recent clean action
        """
        if bars_1m is None or len(bars_1m) < 5:
            return 0.0
        
        recent_bars = bars_1m.tail(5)
        body_ratios = []
        
        for _, bar in recent_bars.iterrows():
            total_range = bar['High'] - bar['Low']
            if total_range <= 0:
                continue
                
            body_size = abs(bar['Close'] - bar['Open'])
            body_ratio = body_size / total_range
            body_ratios.append(body_ratio)
        
        if not body_ratios:
            return 0.0
        
        avg_body_ratio = sum(body_ratios) / len(body_ratios)
        min_ratio = self.thresholds['min_body_ratio']
        
        if avg_body_ratio >= min_ratio:
            # Scale from min_ratio to 1.0 → 60 to 100 points
            normalized = (avg_body_ratio - min_ratio) / (1.0 - min_ratio)
            return 60.0 + (normalized * 40.0)
        else:
            # Scale from 0 to min_ratio → 0 to 60 points
            return (avg_body_ratio / min_ratio) * 60.0
    
    def _score_liquidity(self, bars_1m: Optional[pd.DataFrame]) -> float:
        """
        Score liquidity - no air gaps in recent price action (0-100).
        
        Air gaps = bars with abnormally wide spreads relative to ATR
        """
        if bars_1m is None or len(bars_1m) < 10:
            return 50.0  # Neutral if insufficient data
        
        recent_bars = bars_1m.tail(10)
        ranges = recent_bars['High'] - recent_bars['Low']
        avg_range = ranges.mean()
        
        # Check for air gaps (ranges > 2x average)
        air_gaps = sum(1 for r in ranges if r > 2.0 * avg_range)
        
        if air_gaps == 0:
            return 100.0
        elif air_gaps == 1:
            return 70.0
        elif air_gaps == 2:
            return 40.0
        else:
            return 10.0
    
    def _score_news(self, news_status: Optional[Dict]) -> float:
        """
        Score news event proximity (0-100).
        
        Perfect: No red news events within ±10 minutes
        Zero: Red news event within block window
        """
        if news_status is None:
            return 100.0  # Assume clear if no news data
        
        in_news_block = news_status.get('in_block_window', False)
        
        if in_news_block:
            return 0.0
        else:
            return 100.0


# Example usage and scoring breakdown:
"""
Sample calculate_score() input:
indicators = {
    '1m_EMA_20': 5825.75,
    '5m_EMA_20': 5826.00, 
    '15m_EMA_20': 5824.50,
    '1m_VWAP': 5825.50,
    'ATR_5m': 1.25,
    '1m_Volume_Multiple': 2.1,
    'current_price': 5826.25
}

session_info = {
    'tradable_now': True,
    'current_session': 'rth_a',
    'in_rth_a': True
}

Sample output:
{
    'total_score': 78.5,
    'subscores': {
        'trend': 85.0,        # Good alignment
        'volume': 80.0,       # 2.1x expansion  
        'structure': 100.0,   # ORB retest identified
        'atr_band': 100.0,    # ATR in sweet spot
        'session': 100.0,     # RTH A session
        'body_cleanliness': 75.0,  # Clean recent bars
        'liquidity': 100.0,   # No air gaps
        'news': 100.0        # No news events
    },
    'passing': True          # Above 75 threshold
}

Scoring thresholds from config:
- volume_multiple ≥ 1.8 (≥ 2.2 for ORB)
- atr_min = 0.8, atr_max = 2.0  
- min_body_ratio = 0.35
- min_score = 75 to pass prefilter
"""