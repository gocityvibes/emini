# Render Clean (Python 3.10.14)

Known-good minimal Flask service for Render using Python 3.10.14.

## Local test (Windows-friendly)
1) Install Python 3.10.x
2) In this folder:
   python -m venv .venv && .venv\Scripts\activate
   pip install -U pip setuptools wheel
   pip install --only-binary=:all: numpy==1.26.4 pandas==2.2.3 lxml==5.2.2
   pip install -r requirements.txt
   python app/main.py
3) Visit http://localhost:10000

## Deploy (GitHub → Render)
- Upload this folder to a new GitHub repo (keep structure).
- On Render: New → Web Service → connect the repo.
- If `render.yaml` isn't detected, set:
  Build:
    pip install -U pip setuptools wheel && pip install --only-binary=:all: numpy==1.26.4 pandas==2.2.3 lxml==5.2.2 && pip install -r requirements.txt
  Start:
    gunicorn -w 2 -k gthread -b 0.0.0.0:$PORT app.main:app
- Health check: `/health`

## Add your app
Put your endpoints in `app/main.py` or add modules and adjust the start command accordingly.
