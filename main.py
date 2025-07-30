from flask import Flask
app = Flask(__name__)

# main entry for backend


from flask import request, jsonify

is_running = False
pnl_total = 0.0
trade_log = []

@app.route("/status", methods=["GET"])
def status():
    return jsonify({"running": is_running})

@app.route("/start", methods=["POST"])
def start():
    global is_running
    is_running = True
    return jsonify({"message": "Trading started"})

@app.route("/stop", methods=["POST"])
def stop():
    global is_running
    is_running = False
    return jsonify({"message": "Trading stopped"})

@app.route("/pnl", methods=["GET"])
def pnl():
    return jsonify({"total": pnl_total})

@app.route("/trade-log", methods=["GET"])
def trade_log_route():
    return jsonify(trade_log)
