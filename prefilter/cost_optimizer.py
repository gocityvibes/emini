"""
Cost Optimizer
- Enforces GPT daily caps & emergency pauses
- Skips expensive GPT calls for risky/low-score candidates
- Tracks usage and session outcomes
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from enum import Enum
from datetime import datetime, timezone


class BudgetStatus(str, Enum):
    OK = "ok"
    PAUSED = "paused"
    EXCEEDED = "exceeded"


@dataclass
class BudgetState:
    daily_cap: int
    used_today: int = 0
    paused: bool = False
    paused_reason: Optional[str] = None
    last_reset_date: Optional[str] = None


class CostOptimizer:
    """
    Decision layer for whether to send a candidate to GPT.

    Config keys:
      gpt:
        daily_call_cap: 500
        near_cap_warn: 0.9
      prefilter:
        min_score: 70  # (used upstream; repeated here as safety)
        risky_max_allowed_flags: 1
      safety:
        emergency_pause_triggers:
          recent_gpt_passes: 3
          session_losses: 2
    """

    def __init__(self, config: Dict):
        self.config = config or {}
        gpt_cfg = (self.config.get("gpt", {}) or {})
        self.state = BudgetState(
            daily_cap=int(gpt_cfg.get("daily_call_cap", 500)),
            used_today=0,
            paused=False,
            paused_reason=None,
            last_reset_date=self._today_str()
        )

        pf = (self.config.get("prefilter", {}) or {})
        self.min_score = float(pf.get("min_score", 70.0))
        self.risky_max_allowed_flags = int(pf.get("risky_max_allowed_flags", 1))

        safety = (self.config.get("safety", {}) or {})
        em = (safety.get("emergency_pause_triggers", {}) or {})
        self.trigger_recent_gpt_passes = int(em.get("recent_gpt_passes", 3))
        self.trigger_session_losses = int(em.get("session_losses", 2))

        # rolling trackers
        self.recent_gpt_passes: List[str] = []  # store candidate IDs/summaries passed to GPT
        self.session_losses = 0                 # reset per session if you call reset_session()

    # ---------- Public API ----------

    def reset_session(self):
        """Call when session changes (e.g., moving from RTH-A to RTH-B)."""
        self.session_losses = 0
        self.recent_gpt_passes.clear()

    def note_trade_outcome(self, pnl_pts: float):
        """Call after a trade completes to update session loss counter."""
        if pnl_pts < 0:
            self.session_losses += 1

    def should_send_to_gpt(self, candidate) -> Tuple[bool, str]:
        """
        Decide whether to call GPT for this candidate.
        Returns (allow, reason).
        """
        self._maybe_reset_day()

        if self.state.paused:
            return (False, self.state.paused_reason or "paused")

        # Budget cap checks
        if self.state.used_today >= self.state.daily_cap:
            self.state.paused = True
            self.state.paused_reason = "daily_cap_exceeded"
            return (False, "budget_exceeded")

        # Emergency pause heuristic
        if len(self.recent_gpt_passes) >= self.trigger_recent_gpt_passes and self.session_losses >= self.trigger_session_losses:
            self.state.paused = True
            self.state.paused_reason = "emergency_pause_recent_passes_and_losses"
            return (False, "emergency_pause")

        # Candidate quality gates
        score = float(getattr(candidate, "prefilter_score", 0.0))
        if score < self.min_score:
            return (False, "below_min_score")

        # Negative hooks: too many red flags → skip GPT
        risk_factors = list(getattr(candidate, "risk_factors", []) or [])
        if self._is_overly_risky(risk_factors):
            return (False, "too_many_risks")

        # All clear
        return (True, "ok")

    def record_gpt_call(self, candidate_id: str):
        """Increment usage and rolling pass list when GPT is actually called."""
        self._maybe_reset_day()
        self.state.used_today += 1
        self.recent_gpt_passes.append(candidate_id)
        # keep last N = trigger_recent_gpt_passes
        if len(self.recent_gpt_passes) > self.trigger_recent_gpt_passes:
            self.recent_gpt_passes = self.recent_gpt_passes[-self.trigger_recent_gpt_passes:]

    def get_status(self) -> Dict:
        """Expose current budget status for API/metrics."""
        self._maybe_reset_day()
        status = BudgetStatus.OK
        if self.state.paused:
            status = BudgetStatus.PAUSED
        elif self.state.used_today >= self.state.daily_cap:
            status = BudgetStatus.EXCEEDED
        return {
            "status": status.value,
            "used_today": self.state.used_today,
            "daily_cap": self.state.daily_cap,
            "paused": self.state.paused,
            "paused_reason": self.state.paused_reason
        }

    # ---------- Internals ----------

    def _is_overly_risky(self, risk_factors: List[str]) -> bool:
        """
        If risk flags exceed the allowed count, skip GPT to save budget.
        Example flags: low_volume, weak_trend_alignment, suboptimal_volatility, far_from_vwap, lunch_block
        """
        # Count severe/non-severe; you can tune this weighting if desired.
        severe = {"lunch_block", "outside_hours"}
        count = 0
        for r in risk_factors:
            count += 2 if r in severe else 1
        return count > self.risky_max_allowed_flags

    def _maybe_reset_day(self):
        today = self._today_str()
        if self.state.last_reset_date != today:
            self.state.last_reset_date = today
            self.state.used_today = 0
            self.state.paused = False
            self.state.paused_reason = None
            self.recent_gpt_passes.clear()
            # Note: session_losses stays as-is; call reset_session() when the market session changes.

    @staticmethod
    def _today_str() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
