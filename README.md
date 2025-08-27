# Render Backend (Fixed)
Built: 2025-08-27T17:33:29.726220Z

This package uses the app/ layout required by your Procfile and includes missing deps (gunicorn, PyYAML).

Deploy steps:
1) Upload to Render (or push to GitHub).
2) Ensure Build Command installs: `pip install -r requirements.txt`
3) Start Command defaults from Procfile: `web: gunicorn -w 2 -k gthread -b 0.0.0.0:$PORT app.main:app`
4) Confirm CORS is enabled in your Flask app for your Netlify domain.

Python version is pinned via runtime.txt to 3.11.9 for compatibility.
