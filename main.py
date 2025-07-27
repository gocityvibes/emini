
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import datetime

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return "E-mini GPT Bot Backend Running"

@app.route('/trade', methods=['POST'])
def trade():
    data = request.json
    # Placeholder for actual trade logic
    return jsonify({"status": "success", "message": "Trade endpoint reached", "data": data})

if __name__ == '__main__':
    app.run()
