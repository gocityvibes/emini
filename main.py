
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

trade_log = []
bot_running = False

def chrome_filter_mock():
    indicators = {
        "RSI": True,
        "MACD": True,
        "EMA Stack": False,
        "VWAP": True,
        "Volume Surge": False,
        "Chart Pattern": True,
        "Market Sentiment": False,
        "GPT Score": True
    }
    passed = [k for k, v in indicators.items() if v]
    return len(passed) >= 3, passed

def shadow_filter_mock():
    context_signals = {
        "Multi-timeframe Confirmation": True,
        "News Landmine Check": False,
        "Candle Pattern Type": True,
        "SPY/QQQ Sentiment": True,
        "Trap Pattern Detection": True
    }
    passed = [k for k, v in context_signals.items() if v]
    return len(passed) >= 3, passed

@app.route("/")
def index():
    return jsonify({"status": "Phase 3 backend with Shadow Filter active"})

@app.route("/start", methods=["POST"])
def start_bot():
    global bot_running
    bot_running = True

    passed_chrome, chrome_indicators = chrome_filter_mock()
    passed_shadow, shadow_signals = shadow_filter_mock()

    if passed_chrome and passed_shadow:
        trade = {
            "symbol": "NQ",
            "side": "short",
            "score": 96,
            "reason": "Passed Chrome ({}), Shadow ({}).".format(", ".join(chrome_indicators), ", ".join(shadow_signals)),
            "entry_price": 15882.50,
            "exit_price": 15822.50,
            "pnl": 60.00
        }
        trade_log.append(trade)
        return jsonify({"message": "Trade executed", "trade": trade})
    else:
        return jsonify({"message": "No trade - conditions not met", "chrome": passed_chrome, "shadow": passed_shadow})

@app.route("/stop", methods=["POST"])
def stop_bot():
    global bot_running
    bot_running = False
    return jsonify({"message": "Bot stopped"})

@app.route("/trades", methods=["GET"])
def get_trades():
    return jsonify({"trades": trade_log})
