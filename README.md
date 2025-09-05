# Patched Backend (GPT + Yahoo + CORS + Silent Stop)
Deploy on Render:
- Build: `pip install -r requirements.txt`
- Start: `gunicorn -w 1 -k gthread -b 0.0.0.0:$PORT main:app`

Env Vars:
- `OPENAI_API_KEY` (required for /decide)
- Optional: `OPENAI_MODEL` (default gpt-3.5-turbo), `GPT_RATE_QPS`

Endpoints:
- `GET /health` — always 200
- `GET /status` — engine state
- `POST|GET /control/start?mode=live|training` — resume + set mode
- `POST|GET /control/stop` — stops engine; guarded endpoints return 503
- `POST|GET /control/pause` — guarded endpoints 409
- `GET /train/yahoo?symbol=ES=F&period=7d&interval=1m` — fetches bars
- `GET /live/last?symbol=ES=F` — last 1m bar
- `GET /decide?signal=neutral&context=...` — GPT decision (needs OPENAI_API_KEY)
- `GET /metrics/summary`, `GET /metrics/live`
- `GET /memory/gold.csv`, `GET /memory/hard_negatives.csv`

CORS:
- Allowed origins: https://tradebotmicro.netlify.app, localhost:5173/3000
- OPTIONS preflight handled globally.
