
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

trades = []

@app.route('/start', methods=['POST'])
def start_bot():
    return 'Bot started'

@app.route('/stop', methods=['POST'])
def stop_bot():
    return 'Bot stopped'

@app.route('/trade-log', methods=['GET'])
def trade_log():
    return jsonify(trades)
