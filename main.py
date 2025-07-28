
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

trade_log = []
bot_running = False

@app.route("/")
def index():
    return jsonify({"status": "GPT E-mini backend is live"})

@app.route("/start", methods=["POST"])
def start_bot():
    global bot_running
    bot_running = True
    return jsonify({"message": "Bot started"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    global bot_running
    bot_running = False
    return jsonify({"message": "Bot stopped"})

@app.route("/trades", methods=["GET"])
def get_trades():
    return jsonify({"trades": trade_log})

# Placeholder for GPT-3.5 scan + GPT-4o score + Tradovate order
def simulated_trade_decision():
    return {
        "symbol": "ES",
        "side": "long",
        "score": 97,
        "reason": "Bull flag + RSI oversold + SPY uptrend",
        "entry_price": 4500.25,
        "exit_price": 4545.75,
        "pnl": 45.50
    }

# Simulate trade on bot start
@app.before_request
def simulate_trade():
    global bot_running
    if bot_running and request.path == "/start":
        trade = simulated_trade_decision()
        trade_log.append(trade)
