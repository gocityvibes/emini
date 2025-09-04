# Patched Backend (CORS + Silent Stop)
Deploy on Render:
- Build: `pip install -r requirements.txt`
- Start: `gunicorn -w 1 -k gthread -b 0.0.0.0:$PORT main:app`

CORS:
- Allows origins:
  - https://tradebotmicro.netlify.app
  - localhost dev ports 5173/3000
- Preflight handled globally (OPTIONS → 204).
- All responses include CORS headers via `after_request`.

Silent Stop:
- `/control/stop` sets engine=stopped → guarded endpoints return 503.
- `/control/pause` → guarded endpoints return 409.
- `/status` and `/health` always 200.
