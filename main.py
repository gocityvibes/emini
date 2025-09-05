from flask import Flask, jsonify, request, send_file, Response, make_response
from functools import wraps
import io, csv, threading, time, os

from yahoo_provider import fetch_ohlcv
from gpt_decision import decide as gpt_decide, GPTNotConfigured

app = Flask(__name__)

# -------- CORS (Netlify + local dev) --------
ALLOWED_ORIGINS = {
    "https://tradebotmicro.netlify.app",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
}

def _cors_headers():
    origin = request.headers.get("Origin")
    if origin and origin in ALLOWED_ORIGINS:
        return {
            "Access-Control-Allow-Origin": origin,
            "Vary": "Origin",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Headers": request.headers.get("Access-Control-Request-Headers", "Content-Type, Authorization"),
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        }
    return {}

@app.before_request
def _handle_preflight():
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        for k, v in _cors_headers().items():
            resp.headers[k] = v
        return resp

@app.after_request
def _apply_cors(response):
    for k, v in _cors_headers().items():
        response.headers[k] = v
    return response

# ---------- Runtime State ----------
state_lock = threading.Lock()
STATE = {
    "engine": "running",          # running | stopped | paused
    "mode": "live",               # live | training
    "since": int(time.time()),
    "version": "2025-09-04.3"
}

def set_state(**kwargs):
    with state_lock:
        STATE.update(kwargs)

def get_state():
    with state_lock:
        return dict(STATE)

# ---------- Helpers ----------
def require_running(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        s = get_state()
        if s["engine"] == "stopped":
            return Response(status=503, headers={"Retry-After": "30"})
        if s["engine"] == "paused":
            return jsonify({"ok": False, "status": "paused"}), 409
        return fn(*args, **kwargs)
    return wrapper

# ---------- Health & Status ----------
@app.route("/health")
def health():
    return "OK", 200

@app.route("/")
def root():
    return "Service online. Use /status.", 200

@app.route("/status")
def status():
    return jsonify({"ok": True, "state": get_state()})

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        mode = body.get("mode")
        if mode in ("live", "training"):
            set_state(mode=mode)
        return jsonify({"ok": True, "state": get_state()})
    return jsonify({"ok": True, "settings": {"data_source": "yahoo", "model": "gpt-3.5"}, "state": get_state()})

# ---------- Control ----------
@app.route("/control/start", methods=["POST", "GET"])
def control_start():
    mode = request.args.get("mode") or (request.get_json().get("mode") if request.is_json else None)
    if mode not in ("live", "training"):
        mode = "live"
    set_state(engine="running", mode=mode)
    return jsonify({"ok": True, "message": "engine started", "state": get_state()})

@app.route("/control/stop", methods=["POST", "GET"])
def control_stop():
    set_state(engine="stopped")
    return jsonify({"ok": True, "message": "engine stopped", "state": get_state()})

@app.route("/control/pause", methods=["POST", "GET"])
def control_pause():
    set_state(engine="paused")
    return jsonify({"ok": True, "message": "engine paused", "state": get_state()})

@app.route("/control/resume", methods=["POST", "GET"])
def control_resume():
    set_state(engine="running")
    return jsonify({"ok": True, "message": "engine resumed", "state": get_state()})

# ---------- Yahoo endpoints (real) ----------
@app.route("/train/yahoo")
@require_running
def train_yahoo():
    symbol = request.args.get("symbol", "ES=F")
    period = request.args.get("period", "7d")
    interval = request.args.get("interval", "1m")
    df = fetch_ohlcv(symbol, period=period, interval=interval)
    if df is None or df.empty:
        return jsonify({"ok": False, "error": "No data", "symbol": symbol}), 404
    # Minimal "training" example: return counts
    return jsonify({
        "ok": True,
        "symbol": symbol,
        "rows": int(df.shape[0]),
        "start": df.index.min().isoformat() if not df.empty else None,
        "end": df.index.max().isoformat() if not df.empty else None
    })

@app.route("/live/last")
@require_running
def live_last():
    symbol = request.args.get("symbol", "ES=F")
    df = fetch_ohlcv(symbol, period="1d", interval="1m")
    if df is None or df.empty:
        return jsonify({"ok": False, "error": "No data"}), 404
    last = df.iloc[-1].to_dict()
    last["timestamp"] = df.index[-1].isoformat()
    return jsonify({"ok": True, "symbol": symbol, "last": last})

# ---------- GPT decision (real) ----------
@app.route("/decide")
@require_running
def decide():
    signal = request.args.get("signal", "neutral")
    context = request.args.get("context", "")
    try:
        decision = gpt_decide(signal=signal, context=context)
        return jsonify({"ok": True, "decision": decision})
    except GPTNotConfigured as e:
        # Informative error if OPENAI_API_KEY is missing
        return jsonify({"ok": False, "error": str(e)}), 501
    except Exception as e:
        return jsonify({"ok": False, "error": f"gpt_error: {e}"}), 500

# ---------- Metrics (guarded) ----------
@app.route("/metrics/summary")
@require_running
def metrics_summary():
    return jsonify({
        "ok": True,
        "summary": {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
        }
    })

@app.route("/metrics/live")
@require_running
def metrics_live():
    return jsonify({"ok": True, "live": {"rth": False, "last_check": int(time.time())}})

# ---------- Memory CSV (guarded) ----------
def _csv_bytes(rows, headers):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=headers)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return io.BytesIO(buf.getvalue().encode("utf-8"))

@app.route("/memory/gold.csv")
@require_running
def memory_gold():
    data = [{"ts": int(time.time()), "symbol": "ES", "pattern": "gold", "result": "win"}]
    b = _csv_bytes(data, ["ts", "symbol", "pattern", "result"])
    return send_file(b, mimetype="text/csv", as_attachment=True, download_name="gold.csv")

@app.route("/memory/hard_negatives.csv")
@require_running
def memory_hard_negatives():
    data = [{"ts": int(time.time()), "symbol": "ES", "pattern": "neg", "result": "loss"}]
    b = _csv_bytes(data, ["ts", "symbol", "pattern", "result"])
    return send_file(b, mimetype="text/csv", as_attachment=True, download_name="hard_negatives.csv")

# ---------- Entry point ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
