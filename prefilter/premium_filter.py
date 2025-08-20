"""
Premium Filter
- Validates session/time rules
- Scores confluence + quality
- Extracts risk factors (negatives)
- Produces a TradingCandidate or returns None
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

from .session_validator import SessionValidator
from .confluence_scorer import ConfluenceScorer, SetupType


@dataclass
class TradingCandidate:
    # Core identity
    symbol: str
    setup_type: str            # e.g., 'ORB', 'EMA-Tap', 'VWAP-Reject'
    direction: str             # 'long' | 'short'
    timestamp: datetime

    # Session / regime
    session_label: str         # 'rth_a' | 'rth_b' | 'lunch_block' | 'outside_hours'
    market_regime: str         # 'bull' | 'bear' | 'sideways' | 'mixed'

    # Indicators / features
    prefilter_score: float
    confluence_factors: List[str]
    ema_alignment: str         # 'bullish_aligned' | 'bearish_aligned' | 'mixed'
    volume_multiple: float     # vs. 20-bar avg, etc.
    atr_5m: float              # ATR(5m) in points
    vwap_distance: float       # points from VWAP (signed)
    wickiness: float = 1.0

    # Negatives
    risk_factors: List[str] = field(default_factory=list)


class PremiumFilter:
    """
    Builds a TradingCandidate from raw feature blobs.
    Applies:
      - Session validation
      - Confluence scoring
      - Negative (risk) factor extraction
      - Final prefilter scoring w/ penalties
    Returns None if:
      - Outside tradable windows
      - Hard negative rule fires (e.g., major event block)
      - Score below min threshold
    """

    def __init__(self, config: Dict, session_validator: SessionValidator, confluence_scorer: ConfluenceScorer):
        self.config = config or {}
        self.validator = session_validator
        self.scorer = confluence_scorer

        # Thresholds
        th = (self.config.get("prefilter", {}) or {})
        self.min_score = float(th.get("min_score", 70.0))
        self.max_vwap_abs = float(th.get("max_vwap_abs", 2.0))              # far from VWAP → risky
        self.min_volume_mult = float(th.get("min_volume_mult", 1.2))        # < 1.2x volume → low_volume
        self.atr_range: Tuple[float, float] = tuple(th.get("atr_range", [0.6, 2.2]))  # outside → suboptimal_volatility
        self.event_block_tags = set(th.get("event_block_tags", ["FOMC", "CPI", "NFP"]))

        # Bonuses/Penalties
        self.ema_bonus = float(th.get("ema_bonus", 2.0))
        self.vwap_near_bonus = float(th.get("vwap_near_bonus", 1.0))
        self.penalty_low_volume = float(th.get("penalty_low_volume", 2.0))
        self.penalty_weak_trend = float(th.get("penalty_weak_trend", 1.5))
        self.penalty_suboptimal_vol = float(th.get("penalty_suboptimal_vol", 1.0))
        self.penalty_far_vwap = float(th.get("penalty_far_vwap", 1.0))
        self.penalty_lunch = float(th.get("penalty_lunch", 3.0))
        self.penalty_outside_hours = float(th.get("penalty_outside_hours", 99.0))  # auto-kill

    # ---------- Public API ----------

    def evaluate(self, raw: Dict) -> Optional[TradingCandidate]:
        """
        Convert a raw feature dict to a scored TradingCandidate.
        raw must include:
          symbol, setup_type, direction, indicators, regime, timestamp (UTC or aware)
        """
        # Timestamp
        ts = raw.get("timestamp")
        if not isinstance(ts, datetime):
            ts = datetime.now(timezone.utc)

        # Session validation
        sess = self.validator.validate_session(ts)  # dict with flags + session label
        session_label = sess.get("current_session", "outside_hours")
        if not sess.get("tradable_now", False):
            # mark risk factors; we may still compute but will likely return None
            rf = []
            if sess.get("is_weekend"): rf.append("weekend_block")
            if sess.get("is_holiday"): rf.append("holiday_block")
            if session_label == "lunch_block": rf.append("lunch_block")
            rf.append("outside_hours")
            # outright block
            return None

        # Indicators blob
        ind = raw.get("indicators", {}) or {}
        # Expected keys:
        # ema_alignment, volume_multiple, atr_5m, vwap_distance, wickiness, trend_strength, news_tags(list)

        ema_alignment = ind.get("ema_alignment", "mixed")
        volume_mult = float(ind.get("volume_multiple", 1.0))
        atr_5m = float(ind.get("atr_5m", 1.0))
        vwap_dist = float(ind.get("vwap_distance", 0.0))
        wick = float(ind.get("wickiness", 1.0))
        trend_strength = float(ind.get("trend_strength", 0.0))
        news_tags = set(ind.get("news_tags", []) or [])

        # Hard negative: major event block
        if self.event_block_tags.intersection(news_tags):
            return None  # don’t form candidate at all

        # Confluence scoring
        setup = raw.get("setup_type", "Unknown")
        direction = raw.get("direction", "long")
        try:
            setup_enum = SetupType[setup] if isinstance(setup, str) else setup
        except Exception:
            setup_enum = SetupType.ORB  # sane default

        conf_score, conf_factors = self.scorer.score(
            setup_type=setup_enum,
            direction=direction,
            ema_alignment=ema_alignment,
            volume_multiple=volume_mult,
            atr_5m=atr_5m,
            vwap_distance=vwap_dist,
            wickiness=wick,
            trend_strength=trend_strength,
            extras=ind
        )

        # Negatives (risk) extraction
        risk_factors = self._extract_risk_factors(
            volume_mult=volume_mult,
            ema_alignment=ema_alignment,
            atr_5m=atr_5m,
            vwap_distance=vwap_dist,
            session_label=session_label,
            trend_strength=trend_strength
        )

        # Final prefilter score (0..100)
        score = self._compute_prefilter_score(
            base_conf=conf_score,
            ema_alignment=ema_alignment,
            vwap_distance=vwap_dist,
            volume_mult=volume_mult,
            atr_5m=atr_5m,
            risk_factors=risk_factors
        )

        if score < self.min_score:
            return None

        return TradingCandidate(
            symbol=raw.get("symbol", "MES=F"),
            setup_type=setup,
            direction=direction,
            timestamp=ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc),
            session_label=session_label,
            market_regime=raw.get("regime", "mixed"),
            prefilter_score=round(score, 2),
            confluence_factors=conf_factors,
            ema_alignment=ema_alignment,
            volume_multiple=volume_mult,
            atr_5m=atr_5m,
            vwap_distance=vwap_dist,
            wickiness=wick,
            risk_factors=risk_factors
        )

    # ---------- Internals ----------

    def _extract_risk_factors(
        self,
        *,
        volume_mult: float,
        ema_alignment: str,
        atr_5m: float,
        vwap_distance: float,
        session_label: str,
        trend_strength: float
    ) -> List[str]:
        rf: List[str] = []

        # Session negatives
        if session_label == "lunch_block":
            rf.append("lunch_block")

        # Volume
        if volume_mult < self.min_volume_mult:
            rf.append("low_volume")

        # EMA / trend alignment
        if ema_alignment == "mixed" or trend_strength < 0.25:
            rf.append("weak_trend_alignment")

        # Volatility window
        lo, hi = self.atr_range
        if atr_5m < lo or atr_5m > hi:
            rf.append("suboptimal_volatility")

        # VWAP distance
        if abs(vwap_distance) > self.max_vwap_abs:
            rf.append("far_from_vwap")

        return rf

    def _compute_prefilter_score(
        self,
        *,
        base_conf: float,
        ema_alignment: str,
        vwap_distance: float,
        volume_mult: float,
        atr_5m: float,
        risk_factors: List[str]
    ) -> float:
        score = float(base_conf)

        # Bonuses
        if ema_alignment in ("bullish_aligned", "bearish_aligned"):
            score += self.ema_bonus
        if abs(vwap_distance) <= 0.5:
            score += self.vwap_near_bonus

        # Light quality shaping
        if volume_mult > 2.0:
            score += 1.0
        lo, hi = self.atr_range
        if lo <= atr_5m <= hi:
            score += 0.5

        # Penalties from negatives (stacking)
        if "low_volume" in risk_factors:
            score -= self.penalty_low_volume
        if "weak_trend_alignment" in risk_factors:
            score -= self.penalty_weak_trend
        if "suboptimal_volatility" in risk_factors:
            score -= self.penalty_suboptimal_vol
        if "far_from_vwap" in risk_factors:
            score -= self.penalty_far_vwap
        if "lunch_block" in risk_factors:
            score -= self.penalty_lunch
        if "outside_hours" in risk_factors:
            score -= self.penalty_outside_hours  # effectively 0

        # Clamp
        return max(0.0, min(100.0, score))
