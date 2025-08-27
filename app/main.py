
import os
import threading
import time
import json
import yaml
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from flask import Flask, jsonify, request, send_file, abort
from flask_cors import CORS

# --- External deps expected in your repo ---
# Technicals, prefilters, simulator, GPT, rate limiter
from data.yahoo_provider import YahooProvider
from data.technical_analyzer import TechnicalAnalyzer
from simulation.realistic_sim import RealisticSimulator, TradeDirection
from prefilter.session_validator import SessionValidator
from prefilter.confluence_scorer import ConfluenceScorer
from prefilter.premium_filter import PremiumFilter
from prefilter.cost_optimizer import CostOptimizer
from gpt.trainer import GPTTrainer
from gpt.rate_limiter import RateLimiter

# ---------------------- App Setup ----------------------
app = Flask(__name__)
CORS(app)

# Load config.yaml if present
CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.yaml")
config: Dict[str, Any] = {}
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f) or {}
else:
    config = {}

# Components
yahoo = YahooProvider(symbol=(config.get("market", {}) or {}).get("symbol", "MES=F"))
analyzer = TechnicalAnalyzer()
simulator = RealisticSimulator(config=config)

session_validator = SessionValidator(config=config)
confluence_scorer = ConfluenceScorer(config=config)
prefilter = PremiumFilter(config=config, session_validator=session_validator, confluence_scorer=confluence_scorer)

optimizer = CostOptimizer(config=config)

# GPT
openai_key = os.getenv("OPENAI_API_KEY")
trainer = GPTTrainer(config=config, api_key=openai_key)
rate_limiter = RateLimiter(config=config)

# ---------------------- Runtime State ----------------------
app_state: Dict[str, Any] = {
    "running": False,
    "metrics": {
        "trades_today": 0,
        "net_points_today": 0.0,
        "avg_time_to_target_sec": 0,
        "win_rate_trailing20": 0.0
    },
    "trades": []  # last 50 visible trades
}

DEFAULT_SETTINGS: Dict[str, Any] = {
    "symbol": (config.get("market", {}) or {}).get("symbol", "MES=F"),
    "score_cutoff": 90,
    "premium_threshold": 0.80,
    "require_confluence": 2,
    "max_trades_per_day": 5,
    "risk_per_trade_pct": 1.0,
    "stop_loss_pct": 5.0,
    "take_profit_pct": 10.0,
    "trailing": {"enabled": True, "pct": 2.0},
    "session_hours": True,
    "windows": [{"start": "09:30", "end": "11:30"}],
    "no_new_trades_after": "15:00",
    "flat_at_time": "15:45",
    "volume_surge": 1.0,
    "spread_atr": 0.2,
    "interval": (config.get("market", {}) or {}).get("interval", "1m"),
}

runtime_settings: Dict[str, Any] = DEFAULT_SETTINGS.copy()
settings_lock = threading.Lock()

stop_event = threading.Event()
trainer_thread: Optional[threading.Thread] = None

DATA_DIR = os.environ.get("DATA_DIR", "data")
os.makedirs(DATA_DIR, exist_ok=True)
GOLD_CSV = os.path.join(DATA_DIR, "gold.csv")
NEG_CSV = os.path.join(DATA_DIR, "hard_negatives.csv")

# ---------------------- Helpers ----------------------

def parse_time_hhmm(s: str) -> Optional[time.struct_time]:
    try:
        datetime.strptime(s, "%H:%M")
        return True
    except Exception:
        return None

def now_utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def as_iso(ts: Any) -> str:
    if ts is None: 
        return ""
    if isinstance(ts, str): 
        return ts
    if hasattr(ts, "isoformat"): 
        return ts.isoformat()
    return str(ts)

def valid_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and coerce incoming settings JSON."""
    s = runtime_settings.copy()
    for k, v in (payload or {}).items():
        if k == "trailing" and isinstance(v, dict):
            s["trailing"] = {
                "enabled": bool(v.get("enabled", s["trailing"]["enabled"])),
                "pct": float(v.get("pct", s["trailing"]["pct"])),
            }
        elif k in ("windows",):
            ws = []
            for w in (v or []):
                st, en = (w.get("start"), w.get("end"))
                if not st or not en: 
                    continue
                # basic validate HH:MM
                try:
                    datetime.strptime(st, "%H:%M")
                    datetime.strptime(en, "%H:%M")
                    ws.append({"start": st, "end": en})
                except:
                    continue
            s["windows"] = ws
        elif k in ("score_cutoff", "premium_threshold", "volume_surge", "spread_atr", "stop_loss_pct", "take_profit_pct", "risk_per_trade_pct"):
            s[k] = float(v)
        elif k in ("require_confluence", "max_trades_per_day"):
            s[k] = int(v)
        elif k in ("session_hours",):
            s[k] = bool(v)
        elif k in ("no_new_trades_after", "flat_at_time"):
            if isinstance(v, str):
                try:
                    datetime.strptime(v, "%H:%M")
                    s[k] = v
                except:
                    pass
        elif k in ("symbol", "interval"):
            s[k] = str(v)
        else:
            s[k] = v
    return s

def update_metrics_with_trade(trade: Dict[str, Any]):
    """Update app_state metrics using a new trade object."""
    app_state.setdefault("trades", [])
    app_state["trades"].insert(0, trade)
    app_state["trades"] = app_state["trades"][:50]

    # today metrics (UTC day)
    today = datetime.utcnow().date()
    trades_today = [t for t in app_state["trades"] if (t.get("timestamp") or "").split("T")[0] == today.isoformat()]
    app_state["metrics"]["trades_today"] = len(trades_today)
    app_state["metrics"]["net_points_today"] = sum(float(t.get("pnl_pts") or 0.0) for t in trades_today)

    recent = app_state["trades"][:20]
    wins = sum(1 for t in recent if float(t.get("pnl_pts") or 0.0) > 0.0)
    app_state["metrics"]["win_rate_trailing20"] = (wins / len(recent)) if recent else 0.0

def append_memory_csv(trade: Dict[str, Any]):
    """Persist gold / hard negatives based on pnl sign."""
    cols = [
        "timestamp","symbol","direction","entry_price","exit_price","pnl_pts","duration_s",
        "fingerprint_id","gpt_score","confluence","premium_threshold","score_cutoff"
    ]
    line = ",".join([csv_escape(trade.get(c, "")) for c in cols]) + "\n"
    is_win = float(trade.get("pnl_pts") or 0.0) > 0.0
    path = GOLD_CSV if is_win else NEG_CSV
    header_needed = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if header_needed:
            f.write(",".join(cols) + "\n")
        f.write(line)

def csv_escape(v: Any) -> str:
    s = "" if v is None else str(v)
    if any(ch in s for ch in [",", "\"", "\n"]):
        s = "\"" + s.replace("\"", "\"\"") + "\""
    return s

def get_settings_snapshot() -> Dict[str, Any]:
    with settings_lock:
        return json.loads(json.dumps(runtime_settings))

def should_block_starts() -> bool:
    return os.getenv("BLOCK_TRAINER", "0") == "1"

def forced_stop() -> bool:
    return os.getenv("FORCE_STOP", "0") == "1"

# ---------------------- Trainer Loop ----------------------

def run_live_loop():
    app.logger.info("Live loop started")
    interval = get_settings_snapshot().get("interval", "1m")
    try:
        while True:
            if stop_event.is_set() or forced_stop():
                break
            s = get_settings_snapshot()
            # Update provider symbol if changed
            yahoo.symbol = s.get("symbol", yahoo.symbol)

            # Get latest snapshot (safe ranges handled inside provider)
            snap = yahoo.get_multi_timeframe_snapshot(interval=interval)
            df = snap.get("1m")
            if df is None or df.empty:
                time.sleep(2)
                continue

            # Technicals
            try:
                df = analyzer.add_all_indicators(df, "1m")
            except Exception as e:
                app.logger.warning(f"Analyzer failed: {e}")
                time.sleep(1)
                continue

            if stop_event.is_set() or forced_stop():
                break

            # Prefilter
            try:
                candidate = prefilter.evaluate(df)
            except Exception as e:
                app.logger.warning(f"Prefilter error: {e}")
                time.sleep(1)
                continue
            if not candidate:
                time.sleep(1)
                continue

            # Convert candidate to dict safely
            if hasattr(candidate, "to_dict"):
                cdict = candidate.to_dict()
            elif isinstance(candidate, dict):
                cdict = candidate
            else:
                # Minimal extraction
                cdict = {
                    "timestamp": as_iso(getattr(candidate, "timestamp", None)),
                    "entry_price": float(getattr(candidate, "entry_price", 0.0)),
                }

            if stop_event.is_set() or forced_stop():
                break

            # Optimizer gate
            try:
                if not optimizer.should_send_to_gpt(candidate):
                    time.sleep(1)
                    continue
            except Exception as e:
                app.logger.warning(f"Optimizer error: {e}")
                time.sleep(1)
                continue

            # GPT decision
            try:
                decision = rate_limiter.submit_request({"candidate": cdict}, trainer.score_candidate)
            except Exception as e:
                app.logger.warning(f"RateLimiter/Trainer error: {e}")
                time.sleep(1)
                continue

            if not decision or "direction" not in decision:
                time.sleep(1)
                continue

            direction = decision["direction"].lower()
            dir_enum = TradeDirection.LONG if direction == "long" else TradeDirection.SHORT

            # Simulate
            try:
                bar_data = df.tail(200)
                trade = simulator.simulate_trade(
                    entry_price=cdict.get("entry_price"),
                    entry_time=cdict.get("timestamp"),
                    direction=dir_enum,
                    bar_data=bar_data
                )
            except Exception as e:
                app.logger.warning(f"Simulator error: {e}")
                time.sleep(1)
                continue

            # enrich trade
            trade["timestamp"] = trade.get("timestamp") or now_utc_iso()
            trade["symbol"] = s.get("symbol")
            trade["fingerprint_id"] = cdict.get("fingerprint_id", "")
            trade["gpt_score"] = decision.get("score", None)
            trade["confluence"] = s.get("require_confluence")
            trade["premium_threshold"] = s.get("premium_threshold")
            trade["score_cutoff"] = s.get("score_cutoff")

            update_metrics_with_trade(trade)
            append_memory_csv(trade)

            time.sleep(2)
    finally:
        app.logger.info("Live loop stopped")

def run_training_loop(start_iso: str, end_iso: str):
    app.logger.info(f"Training loop started {start_iso} -> {end_iso}")
    s = get_settings_snapshot()
    symbol = s.get("symbol", "MES=F")
    interval = s.get("interval", "1m")

    # Fetch historical intraday with chunking
    hist = yahoo.get_intraday_history(symbol=symbol, interval=interval, start_iso=start_iso, end_iso=end_iso)
    if hist is None or hist.empty:
        app.logger.warning("No history returned for training")
        return

    # Walk through bars without sleep
    window_size = 500
    for idx in range(window_size, len(hist)):
        if stop_event.is_set() or forced_stop():
            break

        window = hist.iloc[idx - window_size: idx].copy()

        # Technicals
        try:
            window = analyzer.add_all_indicators(window, "1m")
        except Exception as e:
            app.logger.warning(f"Analyzer failed: {e}")
            continue

        # Prefilter
        try:
            candidate = prefilter.evaluate(window)
        except Exception as e:
            app.logger.warning(f"Prefilter error: {e}")
            continue
        if not candidate:
            continue

        # Candidate dict
        if hasattr(candidate, "to_dict"):
            cdict = candidate.to_dict()
        elif isinstance(candidate, dict):
            cdict = candidate
        else:
            # build from last bar
            last = window.iloc[-1]
            cdict = {
                "timestamp": as_iso(last.get("timestamp")),
                "entry_price": float(last.get("Close", 0.0)),
            }

        # Optimizer gate
        try:
            if not optimizer.should_send_to_gpt(candidate):
                continue
        except Exception as e:
            app.logger.warning(f"Optimizer error: {e}")
            continue

        # GPT scoring
        try:
            decision = rate_limiter.submit_request({"candidate": cdict}, trainer.score_candidate)
        except Exception as e:
            app.logger.warning(f"RateLimiter/Trainer error: {e}")
            continue

        if not decision or "direction" not in decision:
            continue

        direction = decision["direction"].lower()
        dir_enum = TradeDirection.LONG if direction == "long" else TradeDirection.SHORT

        # Simulate using a recent subset
        try:
            bar_data = window.tail(200)
            trade = simulator.simulate_trade(
                entry_price=cdict.get("entry_price"),
                entry_time=cdict.get("timestamp"),
                direction=dir_enum,
                bar_data=bar_data
            )
        except Exception as e:
            app.logger.warning(f"Simulator error: {e}")
            continue

        trade["timestamp"] = trade.get("timestamp") or as_iso(window.iloc[-1].get("timestamp"))
        trade["symbol"] = symbol
        trade["fingerprint_id"] = cdict.get("fingerprint_id", "")
        trade["gpt_score"] = decision.get("score", None)
        trade["confluence"] = s.get("require_confluence")
        trade["premium_threshold"] = s.get("premium_threshold")
        trade["score_cutoff"] = s.get("score_cutoff")

        update_metrics_with_trade(trade)
        append_memory_csv(trade)

    app.logger.info("Training loop stopped")

def trainer_loop(mode: str, replay: Optional[Dict[str, str]]):
    try:
        if mode == "training" and replay:
            run_training_loop(replay.get("start"), replay.get("end"))
        else:
            run_live_loop()
    except Exception as e:
        app.logger.exception(f"Trainer loop exception: {e}")
    finally:
        app_state["running"] = False

# ---------------------- Routes ----------------------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})

@app.route("/status", methods=["GET"])
def status():
    alive = bool(trainer_thread and trainer_thread.is_alive())
    return jsonify({
        "running": app_state["running"],
        "thread_alive": alive,
        "force_stop": os.getenv("FORCE_STOP", "0"),
        "block_trainer": os.getenv("BLOCK_TRAINER", "0")
    })

@app.route("/metrics/summary", methods=["GET"])
def metrics_summary():
    out = dict(app_state["metrics"])
    out["running"] = app_state["running"]
    return jsonify(out)

@app.route("/metrics/trades", methods=["GET"])
def metrics_trades():
    return jsonify(app_state.get("trades", []))

@app.route("/settings", methods=["GET", "POST"])
def settings_handler():
    global runtime_settings
    if request.method == "GET":
        return jsonify(get_settings_snapshot())
    # POST update
    incoming = request.get_json(silent=True) or {}
    new_settings = valid_settings(incoming)
    with settings_lock:
        runtime_settings.update(new_settings)
    return jsonify({"ok": True, "settings": get_settings_snapshot()})

@app.route("/control/start", methods=["POST"])
def control_start():
    global trainer_thread
    if should_block_starts():
        return jsonify({"ok": False, "running": False, "error": "Trainer blocked by BLOCK_TRAINER=1"}), 423

    payload = request.get_json(silent=True) or {}
    mode = payload.get("mode", "live")
    replay = payload.get("replay")

    # Settings payload
    if "settings" in payload:
        s = valid_settings(payload["settings"])
        with settings_lock:
            runtime_settings.update(s)
        # Apply symbol to provider immediately
        yahoo.symbol = runtime_settings.get("symbol", yahoo.symbol)

    # Prevent double start
    if app_state.get("running") and trainer_thread and trainer_thread.is_alive():
        return jsonify({"ok": True, "running": True, "note": "already running"}), 200

    stop_event.clear()
    app_state["running"] = True
    trainer_thread = threading.Thread(target=trainer_loop, args=(mode, replay), daemon=True)
    trainer_thread.start()
    return jsonify({"ok": True, "running": True}), 200

@app.route("/control/stop", methods=["POST"])
def control_stop():
    stop_event.set()
    app_state["running"] = False

    # Attempt to stop rate limiter worker if present
    try:
        if hasattr(rate_limiter, "stop"):
            rate_limiter.stop()
    except Exception as e:
        app.logger.warning(f"RateLimiter stop error: {e}")

    global trainer_thread
    alive = False
    if trainer_thread and trainer_thread.is_alive():
        trainer_thread.join(timeout=10.0)
        alive = trainer_thread.is_alive()

    return jsonify({"ok": True, "running": False, "stopped": (not alive)}), 200

@app.route("/control/kill", methods=["POST"])
def control_kill():
    os.environ["FORCE_STOP"] = "1"
    stop_event.set()
    app_state["running"] = False

    try:
        if hasattr(rate_limiter, "stop"):
            rate_limiter.stop()
    except Exception as e:
        app.logger.warning(f"RateLimiter stop error: {e}")

    global trainer_thread
    if trainer_thread and trainer_thread.is_alive():
        trainer_thread.join(timeout=10.0)
    return jsonify({"ok": True, "running": False, "killed": True}), 200

# ---- Memory Exports ----

def require_admin_if_set():
    admin_key = os.getenv("ADMIN_KEY")
    if admin_key:
        if request.headers.get("X-ADMIN-KEY") != admin_key:
            abort(403)

@app.route("/memory/gold.csv", methods=["GET"])
def memory_gold():
    require_admin_if_set()
    if not os.path.exists(GOLD_CSV):
        # empty file response
        return jsonify({"error": "no gold yet"}), 404
    return send_file(GOLD_CSV, mimetype="text/csv", as_attachment=True, download_name="gold.csv")

@app.route("/memory/hard_negatives.csv", methods=["GET"])
def memory_neg():
    require_admin_if_set()
    if not os.path.exists(NEG_CSV):
        return jsonify({"error": "no hard negatives yet"}), 404
    return send_file(NEG_CSV, mimetype="text/csv", as_attachment=True, download_name="hard_negatives.csv")

@app.route("/memory/clear", methods=["POST"])
def memory_clear():
    require_admin_if_set()
    for p in (GOLD_CSV, NEG_CSV):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
    return jsonify({"ok": True})

# ---- Entrypoint ----
# gunicorn entry uses 'app:app', so no debug run here

