import os, time
from typing import Dict, Any

# OpenAI official sdk v1.x
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

RATE_LIMIT_QPS = float(os.environ.get("GPT_RATE_QPS", "0.5"))
_last_call_ts = 0.0

class GPTNotConfigured(Exception):
    pass

def _throttle():
    global _last_call_ts
    dt = time.time() - _last_call_ts
    min_dt = 1.0 / max(RATE_LIMIT_QPS, 0.01)
    if dt < min_dt:
        time.sleep(min_dt - dt)
    _last_call_ts = time.time()

def decide(signal: str, context: str = "") -> Dict[str, Any]:
    """Calls GPT-3.5/4 via OpenAI SDK and returns a simple decision block.
       Requires env var OPENAI_API_KEY.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        raise GPTNotConfigured("OPENAI_API_KEY not set or openai package missing")

    _throttle()

    client = OpenAI(api_key=api_key)
    prompt = (
        f"You are a trading decision helper. Given a signal '{signal}' and context '{context}', "
        "reply with JSON keys: decision(one of: buy,sell,hold), confidence(0-100), reason(short)."
    )

    # Use responses API for structured JSON-ish output
    resp = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo"),
        messages=[
            {"role": "system", "content": "You output compact JSON only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=100,
    )
    text = resp.choices[0].message.content.strip()

    # very lenient safety parse
    decision = {"decision": "hold", "confidence": 50, "raw": text}
    # best-effort JSON-ish parse
    try:
        import json, re
        # extract JSON block if wrapped
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            decision.update(json.loads(m.group(0)))
    except Exception:
        pass
    return decision
