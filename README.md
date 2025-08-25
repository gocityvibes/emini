# Render Clean (Py 3.13 Safe)
Works with Render's default Python 3.13.x.

## Deploy
1) Push this folder to GitHub (keep structure).
2) On Render: New → Web Service → connect repo.
3) If render.yaml isn't picked up, set:
   Build:  pip install -U pip setuptools wheel && pip install -r requirements.txt
   Start:  gunicorn -w 2 -k gthread -b 0.0.0.0:$PORT app.main:app
4) Health check at /health.

## Notes
- Uses numpy 2.3.2 and pandas 2.2.3 which have wheels for Python 3.13.
- If you prefer 3.10/3.11, set PYTHON_VERSION in Render and use the other ZIP I gave you.
