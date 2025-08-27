# Render Backend (Fixed + Tenacity)
Built: 2025-08-27T17:40:40.524312Z

- Includes missing dependency `tenacity`
- Provides `data/` package with `__init__.py` and `yahoo_provider.py` to satisfy `from data.yahoo_provider import YahooProvider`
- Also keeps `app/yahoo_provider.py` for legacy `import yahoo_provider`

**Deploy**
1) `pip install -r requirements.txt`
2) Procfile: uses `app.main:app`
3) Python: 3.11.9 (via runtime.txt)
