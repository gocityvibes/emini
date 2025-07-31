from flask import Flask
from flask_cors import cross_origin

app = Flask(__name__)

# main entry for backend


from flask import request, jsonify
# --- Gemini Simulation Hook ---
import sys
if "--simulate" in sys.argv:
    from main_simulation_runner import run_full_simulation
    run_full_simulation()
    sys.exit()
# --- End Simulation Hook ---

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