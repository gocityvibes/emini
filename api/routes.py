from flask import jsonify, request

def register_routes(app, app_state):
    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/metrics/summary")
    def metrics_summary():
        return jsonify({
            "running": app_state.get("running", False),
            "gpt_calls_used": app_state.get("gpt_calls_used", 0)
        })

    @app.get("/metrics/live")
    def metrics_live():
        return jsonify({
            "latest_candidate": app_state.get("latest_candidate")
        })

    @app.get("/metrics/budget")
    def metrics_budget():
        return jsonify({
            "calls_used": app_state.get("gpt_calls_used", 0),
            "paused": app_state.get("budget_paused", False),
            "paused_reason": app_state.get("budget_paused_reason")
        })

    @app.post("/control/start")
    def control_start():
        app_state["running"] = True
        return jsonify({"running": True})

    @app.post("/control/stop")
    def control_stop():
        app_state["running"] = False
        return jsonify({"running": False})

    @app.get("/metrics/trades")
    def metrics_trades():
        return jsonify(app_state.get("trades", []))

    @app.get("/metrics/fingerprints")
    def metrics_fingerprints():
        return jsonify(app_state.get("fingerprints", []))
