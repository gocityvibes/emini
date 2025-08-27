Requirements Patch
Built: 2025-08-27T17:47:15.654413Z

This requirements.txt adds the missing libraries:
- openai==0.28.1 (legacy SDK to match code using `import openai` and ChatCompletion)
- tenacity

How to apply on Render:
1) Replace your repo's requirements.txt with this one (or merge the missing lines).
2) Redeploy so Render runs `pip install -r requirements.txt`.
3) In Render → Settings → Environment, add OPENAI_API_KEY with your API key.
