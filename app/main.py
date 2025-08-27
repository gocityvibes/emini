
import os
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List
import random

from flask import Flask, jsonify, request, send_file, abort, make_response
from flask_cors import CORS

app = Flask(__name__)
# Broad CORS enablement
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

@app.after_request
def add_cors_headers(resp):
    origin = request.headers.get("Origin", "*")
    resp.headers["Access-Control-Allow-Origin"] = origin
    resp.headers["Access-Control-Allow-Headers"] = request.headers.get("Access-Control-Request-Headers", "Content-Type, X-ADMIN-KEY")
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Vary"] = "Origin"
    return resp

# Explicit preflight handler for ALL paths (avoids 404/405 on OPTIONS)
def _preflight_ok():
    origin = request.headers.get("Origin", "*")
    allow_headers = request.headers.get("Access-Control-Request-Headers", "Content-Type, X-ADMIN-KEY")
    resp = make_response("", 204)
    resp.headers["Access-Control-Allow-Origin"] = origin
    resp.headers["Access-Control-Allow-Headers"] = allow_headers
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Max-Age"] = "86400"
    resp.headers["Vary"] = "Origin"
    return resp

@app.route("/", methods=["OPTIONS"])
def options_root():
    return _preflight_ok()

@app.route("/<path:_>", methods=["OPTIONS"])
def options_all(_):
    return _preflight_ok()

# ---------- Minimal state + worker (same as stopfix) ----------
DATA_DIR = os.environ.get("DATA_DIR", "datafiles")
os.makedirs(DATA_DIR, exist_ok=True)
GOLD_CSV = os.path.join(DATA_DIR, "gold.csv")
NEG_CSV = os.path.join(DATA_DIR, "hard_negatives.csv")

ADMIN_KEY = os.environ.get("ADMIN_KEY")
def require_admin_if_set():
    if not ADMIN_KEY:
        return
    key = request.headers.get("X-ADMIN-KEY") or request.args.get("key")
    if key != ADMIN_KEY:
        abort(401)

state_lock = threading.RLock()
stop_event = threading.Event()
worker_thread: Optional[threading.Thread] = None

default_settings: Dict[str, Any] = {
    "symbol": "MES=F",
    "interval": "1m",
    "score_cutoff": 90,
    "premium_threshold": 0.8,
    "require_confluence": 2,
    "max_trades_per_day": 5,
    "risk_per_trade_pct": 1.0,
    "stop_loss_pct": 5.0,
    "take_profit_pct": 10.0,
    "session_hours": False,
    "no_new_trades_after": "15:00",
    "flat_at_time": "15:45",
    "volume_surge": 1.0,
    "spread_atr": 0.2,
    "trailing": {"enabled": False, "pct": 2.0},
}
app_state: Dict[str, Any] = {
    "running": False,
    "thread_alive": False,
    "force_stop": "0",
    "block_trainer": "0",
    "settings": default_settings.copy(),
    "trades": [],
    "mode": "live",
    "replay": None,
    "metrics": {"trades_today":0,"net_points_today":0.0,"win_rate_trailing20":0.0,"avg_time_to_target_sec":0}
}

def clamp(v, lo, hi):
    try: x = float(v)
    except Exception: return lo
    return max(lo, min(hi, x))

def valid_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    s = app_state["settings"].copy()
    for k, v in (payload or {}).items():
        if k == "symbol":
            s[k] = str(v)[:20]
        elif k == "interval":
            s[k] = str(v) if str(v) in ("1m","5m","15m") else "1m"
        elif k in ("score_cutoff",):
            s[k] = int(clamp(v, 0, 100))
        elif k in ("premium_threshold","volume_surge","spread_atr"):
            s[k] = float(clamp(v, 0.0, 5.0))
        elif k in ("require_confluence","max_trades_per_day"):
            s[k] = int(clamp(v, 0, 100))
        elif k in ("risk_per_trade_pct","stop_loss_pct","take_profit_pct"):
            s[k] = float(clamp(v, 0.0, 100.0))
        elif k == "session_hours":
            s[k] = bool(v)
        elif k in ("no_new_trades_after","flat_at_time"):
            s[k] = str(v)
        elif k == "trailing":
            tv = v or {}
            s["trailing"] = {"enabled": bool(tv.get("enabled", False)), "pct": float(clamp(tv.get("pct", 2.0), 0.0, 100.0))}
    return s

def ring_append(trades: List[Dict[str, Any]], item: Dict[str, Any], maxlen: int = 50):
    trades.insert(0, item)
    if len(trades) > maxlen:
        del trades[maxlen:]

def persist_trade_to_csv(trade: Dict[str, Any]):
    is_win = float(trade.get("pnl_pts") or 0.0) > 0.0
    path = GOLD_CSV if is_win else NEG_CSV
    hdr_needed = not os.path.exists(path)
    try:
        import csv
        with open(path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(trade.keys()))
            if hdr_needed:
                w.writeheader()
            w.writerow(trade)
        # trim file
        with open(path, "r") as f:
            rows = f.readlines()
        if len(rows) > 1000:
            with open(path, "w") as f:
                f.writelines(rows[-1000:])
    except Exception:
        pass

def recalc_metrics():
    from datetime import date
    today = date.today().isoformat()
    trades = app_state["trades"]
    tday = [t for t in trades if (t.get("timestamp") or "")[:10] == today]
    net = sum(float(t.get("pnl_pts") or 0.0) for t in tday)
    last20 = trades[:20]
    wins = sum(1 for t in last20 if float(t.get("pnl_pts") or 0.0) > 0.0)
    wr = (wins/len(last20)) if last20 else 0.0
    avg = int(sum(int(t.get("duration_s") or 0) for t in tday)/len(tday)) if tday else 0
    app_state["metrics"] = {"trades_today":len(tday),"net_points_today":round(net,2),"win_rate_trailing20":round(wr,3),"avg_time_to_target_sec":avg}

def generate_fake_trade(symbol: str) -> Dict[str, Any]:
    import random
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    direction = random.choice(["LONG","SHORT"])
    entry = round(random.uniform(4500, 5600), 2)
    move = round(random.uniform(-3.0, 3.0), 2)
    exitp = round(entry + move if direction == "LONG" else entry - move, 2)
    pnl = round((exitp - entry) if direction == "LONG" else (entry - exitp), 2)
    return {"timestamp":now,"symbol":symbol,"direction":direction,"entry_price":entry,"exit_price":exitp,"pnl_pts":pnl,"duration_s":random.randint(10,600),"gpt_score":random.choice([None,85,90,95,99])}

def worker_loop():
    while not stop_event.is_set():
        with state_lock:
            symbol = app_state["settings"]["symbol"]
        trade = generate_fake_trade(symbol)
        with state_lock:
            ring_append(app_state["trades"], trade, maxlen=50)
            recalc_metrics()
        persist_trade_to_csv(trade)
        if stop_event.wait(5.0):
            break

@app.get("/health")
def health():
    return jsonify({"ok": True})

@app.get("/status")
def status():
    with state_lock:
        return jsonify({"running":bool(app_state["running"]), "thread_alive":bool(app_state["thread_alive"]), "force_stop":app_state.get("force_stop","0"), "block_trainer":app_state.get("block_trainer","0")})

@app.get("/metrics/summary")
def metrics_summary():
    with state_lock:
        return jsonify(app_state["metrics"])

@app.get("/metrics/trades")
def metrics_trades():
    with state_lock:
        return jsonify(app_state["trades"])

@app.route("/control/start", methods=["POST","OPTIONS"])
def control_start():
    require_admin_if_set()
    global worker_thread
    body = request.get_json(silent=True) or {}
    mode = str(body.get("mode","live"))
    replay = body.get("replay")
    with state_lock:
        if app_state["running"] and worker_thread and worker_thread.is_alive():
            return jsonify({"ok": True, "already_running": True})
        app_state["mode"] = mode
        app_state["replay"] = replay
        app_state["force_stop"] = "0"
        app_state["running"] = True
        app_state["thread_alive"] = False
    stop_event.clear()
    def _run():
        with state_lock:
            app_state["thread_alive"] = True
        try:
            worker_loop()
        finally:
            with state_lock:
                app_state["running"] = False
                app_state["thread_alive"] = False
    worker_thread = threading.Thread(target=_run, name="bot", daemon=True)
    worker_thread.start()
    return jsonify({"ok": True})

@app.route("/control/stop", methods=["POST","OPTIONS"])
def control_stop():
    require_admin_if_set()
    global worker_thread
    with state_lock:
        app_state["force_stop"] = "1"
        app_state["running"] = False
    stop_event.set()
    alive = False
    if worker_thread and worker_thread.is_alive():
        worker_thread.join(timeout=8)
        alive = worker_thread.is_alive()
    with state_lock:
        app_state["thread_alive"] = alive
    return jsonify({"ok": True, "thread_alive": alive})

@app.post("/control/kill")
def control_kill():
    require_admin_if_set()
    stop_event.set()
    with state_lock:
        app_state["force_stop"] = "1"
        app_state["running"] = False
        app_state["thread_alive"] = False
    return jsonify({"ok": True})

@app.get("/settings")
def get_settings():
    with state_lock:
        return jsonify(app_state["settings"])

@app.post("/settings")
def post_settings():
    require_admin_if_set()
    payload = request.get_json(silent=True) or {}
    with state_lock:
        app_state["settings"] = valid_settings(payload)
    return jsonify({"ok": True})

@app.get("/memory/gold.csv")
def memory_gold():
    require_admin_if_set()
    if not os.path.exists(GOLD_CSV):
        open(GOLD_CSV, "w").close()
    return send_file(GOLD_CSV, as_attachment=True, download_name="gold.csv")

@app.get("/memory/hard_negatives.csv")
def memory_neg():
    require_admin_if_set()
    if not os.path.exists(NEG_CSV):
        open(NEG_CSV, "w").close()
    return send_file(NEG_CSV, as_attachment=True, download_name="hard_negatives.csv")

@app.post("/memory/clear")
def memory_clear():
    require_admin_if_set()
    for p in (GOLD_CSV, NEG_CSV):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
    return jsonify({"ok": True})
