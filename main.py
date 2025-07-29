
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for all origins

@app.route("/", methods=["GET"])
def index():
    return "E-mini bot is live!", 200

@app.route("/start", methods=["POST"])
def start_trade():
    return jsonify({"status": "trade started"}), 200

@app.route("/stop", methods=["POST"])
def stop_trade():
    return jsonify({"status": "trade stopped"}), 200

if __name__ == "__main__":
    app.run()
