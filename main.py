from flask import Flask, jsonify, request
import gpt_decision

app = Flask(__name__)

@app.route('/status')
def status():
    return jsonify({"status": "running", "mode": "ready"})

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        return jsonify({"message": "Settings updated"})
    return jsonify({"settings": {"source": "yahoo", "model": "gpt-3.5"}})

@app.route('/control/start')
def control_start():
    return jsonify({"control": "started"})

@app.route('/control/stop')
def control_stop():
    return jsonify({"control": "stopped"})

@app.route('/metrics/summary')
def metrics_summary():
    return jsonify({"metrics": {"trades": 0, "wins": 0, "losses": 0}})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
