# trading_bot/datetime_fix.py - Robust DateTime cleaning for AI & JSON

import json
from datetime import datetime
from typing import Any

# ---------- Core cleaners ----------

def _obj_to_serializable(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    # Pydantic v1/v2 models
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        return clean_for_ai(obj.model_dump())
    if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
        return clean_for_ai(obj.dict())
    if hasattr(obj, "__dict__") and not isinstance(obj, (str, int, float, bool, bytes)):
        return clean_for_ai(vars(obj))
    return obj

def clean_for_ai(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: clean_for_ai(v) for k, v in data.items()}
    if isinstance(data, (list, tuple, set)):
        t = type(data)
        return t(clean_for_ai(v) for v in data)
    return _obj_to_serializable(data)

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        ser = _obj_to_serializable(obj)
        if ser is not obj:
            return ser
        return super().default(obj)

# ---------- OpenAI monkey patches (broad) ----------

def _patch_openai():
    try:
        import openai
    except Exception as e:
        print(f"⚠️ OpenAI import failed; datetime patch not applied: {e}")
        return

    # Resolve SDK objects safely across versions
    chat = getattr(getattr(openai, "chat", openai), "completions", None)
    responses = getattr(openai, "responses", None)

    def _wrap(func):
        def _patched(*args, **kwargs):
            args = clean_for_ai(list(args))
            kwargs = clean_for_ai(dict(kwargs))
            return func(*args, **kwargs)
        return _patched

    try:
        if chat and hasattr(chat, "create"):
            chat.create = _wrap(chat.create)
    except Exception as e:
        print(f"⚠️ Could not patch openai.chat.completions.create: {e}")

    try:
        # Newer SDK path
        if responses and hasattr(responses, "create"):
            responses.create = _wrap(responses.create)
    except Exception as e:
        print(f"⚠️ Could not patch openai.responses.create: {e}")

# Auto-apply at import
try:
    _patch_openai()
    print("✅ Robust DateTime cleaning patch applied")
except Exception as e:
    print(f"⚠️ DateTime cleaning patch error: {e}")
