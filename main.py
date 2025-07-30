
# === SIMULATION MODE INJECTED ===
SIMULATION_MODE = True

def fake_market_data(symbol):
    import random, time
    return {
        "symbol": symbol,
        "price": round(random.uniform(3950, 4100), 2),
        "volume": random.randint(10000, 50000),
        "float": random.randint(10_000_000, 90_000_000),
        "sentiment": random.choice(["bullish", "bearish", "neutral"]),
        "news": random.choice(["lawsuit", "upgrade", "none"]),
        "timestamp": time.time(),
    }

from flask import Flask
from flask_cors import cross_origin

app = Flask(__name__)

# main entry for backend


from flask import request, jsonify

is_running = False
pnl_total = 0.0
trade_log = []

@app.route("/status", methods=["GET"])
@cross_origin()
def status():
    return jsonify({"running": is_running})

@app.route("/start", methods=["POST"])
@cross_origin()
def start():
    global is_running
    is_running = True
    return jsonify({"message": "Trading started"})

@app.route("/stop", methods=["POST"])
@cross_origin()
def stop():
    global is_running
    is_running = False
    return jsonify({"message": "Trading stopped"})

@app.route("/pnl", methods=["GET"])
@cross_origin()
def pnl():
    return jsonify({"total": pnl_total})

@app.route("/trade-log", methods=["GET"])
@cross_origin()
def trade_log_route():
    return jsonify(trade_log)