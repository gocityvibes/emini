
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
