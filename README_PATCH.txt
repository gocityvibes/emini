Backend (Render-ready) - Patched

What changed:
- main.py now finds config.yaml in the SAME folder first, then parent, or CONFIG_PATH env.
- Minimal endpoints are added if your Blueprints fail to register, so the frontend won't 404:
  * GET  /health, /status, /proxy/health, /proxy/status, /proxy/api/health, /proxy/api/status
  * GET  /metrics/summary, /metrics/live, /metrics/trades, /metrics/fingerprints, /metrics/budget
  * POST /control/start, /control/stop

Deploy on Render:
1) Zip this folder and upload to your repo OR push via Git.
2) Ensure Procfile is present and points to app.main:app
3) Confirm requirements install successfully.
4) Visit /health and /metrics/summary after deploy.