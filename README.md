# emini (Py 3.13 fix)

Deploy steps:
1) Push to GitHub.
2) On Render → New → Web Service → connect repo.
3) If Render shows an old **Build Command** with `numpy==1.26.4`, replace it with:
   `pip install -U pip setuptools wheel && pip install -r requirements.txt`
   (Or delete the custom build command so Render reads `render.yaml`.)
4) Deploy → open `/health`.

Notes:
- This repo pins **PYTHON_VERSION=3.13.4** and uses **numpy==2.3.2**.
- If you *must* keep numpy 1.26.4, change PYTHON_VERSION to 3.10.14.
