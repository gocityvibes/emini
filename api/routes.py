"""
API Routes for MES Scalper Backend
RESTful endpoints for frontend monitoring and control.
"""

from flask import jsonify, request
from datetime import datetime, timezone
import pytz

def _get(app_state, path, default=None):
    """Safe nested getter: _get(state, 'config.meta.timezone', 'America/Chicago')"""
    cur = app_state
    for part in path.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur

def _as_ct(dt, tzname):
    if not isinstance(dt, datetime):
        return None
    try:
        tz = pytz.timezone(tzname or 'America/Chicago')
    except Exception:
        tz = pytz.timezone('America/Chicago')
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)

def _iso(dt):
    return dt.isoformat() if isinstance(dt, datetime) else None

def register_routes(app, app_state):
    """Register all API routes with the Flask app."""

    @app.route('/health', methods=['GET'])
    def health():
        utc_now = datetime.now(timezone.utc)
        tzname = _get(app_state, 'config.meta.timezone', 'America/Chicago')
        ct_now = _as_ct(utc_now, tzname)
        return jsonify({
            'status': 'ok',
            'server_time_utc': _iso(utc_now),
            'server_time_ct': ct_now.strftime('%Y-%m-%d %H:%M:%S') if ct_now else None
        })

    @app.route('/metrics/summary', methods=['GET'])
    def metrics_summary():
        tzname = _get(app_state, 'config.meta.timezone', 'America/Chicago')
        tz = pytz.timezone(tzname)
        today_ct = datetime.now(timezone.utc).astimezone(tz).date()

        trades = app_state.get('trades', []) or []
        # Normalize and filter today’s trades (by CT date)
        def _trade_date_ct(t):
            ts = t.get('timestamp')
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except Exception:
                    return None
            if isinstance(ts, datetime):
                return _as_ct(ts, tzname).date()
            return None

        todays = [t for t in trades if _trade_date_ct(t) == today_ct]

        # Determine win/loss from explicit 'result' or pnl_pts > 0
        def _is_win(t):
            if 'result' in t:
                return str(t['result']).lower() in ('win', 'true', '1')
            return float(t.get('pnl_pts', 0)) > 0

        trailing = trades[-20:] if len(trades) >= 20 else trades
        wins = sum(1 for t in trailing if _is_win(t))
        wr_20 = (wins / len(trailing) * 100.0) if trailing else 0.0

        net_points_today = sum(float(t.get('pnl_pts', 0.0)) for t in todays)

        tt = [float(t.get('time_to_target_sec', t.get('time_to_target', 0))) 
              for t in todays if _is_win(t)]
        avg_ttt = (sum(tt) / len(tt)) if tt else 0.0

        calls_used = int(app_state.get('gpt_calls_used', 0))
        calls_cap = int(_get(app_state, 'config.gpt.daily_call_cap', 0))

        return jsonify({
            'running': bool(app_state.get('running', False)),
            'trades_today': len(todays),
            'win_rate_trailing20': round(wr_20, 2),
            'net_points_today': round(net_points_today, 4),
            'avg_time_to_target_sec': round(avg_ttt, 2),
            'gpt_calls_used': calls_used,
            'gpt_calls_cap': calls_cap
        })

    @app.route('/metrics/live', methods=['GET'])
    def metrics_live():
        # Expect latest candidate in app_state['latest_candidate']
        cand = app_state.get('latest_candidate')
        if not isinstance(cand, dict):
            return jsonify({
                'setup_type': None,
                'direction': None,
                'prefilter_score': None,
                'volume_multiple': None,
                'atr_5m': None,
                'session_label': None,
                'timestamp_ct': None
            })
        tzname = _get(app_state, 'config.meta.timezone', 'America/Chicago')
        ts = cand.get('timestamp')
        ts_ct = _as_ct(ts, tzname) if isinstance(ts, datetime) else None
        out = {
            'setup_type': cand.get('setup_type'),
            'direction': cand.get('direction'),
            'prefilter_score': cand.get('prefilter_score'),
            'volume_multiple': cand.get('volume_multiple'),
            'atr_5m': cand.get('atr_5m'),
            'session_label': cand.get('session_label'),
            'timestamp_ct': ts_ct.strftime('%Y-%m-%d %H:%M:%S') if ts_ct else cand.get('timestamp_ct')
        }
        return jsonify(out)

    @app.route('/metrics/budget', methods=['GET'])
    def metrics_budget():
        calls_used = int(app_state.get('gpt_calls_used', 0))
        calls_cap = int(_get(app_state, 'config.gpt.daily_call_cap', 0))
        paused = bool(app_state.get('budget_paused', False))
        paused_reason = app_state.get('budget_paused_reason')
        return jsonify({
            'calls_used': calls_used,
            'calls_cap': calls_cap,
            'paused': paused,
            'paused_reason': paused_reason
        })

    @app.route('/control/start', methods=['POST'])
    def control_start():
        app_state['running'] = True
        return jsonify({'running': True})

    @app.route('/control/stop', methods=['POST'])
    def control_stop():
        app_state['running'] = False
        return jsonify({'running': False})

    @app.route('/metrics/trades', methods=['GET'])
    def metrics_trades():
        date_filter = request.args.get('date')  # YYYY-MM-DD
        tzname = _get(app_state, 'config.meta.timezone', 'America/Chicago')
        tz = pytz.timezone(tzname)

        trades = app_state.get('trades', []) or []
        result = []

        def _normalize_timestamp(ts):
            if isinstance(ts, datetime):
                return _iso(_as_ct(ts, tzname))
            if isinstance(ts, str):
                return ts
            return None

        for t in trades:
            if date_filter:
                try:
                    y, m, d = map(int, date_filter.split('-'))
                    target = datetime(y, m, d, tzinfo=tz).date()
                except Exception:
                    target = None
                ts = t.get('timestamp')
                if isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts)
                    except Exception:
                        ts = None
                if isinstance(ts, datetime):
                    if _as_ct(ts, tzname).date() != target:
                        continue

            result.append({
                'result': t.get('result'),
                'prefilter_score': t.get('prefilter_score'),
                'confidence': t.get('confidence'),
                'setup': t.get('setup'),
                'session': t.get('session'),
                'entry_price': t.get('entry_price'),
                'exit_price': t.get('exit_price'),
                'pnl_pts': t.get('pnl_pts'),
                'time_to_target_sec': t.get('time_to_target_sec', t.get('time_to_target')),
                'mae': t.get('mae'),
                'mfe': t.get('mfe'),
                'volume_multiple': t.get('volume_multiple'),
                'atr_5m': t.get('atr_5m'),
                'wickiness': t.get('wickiness'),
                'timestamp_ct': _normalize_timestamp(t.get('timestamp'))
            })

        return jsonify(result)

    @app.route('/metrics/fingerprints', methods=['GET'])
    def metrics_fingerprints():
        # Expect list of fingerprint dicts in app_state['fingerprints']
        fps = app_state.get('fingerprints', []) or []
        # Ensure only JSON-serializable fields are returned
        out = []
        for f in fps:
            if isinstance(f, dict):
                out.append({
                    'setup': f.get('setup'),
                    'fingerprint_id': f.get('fingerprint_id'),
                    'status': f.get('status'),
                    'samples': f.get('samples'),
                    'win_rate': f.get('win_rate'),
                    'expectancy': f.get('expectancy')
                })
        return jsonify(out)
