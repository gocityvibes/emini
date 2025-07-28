
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return jsonify({"message": "Backend is working"})

@app.route("/start", methods=["POST"])
def start_bot():
    return jsonify({"status": "Bot started (placeholder logic)"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    return jsonify({"status": "Bot stopped (placeholder logic)"})

@app.route("/trades", methods=["GET"])
def get_trades():
    return jsonify({"trades": []})
