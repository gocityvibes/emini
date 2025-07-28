
from flask import Flask, jsonify, request
from flask_cors import CORS
import time
import random
import os

app = Flask(__name__)
CORS(app)

trade_log = []
bot_running = False

# Load env config
TRADOVATE_MODE = os.getenv("TRADOVATE_MODE", "paper")
TRADOVATE_ACCOUNT_ID = os.getenv("TRADOVATE_ACCOUNT_ID", "demo123")
CONTRACT_TYPE = os.getenv("CONTRACT_TYPE", "/MESU5")  # e.g., /ESU5 or /MNQU5

def chrome_filter_mock():
    return True, ["RSI", "MACD", "VWAP"]

def shadow_filter_mock():
    return True, ["Multi-timeframe Confirmation", "Candle Pattern Type", "SPY/QQQ Sentiment"]

@app.route("/")
def index():
    return jsonify({"status": "Phase 5 backend with Tradovate execution toggle"})

@app.route("/start", methods=["POST"])
def start_bot():
    global bot_running
    bot_running = True

    passed_chrome, chrome_indicators = chrome_filter_mock()
    passed_shadow, shadow_signals = shadow_filter_mock()

    if passed_chrome and passed_shadow:
        entry_price = round(random.uniform(4500, 4600), 2)
        exit_price = round(entry_price + random.uniform(20, 40), 2)
        expected_price = round(entry_price - random.uniform(0.25, 1.0), 2)
        duration = round(random.uniform(120, 900), 2)
        pnl = round(exit_price - entry_price, 2)
        slippage = round(entry_price - expected_price, 2)
        win = pnl > 0

        trade = {
            "symbol": "ES",
            "contract": CONTRACT_TYPE,
            "mode": TRADOVATE_MODE,
            "account_id": TRADOVATE_ACCOUNT_ID,
            "side": "long",
            "score": 97,
            "reason": f"Chrome: {', '.join(chrome_indicators)} | Shadow: {', '.join(shadow_signals)}",
            "entry_price": entry_price,
            "expected_entry": expected_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "slippage": slippage,
            "duration_sec": duration,
            "win": win,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }

        trade_log.append(trade)
        return jsonify({"message": "Trade executed", "trade": trade})
    else:
        return jsonify({"message": "No trade - filter conditions not met"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    global bot_running
    bot_running = False
    return jsonify({"message": "Bot stopped"})

@app.route("/trades", methods=["GET"])
def get_trades():
    return jsonify({"trades": trade_log})

@app.route("/analytics", methods=["GET"])
def analytics():
    if not trade_log:
        return jsonify({"total_trades": 0, "wins": 0, "win_pct": 0, "pnl_total": 0})

    total = len(trade_log)
    wins = sum(1 for t in trade_log if t["win"])
    pnl_total = round(sum(t["pnl"] for t in trade_log), 2)
    win_pct = round((wins / total) * 100, 2)
    return jsonify({
        "total_trades": total,
        "wins": wins,
        "win_pct": win_pct,
        "pnl_total": pnl_total
    })



# === Toggle Feature Flags ===
ironwall_enabled = False
chrome_enabled = False
shadow_enabled = False

@app.route("/toggle", methods=["POST"])
def toggle_feature():
    global ironwall_enabled, chrome_enabled, shadow_enabled
    data = request.get_json()
    feature = data.get("feature")

    if feature == "ironwall":
        ironwall_enabled = not ironwall_enabled
        return jsonify({"status": f"Ironwall {'ON' if ironwall_enabled else 'OFF'}"})
    elif feature == "chrome":
        chrome_enabled = not chrome_enabled
        return jsonify({"status": f"Chrome {'ON' if chrome_enabled else 'OFF'}"})
    elif feature == "shadow":
        shadow_enabled = not shadow_enabled
        return jsonify({"status": f"Shadow {'ON' if shadow_enabled else 'OFF'}"})
    else:
        return jsonify({"error": "Invalid feature"}), 400

# Optional root display of status
@app.route("/")
def status():
    return jsonify({
        "status": "Bot online",
        "ironwall": ironwall_enabled,
        "chrome": chrome_enabled,
        "shadow": shadow_enabled
    })



import os
import json
from datetime import datetime

# Trade log file
LOG_FILE = "trade_log.json"
MAX_TRADES_PER_DAY = 3

# Utility: read log
def read_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            return json.load(f)
    return []

# Utility: write log
def write_log(data):
    with open(LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)

# Utility: add trade
def log_trade(symbol, score, profit, toggles):
    log = read_log()
    log.append({
        "timestamp": datetime.now().isoformat(),
        "symbol": symbol,
        "score": score,
        "profit": profit,
        "toggles": toggles
    })
    write_log(log)

@app.route("/trade-log")
def get_trade_log():
    return jsonify(read_log())

@app.route("/daily-summary")
def daily_summary():
    log = read_log()
    today = datetime.now().date().isoformat()
    today_trades = [t for t in log if t["timestamp"].startswith(today)]

    wins = [t for t in today_trades if t["profit"] > 0]
    losses = [t for t in today_trades if t["profit"] <= 0]
    total_profit = sum(t["profit"] for t in today_trades)

    return jsonify({
        "date": today,
        "trades": len(today_trades),
        "wins": len(wins),
        "losses": len(losses),
        "total_profit": total_profit
    })



# Smart Entry Evaluation
@app.route("/smart-entry-check", methods=["POST"])
def smart_entry_check():
    data = request.json
    symbol = data.get("symbol")
    indicators = data.get("indicators", {})
    score = int(data.get("score", 0))

    pattern_check = gpt_check_patterns(symbol, indicators)
    passes_all = pattern_check["score"] >= 90 and pattern_check["alignment_ok"]

    return jsonify({
        "symbol": symbol,
        "pattern_reason": pattern_check["reason"],
        "score": pattern_check["score"],
        "trade_allowed": passes_all
    })

def gpt_check_patterns(symbol, indicators):
    prompt = f"Analyze this trading setup for {symbol}:
"
    prompt += f"1-min RSI: {indicators.get('rsi_1m')} | MACD: {indicators.get('macd_1m')} | EMA: {indicators.get('ema_1m')}
"
    prompt += f"5-min RSI: {indicators.get('rsi_5m')} | MACD: {indicators.get('macd_5m')} | EMA: {indicators.get('ema_5m')}
"
    prompt += f"Daily RSI: {indicators.get('rsi_d')} | MACD: {indicators.get('macd_d')} | EMA: {indicators.get('ema_d')}
"
    prompt += f"VWAP: {indicators.get('vwap')} | Volume Surge: {indicators.get('vol_surge')}
"
    prompt += f"Return JSON with fields: reason, score (0-100), alignment_ok (boolean)"

    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a trading signal analyst."},
            {"role": "user", "content": prompt}
        ]
    )
    parsed = response.choices[0].message.content
    try:
        return json.loads(parsed)
    except:
        return {"reason": "Could not parse GPT response", "score": 0, "alignment_ok": False}
