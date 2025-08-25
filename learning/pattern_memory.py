"""
Pattern Memory System
Tracks setup fingerprints and promotes high-performing patterns to gold status.
"""

import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict, Counter


class PatternStatus(Enum):
    """Pattern promotion status."""
    ACTIVE = "active"
    GOLD = "gold"
    FROZEN = "frozen"


@dataclass
class PatternFingerprint:
    """Setup pattern fingerprint with performance tracking."""
    fingerprint_id: str
    setup_type: str

    # Pattern signature
    signature_features: Dict[str, str]

    # Performance tracking
    total_samples: int
    wins: int
    losses: int
    breakevens: int
    timeouts: int

    # Calculated metrics
    win_rate: float
    avg_pnl_pts: float
    profit_factor: float
    avg_time_to_target: float
    expectancy: float

    # Status and promotion
    status: PatternStatus
    promotion_timestamp: Optional[datetime]
    last_trade_timestamp: datetime

    # Trade history
    trade_ids: List[str]

    # Quality metrics
    consistency_score: float
    recent_performance: float

    # 🔥 New fields (decay/credible intervals/cooldowns)
    ew_win_rate: float = 0.0          # decay-weighted win rate (%, EWMA)
    ew_expectancy: float = 0.0        # decay-weighted expectancy (points)
    wr_lo95: float = 0.0              # Wilson 95% lower bound (%)
    wr_hi95: float = 0.0              # Wilson 95% upper bound (%)
    last_promo_check: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None


class PatternMemory:
    """
    Pattern fingerprint tracking and promotion system.

    Features:
    - Fingerprint generation from setup characteristics
    - Performance tracking per fingerprint
    - Gold promotion (≥30 samples, credible WR lower bound clears threshold)
    - Active/Frozen status management with cooldowns
    - Regime-aware stats and confluence attribution
    - Cost-aware expectancy (commission + slippage)
    - Export/Import with guardrails
    """

    def __init__(self, config: Dict):
        """
        Initialize pattern memory system.

        Args:
            config: System configuration
        """
        self.config = config

        # Promotion thresholds (base)
        self.min_samples_for_gold = 30
        self.min_win_rate_for_gold = 82.0
        self.min_expectancy_for_gold = 0.5

        # Pattern storage
        self.fingerprints: Dict[str, PatternFingerprint] = {}
        self.fingerprints_by_setup: Dict[str, List[str]] = defaultdict(list)

        # Active pattern lists
        self.active_patterns: Set[str] = set()
        self.gold_patterns: Set[str] = set()
        self.frozen_patterns: Set[str] = set()

        # 🌦 Regime aggregation across all fingerprints
        self.by_regime = defaultdict(lambda: {'samples': 0, 'wins': 0, 'wr': 0.0})

        # 🧩 Confluence attribution (wins vs losses)
        self.confluence_wins = Counter()
        self.confluence_losses = Counter()

        # Cost model (points). Override via config if present.
        self._commission_pts = float(self.config.get('costs', {}).get('commission_pts', 0.06))
        self._slip_pts = float(self.config.get('costs', {}).get('slippage_pts', 0.02))

    # ------------------------------
    # Public update path
    # ------------------------------
    def update_pattern_stats(self, trade_record) -> Optional[PatternFingerprint]:
        """
        Update pattern statistics with new trade.

        Args:
            trade_record: TradeRecord from feedback loop

        Returns:
            Updated or created PatternFingerprint
        """
        fingerprint_id = self._generate_fingerprint_id(trade_record)

        # Get or create fingerprint
        if fingerprint_id in self.fingerprints:
            fingerprint = self.fingerprints[fingerprint_id]
        else:
            fingerprint = self._create_new_fingerprint(fingerprint_id, trade_record)
            self.fingerprints[fingerprint_id] = fingerprint
            self.fingerprints_by_setup[trade_record.setup_type].append(fingerprint_id)
            self.active_patterns.add(fingerprint_id)

        # Update stats & attribution
        self._update_fingerprint_stats(fingerprint, trade_record)

        # Status transitions (promotion/freeze/reactivation)
        self._check_status_changes(fingerprint)

        return fingerprint

    # ------------------------------
    # Fingerprint construction
    # ------------------------------
    def _generate_fingerprint_id(self, trade_record) -> str:
        """
        Generate fingerprint ID from trade characteristics.

        Uses key setup characteristics to create unique pattern signature.
        """
        signature_components = [
            trade_record.setup_type,
            trade_record.session,
            trade_record.direction,

            # Binned market conditions
            self._bin_atr(trade_record.atr_5m),
            self._bin_volume_multiple(trade_record.volume_multiple),
            self._bin_ema_alignment(trade_record.ema_alignment),
            self._bin_vwap_distance(trade_record.vwap_distance),

            # Confluence factors (top 3 for consistency)
            '|'.join(sorted(trade_record.confluence_factors[:3])),

            # Market regime
            trade_record.market_regime
        ]

        signature_string = '|'.join(str(component) for component in signature_components)
        hash_object = hashlib.md5(signature_string.encode())
        return f"pattern_{hash_object.hexdigest()[:12]}"

    def _bin_atr(self, atr: float) -> str:
        """Bin ATR into categories."""
        if atr < 0.8:
            return "low"
        elif atr < 1.2:
            return "normal"
        elif atr < 1.6:
            return "elevated"
        else:
            return "high"

    def _bin_volume_multiple(self, volume_multiple: float) -> str:
        """Bin volume multiple into categories."""
        if volume_multiple < 1.5:
            return "low"
        elif volume_multiple < 2.0:
            return "normal"
        elif volume_multiple < 2.5:
            return "high"
        else:
            return "extreme"

    def _bin_ema_alignment(self, alignment: str) -> str:
        """EMA alignment is already categorical."""
        return alignment  # bullish_aligned, bearish_aligned, mixed

    def _bin_vwap_distance(self, distance: float) -> str:
        """Bin VWAP distance into categories."""
        abs_distance = abs(distance)
        if abs_distance < 0.5:
            return "near"
        elif abs_distance < 1.0:
            return "medium"
        else:
            return "far"

    def _create_new_fingerprint(self, fingerprint_id: str, trade_record) -> PatternFingerprint:
        """Create new pattern fingerprint."""
        signature_features = {
            'setup_type': trade_record.setup_type,
            'session': trade_record.session,
            'direction': trade_record.direction,
            'atr_bin': self._bin_atr(trade_record.atr_5m),
            'volume_bin': self._bin_volume_multiple(trade_record.volume_multiple),
            'ema_alignment': self._bin_ema_alignment(trade_record.ema_alignment),
            'vwap_distance_bin': self._bin_vwap_distance(trade_record.vwap_distance),
            'top_confluences': '|'.join(sorted(trade_record.confluence_factors[:3])),
            'market_regime': trade_record.market_regime
        }

        return PatternFingerprint(
            fingerprint_id=fingerprint_id,
            setup_type=trade_record.setup_type,
            signature_features=signature_features,
            total_samples=0,
            wins=0,
            losses=0,
            breakevens=0,
            timeouts=0,
            win_rate=0.0,
            avg_pnl_pts=0.0,
            profit_factor=0.0,
            avg_time_to_target=0.0,
            expectancy=0.0,
            status=PatternStatus.ACTIVE,
            promotion_timestamp=None,
            last_trade_timestamp=trade_record.timestamp,
            trade_ids=[],
            consistency_score=0.0,
            recent_performance=0.0,
            ew_win_rate=0.0,
            ew_expectancy=0.0,
            wr_lo95=0.0,
            wr_hi95=0.0,
            last_promo_check=None,
            cooldown_until=None
        )

    # ------------------------------
    # Stats updates
    # ------------------------------
    def _update_fingerprint_stats(self, fingerprint: PatternFingerprint, trade_record):
        """Update fingerprint statistics with new trade."""
        # Trade linkage
        fingerprint.trade_ids.append(trade_record.trade_id)
        fingerprint.last_trade_timestamp = trade_record.timestamp
        if len(fingerprint.trade_ids) > 100:
            fingerprint.trade_ids = fingerprint.trade_ids[-50:]

        # Counters
        fingerprint.total_samples += 1
        if trade_record.result == 'win':
            fingerprint.wins += 1
        elif trade_record.result == 'loss':
            fingerprint.losses += 1
        elif trade_record.result == 'breakeven':
            fingerprint.breakevens += 1
        elif trade_record.result == 'timeout':
            fingerprint.timeouts += 1

        # Regime-level aggregation (global)
        reg = getattr(trade_record, 'market_regime', 'mixed')
        bucket = self.by_regime[reg]
        bucket['samples'] += 1
        if trade_record.result == 'win':
            bucket['wins'] += 1
        bucket['wr'] = (bucket['wins'] / bucket['samples']) * 100.0

        # Confluence attribution
        for c in (trade_record.confluence_factors[:3] or []):
            if trade_record.result == 'win':
                self.confluence_wins[c] += 1
            elif trade_record.result == 'loss':
                self.confluence_losses[c] += 1

        # Recompute metrics (EWMA, Wilson bounds, expectancy, etc.)
        self._recalculate_metrics(fingerprint, trade_record)

    def _recalculate_metrics(self, fingerprint: PatternFingerprint, latest_trade):
        """Recalculate all performance metrics with decay and credible intervals."""
        if fingerprint.total_samples == 0:
            return

        # Classic WR
        fingerprint.win_rate = (fingerprint.wins / fingerprint.total_samples) * 100.0

        # Cost-aware EV for latest trade; EWMA expectancy
        net_pts = self._cost_aware_ev(latest_trade.pnl_pts)
        if fingerprint.total_samples == 1:
            fingerprint.avg_pnl_pts = net_pts
        else:
            fingerprint.avg_pnl_pts += (net_pts - fingerprint.avg_pnl_pts) / fingerprint.total_samples

        fingerprint.expectancy = fingerprint.avg_pnl_pts

        # Profit factor (approx using avg pnl & counts)
        # If avg loss is not negative (insufficient info), default to inf
        if fingerprint.losses > 0:
            # Simple approximation, still directional
            # (A precise PF needs full returns history.)
            avg_win_pts = max(fingerprint.avg_pnl_pts, 0.000001)
            avg_loss_pts = min(fingerprint.avg_pnl_pts, -0.000001)
            if avg_loss_pts < 0:
                fingerprint.profit_factor = abs(avg_win_pts / avg_loss_pts)
            else:
                fingerprint.profit_factor = float('inf')
        else:
            fingerprint.profit_factor = float('inf')

        # EWMA of wins
        last_win = 1.0 if latest_trade.result == 'win' else 0.0
        fingerprint.ew_win_rate = self._ewma(fingerprint.ew_win_rate, last_win) * 100.0

        # Wilson 95% bounds for credible win rate
        lo, hi = self._wilson_interval(fingerprint.wins, fingerprint.total_samples)
        fingerprint.wr_lo95, fingerprint.wr_hi95 = lo * 100.0, hi * 100.0

        # Consistency / recency proxies
        if fingerprint.total_samples >= 10:
            fingerprint.consistency_score = min(100.0, fingerprint.win_rate * 1.2)
        else:
            fingerprint.consistency_score = 50.0
        fingerprint.recent_performance = max(fingerprint.recent_performance, fingerprint.ew_win_rate)

    # ------------------------------
    # Math helpers
    # ------------------------------
    def _ewma(self, old: float, new: float, alpha: float = 0.12) -> float:
        """Exponential moving average for decay-weighted metrics."""
        return new if old == 0 else (alpha * new + (1 - alpha) * old)

    def _wilson_interval(self, wins: int, total: int, z: float = 1.96) -> Tuple[float, float]:
        """Wilson score interval (returns [0..1])."""
        if total <= 0:
            return (0.0, 0.0)
        p = wins / total
        denom = 1 + (z * z) / total
        center = (p + (z * z) / (2 * total)) / denom
        margin = (z * ((p * (1 - p) / total + (z * z) / (4 * total * total)) ** 0.5)) / denom
        return (max(0.0, center - margin), min(1.0, center + margin))

    def _cost_aware_ev(self, pnl_points: float) -> float:
        """Apply commission & slippage to PnL (in points) and return net."""
        return pnl_points - self._commission_pts - self._slip_pts

    # ------------------------------
    # Status transitions
    # ------------------------------
    def _check_status_changes(self, fingerprint: PatternFingerprint):
        """Promotion/demotion/reactivation logic with cooldowns and credible WR."""
        now = datetime.now(timezone.utc)
        if fingerprint.cooldown_until and now < fingerprint.cooldown_until:
            return

        min_samples = self.min_samples_for_gold
        wr_bar = self.min_win_rate_for_gold
        exp_bar = self.min_expectancy_for_gold

        credible_ok = (fingerprint.wr_lo95 >= wr_bar)
        recency_ok = (
            fingerprint.last_trade_timestamp is not None and
            (now - fingerprint.last_trade_timestamp).days <= 7
        )

        # Promote to GOLD when strong & recent & credible
        if (fingerprint.status == PatternStatus.ACTIVE and
            fingerprint.total_samples >= min_samples and
            credible_ok and recency_ok and
            fingerprint.ew_expectancy >= exp_bar):
            self._promote_to_gold(fingerprint)
            fingerprint.last_promo_check = now
            return

        # Freeze if recent decay and negative expectancy
        if (fingerprint.total_samples >= 20 and
            fingerprint.recent_performance < 60.0 and
            fingerprint.ew_expectancy < 0.0):
            self._freeze_pattern(fingerprint)
            fingerprint.cooldown_until = now + timedelta(days=3)
            return

        # Reactivate frozen if improving
        if (fingerprint.status == PatternStatus.FROZEN and
            fingerprint.total_samples >= 10 and
            fingerprint.recent_performance > 70.0 and
            fingerprint.ew_expectancy >= 0.0):
            self._reactivate_pattern(fingerprint)
            fingerprint.cooldown_until = None

    def _promote_to_gold(self, fingerprint: PatternFingerprint):
        """Promote pattern to gold status."""
        fingerprint.status = PatternStatus.GOLD
        fingerprint.promotion_timestamp = datetime.now(timezone.utc)
        self.active_patterns.discard(fingerprint.fingerprint_id)
        self.gold_patterns.add(fingerprint.fingerprint_id)

    def _freeze_pattern(self, fingerprint: PatternFingerprint):
        """Freeze underperforming pattern."""
        fingerprint.status = PatternStatus.FROZEN
        self.active_patterns.discard(fingerprint.fingerprint_id)
        self.gold_patterns.discard(fingerprint.fingerprint_id)
        self.frozen_patterns.add(fingerprint.fingerprint_id)

    def _reactivate_pattern(self, fingerprint: PatternFingerprint):
        """Reactivate frozen pattern."""
        fingerprint.status = PatternStatus.ACTIVE
        self.frozen_patterns.discard(fingerprint.fingerprint_id)
        self.active_patterns.add(fingerprint.fingerprint_id)

    # ------------------------------
    # Summaries & details
    # ------------------------------
    def get_pattern_summary(self) -> List[Dict]:
        """
        Get summary of all patterns for UI.

        Returns:
            List of pattern summaries
        """
        summaries = []

        for fingerprint in self.fingerprints.values():
            summary = {
                'setup': fingerprint.setup_type,
                'fingerprint_id': fingerprint.fingerprint_id,
                'status': fingerprint.status.value,
                'samples': fingerprint.total_samples,
                'win_rate': round(fingerprint.win_rate, 1),
                'wr_lo95': round(fingerprint.wr_lo95, 1),
                'expectancy': round(fingerprint.expectancy, 3),
                'ew_expectancy': round(fingerprint.ew_expectancy, 3),
                'last_trade': fingerprint.last_trade_timestamp.isoformat() if fingerprint.last_trade_timestamp else None,
                'signature_summary': self._get_signature_summary(fingerprint.signature_features),
                'top_confluences': [c for c, _ in self.confluence_wins.most_common(3)],
                'regime_wr': {k: round(v['wr'], 1) for k, v in self.by_regime.items()}
            }
            summaries.append(summary)

        # Sort by status (gold first) then by win rate
        summaries.sort(key=lambda x: (
            0 if x['status'] == 'gold' else 1 if x['status'] == 'active' else 2,
            -x['win_rate']
        ))

        return summaries

    def _get_signature_summary(self, signature_features: Dict[str, str]) -> str:
        """Generate human-readable signature summary."""
        key_features = [
            signature_features.get('direction', ''),
            signature_features.get('session', ''),
            signature_features.get('atr_bin', ''),
            signature_features.get('volume_bin', '')
        ]
        return ' | '.join(filter(None, key_features))

    def get_pattern_details(self, fingerprint_id: str) -> Optional[Dict]:
        """Get detailed information about specific pattern."""
        if fingerprint_id not in self.fingerprints:
            return None

        f = self.fingerprints[fingerprint_id]
        return {
            'fingerprint_id': f.fingerprint_id,
            'setup_type': f.setup_type,
            'status': f.status.value,
            'signature_features': f.signature_features,
            'performance': {
                'total_samples': f.total_samples,
                'wins': f.wins,
                'losses': f.losses,
                'breakevens': f.breakevens,
                'timeouts': f.timeouts,
                'win_rate': f.win_rate,
                'wr_lo95': f.wr_lo95,
                'wr_hi95': f.wr_hi95,
                'avg_pnl_pts': f.avg_pnl_pts,
                'profit_factor': f.profit_factor,
                'expectancy': f.expectancy,
                'ew_win_rate': f.ew_win_rate,
                'ew_expectancy': f.ew_expectancy,
                'consistency_score': f.consistency_score,
                'recent_performance': f.recent_performance
            },
            'timestamps': {
                'promotion_timestamp': f.promotion_timestamp.isoformat() if f.promotion_timestamp else None,
                'last_trade_timestamp': f.last_trade_timestamp.isoformat()
            },
            'trade_history': f.trade_ids[-10:],  # Last 10 trades
            'promotion_status': self._get_promotion_status(f),
            'cooldown_until': f.cooldown_until.isoformat() if f.cooldown_until else None
        }

    def _get_promotion_status(self, f: PatternFingerprint) -> Dict:
        """Get promotion status and requirements."""
        if f.status == PatternStatus.GOLD:
            return {
                'status': 'promoted',
                'promoted_at': f.promotion_timestamp.isoformat() if f.promotion_timestamp else None
            }

        samples_needed = max(0, self.min_samples_for_gold - f.total_samples)
        win_rate_gap = max(0.0, self.min_win_rate_for_gold - f.wr_lo95)  # use credible WR
        expectancy_gap = max(0.0, self.min_expectancy_for_gold - f.ew_expectancy)

        return {
            'status': 'eligible' if samples_needed == 0 and win_rate_gap == 0 and expectancy_gap == 0 else 'developing',
            'requirements': {
                'samples_needed': int(samples_needed),
                'win_rate_gap': round(win_rate_gap, 2),
                'expectancy_gap': round(expectancy_gap, 3),
                'current_wr_lo95': round(f.wr_lo95, 2),
                'current_ew_expectancy': round(f.ew_expectancy, 3)
            }
        }

    def get_gold_patterns(self) -> List[Dict]:
        """Get list of gold status patterns."""
        gold_patterns = []

        for fingerprint_id in self.gold_patterns:
            if fingerprint_id in self.fingerprints:
                f = self.fingerprints[fingerprint_id]
                gold_patterns.append({
                    'fingerprint_id': fingerprint_id,
                    'setup_type': f.setup_type,
                    'samples': f.total_samples,
                    'win_rate': round(f.win_rate, 1),
                    'wr_lo95': round(f.wr_lo95, 1),
                    'expectancy': round(f.expectancy, 3),
                    'ew_expectancy': round(f.ew_expectancy, 3),
                    'promotion_date': f.promotion_timestamp.isoformat() if f.promotion_timestamp else None,
                    'signature_summary': self._get_signature_summary(f.signature_features)
                })

        return sorted(gold_patterns, key=lambda x: (-(x['wr_lo95']), -x['expectancy']))

    def get_setup_performance_breakdown(self) -> Dict:
        """Get performance breakdown by setup type."""
        setup_stats = defaultdict(lambda: {
            'total_patterns': 0,
            'gold_patterns': 0,
            'active_patterns': 0,
            'frozen_patterns': 0,
            'total_trades': 0,
            'avg_win_rate': 0.0,
            'best_pattern_id': None,
            'best_win_rate': 0.0
        })

        for f in self.fingerprints.values():
            setup = f.setup_type
            stats = setup_stats[setup]

            stats['total_patterns'] += 1
            stats['total_trades'] += f.total_samples

            if f.status == PatternStatus.GOLD:
                stats['gold_patterns'] += 1
            elif f.status == PatternStatus.ACTIVE:
                stats['active_patterns'] += 1
            elif f.status == PatternStatus.FROZEN:
                stats['frozen_patterns'] += 1

            # Track best pattern by WR lower bound (credible)
            if f.wr_lo95 > stats['best_win_rate']:
                stats['best_win_rate'] = f.wr_lo95
                stats['best_pattern_id'] = f.fingerprint_id

        # Weighted average WR (by samples)
        for setup, stats in setup_stats.items():
            fps = [f for f in self.fingerprints.values() if f.setup_type == setup]
            if fps:
                total_weighted_wr = sum(f.win_rate * f.total_samples for f in fps)
                total_samples = sum(f.total_samples for f in fps)
                stats['avg_win_rate'] = total_weighted_wr / total_samples if total_samples > 0 else 0

        return dict(setup_stats)

    # ------------------------------
    # Cleanup & removal
    # ------------------------------
    def cleanup_old_patterns(self, days_old: int = 90, min_samples: int = 5) -> int:
        """
        Clean up old patterns with insufficient data.

        Args:
            days_old: Remove patterns older than this many days
            min_samples: Minimum samples required to keep pattern

        Returns:
            Number of patterns removed
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
        patterns_to_remove = []

        for fingerprint_id, f in self.fingerprints.items():
            if f.status == PatternStatus.GOLD:
                continue
            if (f.last_trade_timestamp < cutoff_date and f.total_samples < min_samples):
                patterns_to_remove.append(fingerprint_id)

        removed_count = 0
        for fingerprint_id in patterns_to_remove:
            if self._remove_pattern(fingerprint_id):
                removed_count += 1

        return removed_count

    def _remove_pattern(self, fingerprint_id: str) -> bool:
        """Remove a pattern from all tracking."""
        if fingerprint_id not in self.fingerprints:
            return False

        f = self.fingerprints[fingerprint_id]

        if f.setup_type in self.fingerprints_by_setup:
            self.fingerprints_by_setup[f.setup_type].remove(fingerprint_id)

        self.active_patterns.discard(fingerprint_id)
        self.gold_patterns.discard(fingerprint_id)
        self.frozen_patterns.discard(fingerprint_id)

        del self.fingerprints[fingerprint_id]
        return True

    # ------------------------------
    # Persistence & guardrails
    # ------------------------------
    def export_patterns(self) -> Dict:
        """Export all pattern data for analysis."""
        return {
            'fingerprints': {
                fid: {
                    'fingerprint_id': f.fingerprint_id,
                    'setup_type': f.setup_type,
                    'signature_features': f.signature_features,
                    'performance': {
                        'total_samples': f.total_samples,
                        'wins': f.wins,
                        'losses': f.losses,
                        'breakevens': f.breakevens,
                        'timeouts': f.timeouts,
                        'win_rate': f.win_rate,
                        'wr_lo95': f.wr_lo95,
                        'wr_hi95': f.wr_hi95,
                        'avg_pnl_pts': f.avg_pnl_pts,
                        'profit_factor': f.profit_factor,
                        'expectancy': f.expectancy,
                        'ew_win_rate': f.ew_win_rate,
                        'ew_expectancy': f.ew_expectancy,
                        'consistency_score': f.consistency_score
                    },
                    'status': f.status.value,
                    'timestamps': {
                        'promotion': f.promotion_timestamp.isoformat() if f.promotion_timestamp else None,
                        'last_trade': f.last_trade_timestamp.isoformat()
                    },
                    'trade_ids': f.trade_ids,
                    'cooldown_until': f.cooldown_until.isoformat() if f.cooldown_until else None
                }
                for fid, f in self.fingerprints.items()
            },
            'status_counts': {
                'active': len(self.active_patterns),
                'gold': len(self.gold_patterns),
                'frozen': len(self.frozen_patterns)
            },
            'promotion_thresholds': {
                'min_samples': self.min_samples_for_gold,
                'min_win_rate': self.min_win_rate_for_gold,
                'min_expectancy': self.min_expectancy_for_gold
            },
            'regime_wr': {k: v for k, v in self.by_regime.items()},
            'top_confluences': {
                'wins': self.confluence_wins.most_common(10),
                'losses': self.confluence_losses.most_common(10)
            },
            'export_timestamp': datetime.now(timezone.utc).isoformat()
        }

    def import_patterns(self, blob: Dict, max_patterns: int = 2000) -> int:
        """
        Import patterns with guardrails (staleness & size caps).

        Returns:
            Number of patterns imported.
        """
        count = 0
        fps = blob.get('fingerprints', {})
        for fid, data in fps.items():
            if len(self.fingerprints) >= max_patterns:
                break
            ts = data.get('timestamps', {})
            last_ts_raw = ts.get('last_trade')
            if not last_ts_raw:
                continue
            last_ts = datetime.fromisoformat(last_ts_raw)
            # Skip stale > 180 days
            if (datetime.now(timezone.utc) - last_ts).days > 180:
                continue

            perf = data.get('performance', {})
            status_val = data.get('status', 'active')

            pf = PatternFingerprint(
                fingerprint_id=fid,
                setup_type=data['setup_type'],
                signature_features=data.get('signature_features', {}),
                total_samples=int(perf.get('total_samples', 0)),
                wins=int(perf.get('wins', 0)),
                losses=int(perf.get('losses', 0)),
                breakevens=int(perf.get('breakevens', 0)),
                timeouts=int(perf.get('timeouts', 0)),
                win_rate=float(perf.get('win_rate', 0.0)),
                avg_pnl_pts=float(perf.get('avg_pnl_pts', 0.0)),
                profit_factor=float(perf.get('profit_factor', 0.0)),
                avg_time_to_target=0.0,  # not persisted here
                expectancy=float(perf.get('expectancy', 0.0)),
                status=PatternStatus(status_val),
                promotion_timestamp=None if not ts.get('promotion') else datetime.fromisoformat(ts['promotion']),
                last_trade_timestamp=last_ts,
                trade_ids=(data.get('trade_ids', []) or [])[-50:],  # limit history
                consistency_score=float(perf.get('consistency_score', 0.0)),
                recent_performance=0.0,
                ew_win_rate=float(perf.get('ew_win_rate', 0.0)),
                ew_expectancy=float(perf.get('ew_expectancy', 0.0)),
                wr_lo95=float(perf.get('wr_lo95', 0.0)),
                wr_hi95=float(perf.get('wr_hi95', 0.0)),
                last_promo_check=None,
                cooldown_until=None if not data.get('cooldown_until') else datetime.fromisoformat(data['cooldown_until'])
            )

            self.fingerprints[fid] = pf
            self.fingerprints_by_setup[pf.setup_type].append(fid)
            if pf.status == PatternStatus.GOLD:
                self.gold_patterns.add(fid)
            elif pf.status == PatternStatus.ACTIVE:
                self.active_patterns.add(fid)
            else:
                self.frozen_patterns.add(fid)
            count += 1

        return count

    # ------------------------------
    # Confidence hooks for other modules
    # ------------------------------
    def get_confidence_adjustment(self, fingerprint_id: str) -> float:
        """
        Modest confidence adjustments based on pattern status/credibility.
        GOLD: +1 to +3 (if very credible), FROZEN: -5, otherwise 0.
        """
        f = self.fingerprints.get(fingerprint_id)
        if not f:
            return 0.0
        if f.status == PatternStatus.GOLD:
            return 3.0 if f.wr_lo95 >= 85.0 else 1.0
        if f.status == PatternStatus.FROZEN:
            return -5.0
        return 0.0
