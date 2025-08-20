"""
Hard Negatives System (Upgraded)
Learns from high-confidence losses and vetoes risky lookalikes before GPT is called.
- Fuzzy feature matching (bin distance / mismatches)
- Credibility via Wilson lower bound on loss rate
- Regime/session aware with penalties
- Cooldowns, expiry, import/export
- Tracks true-saves vs false-vetoes with post-outcome feedback
"""

import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

# ----------------------------
# Data structures
# ----------------------------

@dataclass
class NoTradeTemplate:
    """Template for vetoing similar losing trades."""
    template_id: str
    setup_type: str
    session: str
    regime: str  # market_regime at time of loss

    # Binned features for matching
    atr_bin: str
    vwap_distance_bin: str
    pullback_depth_bin: str
    wick_ratio_bin: str
    volume_multiple_bin: str

    # Source loss metadata
    created_from_trade_id: str
    creation_timestamp: datetime
    loss_pnl: float
    original_confidence: int

    # Aggregated severity / stats
    severity_sum: float = 0.0          # sum of |loss_pnl| * confidence factor
    samples: int = 0                   # number of high-conf losses merged into this template

    # Online performance tracking
    total_checks: int = 0              # times a candidate matched this template
    vetoes: int = 0                    # times this template vetoed
    passed: int = 0                    # matches that were allowed (when threshold not met or veto disabled)
    true_saves: int = 0                # vetoed -> likely loss confirmed later
    false_vetoes: int = 0              # vetoed -> would have won (penalize)
    post_pass_losses: int = 0          # allowed -> resulted in loss (we should tighten)
    post_pass_wins: int = 0            # allowed -> win (we should loosen)

    # Timestamps
    last_match_timestamp: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None

    # Cached credibility metrics
    loss_rate_lo95: float = 0.0        # Wilson lower bound on (losses / (losses+wins)) from post outcomes
    save_rate_lo95: float = 0.0        # Lower bound on (true_saves / vetoes)

    # Config snapshot at creation (optional, helps debugging)
    max_mismatches: int = 1
    regime_penalty: float = 0.5
    session_penalty: float = 0.25


# ----------------------------
# Utility
# ----------------------------

def _wilson_interval(success: int, total: int, z: float = 1.96) -> Tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    p = success / total
    denom = 1 + (z * z) / total
    center = (p + (z * z) / (2 * total)) / denom
    margin = (z * ((p * (1 - p) / total + (z * z) / (4 * total * total)) ** 0.5)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------
# Main class
# ----------------------------

class HardNegatives:
    """
    Hard negatives learning system for preventing repeated losses.

    Core rule:
      - Any **loss with GPT confidence >= high_confidence_threshold** becomes a template
      - Future candidates are matched fuzzily (allow small bin mismatches)
      - Veto when (match_score high) AND (template credibility high) AND (not in cooldown)

    Config keys (with defaults if missing):
      thresholds:
        high_confidence: 90
        min_veto_score: 1.0
        min_loss_lb: 0.60          # require Wilson lower bound of loss rate ≥ 60%
      matching:
        max_mismatches: 1
        regime_penalty: 0.5
        session_penalty: 0.25
      maintenance:
        expiry_days: 30
        cooldown_days: 3
    """

    def __init__(self, config: Dict):
        self.config = config or {}

        th = self.config.get('thresholds', {}) or {}
        self.high_confidence_threshold = int(th.get('high_confidence', 90))
        self.min_veto_score = float(th.get('min_veto_score', 1.0))
        self.min_loss_lb = float(th.get('min_loss_lb', 0.60))

        mt = self.config.get('matching', {}) or {}
        self.max_mismatches = int(mt.get('max_mismatches', 1))
        self.regime_penalty = float(mt.get('regime_penalty', 0.5))
        self.session_penalty = float(mt.get('session_penalty', 0.25))

        ma = self.config.get('maintenance', {}) or {}
        self.expiry_days = int(ma.get('expiry_days', 30))
        self.cooldown_days = int(ma.get('cooldown_days', 3))

        # Storage
        self.templates: Dict[str, NoTradeTemplate] = {}
        self.templates_by_setup: Dict[str, List[str]] = defaultdict(list)

        # Binning ranges (index order matters for distance)
        self.binning_config = {
            'atr_bins':        [(0, 0.8), (0.8, 1.2), (1.2, 1.6), (1.6, 2.0), (2.0, 999)],
            'vwap_distance':  [(-999, -2), (-2, -0.5), (-0.5, 0.5), (0.5, 2), (2, 999)],
            'pullback_depth': [(-999, -1), (-1, -0.3), (-0.3, 0.3), (0.3, 1), (1, 999)],
            'wick_ratio':     [(0, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 999)],
            'volume_mult':    [(0, 1.5), (1.5, 2.0), (2.0, 2.5), (2.5, 999)]
        }

    # ----------------------------
    # Public API
    # ----------------------------

    def process_loss(self, trade_record) -> Optional[NoTradeTemplate]:
        """
        Process a losing trade and potentially create/merge a hard-negative template.
        trade_record must have:
          - trade_id, setup_type, session, market_regime
          - atr_5m, vwap_distance, wickiness, volume_multiple
          - pnl_pts (negative), gpt_confidence (int)
        """
        if trade_record.result != 'loss' or int(getattr(trade_record, 'gpt_confidence', 0)) < self.high_confidence_threshold:
            return None

        features = self._extract_and_bin_features(
            atr=trade_record.atr_5m,
            vwap_distance=trade_record.vwap_distance,
            wickiness=getattr(trade_record, 'wickiness', 1.0),
            volume_multiple=trade_record.volume_multiple
        )
        # Simplified pullback proxy from vwap distance
        pullback_bin = self._bin_value(abs(trade_record.vwap_distance) * 0.5, self.binning_config['pullback_depth'])
        features['pullback_depth_bin'] = pullback_bin

        template_id = self._generate_template_id(trade_record.setup_type, features)

        # Merge if exists; else create
        if template_id in self.templates:
            t = self.templates[template_id]
        else:
            t = NoTradeTemplate(
                template_id=template_id,
                setup_type=trade_record.setup_type,
                session=trade_record.session,
                regime=getattr(trade_record, 'market_regime', 'mixed'),
                atr_bin=features['atr_bin'],
                vwap_distance_bin=features['vwap_distance_bin'],
                pullback_depth_bin=features['pullback_depth_bin'],
                wick_ratio_bin=features['wick_ratio_bin'],
                volume_multiple_bin=features['volume_multiple_bin'],
                created_from_trade_id=trade_record.trade_id,
                creation_timestamp=_now_utc(),
                loss_pnl=float(trade_record.pnl_pts),
                original_confidence=int(getattr(trade_record, 'gpt_confidence', self.high_confidence_threshold)),
                max_mismatches=self.max_mismatches,
                regime_penalty=self.regime_penalty,
                session_penalty=self.session_penalty
            )
            self.templates[template_id] = t
            self.templates_by_setup[trade_record.setup_type].append(template_id)

        # Update severity aggregate
        severity = abs(float(trade_record.pnl_pts)) * max(1.0, (int(getattr(trade_record, 'gpt_confidence', 90)) - 80) / 10.0)
        t.severity_sum += severity
        t.samples += 1

        return t

    def check_candidate_against_templates(self, candidate_data: Dict) -> Dict:
        """
        Check a candidate against hard negatives and decide whether to veto.
        candidate_data['candidate'] must have:
          setup_type, session_label, market_regime, atr_5m, vwap_distance, wickiness?, volume_multiple
        Returns:
          {
            'veto': bool,
            'score': float,
            'reason': str|None,
            'matched_template': {...} | None,
            'candidate_features': {...},
          }
        """
        c = candidate_data['candidate']
        cand_features = self._extract_and_bin_features(
            atr=c.atr_5m,
            vwap_distance=c.vwap_distance,
            wickiness=getattr(c, 'wickiness', 1.0),
            volume_multiple=c.volume_multiple
        )
        cand_features['pullback_depth_bin'] = self._bin_value(abs(c.vwap_distance) * 0.5, self.binning_config['pullback_depth'])

        setup_ids = self.templates_by_setup.get(c.setup_type, [])
        best = None
        best_score = -1e9

        for tid in setup_ids:
            t = self.templates[tid]
            # Skip if cooled down
            if t.cooldown_until and _now_utc() < t.cooldown_until:
                continue

            score, mismatches = self._match_score(c, cand_features, t)
            # track total checks
            t.total_checks += 1
            t.last_match_timestamp = _now_utc()

            if score > best_score:
                best = t
                best_score = score

        # Decide veto
        if not best:
            return {
                'veto': False,
                'score': 0.0,
                'reason': None,
                'matched_template': None,
                'candidate_features': cand_features
            }

        credible = (best.loss_rate_lo95 >= self.min_loss_lb)
        if best_score >= self.min_veto_score and credible:
            best.vetoes += 1
            # Cooldown the template slightly after hard vetoes to avoid overfitting bursts
            best.cooldown_until = _now_utc() + timedelta(days=self.cooldown_days)
            return {
                'veto': True,
                'score': round(best_score, 3),
                'reason': f"Fuzzy match with credible high-loss template (LB={best.loss_rate_lo95:.2f})",
                'matched_template': self._template_public_view(best),
                'candidate_features': cand_features
            }
        else:
            best.passed += 1
            return {
                'veto': False,
                'score': round(best_score, 3),
                'reason': "Match not strong/credible enough for veto",
                'matched_template': self._template_public_view(best),
                'candidate_features': cand_features
            }

    def record_outcome_feedback(self, template_id: str, outcome: str):
        """
        After a decision, call this to update credibility.
        Use:
          - if vetoed:   outcome in {'true_save','false_veto'}
          - if allowed:  outcome in {'post_pass_loss','post_pass_win'}
        """
        if template_id not in self.templates:
            return
        t = self.templates[template_id]
        if outcome == 'true_save':
            t.true_saves += 1
        elif outcome == 'false_veto':
            t.false_vetoes += 1
        elif outcome == 'post_pass_loss':
            t.post_pass_losses += 1
        elif outcome == 'post_pass_win':
            t.post_pass_wins += 1
        else:
            return

        # Update credibility metrics
        # Loss rate from allowed outcomes (post_pass_loss vs wins)
        total_allowed = t.post_pass_losses + t.post_pass_wins
        if total_allowed > 0:
            loss_lo, _ = _wilson_interval(t.post_pass_losses, total_allowed)
            t.loss_rate_lo95 = loss_lo
        # Save-rate from vetoed decisions
        total_vetoed = t.true_saves + t.false_vetoes
        if total_vetoed > 0:
            save_lo, _ = _wilson_interval(t.true_saves, total_vetoed)
            t.save_rate_lo95 = save_lo

        # Penalize templates that cause too many false vetoes
        if t.false_vetoes >= 3 and (t.true_saves / max(1, t.false_vetoes)) < 1.0:
            # temporary cooldown
            t.cooldown_until = _now_utc() + timedelta(days=self.cooldown_days)

    # ----------------------------
    # Maintenance / admin
    # ----------------------------

    def clear_old_templates(self, days_old: Optional[int] = None) -> int:
        """Remove templates not matched in N days."""
        if days_old is None:
            days_old = self.expiry_days
        cutoff = _now_utc() - timedelta(days=days_old)
        to_remove = []
        for tid, t in self.templates.items():
            last = t.last_match_timestamp or t.creation_timestamp
            if last < cutoff:
                to_remove.append(tid)
        for tid in to_remove:
            self._remove_template(tid)
        return len(to_remove)

    def remove_template(self, template_id: str) -> bool:
        return self._remove_template(template_id)

    def export_templates(self) -> Dict:
        """Export all templates (JSON-serializable dict)."""
        return {
            'templates': {
                tid: {
                    'template_id': t.template_id,
                    'setup_type': t.setup_type,
                    'session': t.session,
                    'regime': t.regime,
                    'features': {
                        'atr_bin': t.atr_bin,
                        'vwap_distance_bin': t.vwap_distance_bin,
                        'pullback_depth_bin': t.pullback_depth_bin,
                        'wick_ratio_bin': t.wick_ratio_bin,
                        'volume_multiple_bin': t.volume_multiple_bin
                    },
                    'source': {
                        'created_from_trade_id': t.created_from_trade_id,
                        'creation_timestamp': t.creation_timestamp.isoformat(),
                        'loss_pnl': t.loss_pnl,
                        'original_confidence': t.original_confidence
                    },
                    'stats': {
                        'severity_sum': t.severity_sum,
                        'samples': t.samples,
                        'total_checks': t.total_checks,
                        'vetoes': t.vetoes,
                        'passed': t.passed,
                        'true_saves': t.true_saves,
                        'false_vetoes': t.false_vetoes,
                        'post_pass_losses': t.post_pass_losses,
                        'post_pass_wins': t.post_pass_wins,
                        'loss_rate_lo95': t.loss_rate_lo95,
                        'save_rate_lo95': t.save_rate_lo95
                    },
                    'timestamps': {
                        'last_match': t.last_match_timestamp.isoformat() if t.last_match_timestamp else None,
                        'cooldown_until': t.cooldown_until.isoformat() if t.cooldown_until else None
                    },
                    'config_snapshot': {
                        'max_mismatches': t.max_mismatches,
                        'regime_penalty': t.regime_penalty,
                        'session_penalty': t.session_penalty
                    }
                }
                for tid, t in self.templates.items()
            },
            'export_timestamp': _now_utc().isoformat()
        }

    def import_templates(self, blob: Dict, max_templates: int = 4000) -> int:
        """Import templates with guardrails (caps)."""
        count = 0
        payload = blob.get('templates', {})
        for tid, data in payload.items():
            if len(self.templates) >= max_templates:
                break
            t = self._template_from_blob(tid, data)
            self.templates[tid] = t
            self.templates_by_setup[t.setup_type].append(tid)
            count += 1
        return count

    def get_template_summary(self) -> Dict:
        """Compact summary for UI tables."""
        total = len(self.templates)
        active = sum(1 for t in self.templates.values() if not t.cooldown_until or _now_utc() >= t.cooldown_until)
        top = sorted(self.templates.values(), key=lambda x: (x.loss_rate_lo95, x.severity_sum), reverse=True)[:5]
        return {
            'total_templates': total,
            'active_templates': active,
            'top_risky_templates': [
                {
                    'template_id': t.template_id,
                    'setup': t.setup_type,
                    'loss_lb': round(t.loss_rate_lo95, 2),
                    'severity': round(t.severity_sum, 2),
                    'checks': t.total_checks,
                    'vetoes': t.vetoes
                } for t in top
            ]
        }

    # ----------------------------
    # Internals
    # ----------------------------

    def _remove_template(self, template_id: str) -> bool:
        if template_id not in self.templates:
            return False
        t = self.templates[template_id]
        if t.setup_type in self.templates_by_setup:
            try:
                self.templates_by_setup[t.setup_type].remove(template_id)
            except ValueError:
                pass
        del self.templates[template_id]
        return True

    def _template_from_blob(self, tid: str, data: Dict) -> NoTradeTemplate:
        f = data.get('features', {})
        s = data.get('source', {})
        st = data.get('stats', {})
        ts = data.get('timestamps', {})
        snap = data.get('config_snapshot', {})

        return NoTradeTemplate(
            template_id=tid,
            setup_type=data.get('setup_type', ''),
            session=data.get('session', ''),
            regime=data.get('regime', 'mixed'),
            atr_bin=f.get('atr_bin', 'bin_0'),
            vwap_distance_bin=f.get('vwap_distance_bin', 'bin_2'),
            pullback_depth_bin=f.get('pullback_depth_bin', 'bin_2'),
            wick_ratio_bin=f.get('wick_ratio_bin', 'bin_1'),
            volume_multiple_bin=f.get('volume_multiple_bin', 'bin_1'),
            created_from_trade_id=s.get('created_from_trade_id', ''),
            creation_timestamp=datetime.fromisoformat(s.get('creation_timestamp')) if s.get('creation_timestamp') else _now_utc(),
            loss_pnl=float(s.get('loss_pnl', -0.5)),
            original_confidence=int(s.get('original_confidence', self.high_confidence_threshold)),
            severity_sum=float(st.get('severity_sum', 0.0)),
            samples=int(st.get('samples', 1)),
            total_checks=int(st.get('total_checks', 0)),
            vetoes=int(st.get('vetoes', 0)),
            passed=int(st.get('passed', 0)),
            true_saves=int(st.get('true_saves', 0)),
            false_vetoes=int(st.get('false_vetoes', 0)),
            post_pass_losses=int(st.get('post_pass_losses', 0)),
            post_pass_wins=int(st.get('post_pass_wins', 0)),
            loss_rate_lo95=float(st.get('loss_rate_lo95', 0.0)),
            save_rate_lo95=float(st.get('save_rate_lo95', 0.0)),
            last_match_timestamp=datetime.fromisoformat(ts['last_match']) if ts.get('last_match') else None,
            cooldown_until=datetime.fromisoformat(ts['cooldown_until']) if ts.get('cooldown_until') else None,
            max_mismatches=int(snap.get('max_mismatches', self.max_mismatches)),
            regime_penalty=float(snap.get('regime_penalty', self.regime_penalty)),
            session_penalty=float(snap.get('session_penalty', self.session_penalty))
        )

    def _extract_and_bin_features(self, atr: float, vwap_distance: float, wickiness: float, volume_multiple:
