import threading, time, yaml
from flask import Flask, jsonify
from flask_cors import CORS

from data.yahoo_provider import YahooProvider
from data.technical_analyzer import TechnicalAnalyzer
from simulation.realistic_sim import RealisticSimulator, TradeDirection
from prefilter.premium_filter import PremiumFilter
from prefilter.cost_optimizer import CostOptimizer
from gpt.trainer import GPTTrainer
from gpt.rate_limiter import RateLimiter

app = Flask(__name__)
CORS(app)

# load config.yaml
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

yahoo = YahooProvider(symbol=config.get("symbol", "MES=F"))
analyzer = TechnicalAnalyzer()
simulator = RealisticSimulator(config=config)
prefilter = PremiumFilter()
optimizer = CostOptimizer()
trainer = GPTTrainer()
rate_limiter = RateLimiter()

app_state = {
    "running": False,
    "metrics": {"trades_today": 0, "net_points_today": 0.0, "avg_time_to_target_sec": 0, "win_rate_trailing20": 0.0},
    "trades": []
}

stop_event = threading.Event()
trainer_thread = None

def trainer_loop():
    app.logger.info("Trainer loop started")
    while not stop_event.is_set():
        try:
            snapshot = yahoo.get_multi_timeframe_snapshot()
            df = snapshot.get("1m")
            if df is None or df.empty:
                time.sleep(5)
                continue

            df = analyzer.add_all_indicators(df, "1m")
            candidate = prefilter.evaluate(df)
            if not optimizer.should_send_to_gpt(candidate):
                time.sleep(5)
                continue

            decision = rate_limiter.submit_request(
                {"candidate": candidate.to_dict()},
                trainer.score_candidate
            )
            if not decision or "direction" not in decision:
                time.sleep(5)
                continue

            direction = TradeDirection.LONG if decision["direction"] == "long" else TradeDirection.SHORT
            trade = simulator.simulate_trade(
                entry_price=candidate.entry_price,
                entry_time=candidate.timestamp,
                direction=direction,
                bar_data=df.tail(100)
            )

            app_state.setdefault("trades", []).insert(0, trade)
            app_state["trades"] = app_state["trades"][:50]
            app_state["metrics"]["trades_today"] = len(app_state["trades"])
            app_state["metrics"]["net_points_today"] += trade.get("pnl_pts", 0)

        except Exception as e:
            app.logger.warning(f"Trainer error: {e}")
        time.sleep(10)
    app.logger.info("Trainer loop stopped")

@app.route("/control/start", methods=["POST"])
def control_start():
    global trainer_thread
    stop_event.clear()
    app_state["running"] = True
    if not trainer_thread or not trainer_thread.is_alive():
        trainer_thread = threading.Thread(target=trainer_loop, daemon=True)
        trainer_thread.start()
    return jsonify({"ok": True, "running": True}), 200

@app.route("/control/stop", methods=["POST"])
def control_stop():
    stop_event.set()
    app_state["running"] = False
    if trainer_thread and trainer_thread.is_alive():
        trainer_thread.join(timeout=2.0)
    if hasattr(rate_limiter, "stop"):
        rate_limiter.stop()
    return jsonify({"ok": True, "running": False}), 200

@app.route("/metrics/summary", methods=["GET"])
def metrics_summary():
    return jsonify({**app_state["metrics"], "running": app_state["running"]})

@app.route("/metrics/trades", methods=["GET"])
def metrics_trades():
    return jsonify(app_state.get("trades", []))

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
