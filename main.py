
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

trade_log = []
bot_running = False

# Mocked Chrome Filter check (simulates 3+ of 8 confirmations)
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

@app.route("/")
def index():
    return jsonify({"status": "Phase 2 backend with mocked indicators is live"})

@app.route("/start", methods=["POST"])
def start_bot():
    global bot_running
    bot_running = True

    # Simulate a trade with indicator mock logic
    passed_filter, passed_indicators = chrome_filter_mock()
    if passed_filter:
        trade = {
            "symbol": "ES",
            "side": "long",
            "score": 97,
            "reason": "Passed Chrome Filter with: " + ", ".join(passed_indicators),
            "entry_price": 4502.75,
            "exit_price": 4547.00,
            "pnl": 44.25
        }
        trade_log.append(trade)
        return jsonify({"message": "Trade executed", "trade": trade})
    else:
        return jsonify({"message": "No trade - Chrome Filter conditions not met"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    global bot_running
    bot_running = False
    return jsonify({"message": "Bot stopped"})

@app.route("/trades", methods=["GET"])
def get_trades():
    return jsonify({"trades": trade_log})
