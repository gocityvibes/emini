from flask import jsonify, request

def register_routes(app, app_state):
    @app.get("/health")
    def health():
        return jsonify(status="ok")
